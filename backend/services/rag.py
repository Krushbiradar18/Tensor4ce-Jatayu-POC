"""
backend/services/rag.py — Embedding-Enhanced RAG for Compliance Grounding
=========================================================================
Retrieval priority (highest → lowest):

  1. pgvector  (USE_PGVECTOR=true in .env)
     Pure SQL cosine-similarity query against compliance_kb_embeddings table.
     No sentence-transformers needed at query time — embeddings are already
     stored; only the query vector is computed on-the-fly.

  2. JSON sidecar  (fallback when pgvector is disabled / unavailable)
     Cosine-similarity over pre-computed embeddings from
     data/compliance_kb_embeddings.json  (original behaviour).

  3. Keyword overlap  (last resort)
     Original term-overlap scoring — activated when both embedding paths
     are absent or sentence-transformers is not installed.

Public API — UNCHANGED (same function signatures as before):
  load_compliance_kb(path)              → int
  search_compliance_docs(query, k)      → list[dict]
  search_by_regulation(code)            → Optional[dict]
  search_by_rule_flags(blocks, warns, k) → list[dict]

Environment variables
---------------------
  USE_PGVECTOR=true           Enable pgvector path (default: false)
  DATABASE_URL                PostgreSQL connection URL (same as db.py)
  PG_USER / PG_PASSWORD / PG_HOST / PG_PORT / PG_DB  — used if DATABASE_URL unset

Sidecar format (data/compliance_kb_embeddings.json) — unchanged:
  [
    {
      "chunk_id":  <int>,
      "regulation": "<str>",
      "source":     "<str>",
      "embedding":  [<float>, ...]
    },
    ...
  ]

Generate / refresh the sidecar AND the DB table:
  python scripts/build_kb_embeddings.py           # regenerate JSON
  python scripts/migrate_embeddings_to_pgvector.py  # push JSON → pgvector
"""
from __future__ import annotations

import logging
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Console RAG Logger — coloured, human-readable output to stdout
# ---------------------------------------------------------------------------

# ANSI colour codes (auto-disabled when stdout is not a TTY)
_USE_COLOUR = sys.stdout.isatty()
_C = {
    "reset":  "\033[0m"  if _USE_COLOUR else "",
    "bold":   "\033[1m"  if _USE_COLOUR else "",
    "cyan":   "\033[96m" if _USE_COLOUR else "",
    "green":  "\033[92m" if _USE_COLOUR else "",
    "yellow": "\033[93m" if _USE_COLOUR else "",
    "blue":   "\033[94m" if _USE_COLOUR else "",
    "magenta":"\033[95m" if _USE_COLOUR else "",
    "dim":    "\033[2m"  if _USE_COLOUR else "",
}


def _rag_print(msg: str) -> None:
    """Print directly to stdout — bypasses the logging level hierarchy."""
    print(msg, flush=True)


def _print_query_banner(query: str, backend: str) -> None:
    """Print a styled banner when a RAG search begins."""
    width = 72
    _rag_print("")
    _rag_print(_C["cyan"] + _C["bold"] + "┌" + "─" * (width - 2) + "┐" + _C["reset"])
    _rag_print(_C["cyan"] + _C["bold"] + "│" + " RAG QUERY ".center(width - 2) + "│" + _C["reset"])
    _rag_print(_C["cyan"] + _C["bold"] + "├" + "─" * (width - 2) + "┤" + _C["reset"])
    # Wrap long queries
    words = query.split()
    line, lines = "", []
    for w in words:
        if len(line) + len(w) + 1 > width - 6:
            lines.append(line)
            line = w
        else:
            line = (line + " " + w).strip()
    if line:
        lines.append(line)
    for l in lines:
        _rag_print(_C["cyan"] + "│" + _C["reset"] + "  " + _C["bold"] + l + _C["reset"] + " " * (width - 4 - len(l)) + _C["cyan"] + "│" + _C["reset"])
    _rag_print(_C["cyan"] + "├" + "─" * (width - 2) + "┤" + _C["reset"])
    backend_line = f"  Backend: {backend}"
    _rag_print(_C["cyan"] + "│" + _C["reset"] + _C["dim"] + backend_line + " " * (width - 2 - len(backend_line)) + _C["reset"] + _C["cyan"] + "│" + _C["reset"])
    _rag_print(_C["cyan"] + _C["bold"] + "└" + "─" * (width - 2) + "┘" + _C["reset"])


def _print_chunk_table(results: list[dict], backend: str) -> None:
    """Print retrieved chunks as a formatted table to stdout."""
    width = 72
    _rag_print("")
    _rag_print(_C["green"] + _C["bold"] + f"  ╔══ Retrieved {len(results)} chunk(s) via [{backend}] " + "═" * max(0, width - 42 - len(backend)) + "╗" + _C["reset"])
    for i, chunk in enumerate(results, 1):
        chunk_id   = chunk.get("_chunk_id", "?")
        regulation = chunk.get("regulation", "—")
        similarity = chunk.get("_cosine_similarity", None)
        text_raw   = chunk.get("text", "")
        source     = chunk.get("source", "—")
        # Truncate content preview to 120 chars
        preview = text_raw[:120].replace("\n", " ").strip()
        if len(text_raw) > 120:
            preview += "…"
        sim_str = f"{similarity:.4f}" if similarity is not None else "N/A "
        _rag_print(_C["green"] + f"  ║" + _C["reset"])
        _rag_print(_C["green"] + f"  ║" + _C["reset"] +
                   _C["bold"] + f"  [{i}] chunk_id={chunk_id}" + _C["reset"] +
                   _C["yellow"] + f"  cosine={sim_str}" + _C["reset"] +
                   _C["magenta"] + f"  {regulation}" + _C["reset"])
        _rag_print(_C["green"] + f"  ║" + _C["reset"] +
                   _C["dim"] + f"      source : {source[:65]}" + _C["reset"])
        _rag_print(_C["green"] + f"  ║" + _C["reset"] +
                   f"      content: " + _C["blue"] + preview + _C["reset"])
    _rag_print(_C["green"] + _C["bold"] + "  ╚" + "═" * (width - 4) + "╝" + _C["reset"])
    _rag_print("")


def log_llm_response(query: str, response: str, model: str = "") -> None:
    """
    PUBLIC helper — call this after your LLM generates a response.
    Prints the LLM output to stdout with a styled box.

    Usage:
        from services.rag import log_llm_response
        answer = llm.generate(prompt)
        log_llm_response(query=user_query, response=answer, model="gemini-1.5-pro")
    """
    width = 72
    model_tag = f" [{model}]" if model else ""
    _rag_print("")
    _rag_print(_C["magenta"] + _C["bold"] + "┌" + "─" * (width - 2) + "┐" + _C["reset"])
    _rag_print(_C["magenta"] + _C["bold"] + "│" + f" LLM RESPONSE{model_tag} ".center(width - 2) + "│" + _C["reset"])
    _rag_print(_C["magenta"] + _C["bold"] + "├" + "─" * (width - 2) + "┤" + _C["reset"])
    # Wrap response text
    for para in response.strip().split("\n"):
        if not para.strip():
            _rag_print(_C["magenta"] + "│" + _C["reset"] + " " * (width - 2) + _C["magenta"] + "│" + _C["reset"])
            continue
        words = para.split()
        line = ""
        for w in words:
            if len(line) + len(w) + 1 > width - 6:
                padded = line + " " * (width - 4 - len(line))
                _rag_print(_C["magenta"] + "│" + _C["reset"] + "  " + padded + _C["magenta"] + "│" + _C["reset"])
                line = w
            else:
                line = (line + " " + w).strip()
        if line:
            padded = line + " " * (width - 4 - len(line))
            _rag_print(_C["magenta"] + "│" + _C["reset"] + "  " + padded + _C["magenta"] + "│" + _C["reset"])
    _rag_print(_C["magenta"] + _C["bold"] + "└" + "─" * (width - 2) + "┘" + _C["reset"])
    _rag_print("")

# ---------------------------------------------------------------------------
# Minimal .env parser — no python-dotenv required
# ---------------------------------------------------------------------------
def _load_env_file(env_path: Path) -> None:
    """Parse KEY=VALUE lines from a .env file into os.environ (if not already set)."""
    if not env_path.exists():
        return
    with open(env_path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key   = key.strip()
            value = value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value

# ---------------------------------------------------------------------------
# Load .env so USE_PGVECTOR and DB vars are available even when this module
# is imported before FastAPI startup runs load_dotenv.
# ---------------------------------------------------------------------------
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_load_env_file(_BACKEND_DIR / ".env")

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

# Original KB — loaded once at startup (unchanged)
COMPLIANCE_KB: list[dict] = []

# Embedding sidecar — list parallel to COMPLIANCE_KB; None = not loaded
_EMBEDDINGS: Optional[list[dict]] = None

# pgvector connection (lazy)
_PG_CONN = None
_PGVECTOR_ENABLED: bool = os.environ.get("USE_PGVECTOR", "false").lower() == "true"

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
# Embedding helpers (JSON sidecar path — unchanged)
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
            f"(dim={dim}, model={_ST_MODEL_NAME}) — semantic search ENABLED (JSON mode)"
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
# pgvector backend (NEW)
# ---------------------------------------------------------------------------

def _get_pg_conn():
    """
    Return a live psycopg2 connection to PostgreSQL.
    Connection is cached module-level; re-created if closed.
    Returns None if pgvector is disabled or connection fails.
    """
    global _PG_CONN
    if not _PGVECTOR_ENABLED:
        return None

    # Re-use existing live connection
    if _PG_CONN is not None:
        try:
            _PG_CONN.cursor().execute("SELECT 1")
            return _PG_CONN
        except Exception:
            _PG_CONN = None  # stale — reconnect below

    try:
        import psycopg2
        # Use manual .env parser (no python-dotenv dependency needed)
        _load_env_file(_BACKEND_DIR / ".env")

        user = os.environ.get("PG_USER", "postgres")
        pwd  = os.environ.get("PG_PASSWORD", "123456")
        host = os.environ.get("PG_HOST", "localhost")
        port = os.environ.get("PG_PORT", "5432")
        db   = os.environ.get("PG_DB", "jatayu")
        url  = os.environ.get(
            "DATABASE_URL",
            f"postgresql://{user}:{pwd}@{host}:{port}/{db}",
        ).replace("postgresql+psycopg2://", "postgresql://")

        _PG_CONN = psycopg2.connect(url)
        _PG_CONN.autocommit = True
        logger.info("pgvector connection established — semantic search using PostgreSQL")
        return _PG_CONN
    except Exception as exc:
        logger.warning(f"pgvector connection failed: {exc} — falling back to JSON/keyword search")
        _PG_CONN = None
        return None


def _pgvector_search(query_vec: list[float], k: int) -> list[dict]:
    """
    Query the compliance_kb_embeddings table using pgvector cosine distance.
    Returns up to k chunk dicts (matching COMPLIANCE_KB schema: source, text, regulation).

    SQL uses the <=> operator (cosine distance) for ranking; ORDER BY ASC == most similar first.
    """
    conn = _get_pg_conn()
    if conn is None:
        return []

    try:
        from psycopg2.extras import RealDictCursor
        vec_str = "[" + ",".join(str(v) for v in query_vec) + "]"
        sql = """
            SELECT chunk_id, regulation, source,
                   1 - (embedding <=> %s::vector) AS cosine_similarity
            FROM compliance_kb_embeddings
            ORDER BY embedding <=> %s::vector
            LIMIT %s;
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, (vec_str, vec_str, k))
            rows = cur.fetchall()

        results: list[dict] = []
        for row in rows:
            idx = row["chunk_id"]
            if 0 <= idx < len(COMPLIANCE_KB):
                chunk = COMPLIANCE_KB[idx].copy()
                chunk["_chunk_id"]         = idx
                chunk["_cosine_similarity"] = float(row["cosine_similarity"])
                results.append(chunk)
            else:
                logger.debug(f"pgvector chunk_id {idx} out of range for KB size {len(COMPLIANCE_KB)}")

        return results

    except Exception as exc:
        logger.warning(f"pgvector query failed: {exc} — falling back to JSON/keyword search")
        return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_compliance_kb(path: str = "data/compliance_kb.json") -> int:
    """
    Load pre-chunked RBI circulars and policy docs from a JSON file.
    Also attempts to initialise the embedding backend (pgvector or JSON sidecar).
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

    # ---- Initialise embedding backend ------------------------------------
    if _PGVECTOR_ENABLED:
        conn = _get_pg_conn()
        if conn is not None:
            logger.info("USE_PGVECTOR=true — pgvector backend active for semantic search")
        else:
            logger.warning(
                "USE_PGVECTOR=true but connection failed — "
                "falling back to JSON sidecar / keyword search"
            )
            # Try JSON sidecar as fallback
            sidecar_path = os.path.splitext(path)[0] + "_embeddings.json"
            _load_embeddings(sidecar_path)
    else:
        # ---- Load embedding sidecar (non-fatal if absent) ----------------
        sidecar_path = os.path.splitext(path)[0] + "_embeddings.json"
        _load_embeddings(sidecar_path)

    return len(COMPLIANCE_KB)


def search_compliance_docs(query: str, k: int = 3) -> list[dict]:
    """
    Search the compliance knowledge base for chunks relevant to *query*.

    Primary path A — pgvector  (USE_PGVECTOR=true):
        SQL cosine-similarity via pgvector <=> operator.  Zero Python math.

    Primary path B — JSON sidecar  (USE_PGVECTOR=false, sidecar loaded):
        Cosine similarity between query vector and pre-computed chunk vectors.
        Keyword overlap used as tiebreak for equal cosine scores.

    Fallback path — keyword search:
        Original term-overlap scoring (behaviour unchanged).

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
    # PATH A — pgvector cosine similarity (primary when enabled)         #
    # ------------------------------------------------------------------ #
    if _PGVECTOR_ENABLED:
        _print_query_banner(query, backend="pgvector (PostgreSQL)")
        query_vec = _embed_query(query)
        if query_vec is not None:
            results = _pgvector_search(query_vec, k)
            if results:
                _print_chunk_table(results, backend="pgvector")
                return results
            # Empty results from pgvector → fall through to JSON/keyword

    # ------------------------------------------------------------------ #
    # PATH B — JSON sidecar cosine similarity                            #
    # ------------------------------------------------------------------ #
    if _EMBEDDINGS is not None:
        _print_query_banner(query, backend="JSON sidecar (in-memory cosine)")
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
            top_results = []
            for cos_total, _, idx, chunk in scored[:k]:
                c = chunk.copy()
                c["_chunk_id"]         = idx
                c["_cosine_similarity"] = cos_total
                top_results.append(c)
            _print_chunk_table(top_results, backend="JSON sidecar")
            return [item[3] for item in scored[:k]]

    # ------------------------------------------------------------------ #
    # PATH C — Keyword fallback (original behaviour, preserved verbatim) #
    # ------------------------------------------------------------------ #
    _print_query_banner(query, backend="keyword overlap (fallback)")
    query_terms = _tokenize(query)
    if not query_terms:
        return []

    scored_kw: list[tuple[float, int, dict]] = []
    for idx, chunk in enumerate(COMPLIANCE_KB):
        score = _keyword_score(query_terms, chunk)
        if score > 0:
            scored_kw.append((score, idx, chunk))

    scored_kw.sort(key=lambda x: (-x[0], x[1]))
    kw_results = []
    for score, idx, chunk in scored_kw[:k]:
        c = chunk.copy()
        c["_chunk_id"]         = idx
        c["_cosine_similarity"] = None   # keyword mode has no cosine score
        kw_results.append(c)
    _print_chunk_table(kw_results, backend="keyword")
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
