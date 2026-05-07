import json
import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(BACKEND_DIR / ".env")

PG_USER = os.environ.get("PG_USER", "postgres")
PG_PASS = os.environ.get("PG_PASSWORD", "123456")
PG_HOST = os.environ.get("PG_HOST", "localhost")
PG_PORT = os.environ.get("PG_PORT", "5432")
PG_DB   = os.environ.get("PG_DB", "jatayu")

DATABASE_URL = os.environ.get(
    "DATABASE_URL", 
    f"postgresql+psycopg2://{PG_USER}:{PG_PASS}@{PG_HOST}:{PG_PORT}/{PG_DB}"
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
        """DROP TABLE IF EXISTS users""",  # Drop the old malformed table
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(50) NOT NULL DEFAULT 'officer',
            full_name VARCHAR(255) DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS applications (
            application_id TEXT PRIMARY KEY,
            raw_payload TEXT NOT NULL,
            ip_metadata TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'PENDING',
            escalated_by_officer_id TEXT,
            escalated_to_senior_officer_id INTEGER,
            escalated_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS application_contexts (
            application_id TEXT PRIMARY KEY,
            context_json TEXT NOT NULL,
            saved_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
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
            actor_role TEXT DEFAULT 'officer',
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
    ]
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))
    
    # Add missing columns to existing applications table if they don't exist (separate transactions)
    alter_statements = [
        "ALTER TABLE applications ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE applications ADD COLUMN IF NOT EXISTS escalated_by_officer_id TEXT",
        "ALTER TABLE applications ADD COLUMN IF NOT EXISTS escalated_to_senior_officer_id INTEGER",
        "ALTER TABLE applications ADD COLUMN IF NOT EXISTS escalated_at TIMESTAMPTZ",
        "ALTER TABLE officer_actions ADD COLUMN IF NOT EXISTS actor_role TEXT DEFAULT 'officer'",
    ]
    
    for alt_stmt in alter_statements:
        try:
            with engine.begin() as conn:
                conn.execute(text(alt_stmt))
        except Exception:
            pass  # Column already exists
    
    # Now seed the default users
    with engine.begin() as conn:
        _ensure_default_users(conn)


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


def save_application_context(application_id: str, context: dict):
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO application_contexts (application_id, context_json)
                VALUES (:application_id, :context_json)
                ON CONFLICT (application_id) DO UPDATE
                SET context_json = EXCLUDED.context_json,
                    saved_at = CURRENT_TIMESTAMP
                """
            ),
            {
                "application_id": application_id,
                "context_json": json.dumps(context),
            },
        )


def get_application_context(application_id: str) -> dict | None:
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT context_json
                FROM application_contexts
                WHERE application_id = :application_id
                """
            ),
            {"application_id": application_id},
        ).mappings().first()
    if not row:
        return None
    return json.loads(row["context_json"])


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


def save_officer_action(application_id: str, officer_id: str, decision: str, reason: str, actor_role: str = "officer"):
    """
    Save officer/senior officer action and update application status.
    
    Args:
        application_id: Application ID
        officer_id: ID/username of the officer/senior officer
        decision: Decision (APPROVED, REJECTED, CONDITIONAL, ESCALATED)
        reason: Reason for the decision
        actor_role: Role of the actor ('officer' or 'senior_officer')
    """
    # Determine the status based on the role and decision
    if actor_role == "senior_officer":
        status = f"SENIOR_OFFICER_{decision.upper()}"
    else:
        status = f"OFFICER_{decision.upper()}"
    
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO officer_actions (application_id, officer_id, decision, reason, actor_role)
                VALUES (:application_id, :officer_id, :decision, :reason, :actor_role)
                """
            ),
            {
                "application_id": application_id,
                "officer_id": officer_id,
                "decision": decision,
                "reason": reason,
                "actor_role": actor_role,
            },
        )
        conn.execute(
            text("UPDATE applications SET status = :status WHERE application_id = :application_id"),
            {
                "status": status,
                "application_id": application_id,
            },
        )


def assign_application_to_senior_officer(application_id: str, officer_id: str, senior_officer_id: str, reason: str = ""):
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE applications
                SET status = 'OFFICER_ESCALATED',
                    escalated_by_officer_id = :officer_id,
                    escalated_to_senior_officer_id = :senior_officer_id,
                    escalated_at = CURRENT_TIMESTAMP
                WHERE application_id = :application_id
                """
            ),
            {
                "application_id": application_id,
                "officer_id": officer_id,
                "senior_officer_id": senior_officer_id,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO officer_actions (application_id, officer_id, decision, reason, actor_role)
                VALUES (:application_id, :officer_id, 'ESCALATED', :reason, :actor_role)
                """
            ),
            {
                "application_id": application_id,
                "officer_id": officer_id,
                "reason": reason or f"Escalated to senior officer {senior_officer_id}",
                "actor_role": "officer",
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


def get_user_by_username(username: str) -> dict | None:
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT *
                FROM users
                WHERE lower(username) = lower(:username)
                LIMIT 1
                """
            ),
            {"username": username},
        ).mappings().first()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict | None:
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT *
                FROM users
                WHERE id = :user_id
                LIMIT 1
                """
            ),
            {"user_id": user_id},
        ).mappings().first()
    return dict(row) if row else None


def list_users(role: str | None = None) -> list[dict]:
    query = "SELECT * FROM users"
    params: dict[str, object] = {}
    if role:
        query += " WHERE role = :role"
        params["role"] = role
    query += " ORDER BY created_at ASC, id ASC"
    with engine.begin() as conn:
        rows = conn.execute(text(query), params).mappings().all()
    return [dict(row) for row in rows]


def list_senior_officers() -> list[dict]:
    return list_users(role="senior_officer")


def create_user(username: str, password_hash: str, role: str, full_name: str = "") -> dict:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO users (username, password_hash, role, full_name)
                VALUES (:username, :password_hash, :role, :full_name)
                ON CONFLICT (username) DO UPDATE
                SET password_hash = EXCLUDED.password_hash,
                    role = EXCLUDED.role,
                    full_name = COALESCE(NULLIF(EXCLUDED.full_name, ''), users.full_name),
                    updated_at = CURRENT_TIMESTAMP
                """
            ),
            {
                "username": username,
                "password_hash": password_hash,
                "role": role,
                "full_name": full_name or username,
            },
        )
    user = get_user_by_username(username)
    return user or {}


def _ensure_default_users(conn) -> None:
    from password_utils import hash_password
    
    defaults = [
        {"username": "admin", "password": "admin123", "role": "admin", "full_name": "Admin Officer"},
        {"username": "officer1", "password": "password", "role": "officer", "full_name": "Loan Officer"},
        {"username": "so1", "password": "password", "role": "senior_officer", "full_name": "Senior Officer"},
    ]
    for user in defaults:
        try:
            conn.execute(
                text(
                    """
                    INSERT INTO users (username, password_hash, role, full_name)
                    VALUES (:username, :password_hash, :role, :full_name)
                    ON CONFLICT (username) DO NOTHING
                    """
                ),
                {
                    "username": user["username"],
                    "password_hash": hash_password(user["password"]),
                    "role": user["role"],
                    "full_name": user["full_name"],
                },
            )
        except Exception as e:
            print(f"Warning: Failed to create default user {user['username']}: {e}")
            pass


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



def list_applications_extended(limit: int = 50) -> list[dict]:
    """
    Fetched applications and their latest decisions in a single optimized query.
    Used by the Officer Dashboard to avoid N+1 query issues.
    """
    query = text("""
        WITH latest_decisions AS (
            SELECT application_id, payload,
                   ROW_NUMBER() OVER (PARTITION BY application_id ORDER BY decided_at DESC) as rn
            FROM decisions
        )
        SELECT a.application_id, a.status, a.created_at, a.raw_payload,
             a.escalated_by_officer_id, a.escalated_to_senior_officer_id, a.escalated_at,
             d.payload as decision_payload
        FROM applications a
        LEFT JOIN latest_decisions d ON a.application_id = d.application_id AND d.rn = 1
        ORDER BY a.created_at DESC
        LIMIT :limit
    """)
    
    with engine.begin() as conn:
        rows = conn.execute(query, {"limit": limit}).mappings().all()

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
            
        if item.get("decision_payload"):
            try:
                d = json.loads(item["decision_payload"])
                item["ai_recommendation"] = d.get("ai_recommendation")
                item["processing_ms"] = d.get("processing_time_ms")
            except Exception:
                item["ai_recommendation"] = None
                item["processing_ms"] = None
        else:
            item["ai_recommendation"] = None
            item["processing_ms"] = None
            
        result.append(item)
    return result


def find_similar_applications(
    cibil_range: tuple[float, float],
    income_range: tuple[float, float],
    loan_type: str,
    amount_range: tuple[float, float],
    exclude_id: str = "",
    limit: int = 10,
) -> list[dict]:
    """
    Find past applications that are similar in credit profile.
    Matches on CIBIL score range, income range, loan type, and amount range.
    Returns a list with ai_recommendation, officer_decision, and key features.
    """
    query = text("""
        WITH latest_decisions AS (
            SELECT application_id, payload,
                   ROW_NUMBER() OVER (PARTITION BY application_id ORDER BY decided_at DESC) AS rn
            FROM decisions
        ),
        latest_officer AS (
            SELECT application_id, decision,
                   ROW_NUMBER() OVER (PARTITION BY application_id ORDER BY id DESC) AS rn
            FROM officer_actions
        )
        SELECT
            a.application_id,
            a.status,
            a.created_at,
            a.raw_payload,
            d.payload  AS decision_payload,
            o.decision AS officer_decision
        FROM applications a
        LEFT JOIN latest_decisions d ON a.application_id = d.application_id AND d.rn = 1
        LEFT JOIN latest_officer  o ON a.application_id = o.application_id  AND o.rn = 1
        WHERE a.status NOT IN ('PENDING', 'DIL_PROCESSING', 'AGENTS_RUNNING', 'DATA_REQUIRED', 'ERROR')
          AND (:exclude_id = '' OR a.application_id != :exclude_id)
        ORDER BY a.created_at DESC
        LIMIT :pool
    """)

    pool = max(limit * 10, 100)
    with engine.begin() as conn:
        rows = conn.execute(query, {
            "exclude_id": exclude_id or "",
            "pool": pool,
        }).mappings().all()

    results: list[dict] = []
    for row in rows:
        try:
            payload = json.loads(row["raw_payload"])
        except Exception:
            continue

        # Filter by loan type
        if str(payload.get("loan_product_type", "")).upper() != str(loan_type).upper():
            continue

        # Filter by CIBIL range (stored in raw_payload by DIL copy-back or skip if absent)
        cibil = float(payload.get("cibil_score", 0))
        if cibil > 0 and not (cibil_range[0] <= cibil <= cibil_range[1]):
            continue

        # Filter by income range
        income = float(payload.get("annual_income", payload.get("annual_income_verified", 0)))
        if income > 0 and not (income_range[0] <= income <= income_range[1]):
            continue

        # Filter by loan amount range
        amt = float(payload.get("loan_amount_requested", 0))
        if amt > 0 and not (amount_range[0] <= amt <= amount_range[1]):
            continue

        ai_rec = None
        if row["decision_payload"]:
            try:
                dec = json.loads(row["decision_payload"])
                ai_rec = dec.get("ai_recommendation")
            except Exception:
                pass

        results.append({
            "application_id":   row["application_id"],
            "status":           row["status"],
            "created_at":       str(row["created_at"]),
            "loan_amount":      amt,
            "annual_income":    income,
            "cibil_score":      cibil,
            "loan_product":     payload.get("loan_product_type"),
            "ai_recommendation": ai_rec,
            "officer_decision": row["officer_decision"],
        })

        if len(results) >= limit:
            break

    return results


def get_bulk_audit_logs(application_ids: list[str]) -> dict[str, list[dict]]:
    """
    Fetches audit logs for multiple applications in a single query.
    """
    if not application_ids:
        return {}
        
    query = text("""
        SELECT *
        FROM audit_log
        WHERE application_id IN :ids
        ORDER BY application_id, id ASC
    """)
    
    with engine.begin() as conn:
        rows = conn.execute(query, {"ids": tuple(application_ids)}).mappings().all()
        
    result = {}
    for row in rows:
        app_id = row["application_id"]
        if app_id not in result:
            result[app_id] = []
        result[app_id].append(dict(row))
    return result
