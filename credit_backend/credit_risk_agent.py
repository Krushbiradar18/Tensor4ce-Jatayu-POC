"""
LangGraph Credit Risk Agent
============================
State machine that orchestrates the credit risk assessment pipeline using
the real LangGraph StateGraph with conditional edges:

  [START]
    │
    ▼
  fetch_user_profile    ← Fetch user data from DB by PAN
    │ (error? → compile_result)
    ▼
  validate_inputs       ← Validate all required fields + DTI check
    │ (errors? → compile_result)
    ▼
  run_ml_scoring        ← Run ML model + SHAP approximation
    │ (error? → compile_result)
    ▼
  generate_explanation  ← Call Gemini LLM for human-readable explanation
    │
    ▼
  compile_result        ← Assemble final JSON response
    │
    ▼
  [END]
"""

from typing import TypedDict, Optional, Dict, Any, List
import math

from langgraph.graph import StateGraph, END

from db_repository import get_user_by_pan
from inference import inference_service
from llm_service import (
    build_explanation_prompt,
    get_llm_explanation,
    generate_recommendation,
)


# ─── Agent State ─────────────────────────────────────────────────────────────
# LangGraph uses this TypedDict as its state schema.  Each node receives the
# full state and returns a *partial* dict containing only the keys it updates;
# LangGraph merges those updates back into the shared state automatically.

class AgentState(TypedDict):
    # ── Inputs ────────────────────────────────────────────────────────────────
    pan_number: str
    loan_amount: float
    loan_type: str
    loan_tenure_months: int
    declared_monthly_income: Optional[float]

    # ── Intermediate ──────────────────────────────────────────────────────────
    user_profile: Optional[Dict[str, Any]]
    merged_data: Optional[Dict[str, Any]]
    validation_errors: List[str]

    # ── ML outputs ────────────────────────────────────────────────────────────
    ml_result: Optional[Dict[str, Any]]
    risk_factors: Optional[List[Dict]]
    positive_factors: Optional[List[Dict]]

    # ── LLM outputs ───────────────────────────────────────────────────────────
    llm_explanation: str
    recommendation: str

    # ── Final ─────────────────────────────────────────────────────────────────
    final_result: Optional[Dict[str, Any]]
    error: Optional[str]
    processing_time_ms: float


# ─── Node Functions ──────────────────────────────────────────────────────────
# Each node receives the full AgentState and returns ONLY the keys it changes.
# LangGraph merges those updates into the shared state via LastValue channels.

def fetch_user_profile(state: AgentState) -> dict:
    """Node 1: Fetch user financial profile from database by PAN."""
    pan = state["pan_number"].strip().upper()
    profile = get_user_by_pan(pan)

    if not profile:
        return {
            "error": f"User with PAN '{pan}' not found in database.",
            "user_profile": None,
        }
    return {"user_profile": profile}


def validate_inputs(state: AgentState) -> dict:
    """Node 2: Validate required fields, DTI feasibility, merge income override."""
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

    tenure = state.get("loan_tenure_months", 12)
    if income > 0 and tenure > 0:
        estimated_emi = loan_amount / tenure
        dti = (estimated_emi / income) * 100
        if dti > 70:
            errors.append(
                f"Debt-to-income ratio too high ({dti:.1f}%). Max recommended: 70%."
            )

    merged = dict(profile)
    if state.get("declared_monthly_income"):
        merged["NETMONTHLYINCOME"] = state["declared_monthly_income"]

    return {"validation_errors": errors, "merged_data": merged}


def run_ml_scoring(state: AgentState) -> dict:
    """Node 3: Run RandomForest ML model + SHAP-approximated feature contributions."""
    try:
        ml_result = inference_service.predict(state["merged_data"])
        risk_factors, positive_factors = inference_service.get_top_factors(
            ml_result["feature_contributions"], n=6
        )
        return {
            "ml_result": ml_result,
            "risk_factors": risk_factors,
            "positive_factors": positive_factors,
        }
    except Exception as exc:
        return {"error": f"ML scoring failed: {exc}"}


def generate_explanation(state: AgentState) -> dict:
    """Node 4: Call Gemini LLM to produce a narrative credit risk explanation."""
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

    return {"llm_explanation": llm_text, "recommendation": recommendation}


def compile_result(state: AgentState) -> dict:
    """Node 5: Assemble the final structured JSON response."""
    if state.get("error"):
        return {"final_result": {"error": state["error"]}}

    if state.get("validation_errors"):
        return {"final_result": {"validation_errors": state["validation_errors"]}}

    ml = state["ml_result"]
    profile = state["merged_data"]
    loan_amount = state["loan_amount"]
    tenure = state["loan_tenure_months"]

    # EMI at 10% annual compound interest
    monthly_rate = 0.10 / 12
    emi = (loan_amount * monthly_rate * (1 + monthly_rate) ** tenure) / \
          ((1 + monthly_rate) ** tenure - 1)

    income = profile.get("NETMONTHLYINCOME", 1)
    dti = round((emi / income) * 100, 2) if income > 0 else 0.0

    # Attach actual profile value to each SHAP factor
    risk_factors = state["risk_factors"]
    positive_factors = state["positive_factors"]
    for factor in risk_factors:
        raw_feat = factor["feature"].lower().replace(" ", "_")
        factor["value"] = profile.get(raw_feat, profile.get(raw_feat + "_enc", "N/A"))
    for factor in positive_factors:
        raw_feat = factor["feature"].lower().replace(" ", "_")
        factor["value"] = profile.get(raw_feat, profile.get(raw_feat + "_enc", "N/A"))

    return {
        "final_result": {
            # Core risk assessment
            "risk_score": ml["risk_score"],
            "risk_category": ml["risk_category"],
            "approved_flag": ml["approved_flag"],
            "confidence": ml["confidence"],
            "class_probabilities": ml["class_probabilities"],

            # Applicant identity
            "applicant_name": profile.get("name", "N/A"),
            "pan_number": state["pan_number"].upper(),

            # Loan details
            "loan_amount": loan_amount,
            "loan_type": state["loan_type"],
            "loan_tenure_months": tenure,
            "emi_estimate": round(emi, 2),

            # Explainability
            "top_risk_factors": risk_factors,
            "top_positive_factors": positive_factors,
            "llm_explanation": state.get("llm_explanation", ""),
            "recommendation": state.get("recommendation", ""),

            # Financial metrics
            "credit_score": profile.get("Credit_Score", 0),
            "debt_to_income_ratio": dti,
            "utilization_summary": {
                "CC_utilization": profile.get("CC_utilization", 0),
                "PL_utilization": profile.get("PL_utilization", 0),
                "max_unsec_exposure_inPct": profile.get("max_unsec_exposure_inPct", 0),
            },
            # Populated by main.py after invoke() returns
            "processing_time_ms": 0,
        }
    }


# ─── Routing / Conditional Edge Functions ────────────────────────────────────

def _route_after_fetch(state: AgentState) -> str:
    """If PAN lookup failed route directly to compile_result, else validate."""
    return "compile_result" if state.get("error") else "validate_inputs"


def _route_after_validate(state: AgentState) -> str:
    """If validation produced errors route to compile_result, else run ML."""
    return "compile_result" if state.get("validation_errors") else "run_ml_scoring"


def _route_after_ml(state: AgentState) -> str:
    """If ML scoring raised an exception route to compile_result, else explain."""
    return "compile_result" if state.get("error") else "generate_explanation"


# ─── Build & Compile LangGraph StateGraph ────────────────────────────────────

def _build_graph():
    """Construct the LangGraph StateGraph and return its compiled form."""
    workflow = StateGraph(AgentState)

    # Register nodes
    workflow.add_node("fetch_user_profile", fetch_user_profile)
    workflow.add_node("validate_inputs", validate_inputs)
    workflow.add_node("run_ml_scoring", run_ml_scoring)
    workflow.add_node("generate_explanation", generate_explanation)
    workflow.add_node("compile_result", compile_result)

    # Entry point
    workflow.set_entry_point("fetch_user_profile")

    # Conditional: PAN found?
    workflow.add_conditional_edges(
        "fetch_user_profile",
        _route_after_fetch,
        {
            "validate_inputs": "validate_inputs",
            "compile_result": "compile_result",
        },
    )

    # Conditional: all fields valid + DTI OK?
    workflow.add_conditional_edges(
        "validate_inputs",
        _route_after_validate,
        {
            "run_ml_scoring": "run_ml_scoring",
            "compile_result": "compile_result",
        },
    )

    # Conditional: ML succeeded?
    workflow.add_conditional_edges(
        "run_ml_scoring",
        _route_after_ml,
        {
            "generate_explanation": "generate_explanation",
            "compile_result": "compile_result",
        },
    )

    # Linear tail: explanation → compile → END
    workflow.add_edge("generate_explanation", "compile_result")
    workflow.add_edge("compile_result", END)

    return workflow.compile()


# Singleton compiled graph — imported by main.py
credit_risk_graph = _build_graph()
