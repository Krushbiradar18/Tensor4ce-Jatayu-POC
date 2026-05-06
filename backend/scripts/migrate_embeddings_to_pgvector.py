"""
backend/scripts/migrate_embeddings_to_pgvector.py
==================================================
ONE-SHOT migration: reads compliance_kb_embeddings.json and upserts
every embedding row into a PostgreSQL table backed by pgvector.

Prerequisites
-------------
  pip install psycopg2-binary pgvector

Run from the backend/ directory:
  python scripts/migrate_embeddings_to_pgvector.py
  python scripts/migrate_embeddings_to_pgvector.py --db postgresql://postgres:123456@localhost:5432/jatayu
  python scripts/migrate_embeddings_to_pgvector.py --embeddings data/compliance_kb_embeddings.json

Table created (idempotent):
  compliance_kb_embeddings (
      chunk_id   INTEGER  PRIMARY KEY,
      regulation TEXT     NOT NULL,
      source     TEXT     NOT NULL,
      embedding  vector(384)          -- all-MiniLM-L6-v2 dim
  )

Re-running this script is safe — it uses INSERT … ON CONFLICT DO UPDATE.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Allow running from backend/ or backend/scripts/
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults (mirror db.py)
# ---------------------------------------------------------------------------
DEFAULT_EMBEDDINGS = str(BACKEND_DIR / "data" / "compliance_kb_embeddings.json")

def _load_dotenv_manual(env_path: Path) -> None:
    """
    Minimal .env parser — no external packages required.
    Reads KEY=VALUE lines (strips quotes, skips comments / blanks).
    Only sets a variable when it is NOT already present in the environment
    (same semantics as python-dotenv's load_dotenv).
    """
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


def _default_db_url() -> str:
    """Build DB URL from .env / env vars (no python-dotenv required)."""
    _load_dotenv_manual(BACKEND_DIR / ".env")
    user = os.environ.get("PG_USER", "postgres")
    pwd  = os.environ.get("PG_PASSWORD", "123456")
    host = os.environ.get("PG_HOST", "localhost")
    port = os.environ.get("PG_PORT", "5432")
    db   = os.environ.get("PG_DB", "jatayu")
    return os.environ.get(
        "DATABASE_URL",
        f"postgresql://{user}:{pwd}@{host}:{port}/{db}",
    )


# ---------------------------------------------------------------------------
# Core migration
# ---------------------------------------------------------------------------

def migrate(db_url: str, embeddings_path: str) -> None:
    # ---- 1. Validate input file -------------------------------------------
    p = Path(embeddings_path)
    if not p.exists():
        log.error(f"Embeddings file not found: {embeddings_path}")
        sys.exit(1)

    log.info(f"Loading embeddings from {embeddings_path} …")
    with open(p, encoding="utf-8") as fh:
        data: list[dict] = json.load(fh)

    if not isinstance(data, list) or len(data) == 0:
        log.error("Embeddings file must be a non-empty JSON array")
        sys.exit(1)

    dim = len(data[0]["embedding"])
    log.info(f"  {len(data)} chunks found  |  vector dim = {dim}")

    # ---- 2. Connect --------------------------------------------------------
    try:
        import psycopg2
        from psycopg2.extras import execute_values
    except ImportError:
        log.error("psycopg2-binary not installed. Run: pip install psycopg2-binary")
        sys.exit(1)

    # Strip SQLAlchemy dialect prefix if present (psycopg2 wants plain URL)
    clean_url = db_url.replace("postgresql+psycopg2://", "postgresql://")

    log.info(f"Connecting to {clean_url} …")
    try:
        conn = psycopg2.connect(clean_url)
    except Exception as exc:
        log.error(f"Cannot connect to PostgreSQL: {exc}")
        sys.exit(1)

    conn.autocommit = False
    cur = conn.cursor()

    # ---- 3. Enable pgvector extension ------------------------------------
    log.info("Enabling pgvector extension (CREATE EXTENSION IF NOT EXISTS vector) …")
    try:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        conn.commit()
    except Exception as exc:
        conn.rollback()
        log.error(f"pgvector extension unavailable: {exc}")
        log.error("Install pgvector: https://github.com/pgvector/pgvector")
        sys.exit(1)

    # ---- 4. Create table (idempotent) ------------------------------------
    log.info(f"Creating table compliance_kb_embeddings (dim={dim}) if not exists …")
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS compliance_kb_embeddings (
            chunk_id   INTEGER  PRIMARY KEY,
            regulation TEXT     NOT NULL DEFAULT '',
            source     TEXT     NOT NULL DEFAULT '',
            embedding  vector({dim})
        );
    """)
    conn.commit()
    log.info("  Table ready.")

    # ---- 5. Upsert rows ---------------------------------------------------
    log.info(f"Upserting {len(data)} embedding rows …")
    rows = []
    for entry in data:
        chunk_id  = int(entry["chunk_id"])
        regulation = entry.get("regulation", "")
        source     = entry.get("source", "")
        emb_str    = "[" + ",".join(str(v) for v in entry["embedding"]) + "]"
        rows.append((chunk_id, regulation, source, emb_str))

    execute_values(
        cur,
        """
        INSERT INTO compliance_kb_embeddings (chunk_id, regulation, source, embedding)
        VALUES %s
        ON CONFLICT (chunk_id) DO UPDATE
            SET regulation = EXCLUDED.regulation,
                source     = EXCLUDED.source,
                embedding  = EXCLUDED.embedding
        """,
        rows,
        template="(%s, %s, %s, %s::vector)",
        page_size=100,
    )
    conn.commit()
    log.info("  Upsert complete.")

    # ---- 6. Create HNSW index for fast ANN search (idempotent) ----------
    log.info("Creating HNSW index on embedding column (idempotent) …")
    try:
        cur.execute("""
            CREATE INDEX IF NOT EXISTS compliance_kb_embeddings_hnsw_idx
            ON compliance_kb_embeddings
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64);
        """)
        conn.commit()
        log.info("  HNSW index ready.")
    except Exception as exc:
        conn.rollback()
        log.warning(f"  HNSW index creation skipped (pgvector < 0.5?): {exc}")
        log.warning("  Falling back to IVFFlat index …")
        try:
            cur.execute("""
                CREATE INDEX IF NOT EXISTS compliance_kb_embeddings_ivf_idx
                ON compliance_kb_embeddings
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 10);
            """)
            conn.commit()
            log.info("  IVFFlat index ready.")
        except Exception as exc2:
            conn.rollback()
            log.warning(f"  Index creation failed: {exc2} — continuing without index.")

    # ---- 7. Verify -------------------------------------------------------
    cur.execute("SELECT COUNT(*) FROM compliance_kb_embeddings;")
    count = cur.fetchone()[0]
    log.info(f"✓ Verified: {count} rows in compliance_kb_embeddings")

    if count != len(data):
        log.warning(
            f"Row count mismatch! Expected {len(data)}, found {count}. "
            "Check for errors above."
        )
    else:
        log.info("✓ Migration complete — all embeddings successfully stored in pgvector.")
        log.info("")
        log.info("Next step: set USE_PGVECTOR=true in your .env (or environment)")
        log.info("  and restart the backend server.")

    cur.close()
    conn.close()


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migrate compliance KB embeddings JSON → PostgreSQL pgvector"
    )
    parser.add_argument(
        "--db",
        default=None,
        help="PostgreSQL connection URL (default: read from .env / db.py env vars)",
    )
    parser.add_argument(
        "--embeddings",
        default=DEFAULT_EMBEDDINGS,
        help=f"Path to compliance_kb_embeddings.json (default: {DEFAULT_EMBEDDINGS})",
    )
    args = parser.parse_args()

    db_url = args.db or _default_db_url()
    migrate(db_url, args.embeddings)
