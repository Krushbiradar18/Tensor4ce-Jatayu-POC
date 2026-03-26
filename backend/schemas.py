"""schemas.py — All Pydantic v2 models used across the system."""
from __future__ import annotations
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class LoanProduct(str, Enum):
    HOME = "HOME"; AUTO = "AUTO"; PERSONAL = "PERSONAL"; EDUCATION = "EDUCATION"

class EmploymentType(str, Enum):
    SALARIED = "SALARIED"; SELF_EMPLOYED = "SELF_EMPLOYED"

class RiskBand(str, Enum):
    LOW = "LOW"; MEDIUM = "MEDIUM"; HIGH = "HIGH"; VERY_HIGH = "VERY_HIGH"

class FraudLevel(str, Enum):
    CLEAN = "CLEAN"; LOW_RISK = "LOW_RISK"; SUSPICIOUS = "SUSPICIOUS"; HIGH_RISK = "HIGH_RISK"

class ComplianceStatus(str, Enum):
    PASS = "PASS"; PASS_WITH_WARNINGS = "PASS_WITH_WARNINGS"; BLOCK_FAIL = "BLOCK_FAIL"

class PortfolioRec(str, Enum):
    ACCEPT = "ACCEPT"; CAUTION = "CAUTION"; REJECT_FOR_PORTFOLIO = "REJECT_FOR_PORTFOLIO"

class AIDecision(str, Enum):
    APPROVE = "APPROVE"; CONDITIONAL = "CONDITIONAL"; REJECT = "REJECT"; ESCALATE = "ESCALATE"

class AppStatus(str, Enum):
    PENDING = "PENDING"
    DIL_PROCESSING = "DIL_PROCESSING"
    AGENTS_RUNNING = "AGENTS_RUNNING"
    DECIDED_PENDING_OFFICER = "DECIDED_PENDING_OFFICER"
    OFFICER_APPROVED = "OFFICER_APPROVED"
    OFFICER_REJECTED = "OFFICER_REJECTED"
    OFFICER_CONDITIONAL = "OFFICER_CONDITIONAL"
    OFFICER_ESCALATED = "OFFICER_ESCALATED"
    ERROR = "ERROR"


class AddressIn(BaseModel):
    line1: str = ""; city: str = ""; state: str = "Maharashtra"; pincode: str = "400001"

class LoanApplicationIn(BaseModel):
    applicant_name: str
    pan_number: str
    aadhaar_last4: str
    date_of_birth: str
    gender: str = "MALE"
    employment_type: EmploymentType
    employer_name: str
    annual_income: float
    employment_tenure_years: float = 1.0
    loan_amount_requested: float
    loan_tenure_months: int
    loan_purpose: LoanProduct
    existing_emi_monthly: float = 0.0
    residential_assets_value: float = 0.0
    mobile_number: str = ""
    email: str = ""
    address: AddressIn = Field(default_factory=AddressIn)
    submitted_at: str = ""

class IPMetaIn(BaseModel):
    ip_address: str = "103.21.1.1"
    form_fill_seconds: float = 300.0
    device_fingerprint: str = "unknown"
    user_agent: str = ""

class SubmitRequest(BaseModel):
    form_data: dict
    ip_metadata: dict = Field(default_factory=dict)
    # Optional: OCR-extracted fields from uploaded Aadhaar/PAN PDFs.
    # When present, document_identity_check runs before orchestration.
    # Keys: name, aadhaar_number (12-digit str), pan_number
    document_data: dict = Field(default_factory=dict)


class FeatureVector(BaseModel):
    cibil_score: float = 0.0
    num_active_loans: int = 0
    num_hard_enquiries_6m: int = 0
    payment_history_score: float = 0.0
    dpd_30_count: int = 0
    dpd_90_count: int = 0
    credit_utilization_pct: float = 0.0
    oldest_account_age_years: float = 0.0
    total_outstanding_debt: float = 0.0
    bureau_unavailable: bool = False
    annual_income_verified: float = 0.0
    foir: float = 0.0
    dti_ratio: float = 0.0
    proposed_emi: float = 0.0
    emi_to_income_ratio: float = 0.0
    net_monthly_surplus: float = 0.0
    income_stability_score: float = 0.0
    ltv_ratio: float = 0.0
    loan_to_income_ratio: float = 0.0
    loan_purpose_risk_weight: float = 0.5
    tenure_risk_score: float = 0.0
    collateral_coverage: float = 0.0
    avg_monthly_credit: float = 0.0
    avg_monthly_debit: float = 0.0
    min_eod_balance: float = 0.0
    avg_eod_balance: float = 0.0
    emi_bounce_count: int = 0
    salary_regularity: float = 1.0
    cash_flow_volatility: float = 0.15
    debit_credit_ratio: float = 0.75
    balance_utilization: float = 0.3
    ip_risk_score: float = 0.0
    ip_country_mismatch: bool = False
    application_velocity: int = 1
    device_fingerprint_new: bool = False
    form_fill_time_seconds: float = 300.0
    address_pincode_mismatch: bool = False
    income_loan_ratio_outlier: float = 0.0
    enquiry_spike_flag: bool = False
    applicant_age: int = 30
    employment_tenure_years: float = 1.0
    is_salaried: bool = True
    state_code: str = ""
    loan_product_code: int = 0
    kyc_pan_present: bool = True
    kyc_aadhaar_present: bool = True
    bureau_check_done: bool = True
    pan_blacklisted: bool = False
    aml_declaration_present: bool = False
    income_proof_age_months: int = 12
    bank_statement_months: int = 6
    name_match_score: float = 1.0


class FactorShap(BaseModel):
    feature: str; value: float; shap_value: float; human_label: str; direction: str

class CreditRiskOutput(BaseModel):
    application_id: str
    credit_score: float = 0.05
    model_risk_score: Optional[float] = None
    model_risk_category: Optional[str] = None
    model_confidence: Optional[float] = None
    model_class_probabilities: dict[str, float] = Field(default_factory=dict)
    risk_band: RiskBand = RiskBand.MEDIUM
    foir: float = 0.0
    dti_ratio: float = 0.0
    ltv_ratio: float = 0.0
    net_monthly_surplus: float = 0.0
    proposed_emi: float = 0.0
    macro_adjusted: bool = False
    stress_scenario: str = "NORMAL"
    alternative_score_used: bool = False
    top_factors: list[FactorShap] = Field(default_factory=list)
    officer_narrative: str = ""
    customer_narrative: str = ""
    agent_execution_mode: str = ""
    prediction_source: str = ""
    data_source: str = ""
    llm_status: str = ""
    llm_provider_error: str = ""
    error: Optional[str] = None

class FraudOutput(BaseModel):
    application_id: str
    fraud_probability: float = 0.0
    fraud_level: FraudLevel = FraudLevel.CLEAN
    fired_hard_rules: list[str] = Field(default_factory=list)
    fired_soft_signals: list[str] = Field(default_factory=list)
    ip_risk_score: float = 0.0
    recommend_kyc_recheck: bool = False
    explanation: str = ""
    agent_execution_mode: str = ""
    prediction_source: str = ""
    llm_status: str = ""
    llm_provider_error: str = ""
    error: Optional[str] = None

class ComplianceFlag(BaseModel):
    rule_id: str; severity: str; description: str; regulation: str; message: str

class ComplianceOutput(BaseModel):
    application_id: str
    all_blocks_passed: bool = True
    block_flags: list[ComplianceFlag] = Field(default_factory=list)
    warn_flags: list[ComplianceFlag] = Field(default_factory=list)
    overall_status: ComplianceStatus = ComplianceStatus.PASS
    kyc_complete: bool = True
    aml_review_required: bool = False
    cot_reasoning: str = ""
    audit_hash: str = ""
    narrative: str = ""
    agent_execution_mode: str = ""
    prediction_source: str = ""
    llm_status: str = ""
    llm_provider_error: str = ""
    error: Optional[str] = None

class PortfolioOutput(BaseModel):
    application_id: str
    portfolio_recommendation: PortfolioRec = PortfolioRec.ACCEPT
    sector_concentration_current: float = 0.0
    sector_concentration_new: float = 0.0
    geo_concentration_current: float = 0.0
    geo_concentration_new: float = 0.0
    risk_band_distribution: dict[str, float] = Field(default_factory=dict)
    el_impact_inr: float = 0.0
    concentration_flags: list[str] = Field(default_factory=list)
    similar_cases_npa_rate: float = 0.03
    cot_reasoning: str = ""
    error: Optional[str] = None

class Condition(BaseModel):
    condition_type: str; description: str; required_by_days: int = 7

class FinalDecision(BaseModel):
    decision_id: str
    application_id: str
    ai_recommendation: AIDecision
    decision_matrix_row: str
    conditions: list[Condition] = Field(default_factory=list)
    max_approvable_amount: Optional[float] = None
    credit_risk: Optional[CreditRiskOutput] = None
    fraud: Optional[FraudOutput] = None
    compliance: Optional[ComplianceOutput] = None
    portfolio: Optional[PortfolioOutput] = None
    officer_summary: str = ""
    processing_time_ms: float = 0.0
    decided_at: str = ""

class OfficerAction(BaseModel):
    officer_id: str = "OFF-001"
    decision: str
    reason: str

class ValidationFlag(BaseModel):
    flag_code: str; severity: str; description: str

class ApplicationContext(BaseModel):
    application_id: str
    form: LoanApplicationIn
    ip_meta: IPMetaIn
    validation_flags: list[ValidationFlag] = Field(default_factory=list)
    features: FeatureVector
    macro_config: dict = Field(default_factory=dict)
    processing_notes: list[str] = Field(default_factory=list)
    dil_completed_at: str = ""
