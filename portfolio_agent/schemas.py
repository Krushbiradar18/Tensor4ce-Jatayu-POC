"""schemas.py — Pydantic v2 models and LangGraph state for the Portfolio Intelligence Agent."""
from __future__ import annotations
from typing import Literal, Optional, TypedDict
from pydantic import BaseModel, Field


# ─── Input Models ────────────────────────────────────────────────────────────

class ApplicationFormData(BaseModel):
    loan_purpose: Literal["PERSONAL"] = "PERSONAL"
    loan_amount_requested: float
    loan_tenure_months: int
    employment_type: Literal["SALARIED", "SELF_EMPLOYED"]
    annual_income: float
    employer_name: str
    applicant_state: str
    applicant_city: str


class CreditAgentOutput(BaseModel):
    """Fields the Portfolio Agent reads from the Credit Risk agent output."""
    risk_band: Literal["LOW", "MEDIUM", "HIGH", "VERY_HIGH"]
    predicted_pd: float = Field(..., ge=0.0, le=1.0)   # probability of default
    credit_score: float = Field(default=0.05)           # alias for predicted_pd in legacy system
    foir: float = Field(default=0.0)
    macro_adjusted: bool = False

    @classmethod
    def from_agent_dict(cls, d: dict) -> "CreditAgentOutput":
        """Build from the raw dict returned by credit_risk_agent (credit_score = PD)."""
        pd_val = float(d.get("credit_score", 0.05))
        return cls(
            risk_band=d.get("risk_band", "MEDIUM"),
            predicted_pd=pd_val,
            credit_score=pd_val,
            foir=float(d.get("foir", 0.0)),
            macro_adjusted=bool(d.get("macro_adjusted", False)),
        )


class FraudAgentOutput(BaseModel):
    fraud_level: Literal["CLEAN", "LOW_RISK", "SUSPICIOUS", "HIGH_RISK"]
    fraud_probability: float = Field(default=0.0, ge=0.0, le=1.0)

    @classmethod
    def from_agent_dict(cls, d: dict) -> "FraudAgentOutput":
        return cls(
            fraud_level=d.get("fraud_level", "CLEAN"),
            fraud_probability=float(d.get("fraud_probability", 0.0)),
        )


class ComplianceAgentOutput(BaseModel):
    """Portfolio agent only needs the overall status to decide whether to run deep analysis."""
    overall_status: Literal["PASS", "PASS_WITH_WARNINGS", "BLOCK_FAIL"]

    @classmethod
    def from_agent_dict(cls, d: dict) -> "ComplianceAgentOutput":
        status = d.get("overall_status", "PASS")
        # Map old compliance_status values just in case
        if status == "FAIL":
            status = "BLOCK_FAIL"
        elif status == "ESCALATE":
            status = "PASS_WITH_WARNINGS"
        if status not in ("PASS", "PASS_WITH_WARNINGS", "BLOCK_FAIL"):
            status = "PASS"
        return cls(overall_status=status)


class BankStatementData(BaseModel):
    avg_monthly_credit: float = 0.0
    emi_bounce_count: int = 0

    @classmethod
    def from_features(cls, features: dict) -> "BankStatementData":
        return cls(
            avg_monthly_credit=float(features.get("avg_monthly_credit", 0.0)),
            emi_bounce_count=int(features.get("emi_bounce_count", 0)),
        )


class MacroConfigData(BaseModel):
    stress_scenario: Literal["NORMAL", "MILD_STRESS", "HIGH_STRESS"] = "NORMAL"
    rbi_repo_rate: float = 6.5
    sector_npa_rates: dict = Field(default_factory=lambda: {"PERSONAL": 0.038})
    gdp_growth_rate: float = 6.8
    inflation_rate: float = 4.8

    @classmethod
    def from_dict(cls, d: dict) -> "MacroConfigData":
        scenario = d.get("stress_scenario", "NORMAL")
        if scenario not in ("NORMAL", "MILD_STRESS", "HIGH_STRESS"):
            scenario = "NORMAL"
        return cls(
            stress_scenario=scenario,
            rbi_repo_rate=float(d.get("rbi_repo_rate", d.get("repo_rate", 6.5))),
            sector_npa_rates=d.get("sector_npa_rates", {"PERSONAL": 0.038}),
            gdp_growth_rate=float(d.get("gdp_growth_rate", 6.8)),
            inflation_rate=float(d.get("inflation_rate", 4.8)),
        )


class PortfolioStats(BaseModel):
    """Pre-aggregated portfolio statistics supplied by the orchestrator."""
    total_loans: int = 0
    total_exposure_inr: float = 0.0
    sector_distribution: dict = Field(default_factory=lambda: {"PERSONAL": 0.28})
    risk_band_distribution: dict = Field(
        default_factory=lambda: {"LOW": 0.45, "MEDIUM": 0.38, "HIGH": 0.12, "VERY_HIGH": 0.05}
    )
    geographic_distribution: dict = Field(default_factory=dict)
    employer_top_10: list = Field(default_factory=list)
    portfolio_weighted_avg_pd: float = 0.05
    portfolio_el_total: float = 0.0
    self_employed_pct: float = 0.20


# ─── LangGraph State ─────────────────────────────────────────────────────────

class PortfolioState(TypedDict):
    # Inputs (populated by orchestrator before graph is invoked)
    application: ApplicationFormData
    credit_output: CreditAgentOutput
    fraud_output: FraudAgentOutput
    compliance_output: ComplianceAgentOutput
    bank_data: BankStatementData
    macro_data: MacroConfigData
    portfolio_stats: PortfolioStats

    # Computed by nodes
    sector_concentration_pct: float
    post_approval_sector_pct: float
    concentration_flag: bool
    sector_threshold_used: float

    geographic_concentration_flag: bool
    city_concentration_flag: bool
    top_state: str
    top_state_pct: float

    employer_concentration_flag: bool
    employer_pct: float

    segment_concentration_flag: bool   # SELF_EMPLOYED > 30%

    high_risk_pct_current: float
    high_risk_pct_post_approval: float
    risk_band_flag: bool
    post_approval_risk_distribution: dict

    pd_adjusted: float
    lgd: float
    ead: float
    expected_loss_impact: float
    portfolio_el_before: float
    portfolio_el_after: float
    el_increase_pct: float

    portfolio_recommendation: str      # "ACCEPT" | "CAUTION" | "REJECT_FOR_PORTFOLIO"
    concentration_flags: list          # all flags that fired

    narrative: str                     # LLM-generated


# ─── Output Model ────────────────────────────────────────────────────────────

class PortfolioAgentOutput(BaseModel):
    """Full rich output from portfolio agent (used internally and by test runner)."""
    portfolio_recommendation: Literal["ACCEPT", "CAUTION", "REJECT_FOR_PORTFOLIO"]
    sector_concentration_pct: float
    post_approval_sector_pct: float
    concentration_flag: bool
    geographic_concentration_flag: bool
    employer_concentration_flag: bool
    expected_loss_impact: float
    el_increase_pct: float
    portfolio_el_before: float
    portfolio_el_after: float
    risk_band_distribution: dict
    post_approval_risk_distribution: dict
    total_portfolio_loans: int
    total_portfolio_exposure: float
    segment_concentration_flag: bool
    concentration_flags: list
    narrative: str
