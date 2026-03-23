"""
backend/agents/credit_risk/agent.py
=====================================
LangGraph StateGraph for the Credit Risk Specialist Agent.

This module contains the full LangGraph pipeline:
  fetch → [score | alt_score] → narrative → finalize

It delegates heavy lifting to the shared tool functions.
"""
from __future__ import annotations
import logging
from typing import TypedDict
from langgraph.graph import StateGraph, START, END

logger = logging.getLogger(__name__)


# ── State ──────────────────────────────────────────────────────────────────────

class CreditRiskState(TypedDict):
    application_id: str
    features: dict
    macro: dict
    bureau_available: bool
    score_result: dict
    officer_narrative: str
    customer_narrative: str
    output: dict
    error: str


# ── Nodes ──────────────────────────────────────────────────────────────────────

def cr_fetch(state: CreditRiskState) -> dict:
    """Node 1: Load features and macro config from the DIL store."""
    from tools import _get_features, _get_macro_config, _log_event, _get_context_dict
    app_id = state["application_id"]
    _log_event(app_id, "credit_risk_graph", "NODE", {"node": "fetch"})
    try:
        features = _get_features(app_id)
        macro    = _get_macro_config()
        ctx_dict = _get_context_dict(app_id)
        features["pan_number"] = ctx_dict["form"]["pan_number"]
        return {
            "features":         features,
            "macro":            macro,
            "bureau_available": not features.get("bureau_unavailable", False),
        }
    except Exception as e:
        return {"error": str(e)}


def cr_score(state: CreditRiskState) -> dict:
    """Node 2a: Compute PD using XGBoost ML model + macro overlay."""
    from tools import _log_event
    from dataset_loader import get_merged_customer_profile
    from agents.credit_risk.inference import inference_service
    _log_event(state["application_id"], "credit_risk_graph", "NODE", {"node": "score"})
    
    pan = state["features"].get("pan_number", "")
    profile = get_merged_customer_profile(pan) if pan else None
    
    if not profile:
        from tools import _compute_pd
        return {"score_result": _compute_pd(state["features"], state["macro"])}
        
    pred = inference_service.predict(profile)
    risk_score = pred.get("risk_score", 5.0)
    risk_category = pred.get("risk_category", "MEDIUM")
    
    band_map = {"Low Risk": "LOW", "Medium-Low Risk": "MEDIUM", "Medium-High Risk": "HIGH", "High Risk": "VERY_HIGH"}
    rb = band_map.get(risk_category, "MEDIUM")
    
    top_risk, top_pos = inference_service.get_top_factors(pred["feature_contributions"])
    factors = []
    for f in top_risk[:3]:
        factors.append({"feature": f["feature"], "value": 0, "shap_value": f["contribution"], "human_label": f["description"], "direction": "NEGATIVE"})
    for f in top_pos[:2]:
        factors.append({"feature": f["feature"], "value": 0, "shap_value": -f["contribution"], "human_label": f["description"], "direction": "POSITIVE"})
        
    result = {
        "pd": round(max(0.0, min(1.0, risk_score / 100.0)), 6),
        "risk_band": rb,
        "shap_factors": factors,
        "macro_adjusted": False,
        "stress_scenario": state["macro"].get("stress_scenario", "NORMAL"),
        "alt_scoring_used": False,
    }
    return {"score_result": result}


def cr_alt_score(state: CreditRiskState) -> dict:
    """
    Node 2b: CONDITIONAL — runs when CIBIL is unavailable.
    Uses alternative data (UPI, utility payments, digital footprint).
    """
    from tools import _log_event
    _log_event(state["application_id"], "credit_risk_graph", "NODE", {"node": "alt_score"})
    f = state["features"]
    alt_composite = f.get("alt_credit_composite", 0.5)
    upi_reg       = f.get("upi_transaction_regularity", 0.5)
    utility_score = f.get("utility_payment_score", 50) / 100

    alt_pd = 0.12 - (alt_composite * 0.05 + upi_reg * 0.03 + utility_score * 0.02)
    alt_pd = max(0.05, min(0.35, alt_pd))
    rb = "MEDIUM" if alt_pd < 0.08 else "HIGH"

    result = {
        "pd": round(alt_pd, 6),
        "risk_band": rb,
        "shap_factors": [
            {"feature": "alt_credit_composite", "value": alt_composite,
             "shap_value": round(-alt_composite * 0.05, 5),
             "human_label": "Alternative Credit Score", "direction": "POSITIVE"},
            {"feature": "upi_transaction_regularity", "value": upi_reg,
             "shap_value": round(-upi_reg * 0.03, 5),
             "human_label": "UPI Payment Regularity", "direction": "POSITIVE"},
        ],
        "macro_adjusted": False,
        "stress_scenario": state["macro"].get("stress_scenario", "NORMAL"),
        "alt_scoring_used": True,
    }
    return {"score_result": result}


def cr_narrative(state: CreditRiskState) -> dict:
    """Node 3: Generate officer and customer narratives via Gemini (or fallback)."""
    from tools import _call_gemini, _log_event
    _log_event(state["application_id"], "credit_risk_graph", "NODE", {"node": "narrative"})
    sr  = state.get("score_result", {})
    f   = state["features"]
    rb  = sr.get("risk_band", "MEDIUM")
    pd  = sr.get("pd", 0.05)
    cibil     = f.get("cibil_score", 0)
    foir      = f.get("foir", 0)
    income    = f.get("annual_income_verified", 0)
    stress    = sr.get("stress_scenario", "NORMAL")
    alt_used  = sr.get("alt_scoring_used", False)

    officer_fb = (
        f"{'[ALT SCORING — no CIBIL bureau data] ' if alt_used else ''}"
        f"Risk band: {rb}, PD: {pd:.2%}, CIBIL: {cibil:.0f}, "
        f"FOIR: {foir:.1%}{'  [MACRO STRESS APPLIED: ' + stress + ']' if sr.get('macro_adjusted') else ''}. "
        f"Net monthly surplus: ₹{f.get('net_monthly_surplus', 0):,.0f}."
    )
    customer_fb = (
        "Your financial profile has been assessed. Our team will review the results."
        if rb in ("HIGH", "VERY_HIGH")
        else "Your application shows a strong repayment profile based on your income and credit history."
    )

    officer_narrative = _call_gemini(
        f"You are a senior credit analyst. Write 2 concise sentences for a credit officer "
        f"summarising this {'no-CIBIL alternative-scored ' if alt_used else ''}{rb.lower().replace('_',' ')} risk application. "
        f"CIBIL={cibil:.0f}, FOIR={foir:.1%}, PD={pd:.2%}, income ₹{income:,.0f}/yr. "
        f"{'Macro stress scenario ' + stress + ' was applied. ' if sr.get('macro_adjusted') else ''}"
        f"Be specific and factual. No mention of AI, XGBoost, or SHAP.",
        fallback=officer_fb
    )
    customer_narrative = _call_gemini(
        f"Write one sentence for a loan applicant explaining their credit assessment result "
        f"({rb.lower().replace('_',' ')} risk category). Simple language, no scores, no AI mention.",
        fallback=customer_fb
    )
    return {"officer_narrative": officer_narrative, "customer_narrative": customer_narrative}


def cr_finalize(state: CreditRiskState) -> dict:
    """Node 4: Assemble the final CreditRiskOutput dict."""
    from tools import _log_event
    _log_event(state["application_id"], "credit_risk_graph", "NODE", {"node": "finalize"})
    sr = state.get("score_result", {})
    f  = state.get("features", {})
    if state.get("error"):
        out = {"application_id": state["application_id"], "error": state["error"],
               "credit_score": 0.5, "risk_band": "HIGH"}
    else:
        out = {
            "application_id":         state["application_id"],
            "credit_score":           sr.get("pd", 0.05),
            "risk_band":              sr.get("risk_band", "MEDIUM"),
            "foir":                   f.get("foir", 0),
            "dti_ratio":              f.get("dti_ratio", 0),
            "ltv_ratio":              f.get("ltv_ratio", 0),
            "net_monthly_surplus":    f.get("net_monthly_surplus", 0),
            "proposed_emi":           f.get("proposed_emi", 0),
            "macro_adjusted":         sr.get("macro_adjusted", False),
            "stress_scenario":        sr.get("stress_scenario", "NORMAL"),
            "alternative_score_used": sr.get("alt_scoring_used", not state.get("bureau_available", True)),
            "top_factors":            sr.get("shap_factors", []),
            "officer_narrative":      state.get("officer_narrative", ""),
            "customer_narrative":     state.get("customer_narrative", ""),
        }
    return {"output": out}


# ── Routing ────────────────────────────────────────────────────────────────────

def _cr_route_after_fetch(state: CreditRiskState) -> str:
    if state.get("error"):
        return "finalize"
    return "score" if state.get("bureau_available", True) else "alt_score"


# ── Graph builder ──────────────────────────────────────────────────────────────

def build_credit_risk_graph():
    g = StateGraph(CreditRiskState)
    g.add_node("fetch",     cr_fetch)
    g.add_node("score",     cr_score)
    g.add_node("alt_score", cr_alt_score)
    g.add_node("narrative", cr_narrative)
    g.add_node("finalize",  cr_finalize)
    g.add_edge(START, "fetch")
    g.add_conditional_edges("fetch", _cr_route_after_fetch,
                             {"score": "score", "alt_score": "alt_score", "finalize": "finalize"})
    g.add_edge("score",     "narrative")
    g.add_edge("alt_score", "narrative")
    g.add_edge("narrative", "finalize")
    g.add_edge("finalize",  END)
    return g.compile()


_GRAPH = None

def get_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_credit_risk_graph()
    return _GRAPH


def run_credit_risk_graph(application_id: str) -> dict:
    """Public entry point: run the Credit Risk LangGraph pipeline."""
    initial: CreditRiskState = {
        "application_id": application_id,
        "features": {}, "macro": {}, "bureau_available": True,
        "score_result": {}, "officer_narrative": "", "customer_narrative": "",
        "output": {}, "error": "",
    }
    result = get_graph().invoke(initial)
    return result["output"]
