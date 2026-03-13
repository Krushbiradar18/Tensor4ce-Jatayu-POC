"""
Repository layer for user_profiles table operations.

This module is the single source of truth for profile reads/writes so API and
agent flows share the same PostgreSQL-backed data access path.
"""

from typing import Any, Dict, List, Optional

from sqlalchemy import select

from db import Base, SessionLocal, engine
from db_models import UserProfile


_db_initialized = False


def _ensure_db_ready() -> None:
    """Create required tables once per process."""
    global _db_initialized
    if _db_initialized:
        return
    Base.metadata.create_all(bind=engine)
    _db_initialized = True


def get_user_by_pan(pan: str) -> Optional[Dict[str, Any]]:
    """Fetch one user by PAN and return API-compatible dict."""
    _ensure_db_ready()
    pan_upper = pan.strip().upper()
    with SessionLocal() as session:
        row = session.execute(
            select(UserProfile).where(UserProfile.pan == pan_upper)
        ).scalar_one_or_none()
    return row.to_feature_dict() if row else None


def get_all_pans() -> List[str]:
    """Fetch all PAN numbers in ascending order."""
    _ensure_db_ready()
    with SessionLocal() as session:
        rows = session.execute(select(UserProfile.pan).order_by(UserProfile.pan)).all()
    return [row[0] for row in rows]


def list_all_users() -> List[Dict[str, Any]]:
    """Return all user profile rows as API-compatible dicts."""
    _ensure_db_ready()
    with SessionLocal() as session:
        rows = session.execute(select(UserProfile).order_by(UserProfile.pan)).scalars().all()
    return [row.to_feature_dict() for row in rows]


def create_user_profile(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Insert a new user profile row and return inserted record."""
    _ensure_db_ready()
    pan = payload["pan"].strip().upper()

    with SessionLocal() as session:
        existing = session.execute(
            select(UserProfile).where(UserProfile.pan == pan)
        ).scalar_one_or_none()
        if existing:
            raise ValueError(f"User with PAN '{pan}' already exists.")

        row = UserProfile(
            pan=pan,
            name=payload["name"],
            aadhaar_last4=payload.get("aadhaar_last4"),
            phone=payload.get("phone"),
            email=payload.get("email"),
            age=payload["AGE"],
            gender=payload["GENDER"],
            marital_status=payload["MARITALSTATUS"],
            education=payload["EDUCATION"],
            net_monthly_income=payload["NETMONTHLYINCOME"],
            time_with_curr_empr=payload["Time_With_Curr_Empr"],
            credit_score=payload["Credit_Score"],
            num_times_delinquent=payload["num_times_delinquent"],
            recent_level_of_deliq=payload["recent_level_of_deliq"],
            num_deliq_6mts=payload["num_deliq_6mts"],
            num_deliq_12mts=payload["num_deliq_12mts"],
            num_times_30p_dpd=payload["num_times_30p_dpd"],
            num_times_60p_dpd=payload["num_times_60p_dpd"],
            num_std=payload["num_std"],
            num_sub=payload["num_sub"],
            num_dbt=payload["num_dbt"],
            num_lss=payload["num_lss"],
            tot_enq=payload["tot_enq"],
            enq_l12m=payload["enq_L12m"],
            enq_l6m=payload["enq_L6m"],
            time_since_recent_enq=payload["time_since_recent_enq"],
            cc_utilization=payload["CC_utilization"],
            pl_utilization=payload["PL_utilization"],
            max_unsec_exposure_in_pct=payload["max_unsec_exposure_inPct"],
            pct_of_active_tls_ever=payload["pct_of_active_TLs_ever"],
            pct_current_bal_all_tl=payload["pct_currentBal_all_TL"],
        )
        session.add(row)
        session.commit()
        session.refresh(row)

    return row.to_feature_dict()
