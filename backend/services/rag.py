"""
backend/services/rag.py — Simple RAG for Compliance Grounding
==============================================================
Keyword-based retrieval over pre-chunked RBI circulars and policy docs.
No vector DB required — uses term-overlap scoring for demo.

Usage:
  from services.rag import load_compliance_kb, search_compliance_docs
  load_compliance_kb("data/compliance_kb.json")
  results = search_compliance_docs("FOIR limits personal loan")
"""
from __future__ import annotations
import os
import json
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Module-level knowledge base — loaded once at startup
COMPLIANCE_KB: list[dict] = []

# Common English stop words to exclude from keyword matching
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

# Regex for tokenizing text into words
_WORD_RE = re.compile(r"[a-z0-9₹%]+", re.IGNORECASE)


def _tokenize(text: str) -> set[str]:
    """Tokenize text into lowercase terms, excluding stop words."""
    words = set(_WORD_RE.findall(text.lower()))
    return words - _STOP_WORDS


def load_compliance_kb(path: str = "data/compliance_kb.json") -> int:
    """
    Load pre-chunked RBI circulars and policy docs from a JSON file.
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
        return len(COMPLIANCE_KB)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Failed to load compliance KB from {path}: {e}")
        COMPLIANCE_KB = []
        return 0


def search_compliance_docs(query: str, k: int = 3) -> list[dict]:
    """
    Simple keyword-based search over the compliance knowledge base.
    
    Scoring: number of overlapping non-stop-word terms between query and chunk text.
    Also gives a bonus for matching the regulation code directly.
    
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

    query_terms = _tokenize(query)
    if not query_terms:
        return []

    scored: list[tuple[float, int, dict]] = []

    for idx, chunk in enumerate(COMPLIANCE_KB):
        chunk_text = chunk.get("text", "")
        chunk_source = chunk.get("source", "")
        chunk_regulation = chunk.get("regulation", "")

        # Tokenize the chunk
        chunk_terms = _tokenize(chunk_text + " " + chunk_source)

        # Base score: term overlap count
        overlap = query_terms & chunk_terms
        score = len(overlap)

        # Bonus: if query contains the regulation code (e.g., "FOIR", "KYC", "LTV")
        query_upper = query.upper()
        if chunk_regulation and chunk_regulation.replace("RBI_", "").replace("_", " ") in query_upper:
            score += 3
        # Also check for regulation sub-terms in the query
        for reg_part in chunk_regulation.split("_"):
            if len(reg_part) >= 3 and reg_part.upper() in query_upper:
                score += 1

        if score > 0:
            scored.append((score, idx, chunk))

    # Sort by score descending, then by original order for ties
    scored.sort(key=lambda x: (-x[0], x[1]))

    return [item[2] for item in scored[:k]]


def search_by_regulation(regulation_code: str) -> Optional[dict]:
    """
    Direct lookup by regulation code (e.g., "RBI_FOIR_LIMITS").
    Returns the first matching chunk or None.
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
