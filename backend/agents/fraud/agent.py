"""
backend/agents/fraud/agent.py
==============================
LangGraph StateGraph for the Fraud Detection Specialist Agent.

Pipeline: fetch → evaluate → [explain | finalize]
"""
from __future__ import annotations
import logging
from typing import TypedDict
from langgraph.graph import StateGraph, START, END

logger = logging.getLogger(__name__)


class FraudState(TypedDict):
    application_id: str
    features: dict
    app_dict: dict
    fraud_checks: dict
    explanation: str
    output: dict
    error: str


def fr_fetch(state: FraudState) -> dict:
    from tools import _get_features, _log_event, _get_context_dict
    _log_event(state["application_id"], "fraud_graph", "NODE", {"node": "fetch"})
    try:
        app_id = state["application_id"]
        features = _get_features(app_id)
        ctx = _get_context_dict(app_id)
        form = ctx.get("form", {})
        ip = ctx.get("ip_meta", {})
        addr = form.get("address", {})
        app_dict = {
            "application_id": app_id,
            "pan_number": form.get("pan_number", ""),
            "annual_income": form.get("annual_income", 0),
            "loan_amount_requested": form.get("loan_amount_requested", 0),
            "address": {"state": addr.get("state", ""), "city": addr.get("city", ""), "pincode": addr.get("pincode", "")},
            "ip_metadata": {"ip_address": ip.get("ip_address", ""), "form_fill_seconds": ip.get("form_fill_seconds", 300), "device_fingerprint": ip.get("device_fingerprint", ""), "user_agent": ip.get("user_agent", "")}
        }
        return {"features": features, "app_dict": app_dict}
    except Exception as e:
        return {"error": str(e)}


def fr_evaluate(state: FraudState) -> dict:
    """Node 2: Evaluate using IsolationForest ML model."""
    from tools import _run_fraud_checks, _log_event
    from agents.fraud.fraud_model import load_model, extract_features, predict, shap_explain
    
    _log_event(state["application_id"], "fraud_graph", "NODE", {"node": "evaluate"})
    app_dict = state.get("app_dict")
    if not app_dict:
        return {"fraud_checks": _run_fraud_checks(state["features"])}
        
    try:
        feat_vector = extract_features(app_dict)
        model = load_model()
        prob = predict(model, feat_vector)
        shap = shap_explain(model, feat_vector, top_k=3)
        
        if prob < 0.15: level = "CLEAN"
        elif prob < 0.35: level = "LOW_RISK"
        elif prob < 0.60: level = "SUSPICIOUS"
        else: level = "HIGH_RISK"
        
        checks = {
            "fraud_level": level,
            "fraud_probability": round(prob, 4),
            "fired_hard_rules": [],
            "fired_soft_signals": [f['feature'] for f in shap if f['direction'] == 'fraud'],
            "ip_risk_score": feat_vector.get("ip_risk_score", 0.0),
            "recommend_kyc_recheck": level in ("SUSPICIOUS", "HIGH_RISK"),
            "shap_top_features": shap
        }
    except Exception as e:
        logger.exception(f"Fraud ML failed, falling back: {e}")
        checks = _run_fraud_checks(state["features"])
        
    return {"fraud_checks": checks}


def fr_explain(state: FraudState) -> dict:
    """
    Node 3: Generates a Gemini explanation of the fraud signals detected.
    Now runs for ALL cases to provide detailed analysis as requested.
    """
    from tools import _call_gemini, _log_event
    _log_event(state["application_id"], "fraud_graph", "NODE", {"node": "explain"})
    c     = state["fraud_checks"]
    level = c.get("fraud_level", "CLEAN")
    rules = "; ".join(c.get("fired_hard_rules", []) + c.get("fired_soft_signals", [])[:2])
    
    if level == "CLEAN" and not rules:
        prompt = "You are a fraud analyst. The application shows normal behavioural patterns and no suspicious signals. Write 2 concise sentences confirming this for the credit officer."
        fallback = "Application shows normal behavioural patterns. No significant fraud signals detected."
    else:
        prompt = (f"You are a fraud analyst. In 2 concise sentences, explain to a credit officer why this "
                 f"application is rated {level}. Detected signals: {rules or 'none'}. Be specific.")
        fallback = f"Application flagged as {level}. Signals: {rules or 'none detected'}."
        
    explanation = _call_gemini(prompt, fallback=fallback)
    return {"explanation": explanation}


def fr_finalize(state: FraudState) -> dict:
    from tools import _log_event
    _log_event(state["application_id"], "fraud_graph", "NODE", {"node": "finalize"})
    c = state.get("fraud_checks", {})
    if state.get("error"):
        out = {"application_id": state["application_id"], "error": state["error"],
               "fraud_level": "SUSPICIOUS", "fraud_probability": 0.5, "identity_consistency": "LOW"}
    else:
        level = c.get("fraud_level", "CLEAN")
        # Logic for identity consistency
        hard_rules = c.get("fired_hard_rules", [])
        id_flags = [r for r in hard_rules if "IDENTITY" in r or "MISMATCH" in r or "PAN" in r]
        consistency = "HIGH" if not id_flags else ("MEDIUM" if len(id_flags) == 1 else "LOW")
        
        out = {
            "application_id":        state["application_id"],
            "fraud_level":           level,
            "fraud_probability":     c.get("fraud_probability", 0.0),
            "fired_hard_rules":      hard_rules,
            "fired_soft_signals":    c.get("fired_soft_signals", []),
            "ip_risk_score":         c.get("ip_risk_score", 0.0),
            "identity_consistency":  consistency,
            "identity_mismatch_flags": id_flags,
            "recommend_kyc_recheck": c.get("recommend_kyc_recheck", False),
            "explanation":           state.get("explanation", "Application shows normal behavioural patterns."),
        }
    return {"output": out}


def _fr_route_after_evaluate(state: FraudState) -> str:
    if state.get("error"):
        return "finalize"
    # Always run explain for detailed LLM analysis
    return "explain"


def build_fraud_graph():
    g = StateGraph(FraudState)
    g.add_node("fetch",    fr_fetch)
    g.add_node("evaluate", fr_evaluate)
    g.add_node("explain",  fr_explain)
    g.add_node("finalize", fr_finalize)
    g.add_edge(START, "fetch")
    g.add_conditional_edges("fetch", lambda s: "finalize" if s.get("error") else "evaluate",
                             {"evaluate": "evaluate", "finalize": "finalize"})
    g.add_conditional_edges("evaluate", _fr_route_after_evaluate,
                             {"explain": "explain", "finalize": "finalize"})
    g.add_edge("explain",  "finalize")
    g.add_edge("finalize", END)
    return g.compile()


_GRAPH = None

def get_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_fraud_graph()
    return _GRAPH


def run_fraud_graph(application_id: str) -> dict:
    """Public entry point: run the Fraud Detection LangGraph pipeline."""
    initial: FraudState = {
        "application_id": application_id,
        "features": {}, "app_dict": {}, "fraud_checks": {},
        "explanation": "", "output": {}, "error": "",
    }
    result = get_graph().invoke(initial)
    return result["output"]
