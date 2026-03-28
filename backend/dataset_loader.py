"""
dataset_loader.py — Mock API Database Access Layer
===================================================
Replaces the old in-memory Excel loading with a direct SQLAlchemy connection
to a persistent PostgreSQL database (`mock_bureau_records`).
Emulates official Credit Bureau and Internal Bank external APIs.
"""
from __future__ import annotations
import os
import logging
from typing import Optional
from pathlib import Path
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent

for env_path in (PROJECT_ROOT / ".env", BACKEND_DIR / ".env"):
    if env_path.exists():
        load_dotenv(env_path)
        break

# DB Connection Setup
_PG_USER = os.environ.get("PG_USER", "postgres")
_PG_PASS = os.environ.get("PG_PASSWORD", "postgres")
_PG_HOST = os.environ.get("PG_HOST", "localhost")
_PG_PORT = os.environ.get("PG_PORT", "5432")
_PG_DB   = os.environ.get("PG_DB", "jatayu")

_DB_URI = f"postgresql://{_PG_USER}:{_PG_PASS}@{_PG_HOST}:{_PG_PORT}/{_PG_DB}"
_ENGINE: Optional[Engine] = None

def _get_engine() -> Engine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = create_engine(_DB_URI)
    return _ENGINE


def _query_db_for_pan(pan: str) -> Optional[dict]:
    """Execute SQL query to mock an external API lookup by PAN."""
    pan = pan.upper().strip()
    try:
        engine = _get_engine()
        query = text("SELECT * FROM mock_bureau_records WHERE upper(pan) = :pan LIMIT 1")
        with engine.connect() as conn:
            result = conn.execute(query, {"pan": pan}).fetchone()
            if result:
                # _mapping provides dict-like access for SQLAlchemy 2.0 Row
                return dict(result._mapping)
    except Exception as e:
        logger.warning(f"Failed to query Postgres for PAN {pan}: {e}. Ensure setup_pg_db.py was run.")
    return None


def get_cibil_data(pan: str) -> Optional[dict]:
    """
    Get CIBIL bureau data for a PAN.
    Returns dict with keys: cibil_score, num_hard_enquiries_6m, dpd_30_count, etc.
    """
    row = _query_db_for_pan(pan)
    if not row:
        return None

    # Map database row (lowercased) to the expected schema
    # Map database row (lowercased) to the expected schema
    # Handle -99999 sentinels which often represent NULL/Missing in bureau datasets
    def _clean(val, default=0.0):
        if val is None: return default
        try:
            fval = float(val)
            if fval == -99999 or fval < -100: return default
            return val
        except (ValueError, TypeError):
            return default

    # Correct column mappings based on actual DB schema
    return {
        "cibil_score": float(_clean(row.get("credit_score"), 650)),
        "num_hard_enquiries_6m": int(max(0, _clean(row.get("enq_l6m"), 0))),
        "dpd_30_count": int(max(0, _clean(row.get("num_times_30p_dpd"), 0))),
        "dpd_90_count": int(max(0, _clean(row.get("num_times_60p_dpd"), 0))),
        "payment_history_score": float(_clean(row.get("payment_history_score"), 50)),
        # Proper utilization logic: prefer CC utilization, fallback to TL balance pct
        "credit_utilization_pct": float(max(0, _clean(row.get("cc_utilization"), _clean(row.get("pct_currentbal_all_tl"), 0)))),
        "oldest_account_age_years": round(float(_clean(row.get("time_with_curr_empr", 12)/12, 1.0)), 1), 
        "total_outstanding_debt": float(max(0, _clean(row.get("max_unsec_exposure_inpct", 0) * row.get("netmonthlyincome", 0) / 100, 0))),
        "num_active_loans": int(max(0, _clean(row.get("num_std"), 0))),
        "active_tl_pct": float(_clean(row.get("pct_of_active_tls_ever"), 0.0)),
        "recent_enq_product": str(_clean(row.get("last_prod_enq2"), "None")),
        "total_delinquencies": int(max(0, _clean(row.get("num_times_delinquent"), 0))),
        "bureau_unavailable": False,
    }


def get_bank_data(pan: str) -> Optional[dict]:
    """
    Get internal bank data for a PAN.
    """
    row = _query_db_for_pan(pan)
    if not row:
        return None

    # We mock bank data from the same single DB table for the POC
    return {
        "avg_monthly_credit": float(row.get("netmonthlyincome", 50000)),
        "avg_monthly_debit": float(row.get("netmonthlyincome", 50000) * 0.7),
        "min_eod_balance": float(15000.0),
        "avg_eod_balance": float(row.get("netmonthlyincome", 50000) * 0.4),
        "emi_bounce_count": int(row.get("recent_level_of_deliq", 0)),
        "salary_regularity": float(0.95),
        "cash_flow_volatility": float(0.15),
        "debit_credit_ratio": float(0.75),
        "balance_utilization": float(0.3),
    }


def get_merged_customer_profile(pan: str) -> Optional[dict]:
    """
    Get complete customer profile.
    This is useful for the credit risk agent inference.
    """
    row = _query_db_for_pan(pan)
    if not row:
        return None

    return {
        "pan_number": pan,
        "name": row.get("name", "Applicant"),
        # ML Feature inputs
        "Credit_Score": float(row.get("credit_score", 0)),
        "num_times_delinquent": int(row.get("num_times_delinquent", 0)),
        "recent_level_of_deliq": int(row.get("recent_level_of_deliq", 0)),
        "num_deliq_6mts": int(row.get("num_deliq_6mts", 0)),
        "num_deliq_12mts": int(row.get("num_deliq_12mts", 0)),
        "num_times_30p_dpd": int(row.get("num_times_30p_dpd", 0)),
        "num_times_60p_dpd": int(row.get("num_times_60p_dpd", 0)),
        "num_std": int(row.get("num_std", 0)),
        "num_sub": int(row.get("num_sub", 0)),
        "num_dbt": int(row.get("num_dbt", 0)),
        "num_lss": int(row.get("num_lss", 0)),
        "tot_enq": int(row.get("tot_enq", 0)),
        "enq_L12m": int(row.get("enq_l12m", 0)),
        "enq_L6m": int(row.get("enq_l6m", 0)),
        "time_since_recent_enq": int(row.get("time_since_recent_enq", 0)),
        "CC_utilization": float(row.get("cc_utilization", 0)),
        "PL_utilization": float(row.get("pl_utilization", 0)),
        "max_unsec_exposure_inPct": float(row.get("max_unsec_exposure_inpct", 0)),
        "pct_of_active_TLs_ever": float(row.get("pct_of_active_tls_ever", 0)),
        "pct_currentBal_all_TL": float(row.get("pct_currentbal_all_tl", 0)),
        "AGE": int(row.get("age", 30)),
        "NETMONTHLYINCOME": float(row.get("netmonthlyincome", 50000)),
        "Time_With_Curr_Empr": float(row.get("time_with_curr_empr", 12.0)),
        "MARITALSTATUS": str(row.get("maritalstatus", "Single")),
        "EDUCATION": str(row.get("education", "GRADUATE")),
        "GENDER": str(row.get("gender", "M")),
        "Approved_Flag": row.get("approved_flag", None),
        
        # Aliases
        "cibil_score": float(row.get("credit_score", 0)),
        "num_hard_enquiries_6m": int(row.get("enq_l6m", 0)),
        "dpd_30_count": int(row.get("num_times_30p_dpd", 0)),
        "dpd_90_count": int(row.get("num_times_60p_dpd", 0)),
    }


def get_identity_record(pan: str) -> Optional[dict]:
    """Return core identity fields from mock_bureau_records for preliminary checks."""
    row = _query_db_for_pan(pan)
    if not row:
        return None
    return {
        "pan": str(row.get("pan", "")).upper().strip(),
        "name": str(row.get("name", "")).strip(),
        "aadhaar": row.get("aadhaar"),
    }


def get_portfolio_loans() -> list[dict]:
    """Fetch portfolio loan rows from PostgreSQL table portfolio_loans."""
    try:
        engine = _get_engine()
        query = text("SELECT * FROM portfolio_loans")
        with engine.connect() as conn:
            rows = conn.execute(query).fetchall()
            return [dict(r._mapping) for r in rows]
    except Exception as e:
        logger.warning(f"Failed to query portfolio_loans from Postgres: {e}")
        return []


def get_credit_ground_truth(pan: str) -> Optional[dict]:
    row = _query_db_for_pan(pan)
    if not row:
        return None
    return {
        "pan": pan.upper(),
        "approved_flag": row.get("approved_flag"),
        "credit_score": float(row.get("credit_score", 0)),
    }


def list_available_pans(limit: int = 10) -> list[str]:
    try:
        engine = _get_engine()
        query = text(f"SELECT pan FROM mock_bureau_records LIMIT {limit}")
        with engine.connect() as conn:
            return [str(r[0]) for r in conn.execute(query).fetchall()]
    except Exception:
        return []


def get_sample_test_cases(count: int = 10) -> list[dict]:
    try:
        engine = _get_engine()
        query = text(f"SELECT prospectid as prospect_id, pan, credit_score, age, netmonthlyincome as income, num_times_30p_dpd as dpd_30 FROM mock_bureau_records LIMIT {count}")
        with engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(query).fetchall()]
    except Exception:
        return []


def get_dataset_stats() -> dict:
    try:
        engine = _get_engine()
        with engine.connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM mock_bureau_records")).scalar()
            return {
                "cibil_records": count,
                "bank_records": count,  # Mapped identically for the PoC
                "merged_records": count,
                "datasets_loaded": True
            }
    except Exception:
        return {"cibil_records": 0, "bank_records": 0, "merged_records": 0, "datasets_loaded": False}


# No-Ops to maintain compatibility with legacy startup logic
def load_datasets(dataset_dir: str = "dataset"):
    pass

def start_background_dataset_preload(dataset_dir: str = "dataset") -> bool:
    return True
