from datetime import date
from typing import Literal, TypedDict

from pydantic import BaseModel


class ApplicationFormData(BaseModel):
    pan_number: str
    date_of_birth: date
    employment_type: Literal["SALARIED", "SELF_EMPLOYED"]
    annual_income: float
    loan_amount_requested: float
    loan_tenure_months: int
    loan_purpose: Literal["PERSONAL"]
    existing_emi_monthly: float
    uploaded_docs: list[str]
    employer_name: str
    gender: Literal["MALE", "FEMALE", "OTHER"]
    marital_status: Literal["SINGLE", "MARRIED", "DIVORCED"]


class CreditAgentOutput(BaseModel):
    risk_score: float
    risk_band: Literal["LOW", "MEDIUM", "HIGH", "VERY_HIGH"]
    foir: float
    dti_ratio: float
    macro_adjusted: bool


class FraudAgentOutput(BaseModel):
    fraud_level: Literal["CLEAN", "LOW_RISK", "SUSPICIOUS", "HIGH_RISK"]
    fraud_probability: float
    kyc_verified: bool
    triggered_rules: list[str]


class BankStatementData(BaseModel):
    avg_monthly_credit: float
    emi_bounce_count: int
    salary_credit_regularity: float


class MacroConfigData(BaseModel):
    stress_scenario: Literal["NORMAL", "MILD_STRESS", "HIGH_STRESS"]
    rbi_repo_rate: float
    sector_npa_rates: dict[str, float]


class ComplianceState(TypedDict):
    application: ApplicationFormData
    credit_output: CreditAgentOutput
    fraud_output: FraudAgentOutput
    bank_data: BankStatementData
    macro_data: MacroConfigData

    age_eligible: bool
    income_eligible: bool
    kyc_complete: bool
    purpose_valid: bool
    foir_within_limit: bool
    loan_amount_eligible: bool
    tenure_within_limit: bool
    prepayment_penalty_applicable: bool
    aml_flagged: bool
    aml_check_required: bool
    income_mismatch: bool
    repayment_history_concern: bool
    fairness_flag: bool
    gender_logged_only: bool
    geographic_bias_flag: bool
    compliance_flags: list[str]

    compliance_status: str
    rbi_compliant: bool
    audit_ready: bool
    narrative: str
    audit_narrative: str
    llm_status: str
    llm_provider_error: str


class ComplianceOutput(BaseModel):
    compliance_status: Literal["PASS", "FAIL", "ESCALATE"]
    rbi_compliant: bool
    kyc_complete: bool
    age_eligible: bool
    income_eligible: bool
    foir_within_limit: bool
    loan_amount_eligible: bool
    tenure_within_limit: bool
    aml_flagged: bool
    aml_check_required: bool
    income_mismatch: bool
    fairness_flag: bool
    compliance_flags: list[str]
    audit_ready: bool
    narrative: str
    audit_narrative: str
    llm_status: str = "not_called"
    llm_provider_error: str = ""
