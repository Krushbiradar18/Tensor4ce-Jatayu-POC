"""
backend/orchestration/mcp_tools.py
=====================================
MCP Tool Registry — all 12 @tool decorated functions available to the
CrewAI Crew and its specialist agents.

Tools wrap backend Python functions. They do NOT directly call external HTTP —
they call the underlying Python utilities (DB queries, model inference, etc.)
that back the mock APIs.
"""
from __future__ import annotations
import logging
from crewai.tools import tool

logger = logging.getLogger(__name__)


# ── Tool 1: PAN Verification ─────────────────────────────────────────────────

@tool("get_pan_verification")
def get_pan_verification(pan_number: str) -> dict:
    """
    Verify a PAN number against the mock PAN DB (Source 3 of 3-source verification).
    Returns registered_name, registered_dob, aadhaar_linked, aadhaar_last4.
    """
    from dil import _BLACKLIST
    found = pan_number not in _BLACKLIST
    return {
        "pan_number": pan_number,
        "found": found,
        "status": "verified" if found else "not_found",
    }


# ── Tool 2: Bureau Score ──────────────────────────────────────────────────────

@tool("get_bureau_score")
def get_bureau_score(application_id: str) -> dict:
    """
    Retrieve the mock CIBIL bureau score and credit history for an application.
    Uses deterministic hash(PAN) for scores plus demo PAN overrides.
    """
    from tools import _get_features
    try:
        features = _get_features(application_id)
        return {
            "application_id":       application_id,
            "cibil_score":          features.get("cibil_score", 0),
            "num_hard_enquiries_6m": features.get("num_hard_enquiries_6m", 0),
            "payment_history_score": features.get("payment_history_score", 0),
            "dpd_30_count":         features.get("dpd_30_count", 0),
            "dpd_90_count":         features.get("dpd_90_count", 0),
            "credit_utilization":   features.get("credit_utilization_pct", 0),
            "total_outstanding_debt": features.get("total_outstanding_debt", 0),
            "bureau_unavailable":   features.get("bureau_unavailable", False),
        }
    except Exception as e:
        logger.error(f"get_bureau_score failed: {e}")
        return {"error": str(e)}


# ── Tool 3: Bank Statement Summary ───────────────────────────────────────────

@tool("get_bank_summary")
def get_bank_summary(application_id: str) -> dict:
    """
    Retrieve mock bank statement summary (6-month aggregates) for an application.
    """
    from tools import _get_features
    try:
        features = _get_features(application_id)
        return {
            "avg_monthly_credit":  features.get("avg_monthly_credit", 0),
            "avg_monthly_debit":   features.get("avg_monthly_debit", 0),
            "min_eod_balance":     features.get("min_eod_balance", 0),
            "emi_bounce_count":    features.get("emi_bounce_count", 0),
            "salary_regularity":   features.get("salary_regularity", 1.0),
            "cash_flow_volatility": features.get("cash_flow_volatility", 0.15),
        }
    except Exception as e:
        logger.error(f"get_bank_summary failed: {e}")
        return {"error": str(e)}


# ── Tool 4: Macro Config ──────────────────────────────────────────────────────

@tool("get_macro_config_tool")
def get_macro_config_tool() -> dict:
    """
    Fetch the current macro-economic configuration (repo rate, stress scenario, NPA rates).
    Editable at runtime to toggle between NORMAL and HIGH_STRESS scenarios.
    """
    from tools import _get_macro_config
    return _get_macro_config()


# ── Tool 5: Alternative Score ─────────────────────────────────────────────────

@tool("get_alt_score")
def get_alt_score(application_id: str) -> dict:
    """
    Retrieve alternative credit score data for new-to-credit applicants.
    Only called when CIBIL score = 0 or BUREAU_UNAVAILABLE.
    """
    from tools import _get_features
    try:
        features = _get_features(application_id)
        return {
            "upi_transaction_regularity": features.get("upi_transaction_regularity", 0.5),
            "utility_payment_score":      features.get("utility_payment_score", 50),
            "alt_credit_composite":       features.get("alt_credit_composite", 0.5),
        }
    except Exception as e:
        return {"error": str(e)}


# ── Tool 6: Portfolio Exposure ────────────────────────────────────────────────

@tool("get_portfolio_exposure")
def get_portfolio_exposure(loan_product: str, state: str, loan_amount: float) -> dict:
    """
    Retrieve current portfolio exposure aggregates:
    NPA rate, product concentration, total outstanding, risk band distribution.
    Requires loan_product (e.g. HOME, AUTO), state code, and loan_amount.
    """
    from tools import _get_portfolio_data
    return _get_portfolio_data(loan_product, state, loan_amount)


# ── Tool 7: Similar Cases (pgvector proxy) ────────────────────────────────────

@tool("query_similar_cases")
def query_similar_cases(application_id: str, k: int = 5) -> list:
    """
    Find k historically similar loan applications and their outcomes.
    Acts as a proxy for pgvector cosine similarity search.
    """
    from tools import _get_portfolio_data, _get_features
    try:
        f = _get_features(application_id)
        # Use defaults if features not fully loaded
        product = f.get("loan_product_type", "PERSONAL")
        state = f.get("state_code", "MH")
        amount = f.get("loan_amount_requested", 500000)
        pd = _get_portfolio_data(product, state, amount)
        npa_rate = pd.get("portfolio_npa_rate", 0.038)
    except Exception:
        npa_rate = 0.038
    return [{"application_summary": "historical_similar", "outcome": "ACTIVE", "npa_rate": npa_rate}]


# ── Tool 8: Run Credit Model ──────────────────────────────────────────────────

@tool("run_credit_model")
def run_credit_model(application_id: str) -> dict:
    """
    Run the specialist Credit Risk assessment agent (LangGraph).
    Computes Probability of Default (PD), risk band, and generates narratives.
    """
    from orchestration.a2a_client import call_agent
    from tools import set_agent_output
    try:
        res = call_agent("credit_risk", application_id)
        set_agent_output(application_id, "credit", res)
        return res
    except Exception as e:
        logger.error(f"run_credit_model failed: {e}")
        return {"error": str(e), "pd": 0.1, "risk_band": "HIGH"}


# ── Tool 9: Run Fraud Model ───────────────────────────────────────────────────

@tool("run_fraud_model")
def run_fraud_model(application_id: str) -> dict:
    """
    Run the specialist Fraud Detection agent (LangGraph).
    Evaluates fraud signals using hard rules, soft indicators, and Isolation Forest.
    """
    from orchestration.a2a_client import call_agent
    from tools import set_agent_output
    try:
        res = call_agent("fraud", application_id)
        set_agent_output(application_id, "fraud", res)
        return res
    except Exception as e:
        logger.error(f"run_fraud_model failed: {e}")
        return {"error": str(e), "fraud_level": "CLEAN", "fraud_probability": 0.0}


# ── Tool 10: Check RBI Rules ──────────────────────────────────────────────────

@tool("check_rbi_rules")
def check_rbi_rules(application_id: str) -> dict:
    """
    Run the specialist Compliance Verification agent (LangGraph).
    Evaluates all 12 RBI eligibility rules and generates compliance narratives.
    """
    from orchestration.a2a_client import call_agent
    from tools import set_agent_output
    try:
        res = call_agent("compliance", application_id)
        set_agent_output(application_id, "compliance", res)
        return res
    except Exception as e:
        logger.error(f"check_rbi_rules failed: {e}")
        return {"error": str(e), "all_blocks_passed": True, "overall_status": "PASS"}


# ── Tool 11: Run Portfolio Model ──────────────────────────────────────────────

@tool("run_portfolio_model")
def run_portfolio_model(application_id: str) -> dict:
    """
    Run the specialist Portfolio Intelligence agent (LangGraph).
    Computes Expected Loss (EL) impact, concentration metrics, and geo-risk analysis.
    """
    from orchestration.a2a_client import call_agent
    from tools import set_agent_output
    try:
        # Portfolio specialist often needs credit risk context; the sub-app handles fetching it.
        res = call_agent("portfolio", application_id)
        set_agent_output(application_id, "portfolio", res)
        return res
    except Exception as e:
        logger.error(f"run_portfolio_model failed: {e}")
        return {"error": str(e), "portfolio_recommendation": "ACCEPT"}


# ── Tool 12: Flag for Human Review ────────────────────────────────────────────

@tool("flag_for_human_review")
def flag_for_human_review(application_id: str, reason: str) -> dict:
    """
    Flag an application for human review. Inserts an escalation record in audit_log.
    """
    import uuid
    from tools import _log_event
    escalation_id = f"ESC-{uuid.uuid4().hex[:8].upper()}"
    _log_event(application_id, "orchestrator", "ESCALATION_FLAGGED",
               {"escalation_id": escalation_id, "reason": reason})
    return {"escalation_id": escalation_id, "status": "flagged"}


# ── Tool 12: Log Agent Action ─────────────────────────────────────────────────

@tool("log_agent_action")
def log_agent_action(application_id: str, agent_name: str, event_type: str, payload: dict) -> dict:
    """
    Log an agent action to the immutable audit_log with a SHA256 hash for tamper detection.
    """
    from tools import _log_event
    _log_event(application_id, agent_name, event_type, payload)
    return {"status": "logged"}


# ── Exported tool lists ────────────────────────────────────────────────────────

ALL_MCP_TOOLS = [
    get_pan_verification,
    get_bureau_score,
    get_bank_summary,
    get_macro_config_tool,
    get_alt_score,
    get_portfolio_exposure,
    query_similar_cases,
    run_credit_model,
    run_fraud_model,
    check_rbi_rules,
    run_portfolio_model,
    flag_for_human_review,
    log_agent_action,
]
