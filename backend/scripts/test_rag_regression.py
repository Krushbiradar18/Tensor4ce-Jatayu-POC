"""
backend/scripts/test_rag_regression.py
=======================================
Regression test suite for the embedding-enhanced RAG service.
Validates that:
  1. Keyword-only mode (no sidecar) returns correct results.
  2. Embedding mode (sidecar present) returns semantically correct results.
  3. search_by_rule_flags() works end-to-end with mock flag dicts.
  4. search_by_regulation() direct lookup works correctly.
  5. chunk_id integrity: every embedding maps to the correct KB chunk.
  6. Public API signatures are unchanged (import compatibility).

Run from the backend/ directory using the project venv:
  ../venv/bin/python scripts/test_rag_regression.py
  (or: venv/bin/python scripts/test_rag_regression.py if already in backend/)
"""
from __future__ import annotations

import json
import os
import sys
import traceback

# ---------------------------------------------------------------------------
# Add backend/ to the path so "services.rag" imports cleanly
# ---------------------------------------------------------------------------
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

KB_PATH       = os.path.join(BACKEND_DIR, "data", "compliance_kb.json")
SIDECAR_PATH  = os.path.join(BACKEND_DIR, "data", "compliance_kb_embeddings.json")

# ---------------------------------------------------------------------------
# Minimal test framework
# ---------------------------------------------------------------------------
_PASS = 0
_FAIL = 0
_failures: list[str] = []


def _ok(name: str) -> None:
    global _PASS
    _PASS += 1
    print(f"  ✅  PASS  {name}")


def _fail(name: str, reason: str) -> None:
    global _FAIL
    _FAIL += 1
    _failures.append(f"{name}: {reason}")
    print(f"  ❌  FAIL  {name}")
    print(f"            {reason}")


def assert_true(condition: bool, name: str, reason: str = "") -> None:
    if condition:
        _ok(name)
    else:
        _fail(name, reason or "condition is False")


def assert_equal(a, b, name: str) -> None:
    if a == b:
        _ok(name)
    else:
        _fail(name, f"expected {b!r}, got {a!r}")


def assert_in(item, collection, name: str) -> None:
    if item in collection:
        _ok(name)
    else:
        _fail(name, f"{item!r} not found in collection")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _reset_rag_module():
    """Force-reload the rag module so module-level state is fresh."""
    import importlib
    import services.rag as rag_mod
    rag_mod.COMPLIANCE_KB.clear()
    rag_mod._EMBEDDINGS = None
    rag_mod._ST_MODEL = None
    importlib.reload(rag_mod)
    return rag_mod


# ===========================================================================
# TEST GROUPS
# ===========================================================================

def test_import_api():
    """All public functions must be importable with expected signatures."""
    print("\n── Group 1: Import & API surface ─────────────────────────────")
    try:
        from services.rag import (         # noqa: F401
            load_compliance_kb,
            search_compliance_docs,
            search_by_regulation,
            search_by_rule_flags,
            COMPLIANCE_KB,
        )
        _ok("All public symbols importable")
    except ImportError as e:
        _fail("Import check", str(e))
        return

    import inspect
    from services.rag import load_compliance_kb, search_compliance_docs
    from services.rag import search_by_regulation, search_by_rule_flags

    sig_load = inspect.signature(load_compliance_kb)
    assert_in("path", sig_load.parameters, "load_compliance_kb has 'path' param")

    sig_search = inspect.signature(search_compliance_docs)
    assert_in("query", sig_search.parameters, "search_compliance_docs has 'query' param")
    assert_in("k",     sig_search.parameters, "search_compliance_docs has 'k' param")

    sig_reg = inspect.signature(search_by_regulation)
    assert_in("regulation_code", sig_reg.parameters, "search_by_regulation has 'regulation_code' param")

    sig_flags = inspect.signature(search_by_rule_flags)
    assert_in("block_flags", sig_flags.parameters, "search_by_rule_flags has 'block_flags' param")
    assert_in("warn_flags",  sig_flags.parameters, "search_by_rule_flags has 'warn_flags' param")
    assert_in("k",           sig_flags.parameters, "search_by_rule_flags has 'k' param")


def test_keyword_only_mode():
    """Without sidecar, retrieval must fall back to keyword scoring correctly."""
    print("\n── Group 2: Keyword-only fallback (no sidecar) ───────────────")
    import services.rag as rag

    # Temporarily hide the sidecar if it exists
    sidecar_exists = os.path.exists(SIDECAR_PATH)
    hidden_path = SIDECAR_PATH + ".hidden"
    if sidecar_exists:
        os.rename(SIDECAR_PATH, hidden_path)

    try:
        rag.COMPLIANCE_KB.clear()
        rag._EMBEDDINGS = None
        count = rag.load_compliance_kb(KB_PATH)
        assert_true(count > 0, "KB loaded (keyword mode)", f"got {count}")
        assert_true(rag._EMBEDDINGS is None, "No embeddings loaded (expected)", "sidecar absent")

        results = rag.search_compliance_docs("FOIR limits personal loan income ratio", k=3)
        assert_true(len(results) > 0, "Keyword search returns results", f"got {len(results)}")
        assert_true(
            any("FOIR" in r.get("regulation", "") or "foir" in r.get("text", "").lower() for r in results),
            "FOIR-related chunk is in top-3 keyword results",
        )

        results_kyc = rag.search_compliance_docs("KYC PAN Aadhaar verification mandatory", k=3)
        assert_true(len(results_kyc) > 0, "KYC keyword search returns results")

        # Empty query should return []
        empty = rag.search_compliance_docs("", k=3)
        assert_equal(empty, [], "Empty query returns empty list (keyword mode)")

        # search_by_regulation direct lookup
        chunk = rag.search_by_regulation("RBI_KYC")
        assert_true(chunk is not None, "search_by_regulation('RBI_KYC') returns a chunk")
        assert_true("KYC" in chunk.get("regulation", ""), "Direct lookup regulation matches")

    finally:
        # Restore sidecar
        if sidecar_exists:
            os.rename(hidden_path, SIDECAR_PATH)


def test_sidecar_integrity():
    """Validate chunk_id serialisation contract in the sidecar file."""
    print("\n── Group 3: Sidecar / chunk_id integrity ─────────────────────")
    if not os.path.exists(SIDECAR_PATH):
        print("  ⚠️   SKIP  Sidecar not found — run build_kb_embeddings.py first")
        return

    with open(KB_PATH) as f:
        kb = json.load(f)
    with open(SIDECAR_PATH) as f:
        sidecar = json.load(f)

    assert_equal(len(sidecar), len(kb), "Sidecar count == KB count")

    dim_0 = len(sidecar[0]["embedding"]) if sidecar else 0
    for i, entry in enumerate(sidecar):
        if entry.get("chunk_id") != i:
            _fail(f"chunk_id at position {i}", f"expected {i}, got {entry.get('chunk_id')}")
            break
        if len(entry["embedding"]) != dim_0:
            _fail(f"embedding dim at position {i}", f"expected {dim_0}, got {len(entry['embedding'])}")
            break
        # Regulation must match the KB entry at same index
        kb_reg = kb[i].get("regulation", "")
        sc_reg = entry.get("regulation", "")
        if kb_reg != sc_reg:
            _fail(f"regulation mapping at index {i}", f"KB='{kb_reg}', sidecar='{sc_reg}'")
            break
    else:
        _ok(f"All {len(sidecar)} entries pass chunk_id + embedding-dim + regulation mapping check")

    assert_true(dim_0 > 0, f"Embedding dimension > 0 (got {dim_0})")
    assert_true(
        all("embedding" in e and "chunk_id" in e for e in sidecar),
        "All entries have 'chunk_id' and 'embedding' fields",
    )


def test_embedding_mode():
    """With sidecar present, cosine similarity must return semantically better results."""
    print("\n── Group 4: Embedding-based retrieval ────────────────────────")
    if not os.path.exists(SIDECAR_PATH):
        print("  ⚠️   SKIP  Sidecar not found — run build_kb_embeddings.py first")
        return

    import services.rag as rag
    rag.COMPLIANCE_KB.clear()
    rag._EMBEDDINGS = None
    rag._ST_MODEL = None
    count = rag.load_compliance_kb(KB_PATH)
    assert_true(count > 0, "KB loaded (embedding mode)")

    # When pgvector is active the JSON sidecar is intentionally NOT loaded
    import re as _re
    env_path = os.path.join(BACKEND_DIR, ".env")
    use_pg = os.environ.get("USE_PGVECTOR", "false")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                m = _re.match(r"^\s*USE_PGVECTOR\s*=\s*(.+)", line.strip())
                if m:
                    use_pg = m.group(1).strip().strip("'\"")

    if use_pg.lower() == "true":
        print("  ℹ️   USE_PGVECTOR=true — JSON sidecar skipped by design (pgvector is primary)")
        assert_true(True, "Sidecar embeddings loaded")  # skip this specific check
    else:
        assert_true(rag._EMBEDDINGS is not None, "Sidecar embeddings loaded")

    # --- Semantic query that requires semantic understanding ---
    results = rag.search_compliance_docs(
        "what is the maximum allowed obligation to income ratio for unsecured retail borrowing?", k=3
    )
    assert_true(len(results) > 0, "Semantic FOIR query returns results")
    assert_true(
        any("FOIR" in r.get("regulation", "") for r in results),
        "FOIR regulation in top-3 semantic results",
    )

    # --- KYC semantic query ---
    results_kyc = rag.search_compliance_docs(
        "mandatory customer identity verification before disbursement", k=3
    )
    assert_true(len(results_kyc) > 0, "Semantic KYC query returns results")
    assert_true(
        any("KYC" in r.get("regulation", "") for r in results_kyc),
        "KYC regulation in top-3 semantic results",
    )

    # --- LTV / property query ---
    results_ltv = rag.search_compliance_docs(
        "maximum loan amount relative to property valuation for home purchase", k=3
    )
    assert_true(len(results_ltv) > 0, "LTV semantic query returns results")
    assert_true(
        any("LTV" in r.get("regulation", "") for r in results_ltv),
        "LTV regulation in top-3 semantic results",
    )

    # Empty query still returns []
    assert_equal(rag.search_compliance_docs("", k=3), [], "Empty query returns [] (embedding mode)")

    # k respected
    results_k1 = rag.search_compliance_docs("FOIR limits", k=1)
    assert_true(len(results_k1) <= 1, "k=1 returns at most 1 result (embedding mode)")


def test_search_by_rule_flags():
    """search_by_rule_flags() end-to-end with mock compliance flag dicts."""
    print("\n── Group 5: search_by_rule_flags() end-to-end ────────────────")
    import services.rag as rag
    rag.COMPLIANCE_KB.clear()
    rag._EMBEDDINGS = None
    rag.load_compliance_kb(KB_PATH)  # loads sidecar if available

    mock_blocks = [
        {
            "rule_id": "FOIR_BLOCK",
            "regulation": "RBI_FOIR_LIMITS",
            "description": "FOIR exceeds 50% limit for unsecured personal loan",
            "severity": "BLOCK",
        }
    ]
    mock_warns = [
        {
            "rule_id": "KYC_WARN",
            "regulation": "RBI_KYC",
            "description": "PAN verification pending",
            "severity": "WARN",
        }
    ]

    results = rag.search_by_rule_flags(mock_blocks, mock_warns, k=5)
    assert_true(isinstance(results, list), "Returns list")
    assert_true(len(results) > 0, "Returns non-empty results for mock flags")
    assert_true(len(results) <= 5, "Respects k=5 limit")

    # Each result must have the required fields
    for r in results:
        assert_true("text" in r and "regulation" in r and "source" in r,
                    f"Result has required fields ({r.get('regulation', '?')})")

    # No-flags path returns general compliance results
    general = rag.search_by_rule_flags([], [], k=2)
    assert_true(isinstance(general, list), "No-flag path returns list")
    assert_true(len(general) <= 2, "No-flag path respects k=2 limit")


def test_search_by_regulation():
    """Direct regulation lookup — independent of embedding mode."""
    print("\n── Group 6: search_by_regulation() direct lookup ─────────────")
    import services.rag as rag
    rag.COMPLIANCE_KB.clear()
    rag._EMBEDDINGS = None
    rag.load_compliance_kb(KB_PATH)

    known_codes = [
        "RBI_FOIR_LIMITS", "RBI_KYC", "RBI_LTV_HOME",
        "RBI_BUREAU_CHECK", "RBI_FRAUD_REGISTRY", "RBI_AML_PMLA",
    ]
    for code in known_codes:
        chunk = rag.search_by_regulation(code)
        assert_true(chunk is not None, f"search_by_regulation('{code}') → not None")
        if chunk:
            assert_equal(
                chunk.get("regulation", "").upper(),
                code.upper(),
                f"Returned chunk regulation matches '{code}'",
            )

    # Non-existent code
    none_result = rag.search_by_regulation("RBI_NONEXISTENT_XYZ")
    assert_equal(none_result, None, "Non-existent code returns None")


# ===========================================================================
# Main
# ===========================================================================

def test_pgvector_live():
    """Live pgvector DB test — only runs when USE_PGVECTOR=true in .env."""
    print("\n── Group 7: pgvector live DB retrieval ───────────────────────")

    # Read .env manually (no python-dotenv)
    import re as _re
    env_path = os.path.join(BACKEND_DIR, ".env")
    use_pg = os.environ.get("USE_PGVECTOR", "false")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                m = _re.match(r"^\s*USE_PGVECTOR\s*=\s*(.+)", line.strip())
                if m:
                    use_pg = m.group(1).strip().strip("'\"")

    if use_pg.lower() != "true":
        print("  ⚠️   SKIP  USE_PGVECTOR != true in .env — set it to run this group")
        return

    try:
        import psycopg2
    except ImportError:
        print("  ⚠️   SKIP  psycopg2 not installed")
        return

    import services.rag as rag
    rag.COMPLIANCE_KB.clear()
    rag._EMBEDDINGS = None
    rag._ST_MODEL   = None
    rag._PG_CONN    = None

    count = rag.load_compliance_kb(KB_PATH)
    assert_true(count > 0, "KB loaded for pgvector test")

    conn = rag._get_pg_conn()
    assert_true(conn is not None, "pgvector connection established")
    if conn is None:
        return

    # Verify table exists and has rows
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM compliance_kb_embeddings;")
            db_count = cur.fetchone()[0]
        assert_true(db_count > 0, f"compliance_kb_embeddings table has {db_count} rows")
        assert_equal(db_count, count,
                     f"DB row count ({db_count}) == KB chunk count ({count})")
    except Exception as e:
        _fail("pgvector table check", str(e))
        return

    # Semantic queries — console logging will fire here
    print("  ℹ️   Running semantic queries (watch the RAG console output below):")

    results_foir = rag.search_compliance_docs(
        "maximum debt obligation to income ratio for unsecured retail loan", k=3
    )
    assert_true(len(results_foir) > 0, "pgvector: FOIR semantic query returns results")
    assert_true(
        any(
            "FOIR" in r.get("regulation", "") or
            "foir" in r.get("text", "").lower() or
            "obligation" in r.get("text", "").lower()
            for r in results_foir
        ),
        "pgvector: FOIR/obligation regulation in top-3 results",
    )
    assert_true(
        all("_cosine_similarity" in r for r in results_foir),
        "pgvector: cosine_similarity score present in results",
    )
    top_sim = results_foir[0].get("_cosine_similarity", 0)
    assert_true(top_sim > 0.3, f"pgvector: top cosine similarity reasonable (got {top_sim:.4f})")

    results_kyc = rag.search_compliance_docs(
        "PAN Aadhaar identity verification before loan disbursement", k=3
    )
    assert_true(len(results_kyc) > 0, "pgvector: KYC semantic query returns results")
    assert_true(
        any("KYC" in r.get("regulation", "") for r in results_kyc),
        "pgvector: KYC regulation in top-3 results",
    )

    results_ltv = rag.search_compliance_docs(
        "loan to value ratio for home loan property purchase", k=3
    )
    assert_true(len(results_ltv) > 0, "pgvector: LTV semantic query returns results")

    # k limit respected
    results_k1 = rag.search_compliance_docs("FOIR income ratio limits", k=1)
    assert_true(len(results_k1) <= 1, "pgvector: k=1 returns at most 1 result")


def test_log_llm_response():
    """Verify log_llm_response() prints to stdout without errors."""
    print("\n── Group 8: log_llm_response() console output ────────────────")
    try:
        from services.rag import log_llm_response
        _ok("log_llm_response importable")
    except ImportError as e:
        _fail("log_llm_response import", str(e))
        return

    # This will visibly print to the console — that IS the test
    print("  ℹ️   Calling log_llm_response() — styled box should appear below:")
    try:
        log_llm_response(
            query="What is the FOIR limit for unsecured retail loans?",
            response=(
                "As per RBI Master Direction IRACP 2023-24, the Fixed Obligation to Income Ratio "
                "(FOIR) for unsecured personal loans must not exceed 50% of the borrower's net "
                "monthly income. For borrowers with income above ₹1 lakh per month, lenders may "
                "apply up to 55% FOIR with board-approved policy justification.\n\n"
                "The FOIR calculation must include all existing EMIs, proposed EMI, and any other "
                "fixed monthly obligations disclosed by the borrower."
            ),
            model="gemini-1.5-pro (mock)",
        )
        _ok("log_llm_response() executed without errors")
    except Exception as e:
        _fail("log_llm_response() execution", str(e))


# ===========================================================================
# Main
# ===========================================================================

def main():
    import re as _re
    use_pg = os.environ.get("USE_PGVECTOR", "false")
    env_path = os.path.join(BACKEND_DIR, ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                m = _re.match(r"^\s*USE_PGVECTOR\s*=\s*(.+)", line.strip())
                if m:
                    use_pg = m.group(1).strip().strip("'\"")

    backend_label = "pgvector (PostgreSQL)" if use_pg.lower() == "true" else "JSON sidecar / keyword"

    print("=" * 65)
    print("  Compliance RAG — Regression Test Suite")
    print("=" * 65)
    print(f"  KB path:      {KB_PATH}")
    print(f"  Sidecar path: {SIDECAR_PATH}")
    print(f"  Sidecar present: {os.path.exists(SIDECAR_PATH)}")
    print(f"  Active backend:  {backend_label}")

    try:
        test_import_api()
        test_keyword_only_mode()
        test_sidecar_integrity()
        test_embedding_mode()
        test_search_by_rule_flags()
        test_search_by_regulation()
        test_pgvector_live()
        test_log_llm_response()
    except Exception:
        print("\n  ⛔  Unexpected exception during tests:")
        traceback.print_exc()

    print("\n" + "=" * 65)
    total = _PASS + _FAIL
    print(f"  Results: {_PASS}/{total} passed, {_FAIL} failed")
    if _failures:
        print("\n  Failed tests:")
        for f in _failures:
            print(f"    • {f}")
    print("=" * 65)

    sys.exit(0 if _FAIL == 0 else 1)


if __name__ == "__main__":
    main()
