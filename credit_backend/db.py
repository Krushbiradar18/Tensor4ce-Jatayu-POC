"""
Database setup for PostgreSQL-backed credit profile storage.
"""

import os
from sqlalchemy.engine.url import make_url
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/jatayu",
)


def _ensure_postgres_database_exists(database_url: str) -> None:
    """Create the target PostgreSQL database if it does not exist yet."""
    url = make_url(database_url)
    if not str(url.drivername).startswith("postgresql"):
        return

    db_name = url.database
    if not db_name:
        return

    try:
        import psycopg2
        from psycopg2 import sql
    except Exception:
        return

    conn = psycopg2.connect(
        dbname="postgres",
        user=url.username,
        password=url.password,
        host=url.host,
        port=url.port or 5432,
    )
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
            exists = cur.fetchone()
            if not exists:
                cur.execute(sql.SQL("CREATE DATABASE {}") .format(sql.Identifier(db_name)))
    finally:
        conn.close()


_ensure_postgres_database_exists(DATABASE_URL)

# pool_pre_ping avoids stale connection issues on long-running API servers.
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()
