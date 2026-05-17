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
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(50) NOT NULL DEFAULT 'officer',
            full_name VARCHAR(255) DEFAULT '',
            is_verified BOOLEAN NOT NULL DEFAULT TRUE,
            verification_code_hash TEXT DEFAULT '',
            verification_code_expires_at TIMESTAMPTZ,
            verification_code_sent_at TIMESTAMPTZ,
            two_factor_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            two_factor_method VARCHAR(32) NOT NULL DEFAULT 'email',
            totp_secret TEXT DEFAULT '',
            totp_enabled_at TIMESTAMPTZ,
            needs_password_reset BOOLEAN NOT NULL DEFAULT FALSE,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS auth_challenges (
            id SERIAL PRIMARY KEY,
            username VARCHAR(255) NOT NULL,
            purpose VARCHAR(64) NOT NULL,
            method VARCHAR(32) NOT NULL DEFAULT 'email',
            code_hash TEXT NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            consumed_at TIMESTAMPTZ,
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
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
        """
        CREATE TABLE IF NOT EXISTS logs (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            application_id TEXT,
            agent_name TEXT NOT NULL DEFAULT 'system',
            log_level VARCHAR(10) NOT NULL DEFAULT 'INFO',
            log_category VARCHAR(20) NOT NULL DEFAULT 'system',
            message TEXT NOT NULL DEFAULT '',
            error_type TEXT,
            stack_trace TEXT,
            llm_model_name TEXT,
            tool_name TEXT,
            input_data TEXT,
            output_data TEXT,
            execution_time_ms FLOAT,
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
    ]
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))
    
    # Add indexes for logs table
    index_statements = [
        "CREATE INDEX IF NOT EXISTS idx_logs_application_id ON logs (application_id)",
        "CREATE INDEX IF NOT EXISTS idx_logs_agent_name ON logs (agent_name)",
        "CREATE INDEX IF NOT EXISTS idx_logs_log_level ON logs (log_level)",
        "CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs (timestamp DESC)",
        "CREATE INDEX IF NOT EXISTS idx_logs_llm_model_name ON logs (llm_model_name)",
        "CREATE INDEX IF NOT EXISTS idx_logs_created_at ON logs (created_at DESC)",
    ]
    for idx_stmt in index_statements:
        try:
            with engine.begin() as conn:
                conn.execute(text(idx_stmt))
        except Exception:
            pass  # Index already exists

    # Add missing columns to existing applications table if they don't exist (separate transactions)
    alter_statements = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_verified BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_code_hash TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_code_expires_at TIMESTAMPTZ",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_code_sent_at TIMESTAMPTZ",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS two_factor_enabled BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS two_factor_method VARCHAR(32) NOT NULL DEFAULT 'email'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_secret TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_enabled_at TIMESTAMPTZ",
        "ALTER TABLE auth_challenges ADD COLUMN IF NOT EXISTS method VARCHAR(32) NOT NULL DEFAULT 'email'",
        "ALTER TABLE auth_challenges ADD COLUMN IF NOT EXISTS metadata TEXT NOT NULL DEFAULT '{}'",
        "ALTER TABLE applications ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE applications ADD COLUMN IF NOT EXISTS escalated_by_officer_id TEXT",
        "ALTER TABLE applications ADD COLUMN IF NOT EXISTS escalated_to_senior_officer_id INTEGER",
        "ALTER TABLE applications ADD COLUMN IF NOT EXISTS escalated_at TIMESTAMPTZ",
        "ALTER TABLE officer_actions ADD COLUMN IF NOT EXISTS actor_role TEXT DEFAULT 'officer'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS needs_password_reset BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE",
        # ── logs table column migrations ───────────────────────────────────────
        "ALTER TABLE logs ADD COLUMN IF NOT EXISTS timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP",
        "ALTER TABLE logs ADD COLUMN IF NOT EXISTS application_id TEXT",
        "ALTER TABLE logs ADD COLUMN IF NOT EXISTS agent_name TEXT NOT NULL DEFAULT 'system'",
        "ALTER TABLE logs ADD COLUMN IF NOT EXISTS log_level VARCHAR(10) NOT NULL DEFAULT 'INFO'",
        "ALTER TABLE logs ADD COLUMN IF NOT EXISTS log_category VARCHAR(20) NOT NULL DEFAULT 'system'",
        "ALTER TABLE logs ADD COLUMN IF NOT EXISTS message TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE logs ADD COLUMN IF NOT EXISTS error_type TEXT",
        "ALTER TABLE logs ADD COLUMN IF NOT EXISTS stack_trace TEXT",
        "ALTER TABLE logs ADD COLUMN IF NOT EXISTS llm_model_name TEXT",
        "ALTER TABLE logs ADD COLUMN IF NOT EXISTS tool_name TEXT",
        "ALTER TABLE logs ADD COLUMN IF NOT EXISTS input_data TEXT",
        "ALTER TABLE logs ADD COLUMN IF NOT EXISTS output_data TEXT",
        "ALTER TABLE logs ADD COLUMN IF NOT EXISTS execution_time_ms FLOAT",
        "ALTER TABLE logs ADD COLUMN IF NOT EXISTS metadata TEXT NOT NULL DEFAULT '{}'",
        "ALTER TABLE logs ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP",
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


def create_user(
    username: str,
    password_hash: str,
    role: str,
    full_name: str = "",
    *,
    is_verified: bool = True,
    verification_code_hash: str = "",
    verification_code_expires_at=None,
    verification_code_sent_at=None,
    two_factor_enabled: bool = False,
    two_factor_method: str = "email",
    totp_secret: str = "",
    totp_enabled_at=None,
    needs_password_reset: bool = False,
    is_active: bool = True,
) -> dict:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO users (
                    username,
                    password_hash,
                    role,
                    full_name,
                    is_verified,
                    verification_code_hash,
                    verification_code_expires_at,
                    verification_code_sent_at,
                    two_factor_enabled,
                    two_factor_method,
                    totp_secret,
                    totp_enabled_at,
                    needs_password_reset,
                    is_active
                )
                VALUES (
                    :username,
                    :password_hash,
                    :role,
                    :full_name,
                    :is_verified,
                    :verification_code_hash,
                    :verification_code_expires_at,
                    :verification_code_sent_at,
                    :two_factor_enabled,
                    :two_factor_method,
                    :totp_secret,
                    :totp_enabled_at,
                    :needs_password_reset,
                    :is_active
                )
                ON CONFLICT (username) DO UPDATE
                SET password_hash = EXCLUDED.password_hash,
                    role = EXCLUDED.role,
                    full_name = COALESCE(NULLIF(EXCLUDED.full_name, ''), users.full_name),
                    is_verified = EXCLUDED.is_verified,
                    verification_code_hash = EXCLUDED.verification_code_hash,
                    verification_code_expires_at = EXCLUDED.verification_code_expires_at,
                    verification_code_sent_at = EXCLUDED.verification_code_sent_at,
                    two_factor_enabled = EXCLUDED.two_factor_enabled,
                    two_factor_method = EXCLUDED.two_factor_method,
                    totp_secret = EXCLUDED.totp_secret,
                    totp_enabled_at = EXCLUDED.totp_enabled_at,
                    needs_password_reset = EXCLUDED.needs_password_reset,
                    is_active = EXCLUDED.is_active,
                    updated_at = CURRENT_TIMESTAMP
                """
            ),
            {
                "username": username,
                "password_hash": password_hash,
                "role": role,
                "full_name": full_name or username,
                "is_verified": is_verified,
                "verification_code_hash": verification_code_hash or "",
                "verification_code_expires_at": verification_code_expires_at,
                "verification_code_sent_at": verification_code_sent_at,
                "two_factor_enabled": two_factor_enabled,
                "two_factor_method": two_factor_method,
                "totp_secret": totp_secret or "",
                "totp_enabled_at": totp_enabled_at,
                "needs_password_reset": needs_password_reset,
                "is_active": is_active,
            },
        )
    user = get_user_by_username(username)
    return user or {}


def update_user_verification(
    username: str,
    *,
    is_verified: bool,
    verification_code_hash: str = "",
    verification_code_expires_at=None,
    verification_code_sent_at=None,
) -> dict | None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE users
                SET is_verified = :is_verified,
                    verification_code_hash = :verification_code_hash,
                    verification_code_expires_at = :verification_code_expires_at,
                    verification_code_sent_at = :verification_code_sent_at,
                    updated_at = CURRENT_TIMESTAMP
                WHERE lower(username) = lower(:username)
                """
            ),
            {
                "username": username,
                "is_verified": is_verified,
                "verification_code_hash": verification_code_hash or "",
                "verification_code_expires_at": verification_code_expires_at,
                "verification_code_sent_at": verification_code_sent_at,
            },
        )
    return get_user_by_username(username)


def update_user_two_factor(
    username: str,
    *,
    two_factor_enabled: bool,
    two_factor_method: str = "email",
    totp_secret: str = "",
    totp_enabled_at=None,
) -> dict | None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE users
                SET two_factor_enabled = :two_factor_enabled,
                    two_factor_method = :two_factor_method,
                    totp_secret = :totp_secret,
                    totp_enabled_at = :totp_enabled_at,
                    updated_at = CURRENT_TIMESTAMP
                WHERE lower(username) = lower(:username)
                """
            ),
            {
                "username": username,
                "two_factor_enabled": two_factor_enabled,
                "two_factor_method": two_factor_method,
                "totp_secret": totp_secret or "",
                "totp_enabled_at": totp_enabled_at,
            },
        )
    return get_user_by_username(username)


def update_user_password(username: str, password_hash: str) -> dict | None:
    """Update user password and clear reset flag."""
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE users
                SET password_hash = :password_hash,
                    needs_password_reset = FALSE,
                    updated_at = CURRENT_TIMESTAMP
                WHERE lower(username) = lower(:username)
                """
            ),
            {"username": username, "password_hash": password_hash},
        )
    return get_user_by_username(username)


def update_user_status(username: str, is_active: bool) -> dict | None:
    """Enable or disable a user account."""
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE users
                SET is_active = :is_active,
                    updated_at = CURRENT_TIMESTAMP
                WHERE lower(username) = lower(:username)
                """
            ),
            {"username": username, "is_active": is_active},
        )
    return get_user_by_username(username)


def update_user_role(username: str, role: str) -> dict | None:
    """Update a user's role."""
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE users
                SET role = :role,
                    updated_at = CURRENT_TIMESTAMP
                WHERE lower(username) = lower(:username)
                """
            ),
            {"username": username, "role": role},
        )
    return get_user_by_username(username)


def delete_user(username: str) -> bool:
    """Delete a user account."""
    with engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM users WHERE lower(username) = lower(:username)"),
            {"username": username},
        )
    return result.rowcount > 0



def create_auth_challenge(
    username: str,
    purpose: str,
    code_hash: str,
    expires_at,
    *,
    method: str = "email",
    metadata: dict | None = None,
) -> dict:
    with engine.begin() as conn:
        result = conn.execute(
            text(
                """
                INSERT INTO auth_challenges (username, purpose, method, code_hash, expires_at, metadata)
                VALUES (:username, :purpose, :method, :code_hash, :expires_at, :metadata)
                RETURNING *
                """
            ),
            {
                "username": username,
                "purpose": purpose,
                "method": method,
                "code_hash": code_hash,
                "expires_at": expires_at,
                "metadata": json.dumps(metadata or {}),
            },
        )
        row = result.mappings().first()
    return dict(row) if row else {}


def get_auth_challenge(challenge_id: int) -> dict | None:
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT *
                FROM auth_challenges
                WHERE id = :challenge_id
                LIMIT 1
                """
            ),
            {"challenge_id": challenge_id},
        ).mappings().first()
    return dict(row) if row else None


def consume_auth_challenge(challenge_id: int) -> dict | None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE auth_challenges
                SET consumed_at = CURRENT_TIMESTAMP
                WHERE id = :challenge_id
                """
            ),
            {"challenge_id": challenge_id},
        )
    return get_auth_challenge(challenge_id)


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


# ── Structured Logging Functions ───────────────────────────────────────────────

def log_structured(
    agent_name: str,
    log_level: str,
    log_category: str,
    message: str,
    *,
    application_id: str | None = None,
    error_type: str | None = None,
    stack_trace: str | None = None,
    llm_model_name: str | None = None,
    tool_name: str | None = None,
    input_data: dict | str | None = None,
    output_data: dict | str | None = None,
    execution_time_ms: float | None = None,
    metadata: dict | None = None,
    timestamp: str | None = None,
) -> int:
    """
    Insert a single structured log entry into the logs table.
    Returns the new log ID.
    """
    input_str = json.dumps(input_data) if isinstance(input_data, dict) else (input_data or None)
    output_str = json.dumps(output_data) if isinstance(output_data, dict) else (output_data or None)
    meta_str = json.dumps(metadata or {})

    with engine.begin() as conn:
        result = conn.execute(
            text("""
                INSERT INTO logs (
                    timestamp, application_id, agent_name, log_level, log_category,
                    message, error_type, stack_trace, llm_model_name, tool_name,
                    input_data, output_data, execution_time_ms, metadata
                ) VALUES (
                    COALESCE(CAST(:timestamp AS TIMESTAMPTZ), CURRENT_TIMESTAMP),
                    :application_id, :agent_name, :log_level, :log_category,
                    :message, :error_type, :stack_trace, :llm_model_name, :tool_name,
                    :input_data, :output_data, :execution_time_ms, :metadata
                ) RETURNING id
            """),
            {
                "timestamp": timestamp,
                "application_id": application_id,
                "agent_name": agent_name,
                "log_level": log_level.upper(),
                "log_category": log_category.lower(),
                "message": message,
                "error_type": error_type,
                "stack_trace": stack_trace,
                "llm_model_name": llm_model_name,
                "tool_name": tool_name,
                "input_data": input_str,
                "output_data": output_str,
                "execution_time_ms": execution_time_ms,
                "metadata": meta_str,
            },
        )
        row = result.fetchone()
    return row[0] if row else -1


def log_structured_bulk(entries: list[dict]) -> list[int]:
    """
    Insert multiple structured log entries in a single transaction.
    Each entry is a dict matching the log_structured kwargs.
    Returns list of inserted IDs.
    """
    if not entries:
        return []
    ids = []
    with engine.begin() as conn:
        for entry in entries:
            input_data = entry.get("input_data")
            output_data = entry.get("output_data")
            result = conn.execute(
                text("""
                    INSERT INTO logs (
                        timestamp, application_id, agent_name, log_level, log_category,
                        message, error_type, stack_trace, llm_model_name, tool_name,
                        input_data, output_data, execution_time_ms, metadata
                    ) VALUES (
                        COALESCE(CAST(:timestamp AS TIMESTAMPTZ), CURRENT_TIMESTAMP),
                        :application_id, :agent_name, :log_level, :log_category,
                        :message, :error_type, :stack_trace, :llm_model_name, :tool_name,
                        :input_data, :output_data, :execution_time_ms, :metadata
                    ) RETURNING id
                """),
                {
                    "timestamp": entry.get("timestamp"),
                    "application_id": entry.get("application_id"),
                    "agent_name": entry.get("agent_name", "system"),
                    "log_level": str(entry.get("log_level", "INFO")).upper(),
                    "log_category": str(entry.get("log_category", "system")).lower(),
                    "message": entry.get("message", ""),
                    "error_type": entry.get("error_type"),
                    "stack_trace": entry.get("stack_trace"),
                    "llm_model_name": entry.get("llm_model_name"),
                    "tool_name": entry.get("tool_name"),
                    "input_data": json.dumps(input_data) if isinstance(input_data, dict) else input_data,
                    "output_data": json.dumps(output_data) if isinstance(output_data, dict) else output_data,
                    "execution_time_ms": entry.get("execution_time_ms"),
                    "metadata": json.dumps(entry.get("metadata") or {}),
                },
            )
            row = result.fetchone()
            ids.append(row[0] if row else -1)
    return ids


def get_logs(
    application_id: str | None = None,
    agent_name: str | None = None,
    log_level: str | None = None,
    log_category: str | None = None,
    llm_model_name: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    search: str | None = None,
    page: int = 1,
    limit: int = 50,
) -> dict:
    """
    Fetch logs with optional filters, newest first, with pagination.
    Returns {total, page, limit, items}.
    """
    conditions = []
    params: dict = {}

    if application_id:
        conditions.append("application_id = :application_id")
        params["application_id"] = application_id
    if agent_name:
        conditions.append("agent_name = :agent_name")
        params["agent_name"] = agent_name
    if log_level:
        conditions.append("log_level = :log_level")
        params["log_level"] = log_level.upper()
    if log_category:
        conditions.append("log_category = :log_category")
        params["log_category"] = log_category.lower()
    if llm_model_name:
        conditions.append("llm_model_name = :llm_model_name")
        params["llm_model_name"] = llm_model_name
    if date_from:
        conditions.append("created_at >= CAST(:date_from AS TIMESTAMPTZ)")
        params["date_from"] = date_from
    if date_to:
        conditions.append("created_at <= CAST(:date_to AS TIMESTAMPTZ)")
        params["date_to"] = date_to
    if search:
        conditions.append("message ILIKE :search")
        params["search"] = f"%{search}%"

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    offset = (page - 1) * limit

    count_query = text(f"SELECT COUNT(*) FROM logs {where_clause}")
    data_query = text(
        f"SELECT * FROM logs {where_clause} ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
    )
    params["limit"] = limit
    params["offset"] = offset

    with engine.begin() as conn:
        total = conn.execute(count_query, {k: v for k, v in params.items() if k not in ("limit", "offset")}).scalar() or 0
        rows = conn.execute(data_query, params).mappings().all()

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "items": [dict(r) for r in rows],
    }


def get_log_by_id(log_id: int) -> dict | None:
    """Fetch a single log entry by its ID."""
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT * FROM logs WHERE id = :id"),
            {"id": log_id},
        ).mappings().first()
    return dict(row) if row else None


def get_log_stats(
    application_id: str | None = None,
    agent_name: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """
    Return aggregate statistics from the logs table:
    - total logs, error count, warn count
    - errors by agent
    - avg execution time by agent
    - log level distribution
    - log category distribution
    - most common error types
    - recent error rate (last hour vs last 24h)
    """
    conditions = []
    params: dict = {}
    if application_id:
        conditions.append("application_id = :application_id")
        params["application_id"] = application_id
    if agent_name:
        conditions.append("agent_name = :agent_name")
        params["agent_name"] = agent_name
    if date_from:
        conditions.append("created_at >= CAST(:date_from AS TIMESTAMPTZ)")
        params["date_from"] = date_from
    if date_to:
        conditions.append("created_at <= CAST(:date_to AS TIMESTAMPTZ)")
        params["date_to"] = date_to
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    with engine.begin() as conn:
        totals = conn.execute(text(f"""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE log_level = 'ERROR') as error_count,
                COUNT(*) FILTER (WHERE log_level = 'WARN') as warn_count,
                COUNT(*) FILTER (WHERE log_level = 'INFO') as info_count,
                COUNT(*) FILTER (WHERE log_level = 'DEBUG') as debug_count,
                AVG(execution_time_ms) FILTER (WHERE execution_time_ms IS NOT NULL) as avg_exec_ms
            FROM logs {where}
        """), params).mappings().first()

        by_agent = conn.execute(text(f"""
            SELECT agent_name,
                   COUNT(*) as total,
                   COUNT(*) FILTER (WHERE log_level = 'ERROR') as errors,
                   AVG(execution_time_ms) FILTER (WHERE execution_time_ms IS NOT NULL) as avg_exec_ms
            FROM logs {where}
            GROUP BY agent_name
            ORDER BY errors DESC, total DESC
            LIMIT 20
        """), params).mappings().all()

        by_category = conn.execute(text(f"""
            SELECT log_category, COUNT(*) as total
            FROM logs {where}
            GROUP BY log_category
            ORDER BY total DESC
        """), params).mappings().all()

        # For sub-queries that need additional conditions, use AND if WHERE already set
        and_or_where = "AND" if conditions else "WHERE"

        top_errors = conn.execute(text(f"""
            SELECT error_type, COUNT(*) as count
            FROM logs {where}
            {and_or_where} log_level = 'ERROR' AND error_type IS NOT NULL
            GROUP BY error_type
            ORDER BY count DESC
            LIMIT 10
        """), params).mappings().all()

        llm_perf = conn.execute(text(f"""
            SELECT llm_model_name,
                   COUNT(*) as calls,
                   AVG(execution_time_ms) as avg_ms,
                   COUNT(*) FILTER (WHERE log_level = 'ERROR') as errors
            FROM logs {where}
            {and_or_where} llm_model_name IS NOT NULL
            GROUP BY llm_model_name
            ORDER BY calls DESC
            LIMIT 10
        """), params).mappings().all()

    def _safe(v):
        if v is None:
            return None
        try:
            return float(v)
        except Exception:
            return v

    t = dict(totals) if totals else {}
    return {
        "total": int(t.get("total") or 0),
        "error_count": int(t.get("error_count") or 0),
        "warn_count": int(t.get("warn_count") or 0),
        "info_count": int(t.get("info_count") or 0),
        "debug_count": int(t.get("debug_count") or 0),
        "avg_exec_ms": _safe(t.get("avg_exec_ms")),
        "by_agent": [
            {
                "agent_name": r["agent_name"],
                "total": int(r["total"]),
                "errors": int(r["errors"]),
                "avg_exec_ms": _safe(r["avg_exec_ms"]),
            }
            for r in by_agent
        ],
        "by_category": [{"category": r["log_category"], "total": int(r["total"])} for r in by_category],
        "top_errors": [{"error_type": r["error_type"], "count": int(r["count"])} for r in top_errors],
        "llm_performance": [
            {
                "model": r["llm_model_name"],
                "calls": int(r["calls"]),
                "avg_ms": _safe(r["avg_ms"]),
                "errors": int(r["errors"]),
            }
            for r in llm_perf
        ],
    }


def get_log_health() -> dict:
    """
    Returns a system health summary based on log error rates.
    Compares last-1-hour error rate to last-24-hour baseline.
    """
    with engine.begin() as conn:
        row = conn.execute(text("""
            SELECT
                COUNT(*) as total_24h,
                COUNT(*) FILTER (WHERE log_level = 'ERROR') as errors_24h,
                COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '1 hour') as total_1h,
                COUNT(*) FILTER (WHERE log_level = 'ERROR' AND created_at >= NOW() - INTERVAL '1 hour') as errors_1h,
                MAX(created_at) as last_log_at
            FROM logs
            WHERE created_at >= NOW() - INTERVAL '24 hours'
        """)).mappings().first()

    if not row:
        return {"status": "UNKNOWN", "message": "No log data available."}

    r = dict(row)
    total_24h = int(r.get("total_24h") or 0)
    errors_24h = int(r.get("errors_24h") or 0)
    total_1h = int(r.get("total_1h") or 0)
    errors_1h = int(r.get("errors_1h") or 0)

    error_rate_24h = (errors_24h / total_24h) if total_24h > 0 else 0.0
    error_rate_1h = (errors_1h / total_1h) if total_1h > 0 else 0.0

    if error_rate_1h >= 0.5:
        status = "CRITICAL"
        message = f"High error rate in the last hour: {error_rate_1h:.0%}"
    elif error_rate_1h >= 0.2:
        status = "DEGRADED"
        message = f"Elevated error rate in the last hour: {error_rate_1h:.0%}"
    elif total_24h == 0:
        status = "UNKNOWN"
        message = "No logs recorded in the last 24 hours."
    else:
        status = "HEALTHY"
        message = f"System operating normally. Error rate (24h): {error_rate_24h:.0%}"

    return {
        "status": status,
        "message": message,
        "total_24h": total_24h,
        "errors_24h": errors_24h,
        "error_rate_24h": round(error_rate_24h, 4),
        "total_1h": total_1h,
        "errors_1h": errors_1h,
        "error_rate_1h": round(error_rate_1h, 4),
        "last_log_at": str(r.get("last_log_at") or ""),
    }
