"""
Pydantic models for API request/response schemas.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum


class RiskCategory(str, Enum):
    LOW = "Low Risk"
    MEDIUM_LOW = "Medium-Low Risk"
    MEDIUM_HIGH = "Medium-High Risk"
    HIGH = "High Risk"


class LoanType(str, Enum):
    PERSONAL = "Personal Loan"
    HOME = "Home Loan"
    AUTO = "Auto Loan"
    BUSINESS = "Business Loan"
    EDUCATION = "Education Loan"


class LoanApplicationRequest(BaseModel):
    pan_number: str = Field(..., description="PAN number to fetch user profile from DB")
    loan_amount: float = Field(..., gt=0, description="Requested loan amount in INR")
    loan_type: LoanType = Field(..., description="Type of loan")
    loan_tenure_months: int = Field(..., gt=0, le=360, description="Loan tenure in months")
    # Optional overrides (if user provides updated values)
    declared_monthly_income: Optional[float] = Field(None, description="Self-declared monthly income")


class FeatureContribution(BaseModel):
    feature: str
    value: Any
    contribution: float
    direction: str  # "positive" (increases risk) or "negative" (decreases risk)
    description: str


class RiskScoreResponse(BaseModel):
    # Core result
    risk_score: float = Field(..., description="Numeric risk score 0-100 (higher = riskier)")
    risk_category: RiskCategory
    approved_flag: str  # P1, P2, P3, P4

    # Applicant info
    applicant_name: str
    pan_number: str

    # Loan details
    loan_amount: float
    loan_type: str
    loan_tenure_months: int
    emi_estimate: float

    # Model explanation
    top_risk_factors: List[FeatureContribution]
    top_positive_factors: List[FeatureContribution]

    # LLM explanation
    llm_explanation: str
    recommendation: str

    # Model confidence
    confidence: float
    class_probabilities: Dict[str, float]

    # Key metrics snapshot
    credit_score: int
    debt_to_income_ratio: float
    utilization_summary: Dict[str, float]


class UserProfileResponse(BaseModel):
    found: bool
    pan: Optional[str]
    name: Optional[str]
    age: Optional[int]
    income: Optional[float]
    credit_score: Optional[int]
    message: str


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    model_accuracy: float
    version: str
