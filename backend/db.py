"""db.py — Shared PostgreSQL persistence layer for the backend and specialist agents."""
import json
import os
import logging

from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url


logger = logging.getLogger(__name__)


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/jatayu",
)


def _ensure_postgres_database_exists(database_url: str) -> None:
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
                cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
    finally:
        conn.close()


try:
    _ensure_postgres_database_exists(DATABASE_URL)
except Exception as exc:
    logger.warning(f"Could not ensure PostgreSQL database exists at startup: {exc}")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)


def init_db():
    statements = [
        """
        CREATE TABLE IF NOT EXISTS applications (
            application_id TEXT PRIMARY KEY,
            raw_payload TEXT NOT NULL,
            ip_metadata TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'PENDING',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS decisions (
            decision_id TEXT PRIMARY KEY,
            application_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            decided_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS officer_actions (
            id SERIAL PRIMARY KEY,
            application_id TEXT NOT NULL,
            officer_id TEXT NOT NULL,
            decision TEXT NOT NULL,
            reason TEXT NOT NULL,
            acted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id SERIAL PRIMARY KEY,
            application_id TEXT NOT NULL,
            agent_name TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS uploaded_documents (
            id SERIAL PRIMARY KEY,
            application_id TEXT NOT NULL,
            doc_type TEXT NOT NULL,
            filename TEXT NOT NULL,
            extracted_data TEXT NOT NULL DEFAULT '{}',
            uploaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
    ]
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))


def save_application(application_id: str, payload: dict, ip_meta: dict):
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO applications (application_id, raw_payload, ip_metadata, status)
                VALUES (:application_id, :raw_payload, :ip_metadata, :status)
                ON CONFLICT (application_id) DO UPDATE
                SET raw_payload = EXCLUDED.raw_payload,
                    ip_metadata = EXCLUDED.ip_metadata,
                    status = EXCLUDED.status
                """
            ),
            {
                "application_id": application_id,
                "raw_payload": json.dumps(payload),
                "ip_metadata": json.dumps(ip_meta),
                "status": "PENDING",
            },
        )


def update_status(application_id: str, status: str):
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE applications SET status = :status WHERE application_id = :application_id"),
            {"status": status, "application_id": application_id},
        )


def get_application(application_id: str) -> dict | None:
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT * FROM applications WHERE application_id = :application_id"),
            {"application_id": application_id},
        ).mappings().first()
    return dict(row) if row else None


def save_decision(decision_id: str, application_id: str, payload: dict):
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO decisions (decision_id, application_id, payload)
                VALUES (:decision_id, :application_id, :payload)
                ON CONFLICT (decision_id) DO UPDATE
                SET application_id = EXCLUDED.application_id,
                    payload = EXCLUDED.payload,
                    decided_at = CURRENT_TIMESTAMP
                """
            ),
            {
                "decision_id": decision_id,
                "application_id": application_id,
                "payload": json.dumps(payload),
            },
        )


def get_decision(application_id: str) -> dict | None:
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT payload
                FROM decisions
                WHERE application_id = :application_id
                ORDER BY decided_at DESC
                LIMIT 1
                """
            ),
            {"application_id": application_id},
        ).mappings().first()
    if not row:
        return None
    return json.loads(row["payload"])


def save_officer_action(application_id: str, officer_id: str, decision: str, reason: str):
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO officer_actions (application_id, officer_id, decision, reason)
                VALUES (:application_id, :officer_id, :decision, :reason)
                """
            ),
            {
                "application_id": application_id,
                "officer_id": officer_id,
                "decision": decision,
                "reason": reason,
            },
        )
        conn.execute(
            text("UPDATE applications SET status = :status WHERE application_id = :application_id"),
            {
                "status": f"OFFICER_{decision.upper()}",
                "application_id": application_id,
            },
        )


def get_officer_action(application_id: str) -> dict | None:
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT *
                FROM officer_actions
                WHERE application_id = :application_id
                ORDER BY id DESC
                LIMIT 1
                """
            ),
            {"application_id": application_id},
        ).mappings().first()
    return dict(row) if row else None


def log_event(application_id: str, agent_name: str, event_type: str, payload: dict):
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO audit_log (application_id, agent_name, event_type, payload)
                VALUES (:application_id, :agent_name, :event_type, :payload)
                """
            ),
            {
                "application_id": application_id,
                "agent_name": agent_name,
                "event_type": event_type,
                "payload": json.dumps(payload),
            },
        )


def get_audit_log(application_id: str) -> list[dict]:
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT *
                FROM audit_log
                WHERE application_id = :application_id
                ORDER BY id ASC
                """
            ),
            {"application_id": application_id},
        ).mappings().all()
    return [dict(row) for row in rows]


def list_applications(limit: int = 50) -> list[dict]:
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT application_id, status, created_at, raw_payload
                FROM applications
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).mappings().all()

    result = []
    for row in rows:
        item = dict(row)
        try:
            payload = json.loads(item["raw_payload"])
            item["applicant_name"] = payload.get("applicant_name", "—")
            item["loan_purpose"] = payload.get("loan_purpose", "—")
            item["loan_amount"] = payload.get("loan_amount_requested", 0)
        except Exception:
            item["applicant_name"] = "—"
            item["loan_purpose"] = "—"
            item["loan_amount"] = 0
        result.append(item)
    return result


def save_document(application_id: str, doc_type: str, filename: str, extracted_data: dict):
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO uploaded_documents (application_id, doc_type, filename, extracted_data)
                VALUES (:application_id, :doc_type, :filename, :extracted_data)
                """
            ),
            {
                "application_id": application_id,
                "doc_type": doc_type,
                "filename": filename,
                "extracted_data": json.dumps(extracted_data),
            },
        )


def get_documents(application_id: str) -> list[dict]:
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, doc_type, filename, extracted_data, uploaded_at
                FROM uploaded_documents
                WHERE application_id = :application_id
                ORDER BY uploaded_at DESC
                """
            ),
            {"application_id": application_id},
        ).mappings().all()
    result = []
    for row in rows:
        item = dict(row)
        try:
            item["extracted_data"] = json.loads(item["extracted_data"])
        except Exception:
            pass
        result.append(item)
    return result
