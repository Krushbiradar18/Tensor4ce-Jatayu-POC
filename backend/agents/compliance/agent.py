"""
backend/agents/compliance/agent.py
====================================
LangGraph StateGraph for the Compliance Specialist Agent.

Pipeline: fetch → run_rules → [cot | finalize]
"""
from __future__ import annotations
import logging
from typing import TypedDict
from langgraph.graph import StateGraph, START, END

logger = logging.getLogger(__name__)


class ComplianceState(TypedDict):
    application_id: str
    features: dict
    form_data: dict
    rule_result: dict
    cot_reasoning: str
    output: dict
    error: str


def co_fetch(state: ComplianceState) -> dict:
    from tools import _get_context_dict, _log_event
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
    """Node 2: Run all compliance rules deterministically — no LLM involved."""
    from tools import _run_compliance_rules, _log_event
    _log_event(state["application_id"], "compliance_graph", "NODE", {"node": "run_rules"})
    result = _run_compliance_rules(state["features"], state["form_data"])
    return {"rule_result": result}


def co_cot(state: ComplianceState) -> dict:
    """
    Node 3: Chain-of-Thought reasoning via Gemini.
    Now runs for ALL cases to provide audit rationale as requested.
    """
    from tools import _call_gemini, _log_event
    _log_event(state["application_id"], "compliance_graph", "NODE", {"node": "cot"})
    r     = state["rule_result"]
    warns = r.get("warn_flags", [])
    blocks = r.get("block_flags", [])
    f     = state["features"]
    
    warn_text = "; ".join(f"{w['rule_id']}: {w['description']}" for w in warns)
    block_text = "; ".join(f"{b['rule_id']}: {b['description']}" for b in blocks)
    income    = f.get("annual_income_verified", 0)
    foir      = f.get("foir", 0)
    product   = state["form_data"].get("loan_purpose", "PERSONAL")

    if not warns and not blocks:
        prompt = (f"You are an RBI compliance officer. The application for a {product} loan (Income: ₹{income:,.0f}) "
                 "has passed all standard compliance blocks and regulatory checks. "
                 "Write a 2-sentence audit trail summary confirming the application's adherence to standard bank policy.")
        fallback = "System checks validated against standard bank policies. All regulatory gates passed."
    else:
        prompt = (f"You are an RBI compliance officer. Analyze these compliance flags - Blocks: {block_text or 'None'}, Warnings: {warn_text or 'None'}. "
                 f"Applicant: {product} loan, income ₹{income:,.0f}, FOIR {foir:.1%}. "
                 f"Provide a brief 2-3 sentence audit trail & rationale explaining the impact of these findings. Be specific.")
        fallback = f"Regulatory check found flags: {block_text or warn_text}. Manual compliance review required."

    cot = _call_gemini(prompt, fallback=fallback)
    return {"cot_reasoning": cot}


def co_finalize(state: ComplianceState) -> dict:
    from tools import _log_event
    _log_event(state["application_id"], "compliance_graph", "NODE", {"node": "finalize"})
    r = state.get("rule_result", {})
    if state.get("error"):
        out = {"application_id": state["application_id"], "error": state["error"],
               "all_blocks_passed": False, "overall_status": "BLOCK_FAIL", "rbi_compliant": False}
    else:
        all_passed = r.get("all_blocks_passed", True)
        out = {
            "application_id":     state["application_id"],
            "all_blocks_passed":  all_passed,
            "rbi_compliant":      all_passed,
            "block_flags":        r.get("block_flags", []),
            "warn_flags":         r.get("warn_flags", []),
            "overall_status":     r.get("overall_status", "PASS"),
            "kyc_complete":       r.get("kyc_complete", True),
            "aml_review_required": r.get("aml_review_required", False),
            "cot_reasoning":      state.get("cot_reasoning", "Compliance check completed."),
            "narrative":          state.get("cot_reasoning", "System checks validated against standard bank policies."),
            "audit_hash":         r.get("audit_hash", ""),
        }
    return {"output": out}


def _co_route_after_rules(state: ComplianceState) -> str:
    if state.get("error"):
        return "finalize"
    # Always run cot for detailed audit trail
    return "cot"


def build_compliance_graph():
    g = StateGraph(ComplianceState)
    g.add_node("fetch",     co_fetch)
    g.add_node("run_rules", co_run_rules)
    g.add_node("cot",       co_cot)
    g.add_node("finalize",  co_finalize)
    g.add_edge(START, "fetch")
    g.add_conditional_edges("fetch", lambda s: "finalize" if s.get("error") else "run_rules",
                             {"run_rules": "run_rules", "finalize": "finalize"})
    g.add_conditional_edges("run_rules", _co_route_after_rules,
                             {"cot": "cot", "finalize": "finalize"})
    g.add_edge("cot",      "finalize")
    g.add_edge("finalize", END)
    return g.compile()


_GRAPH = None

def get_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_compliance_graph()
    return _GRAPH


def run_compliance_graph(application_id: str) -> dict:
    """Public entry point: run the Compliance LangGraph pipeline."""
    initial: ComplianceState = {
        "application_id": application_id,
        "features": {}, "form_data": {},
        "rule_result": {}, "cot_reasoning": "",
        "output": {}, "error": "",
    }
    result = get_graph().invoke(initial)
    return result["output"]
