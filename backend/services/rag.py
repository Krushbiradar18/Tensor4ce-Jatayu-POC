"""
backend/services/rag.py — Embedding-Enhanced RAG for Compliance Grounding
=========================================================================
Primary retrieval:  cosine-similarity over pre-computed sentence-transformer
                    embeddings (all-MiniLM-L6-v2, loaded from sidecar JSON).
Fallback retrieval: keyword / term-overlap scoring (original behaviour),
                    activated automatically when the sidecar is absent or when
                    sentence-transformers is not installed.

Public API — UNCHANGED (same function signatures as before):
  load_compliance_kb(path)           → int
  search_compliance_docs(query, k)   → list[dict]
  search_by_regulation(code)         → Optional[dict]
  search_by_rule_flags(blocks, warns, k) → list[dict]

Sidecar format (data/compliance_kb_embeddings.json):
  [
    {
      "chunk_id":  <int>,        # positional index into compliance_kb.json
      "regulation": "<str>",
      "source":     "<str>",
      "embedding":  [<float>, ...]
    },
    ...
  ]

Generate / refresh the sidecar:
  python scripts/build_kb_embeddings.py
"""
from __future__ import annotations

import logging
import json
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

# Original KB — loaded once at startup (unchanged)
COMPLIANCE_KB: list[dict] = []

# Embedding sidecar — list parallel to COMPLIANCE_KB; None = not loaded
_EMBEDDINGS: Optional[list[dict]] = None

# Lazy-loaded sentence-transformer model
_ST_MODEL = None
_ST_MODEL_NAME = "all-MiniLM-L6-v2"

# ---------------------------------------------------------------------------
# Keyword-search helpers (original implementation — preserved verbatim)
# ---------------------------------------------------------------------------

_STOP_WORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall",
    "should", "may", "might", "can", "could", "must", "and", "or", "but",
    "if", "of", "at", "by", "for", "with", "about", "as", "to", "in",
    "on", "from", "up", "out", "not", "no", "so", "than", "too", "very",
    "that", "this", "these", "those", "it", "its", "all", "each", "every",
    "any", "such", "into", "over", "under", "between", "through", "during",
    "before", "after", "above", "below",
})

_WORD_RE = re.compile(r"[a-z0-9₹%]+", re.IGNORECASE)


def _tokenize(text: str) -> set[str]:
    """Tokenize text into lowercase terms, excluding stop words."""
    words = set(_WORD_RE.findall(text.lower()))
    return words - _STOP_WORDS


def _keyword_score(query_terms: set[str], chunk: dict) -> float:
    """Original keyword overlap scoring — used as fallback and tiebreak."""
    chunk_terms = _tokenize(
        chunk.get("text", "") + " " + chunk.get("source", "")
    )
    overlap = query_terms & chunk_terms
    score = float(len(overlap))

    # Regulation-code bonus (original logic)
    chunk_regulation = chunk.get("regulation", "")
    query_upper = " ".join(query_terms).upper()
    if chunk_regulation and chunk_regulation.replace("RBI_", "").replace("_", " ") in query_upper:
        score += 3.0
    for reg_part in chunk_regulation.split("_"):
        if len(reg_part) >= 3 and reg_part.upper() in query_upper:
            score += 1.0

    return score


# ---------------------------------------------------------------------------
# Embedding helpers (NEW)
# ---------------------------------------------------------------------------

def _get_st_model():
    """Lazily load the sentence-transformer model (cached after first call)."""
    global _ST_MODEL
    if _ST_MODEL is not None:
        return _ST_MODEL
    try:
        from sentence_transformers import SentenceTransformer
        _ST_MODEL = SentenceTransformer(_ST_MODEL_NAME)
        logger.info(f"Loaded sentence-transformer model '{_ST_MODEL_NAME}'")
        return _ST_MODEL
    except Exception as e:
        logger.warning(f"sentence-transformers unavailable — embedding retrieval disabled: {e}")
        return None


def _embed_query(query: str) -> Optional[list[float]]:
    """
    Encode a query string into an L2-normalised embedding vector.
    Returns None if sentence-transformers is not available.
    """
    model = _get_st_model()
    if model is None:
        return None
    try:
        vec = model.encode(
            query,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return vec.tolist()
    except Exception as e:
        logger.warning(f"Query encoding failed: {e}")
        return None


def _cosine_sim(a: list[float], b: list[float]) -> float:
    """
    Dot product of two pre-normalised (unit) vectors == cosine similarity.
    Both vectors must be L2-normalised (build script guarantees this for KB
    embeddings; _embed_query normalises the query vector).
    """
    return sum(x * y for x, y in zip(a, b))


def _load_embeddings(sidecar_path: str) -> bool:
    """
    Load the embedding sidecar JSON and validate chunk_id integrity.
    Populates module-level _EMBEDDINGS list.

    Integrity contract: sidecar[i]["chunk_id"] == i  AND
                        len(sidecar) == len(COMPLIANCE_KB)

    Returns True on success, False on any failure (graceful degradation).
    """
    global _EMBEDDINGS

    if not os.path.exists(sidecar_path):
        logger.info(
            f"Embedding sidecar not found at '{sidecar_path}' — "
            "using keyword-only retrieval. "
            "Run scripts/build_kb_embeddings.py to enable semantic search."
        )
        _EMBEDDINGS = None
        return False

    try:
        with open(sidecar_path, encoding="utf-8") as fh:
            data = json.load(fh)

        if not isinstance(data, list):
            raise ValueError("Sidecar must be a JSON array")

        # ---- Integrity check 1: count must match KB ----
        if len(data) != len(COMPLIANCE_KB):
            raise ValueError(
                f"Sidecar has {len(data)} entries but KB has {len(COMPLIANCE_KB)} chunks. "
                "Re-run scripts/build_kb_embeddings.py."
            )

        # ---- Integrity check 2: chunk_id == positional index ----
        for i, entry in enumerate(data):
            if not isinstance(entry, dict):
                raise ValueError(f"Sidecar entry {i} is not a dict")
            if "chunk_id" not in entry or "embedding" not in entry:
                raise ValueError(f"Sidecar entry {i} missing 'chunk_id' or 'embedding'")
            if entry["chunk_id"] != i:
                raise ValueError(
                    f"chunk_id integrity violation at position {i}: "
                    f"expected {i}, got {entry['chunk_id']}"
                )
            if not isinstance(entry["embedding"], list) or len(entry["embedding"]) == 0:
                raise ValueError(f"Sidecar entry {i} has invalid embedding")

        _EMBEDDINGS = data
        dim = len(data[0]["embedding"]) if data else 0
        logger.info(
            f"Loaded {len(_EMBEDDINGS)} embeddings from '{sidecar_path}' "
            f"(dim={dim}, model={_ST_MODEL_NAME}) — semantic search ENABLED"
        )
        return True

    except (json.JSONDecodeError, ValueError, IOError, KeyError) as e:
        logger.error(
            f"Failed to load embedding sidecar '{sidecar_path}': {e} — "
            "falling back to keyword retrieval"
        )
        _EMBEDDINGS = None
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_compliance_kb(path: str = "data/compliance_kb.json") -> int:
    """
    Load pre-chunked RBI circulars and policy docs from a JSON file.
    Also attempts to load the embedding sidecar (same dir, *_embeddings.json).
    Returns the number of chunks loaded.

    Each chunk should have:
      - source: str — e.g., "RBI/2023-24/12 - Income Recognition Norms"
      - text: str — the regulatory text content
      - regulation: str — a short code like "RBI_FOIR_LIMITS"
    """
    global COMPLIANCE_KB
    if not os.path.exists(path):
        logger.warning(f"Compliance KB not found at {path} — RAG grounding disabled")
        COMPLIANCE_KB = []
        return 0

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            logger.error(f"Compliance KB at {path} is not a JSON array")
            COMPLIANCE_KB = []
            return 0
        COMPLIANCE_KB = data
        logger.info(f"Loaded {len(COMPLIANCE_KB)} compliance KB chunks from {path}")
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Failed to load compliance KB from {path}: {e}")
        COMPLIANCE_KB = []
        return 0

    # ---- Load embedding sidecar (non-fatal if absent) ----
    sidecar_path = os.path.splitext(path)[0] + "_embeddings.json"
    _load_embeddings(sidecar_path)

    return len(COMPLIANCE_KB)


def search_compliance_docs(query: str, k: int = 3) -> list[dict]:
    """
    Search the compliance knowledge base for chunks relevant to *query*.

    Primary path  (when embeddings loaded):
        Cosine similarity between query vector and pre-computed chunk vectors.
        Keyword overlap used as tiebreak for equal cosine scores.

    Fallback path (no embeddings / sentence-transformers unavailable):
        Original keyword term-overlap scoring (behaviour unchanged).

    Args:
        query: natural language query (e.g., "FOIR ratio exceeds limit")
        k: number of top results to return

    Returns:
        List of up to k matching chunks, each with: source, text, regulation
    """
    if not COMPLIANCE_KB:
        logger.debug("Compliance KB is empty — no RAG results")
        return []

    if not query or not query.strip():
        return []

    # ------------------------------------------------------------------ #
    # PATH A — Embedding-based cosine similarity (primary)               #
    # ------------------------------------------------------------------ #
    if _EMBEDDINGS is not None:
        query_vec = _embed_query(query)
        if query_vec is not None:
            query_terms = _tokenize(query)   # for tiebreak only
            scored: list[tuple[float, float, int, dict]] = []

            for entry in _EMBEDDINGS:
                idx = entry["chunk_id"]
                if idx >= len(COMPLIANCE_KB):
                    continue                   # guard against stale sidecar
                chunk = COMPLIANCE_KB[idx]
                cos_sim = _cosine_sim(query_vec, entry["embedding"])
                kw_bonus = _keyword_score(query_terms, chunk) * 0.01  # small tiebreak
                scored.append((cos_sim + kw_bonus, kw_bonus, idx, chunk))

            # Sort: highest cosine sim first; keyword bonus as tiebreak
            scored.sort(key=lambda x: (-x[0], -x[1], x[2]))
            logger.debug(
                f"Embedding search: top score={scored[0][0]:.4f} "
                f"for query='{query[:60]}'"
            )
            return [item[3] for item in scored[:k]]

    # ------------------------------------------------------------------ #
    # PATH B — Keyword fallback (original behaviour, preserved verbatim) #
    # ------------------------------------------------------------------ #
    logger.debug("Embedding path unavailable — using keyword search")
    query_terms = _tokenize(query)
    if not query_terms:
        return []

    scored_kw: list[tuple[float, int, dict]] = []
    for idx, chunk in enumerate(COMPLIANCE_KB):
        score = _keyword_score(query_terms, chunk)
        if score > 0:
            scored_kw.append((score, idx, chunk))

    scored_kw.sort(key=lambda x: (-x[0], x[1]))
    return [item[2] for item in scored_kw[:k]]


def search_by_regulation(regulation_code: str) -> Optional[dict]:
    """
    Direct lookup by regulation code (e.g., "RBI_FOIR_LIMITS").
    Returns the first matching chunk or None.
    (Unchanged from original)
    """
    if not COMPLIANCE_KB:
        return None
    for chunk in COMPLIANCE_KB:
        if chunk.get("regulation", "").upper() == regulation_code.upper():
            return chunk
    return None


def search_by_rule_flags(block_flags: list[dict], warn_flags: list[dict], k: int = 5) -> list[dict]:
    """
    Search the KB using the regulation fields from triggered compliance flags.
    This is the primary interface used by the compliance agent's RAG lookup node.

    Args:
        block_flags: list of block-severity compliance flags
        warn_flags: list of warn-severity compliance flags
        k: max results to return

    Returns:
        Deduplicated list of regulatory text chunks relevant to the triggered rules
    """
    all_flags = (block_flags or []) + (warn_flags or [])
    if not all_flags:
        # No flags triggered — return general lending guidelines
        return search_compliance_docs("RBI lending guidelines general compliance", k=min(k, 2))

    seen_regulations: set[str] = set()
    results: list[dict] = []

    for flag in all_flags:
        regulation = flag.get("regulation", "")
        description = flag.get("description", "")
        rule_id = flag.get("rule_id", "")

        # Build a search query from the flag's metadata
        query_parts = []
        if regulation:
            query_parts.append(regulation)
        if description:
            query_parts.append(description)
        if rule_id:
            query_parts.append(rule_id)

        query = " ".join(query_parts)
        if not query.strip():
            continue

        # Search for relevant chunks
        matches = search_compliance_docs(query, k=2)
        for match in matches:
            reg_key = match.get("regulation", "")
            if reg_key and reg_key not in seen_regulations:
                seen_regulations.add(reg_key)
                results.append(match)

        if len(results) >= k:
            break

    return results[:k]
