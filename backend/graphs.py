"""
graphs.py — 4 LangGraph StateGraphs
=====================================
Each graph is a proper LangGraph StateGraph with:
  - TypedDict state
  - Multiple nodes (4-5 each)
  - Conditional edges for branching logic
  - Nodes that call MCP data tools directly
  - Final node that writes typed output to the A2A store

Graph patterns:
  Credit Risk:  fetch → [score | alt_score] → macro_overlay → narrative → finalize
  Fraud:        fetch → evaluate → score → [explain | skip] → finalize
  Compliance:   fetch → run_rules → [cot | skip] → finalize
  Portfolio:    fetch → concentration → el_calc → cot → finalize
"""
from __future__ import annotations
import json, logging, time
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, START, END

logger = logging.getLogger(__name__)

# Import the data tool functions (plain Python, no @tool wrapper needed here)
from tools import (
    _get_features, _get_context_dict, _get_macro_config, _get_portfolio_data,
    _compute_pd, _run_fraud_checks, _run_compliance_rules, _call_gemini, _log_event,
    set_agent_output,
)


# ═══════════════════════════════════════════════════════════════════════════════
# GRAPH 1 — CREDIT RISK
# ═══════════════════════════════════════════════════════════════════════════════

class CreditRiskState(TypedDict):
    application_id: str
    features: dict
    macro: dict
    bureau_available: bool
    score_result: dict       # {pd, risk_band, shap_factors, macro_adjusted, stress_scenario}
    officer_narrative: str
    customer_narrative: str
    output: dict
    error: str


def cr_fetch(state: CreditRiskState) -> dict:
    """Node 1: Load features and macro config from the DIL store."""
    app_id = state["application_id"]
    _log_event(app_id, "credit_risk_graph", "NODE", {"node": "fetch"})
    try:
        features = _get_features(app_id)
        macro    = _get_macro_config()
        return {
            "features":        features,
            "macro":           macro,
            "bureau_available": not features.get("bureau_unavailable", False),
        }
    except Exception as e:
        return {"error": str(e)}

def cr_score(state: CreditRiskState) -> dict:
    """Node 2a: Compute PD using CIBIL-based rule scoring + macro overlay."""
    _log_event(state["application_id"], "credit_risk_graph", "NODE", {"node": "score"})
    result = _compute_pd(state["features"], state["macro"])
    return {"score_result": result}

def cr_alt_score(state: CreditRiskState) -> dict:
    """
    Node 2b: CONDITIONAL — runs when CIBIL is unavailable.
    Uses alternative data (UPI, utility payments, digital footprint)
    for a softer credit assessment.
    """
    _log_event(state["application_id"], "credit_risk_graph", "NODE", {"node": "alt_score"})
    f = state["features"]
    alt_composite = f.get("alt_credit_composite", 0.5)
    upi_reg       = f.get("upi_transaction_regularity", 0.5)
    utility_score = f.get("utility_payment_score", 50) / 100

    # Conservative PD for no-bureau applicants using alternative data
    alt_pd = 0.12 - (alt_composite * 0.05 + upi_reg * 0.03 + utility_score * 0.02)
    alt_pd = max(0.05, min(0.35, alt_pd))
    rb = "MEDIUM" if alt_pd < 0.08 else "HIGH"

    result = {
        "pd": round(alt_pd, 6),
        "risk_band": rb,
        "shap_factors": [
            {"feature": "alt_credit_composite", "value": alt_composite,
             "shap_value": round(-alt_composite * 0.05, 5), "human_label": "Alternative Credit Score", "direction": "POSITIVE"},
            {"feature": "upi_transaction_regularity", "value": upi_reg,
             "shap_value": round(-upi_reg * 0.03, 5), "human_label": "UPI Payment Regularity", "direction": "POSITIVE"},
        ],
        "macro_adjusted": False,
        "stress_scenario": state["macro"].get("stress_scenario", "NORMAL"),
        "alt_scoring_used": True,
    }
    return {"score_result": result}

def cr_narrative(state: CreditRiskState) -> dict:
    """Node 3: Generate officer and customer narratives via Gemini (or fallback)."""
    _log_event(state["application_id"], "credit_risk_graph", "NODE", {"node": "narrative"})
    sr = state.get("score_result", {})
    f  = state["features"]
    rb = sr.get("risk_band", "MEDIUM")
    pd = sr.get("pd", 0.05)
    cibil = f.get("cibil_score", 0)
    foir  = f.get("foir", 0)
    income = f.get("annual_income_verified", 0)
    stress = sr.get("stress_scenario", "NORMAL")
    alt_used = sr.get("alt_scoring_used", False)

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
    _log_event(state["application_id"], "credit_risk_graph", "NODE", {"node": "finalize"})
    sr = state.get("score_result", {})
    f  = state.get("features", {})
    if state.get("error"):
        out = {"application_id": state["application_id"], "error": state["error"],
               "credit_score": 0.5, "risk_band": "HIGH"}
    else:
        out = {
            "application_id":       state["application_id"],
            "credit_score":         sr.get("pd", 0.05),
            "risk_band":            sr.get("risk_band", "MEDIUM"),
            "foir":                 f.get("foir", 0),
            "dti_ratio":            f.get("dti_ratio", 0),
            "ltv_ratio":            f.get("ltv_ratio", 0),
            "net_monthly_surplus":  f.get("net_monthly_surplus", 0),
            "proposed_emi":         f.get("proposed_emi", 0),
            "macro_adjusted":       sr.get("macro_adjusted", False),
            "stress_scenario":      sr.get("stress_scenario", "NORMAL"),
            "alternative_score_used": sr.get("alt_scoring_used", not state.get("bureau_available", True)),
            "top_factors":          sr.get("shap_factors", []),
            "officer_narrative":    state.get("officer_narrative", ""),
            "customer_narrative":   state.get("customer_narrative", ""),
        }
    return {"output": out}

# Routing
def _cr_route_after_fetch(state: CreditRiskState) -> str:
    if state.get("error"): return "finalize"
    return "score" if state.get("bureau_available", True) else "alt_score"

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


# ═══════════════════════════════════════════════════════════════════════════════
# GRAPH 2 — FRAUD DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

class FraudState(TypedDict):
    application_id: str
    features: dict
    fraud_checks: dict       # from _run_fraud_checks
    explanation: str
    output: dict
    error: str


def fr_fetch(state: FraudState) -> dict:
    _log_event(state["application_id"], "fraud_graph", "NODE", {"node": "fetch"})
    try:
        return {"features": _get_features(state["application_id"])}
    except Exception as e:
        return {"error": str(e)}

def fr_evaluate(state: FraudState) -> dict:
    """Node 2: Evaluate all fraud signals — hard rules and soft behavioural signals."""
    _log_event(state["application_id"], "fraud_graph", "NODE", {"node": "evaluate"})
    checks = _run_fraud_checks(state["features"])
    return {"fraud_checks": checks}

def fr_explain(state: FraudState) -> dict:
    """
    Node 3 (CONDITIONAL): Only runs for SUSPICIOUS or HIGH_RISK cases.
    Generates a detailed Gemini explanation of the fraud signals detected.
    """
    _log_event(state["application_id"], "fraud_graph", "NODE", {"node": "explain"})
    c     = state["fraud_checks"]
    level = c.get("fraud_level", "CLEAN")
    rules = "; ".join(c.get("fired_hard_rules", []) + c.get("fired_soft_signals", [])[:2])
    explanation = _call_gemini(
        f"You are a fraud analyst. In 2 sentences, explain to a credit officer why this "
        f"application is rated {level}. Detected signals: {rules or 'none'}. Be specific.",
        fallback=f"Application flagged as {level}. Signals: {rules or 'none detected'}."
    )
    return {"explanation": explanation}

def fr_finalize(state: FraudState) -> dict:
    _log_event(state["application_id"], "fraud_graph", "NODE", {"node": "finalize"})
    c = state.get("fraud_checks", {})
    if state.get("error"):
        out = {"application_id": state["application_id"], "error": state["error"],
               "fraud_level": "SUSPICIOUS", "fraud_probability": 0.5}
    else:
        level = c.get("fraud_level", "CLEAN")
        out = {
            "application_id":        state["application_id"],
            "fraud_level":           level,
            "fraud_probability":     c.get("fraud_probability", 0.0),
            "fired_hard_rules":      c.get("fired_hard_rules", []),
            "fired_soft_signals":    c.get("fired_soft_signals", []),
            "ip_risk_score":         c.get("ip_risk_score", 0.0),
            "recommend_kyc_recheck": c.get("recommend_kyc_recheck", False),
            "explanation":           state.get("explanation", "No significant fraud signals detected.") if level in ("SUSPICIOUS","HIGH_RISK") else "Application shows normal behavioural patterns.",
        }
    return {"output": out}

def _fr_route_after_evaluate(state: FraudState) -> str:
    if state.get("error"): return "finalize"
    level = state.get("fraud_checks", {}).get("fraud_level", "CLEAN")
    return "explain" if level in ("SUSPICIOUS", "HIGH_RISK") else "finalize"

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


# ═══════════════════════════════════════════════════════════════════════════════
# GRAPH 3 — COMPLIANCE
# ═══════════════════════════════════════════════════════════════════════════════

class ComplianceState(TypedDict):
    application_id: str
    features: dict
    form_data: dict
    rule_result: dict        # from _run_compliance_rules
    rag_citations: list      # regulatory text from RAG knowledge base
    cot_reasoning: str
    output: dict
    error: str


def co_fetch(state: ComplianceState) -> dict:
    _log_event(state["application_id"], "compliance_graph", "NODE", {"node": "fetch"})
    try:
        ctx = _get_context_dict(state["application_id"])
        return {
            "features":  ctx["features"],
            "form_data": {k: v for k, v in ctx["form"].items()},
        }
    except Exception as e:
        return {"error": str(e)}

def co_run_rules(state: ComplianceState) -> dict:
    """Node 2: Run all 9 RBI compliance rules deterministically."""
    _log_event(state["application_id"], "compliance_graph", "NODE", {"node": "run_rules"})
    result = _run_compliance_rules(state["features"], state["form_data"])
    return {"rule_result": result}

def co_rag_lookup(state: ComplianceState) -> dict:
    """
    Node 3 (NEW): Search the compliance knowledge base for regulatory text
    relevant to the triggered block/warn flags.
    """
    _log_event(state["application_id"], "compliance_graph", "NODE", {"node": "rag_lookup"})
    r = state.get("rule_result", {})
    block_flags = r.get("block_flags", [])
    warn_flags = r.get("warn_flags", [])

    try:
        from services.rag import search_by_rule_flags, COMPLIANCE_KB
        if not COMPLIANCE_KB:
            return {"rag_citations": []}
        citations = search_by_rule_flags(block_flags, warn_flags, k=5)
        return {"rag_citations": [
            {"source": c.get("source", ""), "regulation": c.get("regulation", ""),
             "text": c.get("text", "")[:500]}
            for c in citations
        ]}
    except Exception as e:
        logger.warning(f"RAG lookup failed (non-fatal): {e}")
        return {"rag_citations": []}


def co_cot(state: ComplianceState) -> dict:
    """
    Node 4: Chain-of-Thought reasoning via Gemini.
    Enhanced with RAG citations for regulatory grounding.
    """
    _log_event(state["application_id"], "compliance_graph", "NODE", {"node": "cot"})
    r     = state["rule_result"]
    warns = r.get("warn_flags", [])
    f     = state["features"]
    rag_citations = state.get("rag_citations", [])
    warn_text = "; ".join(f"{w['rule_id']}: {w['description']}" for w in warns)
    income    = f.get("annual_income_verified", 0)
    foir      = f.get("foir", 0)
    product   = state["form_data"].get("loan_purpose", "PERSONAL")

    # Build regulatory context from RAG citations
    reg_context = ""
    if rag_citations:
        citation_lines = []
        for i, cite in enumerate(rag_citations[:3], 1):
            citation_lines.append(
                f"  [{i}] {cite.get('source', 'Unknown')}: "
                f"{cite.get('text', '')[:300]}"
            )
        reg_context = (
            "\n\nRelevant RBI Regulatory References:\n"
            + "\n".join(citation_lines)
            + "\n\nYou MUST cite these regulations in your reasoning using [1], [2], etc."
        )

    cot = _call_gemini(
        f"You are an RBI compliance officer. Analyse these compliance warnings: {warn_text}. "
        f"Applicant: {product} loan, income ₹{income:,.0f}, FOIR {foir:.1%}. "
        f"For each warning, give: [RULE_ID]: 1-sentence reasoning → PROCEED / HOLD. Be brief."
        f"{reg_context}",
        fallback=f"Warnings noted: {warn_text}. Manual review recommended for flagged items."
    )
    return {"cot_reasoning": cot}

def co_finalize(state: ComplianceState) -> dict:
    _log_event(state["application_id"], "compliance_graph", "NODE", {"node": "finalize"})
    r = state.get("rule_result", {})
    if state.get("error"):
        out = {"application_id": state["application_id"], "error": state["error"],
               "all_blocks_passed": False, "overall_status": "BLOCK_FAIL"}
    else:
        all_passed = r.get("all_blocks_passed", True)
        fallback_cot = ("All compliance rules passed." if all_passed and not r.get("warn_flags")
                        else f"{'Blocks: ' + ','.join(b['rule_id'] for b in r.get('block_flags',[])) if not all_passed else 'Warnings noted.'}")
        out = {
            "application_id":    state["application_id"],
            "all_blocks_passed": all_passed,
            "block_flags":       r.get("block_flags", []),
            "warn_flags":        r.get("warn_flags", []),
            "overall_status":    r.get("overall_status", "PASS"),
            "kyc_complete":      r.get("kyc_complete", True),
            "aml_review_required": r.get("aml_review_required", False),
            "cot_reasoning":     state.get("cot_reasoning", fallback_cot),
            "audit_hash":        r.get("audit_hash", ""),
            "rag_citations":     state.get("rag_citations", []),  # NEW
        }
    return {"output": out}

def _co_route_after_rules(state: ComplianceState) -> str:
    if state.get("error"): return "finalize"
    # Always proceed to RAG lookup for regulatory grounding
    return "rag_lookup"

def build_compliance_graph():
    g = StateGraph(ComplianceState)
    g.add_node("fetch",      co_fetch)
    g.add_node("run_rules",  co_run_rules)
    g.add_node("rag_lookup", co_rag_lookup)   # NEW node
    g.add_node("cot",        co_cot)
    g.add_node("finalize",   co_finalize)
    g.add_edge(START, "fetch")
    g.add_conditional_edges("fetch", lambda s: "finalize" if s.get("error") else "run_rules",
                             {"run_rules": "run_rules", "finalize": "finalize"})
    g.add_conditional_edges("run_rules", _co_route_after_rules,
                             {"rag_lookup": "rag_lookup", "finalize": "finalize"})
    g.add_edge("rag_lookup", "cot")           # rag_lookup → cot → finalize
    g.add_edge("cot",       "finalize")
    g.add_edge("finalize",  END)
    return g.compile()


# ═══════════════════════════════════════════════════════════════════════════════
# GRAPH 4 — PORTFOLIO INTELLIGENCE
# ═══════════════════════════════════════════════════════════════════════════════
# This is a bridge to the new portfolio_agent package.
# The rich 6-node LangGraph lives in portfolio_agent/agent.py.
# This file preserves the existing run_portfolio_graph() interface so that
# orchestrator.py, crew_runner.py, and tools.py remain unchanged.
# ═══════════════════════════════════════════════════════════════════════════════

def _run_portfolio_agent_bridge(app_id: str, credit_out: dict) -> dict:
    """
    Bridge: extract context from DIL store → call portfolio_agent → return
    a dict with the field names expected by PortfolioOutput in schemas.py.
    """
    import os, sys
    # Ensure project root is on path so portfolio_agent can be imported
    here = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(here)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from portfolio_agent.agent import run_portfolio_agent
    from portfolio_agent.schemas import (
        ApplicationFormData, CreditAgentOutput, FraudAgentOutput,
        ComplianceAgentOutput, BankStatementData, MacroConfigData, PortfolioStats,
    )
    from portfolio_agent.portfolio_db import get_portfolio_stats_from_file

    # ── Extract context from DIL feature store ────────────────────────────────
    ctx_dict = _get_context_dict(app_id)
    form = ctx_dict.get("form", {})
    features = ctx_dict.get("features", {})
    macro_cfg = _get_macro_config()

    # ── Build ApplicationFormData ─────────────────────────────────────────────
    address = form.get("address") or {}
    application = ApplicationFormData(
        loan_purpose="PERSONAL",
        loan_amount_requested=float(form.get("loan_amount_requested", 300_000)),
        loan_tenure_months=int(form.get("loan_tenure_months", 36)),
        employment_type=(
            "SELF_EMPLOYED"
            if str(form.get("employment_type", "SALARIED")).upper() == "SELF_EMPLOYED"
            else "SALARIED"
        ),
        annual_income=float(form.get("annual_income", 0)),
        employer_name=str(form.get("employer_name", "Unknown")),
        applicant_state=str(address.get("state") or form.get("applicant_state", "Maharashtra")),
        applicant_city=str(address.get("city") or form.get("applicant_city", "Mumbai")),
    )

    # ── Build CreditAgentOutput ───────────────────────────────────────────────
    credit_output = CreditAgentOutput.from_agent_dict(credit_out)

    # ── Fraud / Compliance — use defaults (portfolio called after credit only) ─
    fraud_output = FraudAgentOutput(fraud_level="CLEAN", fraud_probability=0.05)
    compliance_output = ComplianceAgentOutput(overall_status="PASS")

    # ── Bank data from features ────────────────────────────────────────────────
    bank_data = BankStatementData.from_features(features)

    # ── Macro config ──────────────────────────────────────────────────────────
    macro_data = MacroConfigData.from_dict(macro_cfg)

    # ── Portfolio stats from Excel ────────────────────────────────────────────
    raw_ps = get_portfolio_stats_from_file()
    portfolio_stats = PortfolioStats(**{k: v for k, v in raw_ps.items() if k != "data_source"})

    # ── Run the agent ─────────────────────────────────────────────────────────
    result = run_portfolio_agent(
        application=application,
        credit_output=credit_output,
        fraud_output=fraud_output,
        compliance_output=compliance_output,
        bank_data=bank_data,
        macro_data=macro_data,
        portfolio_stats=portfolio_stats,
    )
    result["application_id"] = app_id
    return result


# ─── Compiled graph instances (built once at import time) ─────────────────────
_CREDIT_GRAPH    = None
_FRAUD_GRAPH     = None
_COMPLIANCE_GRAPH = None
_PORTFOLIO_GRAPH  = None

def _get_credit_graph():
    global _CREDIT_GRAPH
    if _CREDIT_GRAPH is None: _CREDIT_GRAPH = build_credit_risk_graph()
    return _CREDIT_GRAPH

def _get_fraud_graph():
    global _FRAUD_GRAPH
    if _FRAUD_GRAPH is None: _FRAUD_GRAPH = build_fraud_graph()
    return _FRAUD_GRAPH

def _get_compliance_graph():
    global _COMPLIANCE_GRAPH
    if _COMPLIANCE_GRAPH is None: _COMPLIANCE_GRAPH = build_compliance_graph()
    return _COMPLIANCE_GRAPH

def _get_portfolio_graph():
    # Portfolio graph is now implemented via portfolio_agent bridge.
    # This function kept for import-compatibility only; returns None.
    return None


# ─── Graph runner functions (called by agent runner @tools) ───────────────────

def run_credit_graph(app_id: str) -> dict:
    initial: CreditRiskState = {
        "application_id": app_id, "features": {}, "macro": {},
        "bureau_available": True, "score_result": {}, "officer_narrative": "",
        "customer_narrative": "", "output": {}, "error": "",
    }
    result = _get_credit_graph().invoke(initial)
    return result["output"]

def run_fraud_graph(app_id: str) -> dict:
    initial: FraudState = {
        "application_id": app_id, "features": {}, "fraud_checks": {},
        "explanation": "", "output": {}, "error": "",
    }
    result = _get_fraud_graph().invoke(initial)
    return result["output"]

def run_compliance_graph(app_id: str) -> dict:
    initial: ComplianceState = {
        "application_id": app_id, "features": {}, "form_data": {},
        "rule_result": {}, "rag_citations": [], "cot_reasoning": "",
        "output": {}, "error": "",
    }
    result = _get_compliance_graph().invoke(initial)
    return result["output"]

def run_portfolio_graph(app_id: str, credit_output: dict) -> dict:
    """
    Portfolio Intelligence Agent entry point.
    Delegates to portfolio_agent/agent.py via _run_portfolio_agent_bridge().
    Falls back to a minimal dict if the bridge fails.
    """
    try:
        return _run_portfolio_agent_bridge(app_id, credit_output)
    except Exception as e:
        logger.exception(f"[{app_id}] Portfolio bridge failed: {e}")
        return {
            "application_id": app_id,
            "portfolio_recommendation": "ACCEPT",
            "sector_concentration_current": 0.28,
            "sector_concentration_new": 0.28,
            "geo_concentration_current": 0.22,
            "geo_concentration_new": 0.22,
            "risk_band_distribution": {"LOW": 0.45, "MEDIUM": 0.38, "HIGH": 0.12, "VERY_HIGH": 0.05},
            "el_impact_inr": 0.0,
            "concentration_flags": [f"bridge_error: {str(e)[:80]}"],
            "similar_cases_npa_rate": 0.038,
            "cot_reasoning": f"Portfolio bridge error: {e}",
            "error": str(e),
        }
