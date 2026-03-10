"""
LangGraph Credit Risk Agent
============================
State machine that orchestrates the credit risk assessment pipeline:

  [START]
    │
    ▼
  fetch_user_profile    ← Fetch user data from DB by PAN
    │
    ▼
  validate_inputs       ← Validate all required fields are present
    │
    ▼
  run_ml_scoring        ← Run ML model + SHAP approximation
    │
    ▼
  generate_explanation  ← Call LLM for human-readable explanation
    │
    ▼
  compile_result        ← Assemble final response
    │
    ▼
  [END]

Integrates with CrewAI as a tool/sub-agent.
"""

from typing import TypedDict, Optional, Dict, Any, List
import time
import math

from mock_db import get_user_by_pan
from inference import inference_service
from llm_service import (
    build_explanation_prompt,
    get_llm_explanation,
    generate_recommendation,
)


# ─── Agent State ────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    # Inputs
    pan_number: str
    loan_amount: float
    loan_type: str
    loan_tenure_months: int
    declared_monthly_income: Optional[float]

    # Intermediate
    user_profile: Optional[Dict[str, Any]]
    merged_data: Optional[Dict[str, Any]]
    validation_errors: List[str]

    # ML outputs
    ml_result: Optional[Dict[str, Any]]
    risk_factors: Optional[List[Dict]]
    positive_factors: Optional[List[Dict]]

    # LLM outputs
    llm_explanation: str
    recommendation: str

    # Final result
    final_result: Optional[Dict[str, Any]]
    error: Optional[str]
    processing_time_ms: float


# ─── Node Functions ──────────────────────────────────────────────────────────

def fetch_user_profile(state: AgentState) -> AgentState:
    """Node 1: Fetch user financial profile from database."""
    pan = state["pan_number"].strip().upper()
    profile = get_user_by_pan(pan)

    if not profile:
        state["error"] = f"User with PAN '{pan}' not found in database."
        state["user_profile"] = None
    else:
        state["user_profile"] = profile

    return state


def validate_inputs(state: AgentState) -> AgentState:
    """Node 2: Validate all required fields are present and within range."""
    if state.get("error"):
        return state

    errors = []
    profile = state["user_profile"]

    required_fields = [
        "AGE", "NETMONTHLYINCOME", "Credit_Score", "Time_With_Curr_Empr",
        "num_times_delinquent", "CC_utilization", "PL_utilization",
    ]
    for field in required_fields:
        if profile.get(field) is None:
            errors.append(f"Missing required field: {field}")

    loan_amount = state.get("loan_amount", 0)
    income = state.get("declared_monthly_income") or profile.get("NETMONTHLYINCOME", 0)

    if loan_amount <= 0:
        errors.append("Loan amount must be positive.")
    if income <= 0:
        errors.append("Monthly income must be positive.")

    # Check DTI ratio feasibility
    tenure = state.get("loan_tenure_months", 12)
    if income > 0 and tenure > 0:
        estimated_emi = loan_amount / tenure
        dti = (estimated_emi / income) * 100
        if dti > 70:
            errors.append(f"Debt-to-income ratio too high ({dti:.1f}%). Max recommended: 70%.")

    state["validation_errors"] = errors

    # Merge declared income override
    merged = dict(profile)
    if state.get("declared_monthly_income"):
        merged["NETMONTHLYINCOME"] = state["declared_monthly_income"]
    state["merged_data"] = merged

    return state


def run_ml_scoring(state: AgentState) -> AgentState:
    """Node 3: Run ML model and compute SHAP-style feature contributions."""
    if state.get("error") or state.get("validation_errors"):
        return state

    data = state["merged_data"]
    ml_result = inference_service.predict(data)
    risk_factors, positive_factors = inference_service.get_top_factors(
        ml_result["feature_contributions"], n=6
    )

    state["ml_result"] = ml_result
    state["risk_factors"] = risk_factors
    state["positive_factors"] = positive_factors

    return state


def generate_explanation(state: AgentState) -> AgentState:
    """Node 4: Generate LLM explanation for the risk score."""
    if state.get("error") or state.get("validation_errors"):
        state["llm_explanation"] = ""
        state["recommendation"] = ""
        return state

    ml = state["ml_result"]
    profile = state["merged_data"]

    prompt = build_explanation_prompt(
        applicant_name=profile.get("name", "Applicant"),
        loan_amount=state["loan_amount"],
        loan_type=state["loan_type"],
        risk_score=ml["risk_score"],
        risk_category=ml["risk_category"],
        approved_flag=ml["approved_flag"],
        credit_score=profile.get("Credit_Score", 0),
        income=profile.get("NETMONTHLYINCOME", 0),
        risk_factors=state["risk_factors"],
        positive_factors=state["positive_factors"],
        class_probabilities=ml["class_probabilities"],
    )

    llm_text = get_llm_explanation(prompt)
    recommendation = generate_recommendation(ml["risk_category"], ml["risk_score"])

    state["llm_explanation"] = llm_text
    state["recommendation"] = recommendation

    return state


def compile_result(state: AgentState) -> AgentState:
    """Node 5: Assemble the final structured response."""
    if state.get("error"):
        state["final_result"] = {"error": state["error"]}
        return state

    if state.get("validation_errors"):
        state["final_result"] = {"validation_errors": state["validation_errors"]}
        return state

    ml = state["ml_result"]
    profile = state["merged_data"]
    loan_amount = state["loan_amount"]
    tenure = state["loan_tenure_months"]

    # EMI estimate (simple flat-rate, ~10% annual)
    monthly_rate = 0.10 / 12
    emi = (loan_amount * monthly_rate * (1 + monthly_rate) ** tenure) / \
          ((1 + monthly_rate) ** tenure - 1)

    income = profile.get("NETMONTHLYINCOME", 1)
    dti = round((emi / income) * 100, 2) if income > 0 else 0.0

    # Attach value to each factor
    for factor in state["risk_factors"]:
        raw_feat = factor["feature"].lower().replace(" ", "_")
        factor["value"] = profile.get(raw_feat, profile.get(raw_feat + "_enc", "N/A"))

    for factor in state["positive_factors"]:
        raw_feat = factor["feature"].lower().replace(" ", "_")
        factor["value"] = profile.get(raw_feat, profile.get(raw_feat + "_enc", "N/A"))

    state["final_result"] = {
        # Core
        "risk_score": ml["risk_score"],
        "risk_category": ml["risk_category"],
        "approved_flag": ml["approved_flag"],
        "confidence": ml["confidence"],
        "class_probabilities": ml["class_probabilities"],

        # Applicant
        "applicant_name": profile.get("name", "N/A"),
        "pan_number": state["pan_number"].upper(),

        # Loan
        "loan_amount": loan_amount,
        "loan_type": state["loan_type"],
        "loan_tenure_months": tenure,
        "emi_estimate": round(emi, 2),

        # Explanation
        "top_risk_factors": state["risk_factors"],
        "top_positive_factors": state["positive_factors"],
        "llm_explanation": state["llm_explanation"],
        "recommendation": state["recommendation"],

        # Metrics
        "credit_score": profile.get("Credit_Score", 0),
        "debt_to_income_ratio": dti,
        "utilization_summary": {
            "CC_utilization": profile.get("CC_utilization", 0),
            "PL_utilization": profile.get("PL_utilization", 0),
            "max_unsec_exposure_inPct": profile.get("max_unsec_exposure_inPct", 0),
        },
        "processing_time_ms": state.get("processing_time_ms", 0),
    }

    return state


# ─── Graph Execution (LangGraph-style without the lib dependency) ─────────────

class CreditRiskGraph:
    """
    Minimal LangGraph-compatible state machine.
    Replace with actual langgraph.graph.StateGraph when langgraph is installed.
    """

    NODES = [
        ("fetch_user_profile", fetch_user_profile),
        ("validate_inputs", validate_inputs),
        ("run_ml_scoring", run_ml_scoring),
        ("generate_explanation", generate_explanation),
        ("compile_result", compile_result),
    ]

    def invoke(self, initial_state: Dict[str, Any]) -> AgentState:
        start = time.perf_counter()
        state: AgentState = {
            "pan_number": initial_state.get("pan_number", ""),
            "loan_amount": initial_state.get("loan_amount", 0),
            "loan_type": initial_state.get("loan_type", ""),
            "loan_tenure_months": initial_state.get("loan_tenure_months", 12),
            "declared_monthly_income": initial_state.get("declared_monthly_income"),
            "user_profile": None,
            "merged_data": None,
            "validation_errors": [],
            "ml_result": None,
            "risk_factors": None,
            "positive_factors": None,
            "llm_explanation": "",
            "recommendation": "",
            "final_result": None,
            "error": None,
            "processing_time_ms": 0,
        }

        for node_name, node_fn in self.NODES:
            try:
                state = node_fn(state)
            except Exception as e:
                state["error"] = f"Agent error in node '{node_name}': {str(e)}"
                state = compile_result(state)
                break

        state["processing_time_ms"] = round((time.perf_counter() - start) * 1000, 2)
        if state.get("final_result"):
            state["final_result"]["processing_time_ms"] = state["processing_time_ms"]

        return state


# Singleton graph instance
credit_risk_graph = CreditRiskGraph()
