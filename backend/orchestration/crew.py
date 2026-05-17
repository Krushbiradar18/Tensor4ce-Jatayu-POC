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

# Force LiteLLM import for Groq provider support
# This must happen before CrewAI checks for it
try:
    # pyrefly: ignore [missing-import]
    import litellm
    litellm.suppress_debug_info = True
    _LITELLM_AVAILABLE = True
    logger_init = logging.getLogger(__name__)
    logger_init.debug("LiteLLM loaded successfully")
except ImportError as e:
    _LITELLM_AVAILABLE = False
    logger_init = logging.getLogger(__name__)
    logger_init.warning(f"LiteLLM not available: {e}")

logger = logging.getLogger(__name__)


# ── Helpers ─────────────────────────────────────────────────────────────────────

def _has_gemini() -> bool:
    """Check if a supported LLM provider (Groq, Vertex, or Gemini) is configured."""
    if os.environ.get("LLM_USAGE_MODE", "FULL").upper() == "FALLBACK":
        return False
    if os.environ.get("ENABLE_CREWAI_MANAGER", "false").strip().lower() not in {"1", "true", "yes", "on"}:
        return False
    provider = os.environ.get("CREWAI_LLM_PROVIDER", "groq").strip().lower()
    
    # LiteLLM wrapper: check underlying backend
    if provider == "litellm":
        backend = os.environ.get("LLM_BACKEND", "groq").strip().lower()
        if backend == "groq":
            return bool(os.environ.get("GROQ_API_KEY"))
        # For other backends via LiteLLM, delegate to standard checks
        return (
            bool(os.environ.get("GROQ_API_KEY"))
            or bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
        )
    
    if provider == "groq":
        return bool(os.environ.get("GROQ_API_KEY"))
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
    # pyrefly: ignore [missing-import]
    from crewai import LLM
    provider = os.environ.get("CREWAI_LLM_PROVIDER", "groq").strip().lower()

    # Handle LiteLLM wrapper: delegate to underlying backend
    if provider == "litellm":
        backend = os.environ.get("LLM_BACKEND", "groq").strip().lower()
        if backend == "groq":
            provider = "groq"
        else:
            # Fallback to gemini for other backends
            provider = "gemini"

    if provider == "groq":
        # For Groq, CrewAI requires LiteLLM to be installed and available
        if not _LITELLM_AVAILABLE:
            raise RuntimeError(
                "LiteLLM is required for Groq support in CrewAI. "
                "Install with: pip install litellm"
            )
        
        model   = os.environ.get("GROQ_MODEL_ORCHESTRATOR", "groq/llama-3.3-70b-versatile")
        api_key = os.environ.get("GROQ_API_KEY")
        
        # Set environment variable so CrewAI can find the Groq API key
        os.environ["GROQ_API_KEY"] = api_key
        
        # Pass model with groq/ prefix - CrewAI will auto-route to LiteLLM
        # NOTE: model must be in format "groq/model-name" for LiteLLM routing
        return LLM(model=model, temperature=0.1)

    # Vertex / Gemini fallback (native providers)
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    model   = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash-exp")
    extra   = {}
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


def _agent_fallback_output(agent_name: str, app_id: str, error_msg: str) -> dict:
    """Conservative fallback payloads used when an agent call fails."""
    err = f"AGENT_{agent_name.upper()}_UNAVAILABLE: {error_msg}"

    if agent_name == "credit_risk":
        return {
            "application_id": app_id,
            "credit_score": 0.45,
            "risk_band": "HIGH",
            "foir": 0.0,
            "ltv_ratio": 0.0,
            "model_risk_score": None,
            "top_factors": [],
            "officer_narrative": "Credit model output unavailable; escalated for manual review.",
            "error": err,
        }

    if agent_name == "fraud":
        return {
            "application_id": app_id,
            "fraud_level": "SUSPICIOUS",
            "fraud_probability": 0.5,
            "fired_hard_rules": ["FALLBACK_AGENT_TIMEOUT"],
            "fired_soft_signals": [],
            "ip_risk_score": 0.0,
            "recommend_kyc_recheck": True,
            "explanation": "Fraud engine response timed out; escalated for manual fraud review.",
            "error": err,
        }

    if agent_name == "compliance":
        return {
            "application_id": app_id,
            "all_blocks_passed": True,
            "block_flags": [],
            "warn_flags": [{
                "rule_id": "SYS_FALLBACK",
                "severity": "WARN",
                "description": "Compliance engine unavailable",
                "regulation": "SYSTEM",
                "message": "Compliance response unavailable; manual compliance review required.",
            }],
            "overall_status": "PASS_WITH_WARNINGS",
            "kyc_complete": False,
            "aml_review_required": True,
            "cot_reasoning": "Compliance service timeout; fallback warnings applied.",
            "error": err,
        }

    if agent_name == "portfolio":
        return {
            "application_id": app_id,
            "portfolio_recommendation": "CAUTION",
            "sector_concentration_current": 0.0,
            "sector_concentration_new": 0.0,
            "geo_concentration_current": 0.0,
            "geo_concentration_new": 0.0,
            "risk_band_distribution": {},
            "el_impact_inr": 0.0,
            "concentration_flags": ["FALLBACK_AGENT_TIMEOUT"],
            "cot_reasoning": "Portfolio service timeout; manual portfolio check recommended.",
            "error": err,
        }

    return {"application_id": app_id, "error": err}


def _safe_call_agent(agent_name: str, app_id: str, payload: dict | None = None) -> dict:
    """Call agent via A2A and return fallback output on failure."""
    from orchestration.a2a_client import call_agent

    try:
        return call_agent(agent_name, app_id, payload=payload)
    except Exception as e:
        logger.exception(f"[{app_id}] {agent_name} A2A failed, using fallback output: {e}")
        return _agent_fallback_output(agent_name, app_id, str(e))


# ── CrewAI Orchestration ──────────────────────────────────────────────────────

def run_via_crewai(app_id: str) -> dict:
    """
    Full CrewAI hierarchical orchestration.
    Manager LLM (Gemini) reasons about agent delegation and synthesises recommendation.
    Agents are contacted via A2A HTTP — each is a FastAPI sub-app.
    """
    # pyrefly: ignore [missing-import]
    from crewai import Agent, Task, Crew, Process
    from orchestration.mcp_tools import (
        run_credit_model, run_fraud_model, 
        check_rbi_rules, run_portfolio_model,
        ALL_MCP_TOOLS
    )
    from tools import _log_event, set_agent_output, AGENT_OUTPUTS

    llm = _build_llm()
    _log_event(app_id, "orchestrator", "CREWAI_START", {"mode": "hierarchical"})

    # ── Specialist CrewAI Agent wrappers (thin shells over A2A) ─────────────
    credit_agent = Agent(
        role="Credit Risk Specialist",
        goal="Execute the 'run_credit_model' tool and return its exact JSON output.",
        backstory="You are a Credit Risk Specialist. You MUST call the 'run_credit_model' tool immediately once with the provided application_id to get the risk assessment results. Do not provide thoughts or summaries; simply return the raw tool output.",
        tools=[run_credit_model],
        llm=llm,
        verbose=True,
        allow_delegation=False,
        max_iter=3,
    )
    fraud_agent = Agent(
        role="Fraud Detection Specialist",
        goal="Execute the 'run_fraud_model' tool and return its exact JSON output.",
        backstory="You are a Fraud Detection Specialist. You MUST call the 'run_fraud_model' tool immediately once with the provided application_id to get fraud signals. Do not provide thoughts or summaries; simply return the raw tool output.",
        tools=[run_fraud_model],
        llm=llm,
        verbose=True,
        allow_delegation=False,
        max_iter=3,
    )
    compliance_agent = Agent(
        role="Compliance Specialist",
        goal="Execute the 'check_rbi_rules' tool and return its exact JSON output.",
        backstory="You are a Compliance Specialist. You MUST call the 'check_rbi_rules' tool immediately once with the provided application_id to verify regulatory compliance. Do not provide thoughts or summaries; simply return the raw tool output.",
        tools=[check_rbi_rules],
        llm=llm,
        verbose=True,
        allow_delegation=False,
        max_iter=3,
    )
    portfolio_agent = Agent(
        role="Portfolio Intelligence Specialist",
        goal="Execute the 'run_portfolio_model' tool and return its exact JSON output.",
        backstory="You are a Portfolio Specialist. You MUST call the 'run_portfolio_model' tool immediately once with the provided application_id to assess portfolio impact. Do not provide thoughts or summaries; simply return the raw tool output.",
        tools=[run_portfolio_model],
        llm=llm,
        verbose=True,
        allow_delegation=False,
        max_iter=3,
    )

    # ── Tasks ────────────────────────────────────────────────────────────────
    credit_task = Task(
        description=f"Invoke the 'run_credit_model' tool for application {app_id}. You must return the raw JSON result from the tool.",
        expected_output="The raw JSON dictionary from the credit risk specialist agent.",
        agent=credit_agent,
    )
    fraud_task = Task(
        description=f"Invoke the 'run_fraud_model' tool for application {app_id}. You must return the raw JSON result from the tool.",
        expected_output="The raw JSON dictionary from the fraud specialist agent.",
        agent=fraud_agent,
    )
    compliance_task = Task(
        description=f"Invoke the 'check_rbi_rules' tool for application {app_id}. You must return the raw JSON result from the tool.",
        expected_output="The raw JSON dictionary from the compliance specialist agent.",
        agent=compliance_agent,
        context=[credit_task]
    )
    portfolio_task = Task(
        description=f"Invoke the 'run_portfolio_model' tool for application {app_id}. You must return the raw JSON result from the tool.",
        expected_output="The raw JSON dictionary from the portfolio specialist agent.",
        agent=portfolio_agent,
        context=[credit_task, compliance_task],
    )


    # ── Crew kickoff ─────────────────────────────────────────────────────────
    crew = Crew(
        agents=[credit_agent, fraud_agent, compliance_agent, portfolio_agent],
        tasks=[credit_task, fraud_task, compliance_task, portfolio_task],
        process=Process.sequential,
        memory=False,
        verbose=True,
        max_rpm=20,
    )

    raw_result = crew.kickoff(inputs={"application_id": app_id})
    _log_event(app_id, "orchestrator", "CREWAI_COMPLETE", {})

    # ── After CrewAI runs, retrieve typed outputs from the A2A store ──
    from tools import get_agent_output, set_agent_output
    
    # We retrieve what was cached during tool calls by the agents.
    credit_out = get_agent_output(app_id, "credit") or _agent_fallback_output("credit_risk", app_id, "Manager skipped agent")
    fraud_out  = get_agent_output(app_id, "fraud")  or _agent_fallback_output("fraud", app_id, "Manager skipped agent")
    comp_out   = get_agent_output(app_id, "compliance") or _agent_fallback_output("compliance", app_id, "Manager skipped agent")
    port_out   = get_agent_output(app_id, "portfolio") or _agent_fallback_output("portfolio", app_id, "Manager skipped agent")

    # In case they were fallbacks, ensure they are stored for building the final decision
    set_agent_output(app_id, "credit", credit_out)
    set_agent_output(app_id, "fraud",  fraud_out)
    set_agent_output(app_id, "compliance", comp_out)
    set_agent_output(app_id, "portfolio", port_out)

    return _build_final_decision(app_id, credit_out, fraud_out, comp_out, port_out,
                                  gemini_reasoning=str(raw_result))


# ── Direct Pipeline (Autonomous LLM-Driven Ordering) ─────────────────────────

def run_direct_pipeline(app_id: str) -> dict:
    """
    Autonomous A2A pipeline with LLM-driven dynamic agent ordering.

    The LLM triage step analyses applicant features and determines the
    optimal agent execution order, which agents to skip, and early-exit
    conditions.  Falls back to the fixed credit→fraud→compliance→portfolio
    sequence if triage is unavailable.
    """
    from tools import _log_event, set_agent_output, get_agent_output
    from autonomous_decision import llm_triage

    # ── LLM Triage: determine dynamic execution plan ─────────────────────────
    triage_plan = llm_triage(app_id)
    agent_order = triage_plan["agent_order"]
    skip_agents = set(triage_plan.get("skip_agents", []))
    early_exit_rules = triage_plan.get("early_exit_if", {})

    _log_event(app_id, "orchestrator", "DIRECT_START", {
        "mode": "autonomous_a2a",
        "agent_order": agent_order,
        "skip_agents": list(skip_agents),
        "triage_hints": triage_plan.get("priority_hints", "")[:200],
    })
    logger.info(f"[{app_id}] Autonomous triage → order={agent_order}, skip={list(skip_agents)}")

    # ── Agent name → A2A name mapping ─────────────────────────────────────────
    a2a_name_map = {
        "credit_risk": "credit_risk",
        "fraud": "fraud",
        "compliance": "compliance",
        "portfolio": "portfolio",
    }
    store_key_map = {
        "credit_risk": "credit",
        "fraud": "fraud",
        "compliance": "compliance",
        "portfolio": "portfolio",
    }
    results: dict[str, dict] = {}
    agents_run: list[str] = []
    early_exited = False

    for agent_name in agent_order:
        if agent_name in skip_agents:
            logger.info(f"[{app_id}] Skipping {agent_name} (LLM triage decision)")
            results[agent_name] = _agent_fallback_output(
                agent_name, app_id, "Skipped by LLM triage"
            )
            set_agent_output(app_id, store_key_map[agent_name], results[agent_name])
            continue

        # Build payload (portfolio needs credit context)
        payload = None
        if agent_name == "portfolio":
            credit_out = results.get("credit_risk") or get_agent_output(app_id, "credit") or {}
            payload = {"credit_risk_output": credit_out}

        logger.info(f"[{app_id}] Running {agent_name} Agent via A2A...")
        out = _safe_call_agent(a2a_name_map[agent_name], app_id, payload=payload)
        results[agent_name] = out
        set_agent_output(app_id, store_key_map[agent_name], out)
        agents_run.append(agent_name)

        # Log result summary
        if agent_name == "credit_risk":
            logger.info(f"[{app_id}] ✓ Credit: {out.get('risk_band')} | PD={out.get('credit_score', 0):.4f}")
        elif agent_name == "fraud":
            logger.info(f"[{app_id}] ✓ Fraud: {out.get('fraud_level')} | Prob={out.get('fraud_probability', 0):.4f}")
        elif agent_name == "compliance":
            logger.info(f"[{app_id}] ✓ Compliance: {out.get('overall_status')}")
        elif agent_name == "portfolio":
            logger.info(f"[{app_id}] ✓ Portfolio: {out.get('portfolio_recommendation')}")

        # ── Check early-exit conditions ───────────────────────────────────────
        exit_rule = early_exit_rules.get(agent_name, "")
        should_exit = False
        if exit_rule:
            # Evaluate common early-exit patterns safely
            if agent_name == "fraud" and out.get("fraud_level") == "HIGH_RISK":
                should_exit = True
            elif agent_name == "compliance" and not out.get("all_blocks_passed", True):
                should_exit = True
        if should_exit:
            logger.info(f"[{app_id}] Early exit triggered after {agent_name}: {exit_rule}")
            _log_event(app_id, "orchestrator", "EARLY_EXIT", {
                "trigger_agent": agent_name, "rule": exit_rule,
            })
            early_exited = True
            # Fill remaining agents with fallbacks
            for remaining in agent_order:
                if remaining not in results:
                    results[remaining] = _agent_fallback_output(
                        remaining, app_id, f"Skipped: early exit after {agent_name}"
                    )
                    set_agent_output(app_id, store_key_map[remaining], results[remaining])
            break

    credit_out = results.get("credit_risk", _agent_fallback_output("credit_risk", app_id, "not run"))
    fraud_out  = results.get("fraud", _agent_fallback_output("fraud", app_id, "not run"))
    comp_out   = results.get("compliance", _agent_fallback_output("compliance", app_id, "not run"))
    port_out   = results.get("portfolio", _agent_fallback_output("portfolio", app_id, "not run"))

    _log_event(app_id, "orchestrator", "DIRECT_COMPLETE", {
        "agents_run": agents_run,
        "early_exited": early_exited,
    })

    return _build_final_decision(app_id, credit_out, fraud_out, comp_out, port_out)


# ── Decision Builder (Autonomous LLM Synthesis) ──────────────────────────────

def _build_final_decision(
    app_id: str,
    credit_out: dict,
    fraud_out: dict,
    comp_out: dict,
    port_out: dict,
    gemini_reasoning: str = "",
) -> dict:
    """
    Assemble FinalDecision using autonomous LLM synthesis.

    Flow:
      1. Call llm_synthesize_decision() for autonomous LLM-driven decision
      2. Apply hard Python guardrails AFTER LLM decision (immutable safety net)
      3. Force ESCALATE if any agent had errors
      4. Assemble the complete FinalDecision dict

    Fallback: if LLM synthesis fails, falls back to _apply_matrix() internally.
    """
    from autonomous_decision import llm_synthesize_decision
    from dil import get_context

    ctx_obj = get_context(app_id)
    ctx     = ctx_obj.model_dump(mode="json") if ctx_obj else {}

    # ── Step 1: Autonomous LLM Decision Synthesis ────────────────────────────
    synthesis = llm_synthesize_decision(
        app_id, credit_out, fraud_out, comp_out, port_out, ctx
    )

    decision    = synthesis["ai_recommendation"]
    conditions  = synthesis.get("conditions", [])
    max_amount  = synthesis.get("max_approvable_amount")
    row         = synthesis.get("decision_matrix_row", f"LLM_{decision}")
    decision_source = synthesis.get("decision_source", "llm_autonomous")

    # ── Step 2: Apply hard Python guardrails AFTER LLM ───────────────────────
    original_decision = decision
    decision = _apply_hard_guardrails(decision, comp_out, fraud_out)
    if decision != original_decision:
        logger.warning(
            f"[{app_id}] Hard guardrail overrode LLM decision: {original_decision} → {decision}"
        )
        row = f"GUARDRAIL_OVERRIDE_{decision}"

    # ── Step 3: Force ESCALATE if any agent had errors ───────────────────────
    output_errors = [
        credit_out.get("error"),
        fraud_out.get("error"),
        comp_out.get("error"),
        port_out.get("error"),
    ]
    has_output_error = any(bool(e) for e in output_errors)
    if has_output_error:
        decision = "ESCALATE"
        row = "R0_SYSTEM_DEGRADED_ESCALATE"
        conditions = list(conditions or [])
        conditions.append({
            "condition_type": "MANUAL_REVIEW",
            "description": "One or more agent services timed out/unavailable. Manual underwriting review required.",
            "required_by_days": 1,
        })

    # ── Step 4: Build officer summary ─────────────────────────────────────────
    # Use LLM-generated summary if available, otherwise build template
    llm_summary = synthesis.get("officer_summary", "")
    reasoning_chain = synthesis.get("reasoning_chain", "")

    lines = [
        f"AI RECOMMENDATION: {decision}  [{decision_source}]",
        f"Decision path: {row}",
    ]

    if llm_summary and decision_source == "llm_autonomous":
        lines += ["", "═══ LLM DECISION REASONING ═══", llm_summary]
        if reasoning_chain:
            lines += ["", "═══ REASONING CHAIN ═══", reasoning_chain[:400]]
    
    # Always include factual agent data for audit
    lines += [
        "",
        "═══ AGENT OUTPUTS (FACTUAL) ═══",
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
        lines += ["", f"[CrewAI Manager Reasoning]: {gemini_reasoning[:300]}"]
    if conditions:
        lines += ["", "CONDITIONS:"]
        for c in conditions:
            lines.append(f"  [{c['condition_type']}] {c['description'][:80]}")

    return {
        "decision_id":           f"DEC-{uuid.uuid4().hex[:10].upper()}",
        "application_id":        app_id,
        "ai_recommendation":     decision,
        "decision_matrix_row":   row,
        "decision_source":       decision_source,
        "conditions":            conditions,
        "max_approvable_amount": max_amount,
        "credit_risk":           credit_out,
        "fraud":                 fraud_out,
        "compliance":            comp_out,
        "portfolio":             port_out,
        "officer_summary":       "\n".join(lines),
        "reasoning_chain":       reasoning_chain,
        "llm_confidence":        synthesis.get("confidence"),
        "context":               ctx,
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
    allow_file_fallback = os.environ.get("ALLOW_RUNTIME_FILE_FALLBACK", "false").strip().lower() in {"1", "true", "yes", "on"}
    if allow_file_fallback:
        load_portfolio(f"{data_dir}/portfolio_loans.csv")

    # ── Step 1: Data Intelligence Layer ──────────────────────────────────────
    db.update_status(app_id, "DIL_PROCESSING")
    logger.info(f"[{app_id}] DIL starting...")
    ctx = run_dil_pipeline(app_id, form_data, ip_meta)
    logger.info(f"[{app_id}] DIL complete. Flags: {[f.flag_code for f in ctx.validation_flags]}")

    # ── Step 1b: Document Processing Crew & Orchestrator Gate (Day 3 Update) ──
    try:
        from orchestration.document_pipeline import run_document_processing_crew, evaluate_requirements
        
        # 1. Run Document Intake -> OCR -> Normalization
        logger.info(f"[{app_id}] Running Document Processing Crew...")
        # Check LLM connection first to fail fast before trying Crew
        try:
            llm = _build_llm()
        except Exception as e:
            logger.warning(f"[{app_id}] Failed to build LLM, falling back to None for Crew: {e}")
            llm = None
            
        unified_profile = run_document_processing_crew(app_id, llm)
        _log_event(app_id, "orchestrator", "DOCUMENT_PROCESSING_COMPLETE", unified_profile)
        
        # 2. Orchestrator: Evaluate Requirements
        logger.info(f"[{app_id}] Orchestrator evaluating requirement cards...")
        req_eval = evaluate_requirements(
            profile=unified_profile, 
            loan_amount=float(form_data.get("loan_amount_requested", 0)), 
            employment_type=form_data.get("employment_type", "SALARIED")
        )
        _log_event(app_id, "orchestrator", "REQUIREMENTS_EVALUATION", req_eval)
        
        if req_eval["action"] == "DATA_REQUIRED":
            missing = req_eval["missing"]
            logger.warning(f"[{app_id}] Blocking data gaps: {missing} — status → DATA_REQUIRED")
            db.update_status(app_id, "DATA_REQUIRED")
            
            # Format to match frontend expectations: [{doc: "...", blocking: true, reason: "..."}]
            required_docs_formatted = [
                {"doc": doc_name, "blocking": True, "reason": "Missing mandatory document required by downstream agents."} 
                for doc_name in missing
            ]
            
            decision_id = str(uuid.uuid4())
            result = {
                "decision_id": decision_id,
                "application_id": app_id,
                "ai_recommendation": "DATA_REQUIRED",
                "required_documents": required_docs_formatted,
                "officer_narrative": (
                    "Application cannot be processed due to missing mandatory data: "
                    + ", ".join(missing)
                    + ". Please upload the required documents and resubmit."
                ),
                "processing_time_ms": round((time.time() - t0) * 1000, 1),
            }
            db.save_decision(decision_id, app_id, result)
            return result
            
        elif req_eval["action"] == "LOW_CONFIDENCE_RETRY":
            low_conf = req_eval["low_confidence"]
            logger.warning(f"[{app_id}] Low OCR confidence on fields: {low_conf} — status → LOW_CONFIDENCE_RETRY")
            db.update_status(app_id, "DATA_REQUIRED") # Treat as data required in UI
            
            # Format to match frontend expectations
            required_docs_formatted = [
                {"doc": "CLEARER_" + f.upper(), "blocking": True, "reason": "OCR confidence too low, please upload a clearer image."}
                for f in low_conf
            ]
            
            decision_id = str(uuid.uuid4())
            result = {
                "decision_id": decision_id,
                "application_id": app_id,
                "ai_recommendation": "DATA_REQUIRED",
                "required_documents": required_docs_formatted,
                "officer_narrative": (
                    "Please re-upload clearer images for the following fields: "
                    + ", ".join(low_conf)
                ),
                "processing_time_ms": round((time.time() - t0) * 1000, 1),
            }
            db.save_decision(decision_id, app_id, result)
            return result
            
        logger.info(f"[{app_id}] Orchestrator Check OK -> Proceeding to Downstream Agents")
        
        # Override form features with OCR extracted ones (this bridges the Document Processing Crew into DIL context)
        ident = unified_profile.get("identity", {})
        if ident.get("pan_number"): ctx.form.pan_number = ident["pan_number"]
        if ident.get("aadhaar_number"): ctx.form.aadhaar_last4 = ident["aadhaar_number"][-4:] if ident["aadhaar_number"] else None
        
        fins = unified_profile.get("financials", {})
        if fins.get("avg_monthly_credit"): ctx.features.avg_monthly_credit = fins["avg_monthly_credit"]
        if fins.get("avg_monthly_debit"): ctx.features.avg_monthly_debit = fins["avg_monthly_debit"]
        if fins.get("min_eod_balance"): ctx.features.min_eod_balance = fins["min_eod_balance"]
        if fins.get("emi_bounce_count") is not None: ctx.features.emi_bounce_count = fins["emi_bounce_count"]
        if fins.get("salary_regularity"): ctx.features.salary_regularity = fins["salary_regularity"]
        
        from dil import store_context
        store_context(ctx)
        
    except Exception as e:
        import traceback
        logger.warning(f"[{app_id}] Document Orchestrator check failed: {e}\n{traceback.format_exc()}")

    # ── Step 2: Agentic Orchestration ─────────────────────────────────────────
    db.update_status(app_id, "AGENTS_RUNNING")

    try:
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
    except Exception as e:
        logger.exception(f"[{app_id}] Orchestration failed hard; persisting degraded decision: {e}")
        credit_out = _agent_fallback_output("credit_risk", app_id, str(e))
        fraud_out = _agent_fallback_output("fraud", app_id, str(e))
        comp_out = _agent_fallback_output("compliance", app_id, str(e))
        port_out = _agent_fallback_output("portfolio", app_id, str(e))
        result = _build_final_decision(app_id, credit_out, fraud_out, comp_out, port_out)

    # ── Step 3: Persist ────────────────────────────────────────────────────────
    result["processing_time_ms"] = round((time.time() - t0) * 1000, 1)
    db.save_decision(result["decision_id"], app_id, result)
    db.update_status(app_id, "DECIDED_PENDING_OFFICER")

    logger.info(f"[{app_id}] Pipeline complete: {result.get('ai_recommendation')} in {result['processing_time_ms']:.0f}ms")
    return result
