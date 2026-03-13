"""
SQLAlchemy models for credit risk user profiles and processed results.
"""

from sqlalchemy import Column, DateTime, Float, Integer, JSON, String, func

from db import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"

    pan = Column(String(10), primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    aadhaar_last4 = Column(String(4), nullable=True)
    phone = Column(String(20), nullable=True)
    email = Column(String(255), nullable=True)

    age = Column("AGE", Integer, nullable=False)
    gender = Column("GENDER", String(20), nullable=False)
    marital_status = Column("MARITALSTATUS", String(50), nullable=False)
    education = Column("EDUCATION", String(50), nullable=False)
    net_monthly_income = Column("NETMONTHLYINCOME", Float, nullable=False)
    time_with_curr_empr = Column("Time_With_Curr_Empr", Integer, nullable=False)
    credit_score = Column("Credit_Score", Integer, nullable=False)
    num_times_delinquent = Column(Integer, nullable=False)
    recent_level_of_deliq = Column(Integer, nullable=False)
    num_deliq_6mts = Column(Integer, nullable=False)
    num_deliq_12mts = Column(Integer, nullable=False)
    num_times_30p_dpd = Column(Integer, nullable=False)
    num_times_60p_dpd = Column(Integer, nullable=False)
    num_std = Column(Integer, nullable=False)
    num_sub = Column(Integer, nullable=False)
    num_dbt = Column(Integer, nullable=False)
    num_lss = Column(Integer, nullable=False)
    tot_enq = Column(Integer, nullable=False)
    enq_l12m = Column("enq_L12m", Integer, nullable=False)
    enq_l6m = Column("enq_L6m", Integer, nullable=False)
    time_since_recent_enq = Column(Integer, nullable=False)
    cc_utilization = Column("CC_utilization", Float, nullable=False)
    pl_utilization = Column("PL_utilization", Float, nullable=False)
    max_unsec_exposure_in_pct = Column("max_unsec_exposure_inPct", Float, nullable=False)
    pct_of_active_tls_ever = Column("pct_of_active_TLs_ever", Float, nullable=False)
    pct_current_bal_all_tl = Column("pct_currentBal_all_TL", Float, nullable=False)

    def to_feature_dict(self) -> dict:
        """Return payload matching the current API/ML expected key format."""
        return {
            "pan": self.pan,
            "name": self.name,
            "aadhaar_last4": self.aadhaar_last4,
            "phone": self.phone,
            "email": self.email,
            "AGE": self.age,
            "GENDER": self.gender,
            "MARITALSTATUS": self.marital_status,
            "EDUCATION": self.education,
            "NETMONTHLYINCOME": self.net_monthly_income,
            "Time_With_Curr_Empr": self.time_with_curr_empr,
            "Credit_Score": self.credit_score,
            "num_times_delinquent": self.num_times_delinquent,
            "recent_level_of_deliq": self.recent_level_of_deliq,
            "num_deliq_6mts": self.num_deliq_6mts,
            "num_deliq_12mts": self.num_deliq_12mts,
            "num_times_30p_dpd": self.num_times_30p_dpd,
            "num_times_60p_dpd": self.num_times_60p_dpd,
            "num_std": self.num_std,
            "num_sub": self.num_sub,
            "num_dbt": self.num_dbt,
            "num_lss": self.num_lss,
            "tot_enq": self.tot_enq,
            "enq_L12m": self.enq_l12m,
            "enq_L6m": self.enq_l6m,
            "time_since_recent_enq": self.time_since_recent_enq,
            "CC_utilization": self.cc_utilization,
            "PL_utilization": self.pl_utilization,
            "max_unsec_exposure_inPct": self.max_unsec_exposure_in_pct,
            "pct_of_active_TLs_ever": self.pct_of_active_tls_ever,
            "pct_currentBal_all_TL": self.pct_current_bal_all_tl,
        }


class RiskProcessed(Base):
    __tablename__ = "risk_processed"

    pan = Column(String(10), primary_key=True, index=True)
    status = Column(String(20), nullable=False, default="completed")
    result = Column(JSON, nullable=False)
    processed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def to_dict(self) -> dict:
        return {
            "pan": self.pan,
            "status": self.status,
            "result": self.result,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
        }
