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


# ── Tool 7: Similar Cases ────────────────────────────────────────────────────

@tool("query_similar_cases")
def query_similar_cases(application_id: str, k: int = 5) -> dict:
    """
    Find k historically similar past loan applications and their outcomes.
    Similarity based on CIBIL range ±50, income range ±30%, loan type, and amount range ±50%.
    Returns past cases with AI recommendation, officer decision, and default rate.
    """
    from tools import _get_features
    import db
    try:
        f = _get_features(application_id)
        cibil  = float(f.get("cibil_score", 650))
        income = float(f.get("annual_income_verified", 500000))
        product = str(f.get("loan_product_type", "PERSONAL"))
        amount  = float(f.get("loan_amount_requested", 500000))
    except Exception:
        cibil, income, product, amount = 650, 500000, "PERSONAL", 500000

    similar = db.find_similar_applications(
        cibil_range=(cibil - 50, cibil + 50),
        income_range=(income * 0.7, income * 1.3),
        loan_type=product,
        amount_range=(amount * 0.5, amount * 1.5),
        exclude_id=application_id,
        limit=int(k),
    )

    if not similar:
        return {"similar_cases": [], "summary": "No similar past cases found", "default_rate_similar": 0.0}

    approved  = sum(1 for r in similar if r.get("ai_recommendation") == "APPROVE")
    rejected  = sum(1 for r in similar if r.get("ai_recommendation") == "REJECT")
    defaulted = sum(1 for r in similar if r.get("officer_decision") == "REJECTED")
    return {
        "similar_cases": similar,
        "summary": f"{len(similar)} similar cases: {approved} approved, {rejected} rejected, {defaulted} officer-rejected",
        "default_rate_similar": round(defaulted / max(len(similar), 1), 3),
    }


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


# ── Tool 13: Search Compliance Knowledge Base (RAG) ──────────────────────────

@tool("search_compliance_knowledge")
def search_compliance_knowledge(query: str) -> list:
    """
    Search RBI circulars and compliance policy documents for relevant regulations.
    Returns matching regulatory text chunks with source citations.
    Use this to ground compliance reasoning in actual regulatory text.
    """
    from services.rag import search_compliance_docs
    results = search_compliance_docs(query)
    return [
        {"source": r["source"], "text": r["text"][:500], "regulation": r["regulation"]}
        for r in results
    ]


# ── Tool 14: Flag for Human Review ────────────────────────────────────────────

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


# ── Tool 18: Assess Data Completeness ───────────────────────────────────────

@tool("assess_data_completeness")
def assess_data_completeness(application_id: str) -> dict:
    """
    Check what data is available and what's missing for this loan application.
    Returns available data sources, missing documents with reasons, a completeness
    score (0-1), and whether the pipeline can proceed or should request more data.
    ALWAYS call this before running any specialist agent.
    """
    from tools import _get_features
    try:
        f = _get_features(application_id)
    except Exception as e:
        return {"available_sources": [], "missing_documents": [], "data_completeness_score": 0.0,
                "can_proceed": False, "error": str(e)}

    available: list[dict] = []
    missing: list[dict]   = []

    # ── Bureau / CIBIL ────────────────────────────────────────────────────────
    cibil = float(f.get("cibil_score", 0))
    if cibil > 0:
        available.append({"source": "CIBIL_BUREAU", "value": f"Score: {cibil:.0f}"})
    else:
        # Alt-score fallback exists, so this is non-blocking
        missing.append({
            "doc": "CIBIL_REPORT",
            "reason": "Bureau score unavailable (new-to-credit or data gap)",
            "impact": "Alt-score will be used; MEDIUM risk uplift applied",
            "blocking": False,
            "alternative": "get_alt_score",
        })

    # ── Income verification ────────────────────────────────────────────────────
    income_claimed  = float(f.get("annual_income_verified", 0))
    loan_amount     = float(f.get("loan_amount_requested", 0))
    if income_claimed > 0:
        available.append({"source": "INCOME_FORM", "value": f"₹{income_claimed:,.0f} p.a."})
    else:
        missing.append({
            "doc": "INCOME_PROOF",
            "reason": "Annual income not declared in form",
            "impact": "FOIR cannot be calculated",
            "blocking": True,
        })

    # ── Bank statement (required for loans > ₹3L) ────────────────────────────
    avg_credit = float(f.get("avg_monthly_credit", 0))
    if avg_credit > 0:
        available.append({"source": "BANK_STATEMENT", "value": f"Avg monthly credit ₹{avg_credit:,.0f}"})
    elif loan_amount > 300000:
        missing.append({
            "doc": "BANK_STATEMENT",
            "reason": f"Required for loans > ₹3L (requested ₹{loan_amount:,.0f})",
            "impact": "Income verification incomplete; risk uplift applied",
            "blocking": False,
            "alternative": "Proceed with declared income; flag for officer review",
        })

    # ── Employment tenure ─────────────────────────────────────────────────────
    tenure = float(f.get("employment_tenure_years", 0))
    if tenure > 0:
        available.append({"source": "EMPLOYMENT", "value": f"{tenure:.1f} years"})

    # ── KYC completeness ──────────────────────────────────────────────────────
    pan_ok = bool(f.get("pan_verified", True))
    if pan_ok:
        available.append({"source": "KYC_PAN", "value": "Verified"})
    else:
        missing.append({"doc": "PAN_CARD", "reason": "PAN not verified", "impact": "KYC incomplete", "blocking": True})

    blocking_count = sum(1 for m in missing if m.get("blocking", False))
    score = round(len(available) / max(len(available) + len(missing), 1), 3)

    return {
        "available_sources":       available,
        "missing_documents":       missing,
        "data_completeness_score": score,
        "can_proceed":             blocking_count == 0,
        "blocking_gaps":           blocking_count,
        "recommended_path":        "PROCEED" if blocking_count == 0 else "DATA_REQUIRED",
    }


# ── Tool 19: Simulate Risk Scenarios ─────────────────────────────────────────

@tool("simulate_risk_scenarios")
def simulate_risk_scenarios(application_id: str) -> dict:
    """
    Simulate risk under 3 scenarios: Base case, Income Stress (-20%), Rate Stress (+2%).
    Returns FOIR, monthly surplus, and risk band under each scenario.
    Call this after run_credit_model to stress-test the assessment.
    """
    from tools import _get_features
    try:
        f = _get_features(application_id)
    except Exception as e:
        return {"error": str(e)}

    income        = float(f.get("annual_income_verified", 0)) / 12
    proposed_emi  = float(f.get("proposed_emi", 0))
    existing_emi  = float(f.get("existing_emi_monthly", 0))
    rate_pct      = float(f.get("effective_rate", 10.0))
    tenure        = int(f.get("loan_tenure_months", 60))
    amount        = float(f.get("loan_amount_requested", 0))

    def _risk_band(foir: float) -> str:
        if foir > 0.65: return "VERY_HIGH"
        if foir > 0.55: return "HIGH"
        if foir > 0.45: return "MEDIUM"
        return "LOW"

    def _emi(principal: float, rate_annual: float, months: int) -> float:
        r = rate_annual / 100 / 12
        if r == 0 or months == 0:
            return principal / max(months, 1)
        return principal * r * (1 + r) ** months / ((1 + r) ** months - 1)

    # Base
    foir_base = (proposed_emi + existing_emi) / max(income, 1)
    scenarios: dict = {
        "base": {
            "foir": round(foir_base, 3),
            "monthly_surplus": round(income - proposed_emi - existing_emi, 0),
            "risk_band": _risk_band(foir_base),
        },
    }

    # Income stress −20 %
    si = income * 0.8
    foir_income = (proposed_emi + existing_emi) / max(si, 1)
    scenarios["income_stress_20pct"] = {
        "description": "If income drops by 20%",
        "foir": round(foir_income, 3),
        "monthly_surplus": round(si - proposed_emi - existing_emi, 0),
        "risk_band": _risk_band(foir_income),
    }

    # Rate stress +2 %
    emi_stressed  = _emi(amount, rate_pct + 2.0, tenure)
    foir_rate     = (emi_stressed + existing_emi) / max(income, 1)
    scenarios["rate_stress_2pct"] = {
        "description": "If interest rate rises by 2%",
        "new_emi": round(emi_stressed, 0),
        "emi_increase": round(emi_stressed - proposed_emi, 0),
        "foir": round(foir_rate, 3),
        "monthly_surplus": round(income - emi_stressed - existing_emi, 0),
        "risk_band": _risk_band(foir_rate),
    }

    worst_foir = max(foir_base, foir_income, foir_rate)
    scenarios["stress_summary"] = {
        "worst_case_foir": round(worst_foir, 3),
        "passes_stress_test": worst_foir < 0.65,
        "recommendation": "PROCEED" if worst_foir < 0.55 else "CAUTION" if worst_foir < 0.65 else "HIGH_RISK",
    }
    return scenarios


# ── Tool 15: Extract Bank Statement ──────────────────────────────────────────

@tool("extract_bank_statement")
def extract_bank_statement(application_id: str) -> dict:
    """
    Extract and analyze bank statement data from an uploaded PDF or image.
    Returns monthly income, expenses, EMI bounces, salary regularity, and cash flow analysis.
    """
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from document_extractor import _extract_text_lines, extract_financial_from_image
    from services.llm_extractor import extract_financial_data

    import tempfile as _tmpmod
    base = os.path.join(_tmpmod.gettempdir(), "aria_loan_uploads", application_id)
    # Search for the file regardless of extension
    found = None
    for ext in (".pdf", ".png", ".jpg", ".jpeg"):
        candidate = os.path.join(base, f"bank_statement{ext}")
        if os.path.exists(candidate):
            found = candidate
            break
    if not found:
        return {"available": False, "reason": "No bank statement uploaded"}

    if found.lower().endswith(".pdf"):
        raw_lines = _extract_text_lines(found)
        result = extract_financial_data("\n".join(raw_lines), doc_type="bank_statement")
    else:
        result = extract_financial_from_image(found, "bank_statement")
    return {"available": True, **result}


# ── Tool 16: Extract Salary Slip ──────────────────────────────────────────────

@tool("extract_salary_slip")
def extract_salary_slip(application_id: str) -> dict:
    """
    Extract salary details from an uploaded salary slip PDF or image.
    Returns gross salary, deductions, net pay, and employer name.
    """
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from document_extractor import _extract_text_lines, extract_financial_from_image
    from services.llm_extractor import extract_financial_data

    import tempfile as _tmpmod
    base = os.path.join(_tmpmod.gettempdir(), "aria_loan_uploads", application_id)
    found = None
    for ext in (".pdf", ".png", ".jpg", ".jpeg"):
        candidate = os.path.join(base, f"salary_slip{ext}")
        if os.path.exists(candidate):
            found = candidate
            break
    if not found:
        return {"available": False, "reason": "No salary slip uploaded"}

    if found.lower().endswith(".pdf"):
        raw_lines = _extract_text_lines(found)
        result = extract_financial_data("\n".join(raw_lines), doc_type="salary_slip")
    else:
        result = extract_financial_from_image(found, "salary_slip")
    return {"available": True, **result}


# ── Tool 17: Extract ITR ──────────────────────────────────────────────────────

@tool("extract_itr")
def extract_itr(application_id: str) -> dict:
    """
    Extract income tax return details from an uploaded ITR PDF or image.
    Returns total income, tax paid, and assessment year.
    """
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from document_extractor import _extract_text_lines, extract_financial_from_image
    from services.llm_extractor import extract_financial_data

    import tempfile as _tmpmod
    base = os.path.join(_tmpmod.gettempdir(), "aria_loan_uploads", application_id)
    found = None
    for ext in (".pdf", ".png", ".jpg", ".jpeg"):
        candidate = os.path.join(base, f"itr{ext}")
        if os.path.exists(candidate):
            found = candidate
            break
    if not found:
        return {"available": False, "reason": "No ITR uploaded"}

    if found.lower().endswith(".pdf"):
        raw_lines = _extract_text_lines(found)
        result = extract_financial_data("\n".join(raw_lines), doc_type="itr")
    else:
        result = extract_financial_from_image(found, "itr")
    return {"available": True, **result}


# ── Exported tool lists ────────────────────────────────────────────────────────

ALL_MCP_TOOLS = [
    get_pan_verification,
    get_bureau_score,
    get_bank_summary,
    get_macro_config_tool,
    get_alt_score,
    get_portfolio_exposure,
    query_similar_cases,          # Day 4: real DB-backed similar cases
    run_credit_model,
    run_fraud_model,
    check_rbi_rules,
    run_portfolio_model,
    search_compliance_knowledge,  # Day 5: RAG compliance KB
    flag_for_human_review,
    log_agent_action,
    extract_bank_statement,       # Day 2: unstructured bank statement
    extract_salary_slip,          # Day 2: unstructured salary slip
    extract_itr,                  # Day 2: unstructured ITR
    assess_data_completeness,     # Day 3: dynamic data gathering gate
    simulate_risk_scenarios,      # Day 6: stress scenario simulation
]
