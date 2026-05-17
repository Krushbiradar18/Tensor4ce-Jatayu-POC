"""
autonomous_decision.py - LLM-Driven Autonomous Orchestration Engine
=====================================================================
Provides two core LLM functions:

  1. llm_triage(app_id)
     Called BEFORE agents run. Analyses applicant features and returns a
     dynamic execution plan: agent ordering, skip recommendations, and
     priority hints.

  2. llm_synthesize_decision(app_id, credit, fraud, compliance, portfolio, ctx)
     Called AFTER agents run. Synthesises all 4 agent outputs into a
     grounded, reasoned final credit decision with rich narrative.

Fallback:
  If LLM calls fail (rate limit, timeout, FALLBACK mode), the module
  falls back to the existing _apply_matrix() in crew_runner.py.

Safety:
  Hard guardrails in crew.py (_apply_hard_guardrails) are ALWAYS applied
  AFTER this module output. The LLM cannot override compliance BLOCKs
  or fraud HIGH_RISK to REJECT rules.
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ==============================================================================
# 1. LLM TRIAGE - Dynamic Agent Execution Plan
# ==============================================================================

def llm_triage(app_id: str) -> dict:
    """
    Analyse application features and return a dynamic agent execution plan.

    Returns:
        {
            "agent_order": ["credit_risk", "fraud", "compliance", "portfolio"],
            "skip_agents": [],
            "early_exit_if": {...},
            "priority_hints": "...",
        }

    Fallback: default sequential order if LLM unavailable.
    """
    from llm_client import get_llm_response
    from llm_config import get_llm_usage_mode
    from tools import _get_features, _log_event

    default_plan = {
        "agent_order": ["credit_risk", "fraud", "compliance", "portfolio"],
        "skip_agents": [],
        "early_exit_if": {},
        "priority_hints": "Default sequential order (LLM triage skipped).",
    }

    if get_llm_usage_mode() == "FALLBACK":
        return default_plan

    # Gather key features for triage
    try:
        features = _get_features(app_id)
    except Exception as e:
        logger.warning("[%s] Triage: cannot load features (%s), using default order", app_id, e)
        return default_plan

    prompt = _build_triage_prompt(app_id, features)

    try:
        raw = get_llm_response(prompt, max_tokens=400)
        plan = _parse_triage_response(raw)
        _log_event(app_id, "orchestrator", "LLM_TRIAGE", {
            "agent_order": plan["agent_order"],
            "skip_agents": plan["skip_agents"],
            "priority_hints": plan["priority_hints"][:200],
        })
        return plan
    except Exception as e:
        logger.warning("[%s] Triage LLM call failed (%s), using default order", app_id, e)
        return default_plan


def _build_triage_prompt(app_id: str, features: dict) -> str:
    """Construct the triage prompt from application features."""
    cibil = features.get("cibil_score", 0)
    foir = features.get("foir", 0)
    income = features.get("annual_income_verified", 0)
    loan_amount = features.get("loan_amount_requested", 0)
    ip_risk = features.get("ip_risk_score", 0)
    dpd_90 = features.get("dpd_90_count", 0)
    pan_blacklisted = features.get("pan_blacklisted", False)
    form_fill_time = features.get("form_fill_time_seconds", 300)
    bounces = features.get("emi_bounce_count", 0)
    enquiries = features.get("num_hard_enquiries_6m", 0)

    parts = [
        "You are the Chief AI Orchestrator for an Indian bank's credit underwriting system.",
        "You must decide the OPTIMAL execution order for 4 specialist agents for loan application %s." % app_id,
        "",
        "Available agents: credit_risk, fraud, compliance, portfolio",
        "",
        "Applicant snapshot:",
        "- CIBIL Score: %.0f (0 = unavailable)" % cibil,
        "- FOIR: %.1f%%" % (foir * 100),
        "- Annual Income: INR {:,.0f}".format(income),
        "- Loan Amount Requested: INR {:,.0f}".format(loan_amount),
        "- IP Risk Score: %.2f (0=safe, 1=VPN/proxy)" % ip_risk,
        "- 90-Day DPD Count: %s" % dpd_90,
        "- PAN Blacklisted: %s" % pan_blacklisted,
        "- Form Fill Time: %.0fs (< 45s is suspicious)" % form_fill_time,
        "- EMI Bounces: %s" % bounces,
        "- Hard Enquiries (6m): %s" % enquiries,
        "",
        "Rules:",
        "1. Return a JSON object with these exact keys: agent_order, skip_agents, early_exit_if, priority_hints",
        "2. agent_order: list of agent names in your recommended execution order",
        '3. skip_agents: list of agents that can be safely skipped (only skip "portfolio" for micro-loans < INR 50,000)',
        '4. early_exit_if: dict mapping agent name to condition string for short-circuiting',
        "5. priority_hints: 1-2 sentence reasoning for your ordering decision",
        "6. If fraud signals are strong (blacklisted PAN, high IP risk, fast form), put fraud FIRST",
        "7. If credit signals are concerning (high DPD, low CIBIL), put credit_risk FIRST",
        "8. compliance must always run AFTER credit_risk (it needs credit context)",
        "9. portfolio must always run LAST (it needs credit output for EL calculation)",
        "",
        "Return ONLY valid JSON, no markdown, no explanation outside the JSON.",
    ]
    return "\n".join(parts)


def _parse_triage_response(raw: str) -> dict:
    """Parse the LLM triage response into a structured plan."""
    default_order = ["credit_risk", "fraud", "compliance", "portfolio"]
    valid_agents = {"credit_risk", "fraud", "compliance", "portfolio"}

    try:
        # Strip markdown fences if present
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
            if text.startswith("json"):
                text = text[4:].strip()

        plan = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Triage: could not parse LLM JSON, using default")
        return {
            "agent_order": default_order,
            "skip_agents": [],
            "early_exit_if": {},
            "priority_hints": "LLM parse failed. Raw: %s" % raw[:100],
        }

    # Validate and sanitize the plan
    order = plan.get("agent_order", default_order)
    if not isinstance(order, list):
        order = default_order
    order = [a for a in order if a in valid_agents]
    for agent in default_order:
        if agent not in order and agent not in plan.get("skip_agents", []):
            order.append(agent)

    # Enforce hard constraints:
    # - compliance must come after credit_risk
    # - portfolio must be last
    if "credit_risk" in order and "compliance" in order:
        ci = order.index("credit_risk")
        co = order.index("compliance")
        if co < ci:
            order.remove("compliance")
            order.insert(ci + 1, "compliance")

    if "portfolio" in order:
        order.remove("portfolio")
        order.append("portfolio")

    skip = plan.get("skip_agents", [])
    if not isinstance(skip, list):
        skip = []
    skip = [a for a in skip if a in valid_agents and a not in {"credit_risk", "compliance"}]

    return {
        "agent_order": order,
        "skip_agents": skip,
        "early_exit_if": plan.get("early_exit_if", {}),
        "priority_hints": str(plan.get("priority_hints", ""))[:500],
    }


# ==============================================================================
# 2. LLM DECISION SYNTHESIS - Autonomous Final Decision
# ==============================================================================

def llm_synthesize_decision(
    app_id: str,
    credit_out: dict,
    fraud_out: dict,
    comp_out: dict,
    port_out: dict,
    ctx: dict,
) -> dict:
    """
    Use the LLM to autonomously synthesise a final credit decision from all
    4 agent outputs plus application context.

    Returns dict with ai_recommendation, reasoning_chain, officer_summary,
    conditions, confidence.

    Fallback: calls _apply_matrix() from crew_runner.py if LLM fails.
    """
    from llm_client import get_llm_response
    from llm_config import get_llm_usage_mode
    from tools import _log_event

    if get_llm_usage_mode() == "FALLBACK":
        return _fallback_to_matrix(app_id, credit_out, fraud_out, comp_out, port_out, ctx)

    prompt = _build_synthesis_prompt(app_id, credit_out, fraud_out, comp_out, port_out, ctx)

    try:
        raw = get_llm_response(prompt, max_tokens=800)
        result = _parse_synthesis_response(raw, app_id, credit_out, fraud_out, comp_out, port_out, ctx)
        _log_event(app_id, "orchestrator", "LLM_SYNTHESIS", {
            "ai_recommendation": result["ai_recommendation"],
            "confidence": result.get("confidence", 0),
            "reasoning_preview": result.get("reasoning_chain", "")[:200],
        })
        return result
    except Exception as e:
        logger.warning("[%s] Synthesis LLM failed (%s), falling back to rule matrix", app_id, e)
        return _fallback_to_matrix(app_id, credit_out, fraud_out, comp_out, port_out, ctx)


def _build_synthesis_prompt(
    app_id: str,
    credit_out: dict,
    fraud_out: dict,
    comp_out: dict,
    port_out: dict,
    ctx: dict,
) -> str:
    """Build the comprehensive synthesis prompt."""
    from crew_runner import _normalize_credit_band, _normalize_fraud_level, _normalize_compliance_status

    risk_band = _normalize_credit_band(credit_out)
    fraud_level = _normalize_fraud_level(fraud_out)
    comp_status = _normalize_compliance_status(comp_out)
    port_rec = port_out.get("portfolio_recommendation", "ACCEPT")

    features = ctx.get("features", {})
    form = ctx.get("form", {})

    parts = [
        "You are the Chief Credit Decision AI for an RBI-regulated Indian bank.",
        "You have received analysis from 4 specialist agents for loan application %s." % app_id,
        "You must produce a FINAL autonomous credit decision.",
        "",
        "=== CREDIT RISK AGENT OUTPUT ===",
        "Risk Band: %s" % risk_band,
        "PD (Probability of Default): %.4f" % credit_out.get("credit_score", 0),
        "FOIR: %.1f%%" % (credit_out.get("foir", 0) * 100),
        "DTI Ratio: %.1f%%" % (credit_out.get("dti_ratio", 0) * 100),
        "LTV Ratio: %.1f%%" % (credit_out.get("ltv_ratio", 0) * 100),
        "Net Monthly Surplus: INR {:,.0f}".format(credit_out.get("net_monthly_surplus", 0)),
        "Macro Adjusted: %s" % credit_out.get("macro_adjusted", False),
        "Top Risk Factors: %s" % json.dumps(credit_out.get("top_factors", [])[:3], default=str),
        "Officer Narrative: %s" % str(credit_out.get("officer_narrative", "N/A"))[:200],
        "",
        "=== FRAUD DETECTION AGENT OUTPUT ===",
        "Fraud Level: %s" % fraud_level,
        "Fraud Probability: %.4f" % fraud_out.get("fraud_probability", 0),
        "Hard Rules Fired: %s" % fraud_out.get("fired_hard_rules", []),
        "Soft Signals: %s" % fraud_out.get("fired_soft_signals", [])[:3],
        "IP Risk Score: %.2f" % fraud_out.get("ip_risk_score", 0),
        "KYC Recheck Recommended: %s" % fraud_out.get("recommend_kyc_recheck", False),
        "Explanation: %s" % str(fraud_out.get("explanation", "N/A"))[:200],
        "",
        "=== COMPLIANCE AGENT OUTPUT ===",
        "Overall Status: %s" % comp_status,
        "Blocks Passed: %s" % comp_out.get("all_blocks_passed", True),
        "Block Flags: %s" % json.dumps(comp_out.get("block_flags", []), default=str)[:300],
        "Warning Flags: %s" % json.dumps(comp_out.get("warn_flags", []), default=str)[:300],
        "KYC Complete: %s" % comp_out.get("kyc_complete", True),
        "AML Review Required: %s" % comp_out.get("aml_review_required", False),
        "",
        "=== PORTFOLIO AGENT OUTPUT ===",
        "Recommendation: %s" % port_rec,
        "Sector Concentration (New): %.1f%%" % (port_out.get("sector_concentration_new", 0) * 100),
        "Geo Concentration (New): %.1f%%" % (port_out.get("geo_concentration_new", 0) * 100),
        "Expected Loss Impact: INR {:,.0f}".format(port_out.get("el_impact_inr", 0)),
        "Concentration Flags: %s" % port_out.get("concentration_flags", []),
        "",
        "=== APPLICANT CONTEXT ===",
        "Loan Amount: INR {:,.0f}".format(form.get("loan_amount_requested", 0)),
        "Loan Purpose: %s" % form.get("loan_purpose", "PERSONAL"),
        "Annual Income: INR {:,.0f}".format(form.get("annual_income", 0)),
        "Employment: %s" % form.get("employment_type", "SALARIED"),
        "",
        "=== YOUR DECISION GUIDELINES (RBI-Compliant) ===",
        "You MUST choose exactly one: APPROVE, CONDITIONAL, ESCALATE, or REJECT.",
        "",
        "REJECT when: Compliance BLOCK failures, Fraud HIGH_RISK, Credit VERY_HIGH with no mitigation.",
        "ESCALATE when: HIGH credit risk but borderline, SUSPICIOUS fraud, mixed signals, agent errors.",
        "CONDITIONAL when: Positive overall but minor issues, FOIR borderline, KYC needs recheck.",
        "APPROVE when: All agents positive, LOW/MEDIUM credit risk, no fraud, compliance passed.",
        "",
        'Return ONLY valid JSON with keys: ai_recommendation, reasoning_chain, officer_summary, conditions, confidence.',
        'ai_recommendation must be one of: APPROVE, CONDITIONAL, ESCALATE, REJECT.',
        'conditions should be empty list [] for APPROVE and REJECT.',
        'Each condition needs: condition_type, description, required_by_days.',
        'confidence should be 0.0 to 1.0.',
        "Return ONLY the JSON, no markdown fences, no extra text.",
    ]
    return "\n".join(parts)


def _parse_synthesis_response(
    raw: str,
    app_id: str,
    credit_out: dict,
    fraud_out: dict,
    comp_out: dict,
    port_out: dict,
    ctx: dict,
) -> dict:
    """Parse the LLM synthesis response. Falls back to matrix on parse failure."""
    valid_decisions = {"APPROVE", "CONDITIONAL", "ESCALATE", "REJECT"}

    try:
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
            if text.startswith("json"):
                text = text[4:].strip()

        result = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        logger.warning("[%s] Synthesis: could not parse LLM JSON", app_id)
        return _fallback_to_matrix(app_id, credit_out, fraud_out, comp_out, port_out, ctx)

    decision = str(result.get("ai_recommendation", "")).upper()
    if decision not in valid_decisions:
        logger.warning("[%s] Synthesis: invalid decision '%s', falling back", app_id, decision)
        return _fallback_to_matrix(app_id, credit_out, fraud_out, comp_out, port_out, ctx)

    conditions = result.get("conditions", [])
    if not isinstance(conditions, list):
        conditions = []
    sanitized_conditions = []
    for c in conditions:
        if isinstance(c, dict) and "description" in c:
            sanitized_conditions.append({
                "condition_type": str(c.get("condition_type", "MANUAL_REVIEW")),
                "description": str(c["description"])[:200],
                "required_by_days": int(c.get("required_by_days", 7)),
            })

    return {
        "ai_recommendation": decision,
        "reasoning_chain": str(result.get("reasoning_chain", ""))[:1000],
        "officer_summary": str(result.get("officer_summary", ""))[:1000],
        "conditions": sanitized_conditions,
        "confidence": min(1.0, max(0.0, float(result.get("confidence", 0.5)))),
        "decision_source": "llm_autonomous",
    }


def _fallback_to_matrix(
    app_id: str,
    credit_out: dict,
    fraud_out: dict,
    comp_out: dict,
    port_out: dict,
    ctx: dict,
) -> dict:
    """Fall back to the existing rule-based decision matrix."""
    from crew_runner import _apply_matrix

    decision, row, conditions, max_amount = _apply_matrix(
        credit_out, fraud_out, comp_out, port_out, ctx
    )

    lines = [
        "AI RECOMMENDATION: %s" % decision,
        "Matrix rule matched: %s" % row,
        "",
        "CREDIT RISK:  %s | PD=%.2f%%" % (credit_out.get("risk_band", "N/A"), credit_out.get("credit_score", 0) * 100),
        "FRAUD:        %s | Prob=%.2f%%" % (fraud_out.get("fraud_level", "N/A"), fraud_out.get("fraud_probability", 0) * 100),
        "COMPLIANCE:   %s" % comp_out.get("overall_status", "N/A"),
        "PORTFOLIO:    %s" % port_out.get("portfolio_recommendation", "N/A"),
    ]

    return {
        "ai_recommendation": decision,
        "reasoning_chain": "Fallback rule matrix applied: %s" % row,
        "officer_summary": "\n".join(lines),
        "conditions": conditions,
        "confidence": 0.7,
        "decision_source": "rule_matrix_fallback",
        "decision_matrix_row": row,
        "max_approvable_amount": max_amount,
    }
