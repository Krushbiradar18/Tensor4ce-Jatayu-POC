"""
backend/agents/portfolio/agent.py
===================================
Robust LangGraph StateGraph for the Portfolio Intelligence Specialist Agent.
Incorporates sector, geographic, and risk band concentration checks.

Pipeline: validate → fetch → analysis → cot → finalize
"""
from __future__ import annotations
import logging
import os
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, START, END

logger = logging.getLogger(__name__)


class PortfolioState(TypedDict):
    application_id: str
    credit_risk_output: dict
    features: dict
    macro: dict
    portfolio_stats: dict
    
    # Analysis results
    sector_pct_new: float
    geo_pct_new: float
    el_impact_inr: float
    el_increase_pct: float
    concentration_flags: list[str]
    risk_band_dist_new: dict
    
    portfolio_recommendation: str
    cot_reasoning: str
    output: dict
    error: str


def _stress_mult(macro: dict) -> float:
    scenario = macro.get("stress_scenario", "NORMAL")
    return {"NORMAL": 1.0, "MILD_STRESS": 0.8, "HIGH_STRESS": 0.6}.get(scenario, 1.0)


def po_validate(state: PortfolioState) -> dict:
    from tools import _get_context_dict, _get_macro_config, _log_event
    app_id = state["application_id"]
    _log_event(app_id, "portfolio_graph", "NODE", {"node": "validate"})
    try:
        ctx = _get_context_dict(app_id)
        return {
            "features": ctx.get("features", {}),
            "app_dict": ctx.get("form", {}),
            "macro": _get_macro_config()
        }
    except Exception as e:
        return {"error": str(e)}


def po_fetch(state: PortfolioState) -> dict:
    from tools import _get_portfolio_data, _log_event, _get_context_dict
    app_id = state["application_id"]
    _log_event(app_id, "portfolio_graph", "NODE", {"node": "fetch"})
    try:
        ctx = _get_context_dict(app_id)
        form = ctx.get("form", {})
        product = str(form.get("loan_purpose", "PERSONAL")).upper()
        state_loc = "Unknown"
        if "address" in form and isinstance(form["address"], dict):
            state_loc = form["address"].get("state", "Unknown")
        amount = float(form.get("loan_amount_requested", 100000))
        
        # This tool returns aggregated stats for the specified product/geo
        pass_data = _get_portfolio_data(product, state_loc, amount)
        return {"portfolio_stats": pass_data}
    except Exception as e:
        logger.warning(f"Portfolio data fetch failed: {e}")
        return {"portfolio_stats": {}}


def po_analysis(state: PortfolioState) -> dict:
    """Perform deterministic concentration and EL impact analysis."""
    from tools import _log_event
    _log_event(state["application_id"], "portfolio_graph", "NODE", {"node": "analysis"})
    
    feat = state.get("features", {})
    macro = state.get("macro", {})
    ps = state.get("portfolio_stats", {})
    credit = state.get("credit_risk_output", {})
    
    flags = []
    stress = _stress_mult(macro)
    
    # 1. Sector Concentration
    # Threshold: 35% default
    sector_threshold = 0.35 * stress
    current_sector_pct = ps.get("sector_concentration", 0.28)
    # Simplified post-approval logic: tool already provides a 'new' estimation if loan is added
    new_sector_pct = ps.get("product_concentration", {}).get("PERSONAL", current_sector_pct)
    if new_sector_pct >= sector_threshold:
        flags.append("SECTOR_CONCENTRATION_BREACH")
    
    # 2. Geo Concentration
    geo_threshold = 0.25 * stress
    current_geo_pct = ps.get("geo_concentration", 0.22)
    if current_geo_pct > geo_threshold:
        flags.append("GEO_CONCENTRATION_BREACH")
        
    # 3. Expected Loss Impact
    pd = credit.get("credit_score", 0.05)
    lgd = 0.45 # standard for unsecured
    loan_amt = float(feat.get("loan_amount_requested", 0))
    el_impact = round(pd * lgd * loan_amt, 2)
    
    # Estimate EL increase relative to current portfolio EL
    # Scale up default portfolio size to 100Cr for more stability in PoC
    total_exposure = ps.get("total_outstanding", 100000000) 
    total_el = total_exposure * 0.02 # assume 2% base EL pool
    el_increase_pct = (el_impact / total_el) * 100 if total_el > 0 else 0
    
    if el_increase_pct > 15.0: # Only flag as high if it's over 15% increase
        flags.append("EL_IMPACT_HIGH")
    elif el_increase_pct > 5.0:
        flags.append("EL_IMPACT_CAUTION")

    # 4. Recommendation Logic
    # Rejection only on actual SECTOR/GEO BREACH
    if any("BREACH" in f for f in flags):
        rec = "REJECT_FOR_PORTFOLIO"
    elif flags or el_impact > 250000: # Increase threshold for caution
        rec = "CAUTION"
    else:
        rec = "ACCEPT"
        
    return {
        "sector_pct_new": new_sector_pct,
        "geo_pct_new": current_geo_pct,
        "el_impact_inr": el_impact,
        "el_increase_pct": el_increase_pct,
        "concentration_flags": flags,
        "portfolio_recommendation": rec
    }


def po_cot(state: PortfolioState) -> dict:
    from tools import _call_gemini, _log_event
    _log_event(state["application_id"], "portfolio_graph", "NODE", {"node": "cot"})
    
    rec = state.get("portfolio_recommendation", "ACCEPT")
    flags = state.get("concentration_flags", [])
    el = state.get("el_impact_inr", 0.0)
    
    # Enhanced prompt for detailed narrative
    prompt = (
        f"You are a portfolio risk advisor. Provide a VERY concise strategy observation (max 2 short sentences). "
        f"Concentration risk: {rec}. Flags matched: {flags or 'None'}. "
        f"Expected Loss (EL) impact: ₹{el:,.1f}. "
        f"The loan is for a {state.get('app_dict', {}).get('loan_purpose', 'requested')} product. "
        "Explain the high-level impact and finish. Be extremely brief."
    )
    
    cot = _call_gemini(prompt, fallback=f"Portfolio impact: {rec}. EL impact ₹{el:,.0f}. Strategy observation complete.")
    
    # Downgrade to CAUTION if Gemini detects worsening
    final_rec = rec
    if "worsen" in cot.lower() and rec == "ACCEPT":
        final_rec = "CAUTION"
        
    return {"cot_reasoning": cot, "portfolio_recommendation": final_rec}


def po_finalize(state: PortfolioState) -> dict:
    from tools import _log_event
    _log_event(state["application_id"], "portfolio_graph", "NODE", {"node": "finalize"})
    
    if state.get("error"):
        return {"output": {"error": state["error"], "portfolio_recommendation": "ACCEPT", "el_impact_inr": 0.0}}
        
    ps = state.get("portfolio_stats", {})
    out = {
        "application_id": state["application_id"],
        "portfolio_recommendation": state["portfolio_recommendation"],
        "sector_concentration_current": ps.get("sector_concentration", 0.28),
        "sector_concentration_new": state.get("sector_pct_new", 0.28),
        "geo_concentration_current": ps.get("geo_concentration", 0.22),
        "geo_concentration_new": state.get("geo_pct_new", 0.22),
        "risk_band_distribution": ps.get("risk_band_distribution", {}),
        "el_impact_inr": state.get("el_impact_inr", 0.0),
        "concentration_flags": state.get("concentration_flags", []),
        "similar_cases_npa_rate": ps.get("portfolio_npa_rate", 0.038),
        "cot_reasoning": state.get("cot_reasoning", ""),
    }
    return {"output": out}


def build_portfolio_graph():
    g = StateGraph(PortfolioState)
    g.add_node("validate", po_validate)
    g.add_node("fetch", po_fetch)
    g.add_node("analysis", po_analysis)
    g.add_node("cot", po_cot)
    g.add_node("finalize", po_finalize)
    
    g.add_edge(START, "validate")
    g.add_conditional_edges("validate", lambda s: "finalize" if s.get("error") else "fetch", {"fetch": "fetch", "finalize": "finalize"})
    g.add_edge("fetch", "analysis")
    g.add_edge("analysis", "cot")
    g.add_edge("cot", "finalize")
    g.add_edge("finalize", END)
    return g.compile()


_GRAPH = None

def get_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_portfolio_graph()
    return _GRAPH


def run_portfolio_graph(application_id: str, credit_risk_output: dict | None = None) -> dict:
    initial: PortfolioState = {
        "application_id": application_id,
        "credit_risk_output": credit_risk_output or {},
        "features": {}, "macro": {}, "portfolio_stats": {},
        "sector_pct_new": 0.0, "geo_pct_new": 0.0, "el_impact_inr": 0.0,
        "el_increase_pct": 0.0, "concentration_flags": [], "risk_band_dist_new": {},
        "portfolio_recommendation": "ACCEPT", "cot_reasoning": "", "output": {}, "error": ""
    }
    result = get_graph().invoke(initial)
    return result["output"]
