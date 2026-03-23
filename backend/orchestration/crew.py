"""
backend/orchestration/crew.py
================================
CrewAI hierarchical Crew — Layer 4 Orchestrator.

Architecture (per Tensor4ce Stage 2 Solutioning v3.1):
  - CrewAI Process.hierarchical: manager LLM (Gemini) decides delegation order
  - 4 specialist CrewAI Agents wrapping LangGraph sub-apps via A2A
  - 4 Tasks with context dependencies (portfolio runs last, needs credit output)
  - 12 MCP tools registered on the crew
  - Python hard guardrails applied AFTER Gemini synthesis (LLM cannot override)

Fallback: if no Gemini key, run_direct_pipeline() calls agents directly via A2A
          with a fixed sequential order (credit → fraud → compliance → portfolio).
"""
from __future__ import annotations
import os
import uuid
import json
import time
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


# ── Helpers ─────────────────────────────────────────────────────────────────────

def _has_gemini() -> bool:
    if os.environ.get("LLM_USAGE_MODE", "FULL").upper() == "FALLBACK":
        return False
    if os.environ.get("ENABLE_CREWAI_MANAGER", "false").strip().lower() not in {"1", "true", "yes", "on"}:
        return False
    provider = os.environ.get("CREWAI_LLM_PROVIDER", "gemini").strip().lower()
    if provider == "vertex":
        return (
            bool(os.environ.get("VERTEX_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT"))
            and bool(os.environ.get("VERTEX_LOCATION") or os.environ.get("GOOGLE_CLOUD_LOCATION"))
            and bool(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
                     or os.environ.get("GOOGLE_API_KEY")
                     or os.environ.get("GEMINI_API_KEY"))
        )
    return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))


def _build_llm():
    from crewai import LLM
    provider = os.environ.get("CREWAI_LLM_PROVIDER", "gemini").strip().lower()
    api_key  = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    model    = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash-exp")
    extra    = {}
    if provider == "vertex":
        if "/" not in model:
            model = f"vertex_ai/{model}"
        extra["vertex_project"]  = os.environ.get("VERTEX_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")
        extra["vertex_location"] = os.environ.get("VERTEX_LOCATION") or os.environ.get("GOOGLE_CLOUD_LOCATION") or "us-central1"
    else:
        if "/" not in model:
            model = f"gemini/{model}"
    if api_key:
        os.environ.setdefault("GOOGLE_API_KEY", api_key)
    return LLM(model=model, api_key=api_key, temperature=0.1, **extra)


def _apply_hard_guardrails(decision: str, comp_out: dict, fraud_out: dict) -> str:
    """
    Post-LLM Python guardrails. LLM cannot override these.
    Runs AFTER Gemini produces its recommendation.
    """
    # Compliance hard block
    if not comp_out.get("all_blocks_passed", True):
        logger.warning("Hard guardrail: compliance block → forcing REJECT")
        return "REJECT"
    # Fraud hard block
    if str(fraud_out.get("fraud_level", "CLEAN")).upper() == "HIGH_RISK":
        logger.warning("Hard guardrail: fraud HIGH_RISK → forcing REJECT")
        return "REJECT"
    return decision


# ── CrewAI Orchestration ──────────────────────────────────────────────────────

def run_via_crewai(app_id: str) -> dict:
    """
    Full CrewAI hierarchical orchestration.
    Manager LLM (Gemini) reasons about agent delegation and synthesises recommendation.
    Agents are contacted via A2A HTTP — each is a FastAPI sub-app.
    """
    from crewai import Agent, Task, Crew, Process
    from orchestration.mcp_tools import ALL_MCP_TOOLS
    from orchestration.a2a_client import call_agent
    from tools import _log_event, set_agent_output, AGENT_OUTPUTS

    llm = _build_llm()
    _log_event(app_id, "orchestrator", "CREWAI_START", {"mode": "hierarchical"})

    # ── Manager Agent ────────────────────────────────────────────────────────
    manager = Agent(
        role="Chief Credit Underwriting AI",
        goal=(
            "Thoroughly assess every loan application by coordinating 4 specialist LangGraph "
            "agents (Credit Risk, Fraud, Compliance, Portfolio), synthesising their findings, "
            "and producing a fair, explainable, RBI-compliant final recommendation."
        ),
        backstory=(
            "You are the Chief Credit Underwriting AI at a leading Indian bank. "
            "You coordinate four specialist AI agents and call them via A2A tools. "
            "You are methodical, fair, and fully RBI-compliant. Your reasoning is recorded "
            "and audited. Never override hard compliance or fraud blocks."
        ),
        llm=llm,
        tools=ALL_MCP_TOOLS,
        verbose=True,
        allow_delegation=True,
        max_iter=20,
    )

    # ── Specialist CrewAI Agent wrappers (thin shells over A2A) ─────────────
    def _make_a2a_agent(name: str, role: str, goal: str) -> Agent:
        return Agent(
            role=role,
            goal=goal,
            backstory=f"You are the {role} for the Tensor4ce credit AI system.",
            tools=ALL_MCP_TOOLS,
            llm=llm,
            verbose=False,
            allow_delegation=False,
        )

    credit_agent = _make_a2a_agent(
        "credit_risk",
        "Credit Risk Specialist",
        "Compute PD, assign risk band, run macro overlay, generate narratives via LangGraph A2A."
    )
    fraud_agent = _make_a2a_agent(
        "fraud",
        "Fraud Detection Specialist",
        "Evaluate fraud signals, run Isolation Forest, apply hard rules via LangGraph A2A."
    )
    compliance_agent = _make_a2a_agent(
        "compliance",
        "Compliance Specialist",
        "Run all 12 RBI compliance rules deterministically and CoT warn flags via LangGraph A2A."
    )
    portfolio_agent = _make_a2a_agent(
        "portfolio",
        "Portfolio Intelligence Specialist",
        "Compute EL impact, check concentration limits, query similar cases via LangGraph A2A."
    )

    # ── Tasks ────────────────────────────────────────────────────────────────
    credit_task = Task(
        description=f"Run Credit Risk assessment for application {app_id} via A2A. "
                    f"Call the run_credit_model MCP tool. Return CreditRiskOutput JSON.",
        expected_output="JSON with risk_band, credit_score (PD), foir, top_factors, officer_narrative.",
        agent=credit_agent,
    )
    fraud_task = Task(
        description=f"Run Fraud Detection for application {app_id} via A2A. "
                    f"Call the run_fraud_model MCP tool. Return FraudOutput JSON.",
        expected_output="JSON with fraud_level, fraud_probability, fired_hard_rules, explanation.",
        agent=fraud_agent,
    )
    compliance_task = Task(
        description=f"Run all 12 RBI Compliance checks for application {app_id} via A2A. "
                    f"Call check_rbi_rules MCP tool. Return ComplianceOutput JSON.",
        expected_output="JSON with all_blocks_passed, block_flags, warn_flags, overall_status.",
        agent=compliance_agent,
        context=[credit_task],   # Compliance gets credit context
    )
    portfolio_task = Task(
        description=f"Run Portfolio Intelligence analysis for application {app_id} via A2A. "
                    f"Call get_portfolio_exposure and query_similar_cases MCP tools. "
                    f"Use the Credit Risk output for EL computation. Return PortfolioOutput JSON.",
        expected_output="JSON with portfolio_recommendation, el_impact_inr, concentration_flags, cot_reasoning.",
        agent=portfolio_agent,
        context=[credit_task, compliance_task],  # Portfolio runs last, needs credit output
    )

    # ── Crew kickoff ─────────────────────────────────────────────────────────
    crew = Crew(
        agents=[credit_agent, fraud_agent, compliance_agent, portfolio_agent],
        tasks=[credit_task, fraud_task, compliance_task, portfolio_task],
        manager_agent=manager,
        process=Process.hierarchical,
        memory=False,   # Disabled: requires OpenAI key; we use Vertex AI
        verbose=True,
        max_rpm=1,      # Maximum throttling to avoid Vertex AI 429 rate limits
    )

    raw_result = crew.kickoff(inputs={"application_id": app_id})
    _log_event(app_id, "orchestrator", "CREWAI_COMPLETE", {})

    # ── After CrewAI runs, invoke each agent via A2A to get typed outputs ──
    # (CrewAI text output is supplementary; real typed outputs come from A2A)
    credit_out = call_agent("credit_risk", app_id)
    fraud_out  = call_agent("fraud", app_id)
    comp_out   = call_agent("compliance", app_id)
    port_out   = call_agent("portfolio", app_id, payload={"credit_risk_output": credit_out})

    set_agent_output(app_id, "credit", credit_out)
    set_agent_output(app_id, "fraud",  fraud_out)
    set_agent_output(app_id, "compliance", comp_out)
    set_agent_output(app_id, "portfolio", port_out)

    return _build_final_decision(app_id, credit_out, fraud_out, comp_out, port_out,
                                  gemini_reasoning=str(raw_result))


# ── Direct Pipeline (no Gemini) ───────────────────────────────────────────────

def run_direct_pipeline(app_id: str) -> dict:
    """
    Sequential A2A pipeline without CrewAI manager LLM.
    Order: Credit Risk → Fraud (parallel-capable) → Compliance → Portfolio
    Falls back to this when GEMINI_API_KEY is not set or ENABLE_CREWAI_MANAGER=false.
    """
    from orchestration.a2a_client import call_agent
    from tools import _log_event, set_agent_output

    _log_event(app_id, "orchestrator", "DIRECT_START", {"mode": "direct_a2a"})

    logger.info(f"[{app_id}] Running Credit Risk Agent via A2A...")
    credit_out = call_agent("credit_risk", app_id)
    set_agent_output(app_id, "credit", credit_out)
    logger.info(f"[{app_id}] ✓ Credit: {credit_out.get('risk_band')} | PD={credit_out.get('credit_score', 0):.4f}")

    logger.info(f"[{app_id}] Running Fraud Detection Agent via A2A...")
    fraud_out = call_agent("fraud", app_id)
    set_agent_output(app_id, "fraud", fraud_out)
    logger.info(f"[{app_id}] ✓ Fraud: {fraud_out.get('fraud_level')} | Prob={fraud_out.get('fraud_probability', 0):.4f}")

    logger.info(f"[{app_id}] Running Compliance Agent via A2A...")
    comp_out = call_agent("compliance", app_id)
    set_agent_output(app_id, "compliance", comp_out)
    logger.info(f"[{app_id}] ✓ Compliance: {comp_out.get('overall_status')}")

    logger.info(f"[{app_id}] Running Portfolio Agent via A2A (with credit context)...")
    port_out = call_agent("portfolio", app_id, payload={"credit_risk_output": credit_out})
    set_agent_output(app_id, "portfolio", port_out)
    logger.info(f"[{app_id}] ✓ Portfolio: {port_out.get('portfolio_recommendation')}")

    _log_event(app_id, "orchestrator", "DIRECT_COMPLETE",
               {"decision": None, "agents_run": ["credit_risk", "fraud", "compliance", "portfolio"]})

    return _build_final_decision(app_id, credit_out, fraud_out, comp_out, port_out)


# ── Decision Builder ──────────────────────────────────────────────────────────

def _build_final_decision(
    app_id: str,
    credit_out: dict,
    fraud_out: dict,
    comp_out: dict,
    port_out: dict,
    gemini_reasoning: str = "",
) -> dict:
    """Assemble FinalDecision from A2A typed outputs and apply decision matrix."""
    from crew_runner import _apply_matrix
    from dil import get_context

    ctx_obj = get_context(app_id)
    ctx     = ctx_obj.model_dump(mode="json") if ctx_obj else {}

    # ── Apply decision matrix (pure Python) ──────────────────────────────────
    decision, row, conditions, max_amount = _apply_matrix(
        credit_out, fraud_out, comp_out, port_out, ctx
    )

    # ── Apply hard Python guardrails AFTER matrix ─────────────────────────
    decision = _apply_hard_guardrails(decision, comp_out, fraud_out)

    # ── Officer summary ───────────────────────────────────────────────────────
    lines = [
        f"AI RECOMMENDATION: {decision}",
        f"Matrix rule matched: {row}",
        "",
        f"CREDIT RISK:  {credit_out.get('risk_band', '—')} | PD={credit_out.get('credit_score', 0):.2%} | FOIR={credit_out.get('foir', 0):.1%} | Surplus ₹{credit_out.get('net_monthly_surplus', 0):,.0f}/mo",
        f"FRAUD:        {fraud_out.get('fraud_level', '—')} | Prob={fraud_out.get('fraud_probability', 0):.2%} | Hard rules: {len(fraud_out.get('fired_hard_rules', []))}",
        f"COMPLIANCE:   {comp_out.get('overall_status', '—')} | Blocks: {len(comp_out.get('block_flags', []))} | Warns: {len(comp_out.get('warn_flags', []))}",
        f"PORTFOLIO:    {port_out.get('portfolio_recommendation', '—')} | EL ₹{port_out.get('el_impact_inr', 0):,.0f}",
    ]
    if credit_out.get("officer_narrative"):
        lines += ["", f"Credit: {credit_out['officer_narrative']}"]
    if fraud_out.get("explanation"):
        lines.append(f"Fraud:  {fraud_out['explanation']}")
    if comp_out.get("cot_reasoning"):
        lines.append(f"Compliance: {comp_out['cot_reasoning'][:200]}")
    if port_out.get("cot_reasoning"):
        lines.append(f"Portfolio: {port_out['cot_reasoning'][:200]}")
    if gemini_reasoning:
        lines += ["", f"[CrewAI Manager Reasoning (truncated)]: {gemini_reasoning[:300]}"]
    if conditions:
        lines += ["", "CONDITIONS:"]
        for c in conditions:
            lines.append(f"  [{c['condition_type']}] {c['description'][:80]}")

    return {
        "decision_id":           f"DEC-{uuid.uuid4().hex[:10].upper()}",
        "application_id":        app_id,
        "ai_recommendation":     decision,
        "decision_matrix_row":   row,
        "conditions":            conditions,
        "max_approvable_amount": max_amount,
        "credit_risk":           credit_out,
        "fraud":                 fraud_out,
        "compliance":            comp_out,
        "portfolio":             port_out,
        "officer_summary":       "\n".join(lines),
        "decided_at":            datetime.utcnow().isoformat(),
    }


# ── Main Entry Point ──────────────────────────────────────────────────────────

def run_crew_pipeline(app_id: str, form_data: dict, ip_meta: dict) -> dict:
    """
    Complete orchestration pipeline:
    DIL → 3-Source Verification → [CrewAI hierarchical | Direct A2A] → FinalDecision

    Called by the Celery task (or FastAPI background task).
    """
    import db
    from dil import run_dil_pipeline, load_static_data
    from agents_base import load_compliance_rules, load_portfolio
    from tools import _log_event

    t0 = time.time()
    data_dir = os.environ.get("DATA_DIR", "data")

    # One-time data loading (idempotent)
    load_static_data(data_dir)
    load_compliance_rules(f"{data_dir}/compliance_rules.yaml")
    load_portfolio(f"{data_dir}/portfolio_loans.csv")

    # ── Step 1: Data Intelligence Layer ──────────────────────────────────────
    db.update_status(app_id, "DIL_PROCESSING")
    logger.info(f"[{app_id}] DIL starting...")
    ctx = run_dil_pipeline(app_id, form_data, ip_meta)
    logger.info(f"[{app_id}] DIL complete. Flags: {[f.flag_code for f in ctx.validation_flags]}")

    # ── Step 2: Agentic Orchestration ─────────────────────────────────────────
    db.update_status(app_id, "AGENTS_RUNNING")

    if _has_gemini():
        logger.info(f"[{app_id}] Mode: CrewAI hierarchical (Gemini manager)")
        try:
            result = run_via_crewai(app_id)
        except Exception as e:
            logger.error(f"[{app_id}] CrewAI failed ({e}), falling back to direct A2A pipeline")
            result = run_direct_pipeline(app_id)
    else:
        logger.info(f"[{app_id}] Mode: Direct A2A pipeline (set ENABLE_CREWAI_MANAGER=true + GEMINI_API_KEY for full agentic mode)")
        result = run_direct_pipeline(app_id)

    # ── Step 3: Persist ────────────────────────────────────────────────────────
    result["processing_time_ms"] = round((time.time() - t0) * 1000, 1)
    db.save_decision(result["decision_id"], app_id, result)
    db.update_status(app_id, "DECIDED_PENDING_OFFICER")

    logger.info(f"[{app_id}] Pipeline complete: {result.get('ai_recommendation')} in {result['processing_time_ms']:.0f}ms")
    return result
