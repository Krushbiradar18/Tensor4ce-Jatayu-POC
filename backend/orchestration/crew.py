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


# ── Direct Pipeline (no Gemini) ───────────────────────────────────────────────

def run_direct_pipeline(app_id: str) -> dict:
    """
    Sequential A2A pipeline without CrewAI manager LLM.
    Order: Credit Risk → Fraud (parallel-capable) → Compliance → Portfolio
    Falls back to this when GEMINI_API_KEY is not set or ENABLE_CREWAI_MANAGER=false.
    """
    from tools import _log_event, set_agent_output

    _log_event(app_id, "orchestrator", "DIRECT_START", {"mode": "direct_a2a"})

    logger.info(f"[{app_id}] Running Credit Risk Agent via A2A...")
    credit_out = _safe_call_agent("credit_risk", app_id)
    set_agent_output(app_id, "credit", credit_out)
    logger.info(f"[{app_id}] ✓ Credit: {credit_out.get('risk_band')} | PD={credit_out.get('credit_score', 0):.4f}")

    logger.info(f"[{app_id}] Running Fraud Detection Agent via A2A...")
    fraud_out = _safe_call_agent("fraud", app_id)
    set_agent_output(app_id, "fraud", fraud_out)
    logger.info(f"[{app_id}] ✓ Fraud: {fraud_out.get('fraud_level')} | Prob={fraud_out.get('fraud_probability', 0):.4f}")

    logger.info(f"[{app_id}] Running Compliance Agent via A2A...")
    comp_out = _safe_call_agent("compliance", app_id)
    set_agent_output(app_id, "compliance", comp_out)
    logger.info(f"[{app_id}] ✓ Compliance: {comp_out.get('overall_status')}")

    logger.info(f"[{app_id}] Running Portfolio Agent via A2A (with credit context)...")
    port_out = _safe_call_agent("portfolio", app_id, payload={"credit_risk_output": credit_out})
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

    # Any fallback/error output forces manual escalation.
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

    # ── Step 1b: Data Completeness Gate (Day 3) ───────────────────────────────
    try:
        from orchestration.mcp_tools import assess_data_completeness
        # Call the underlying function directly (bypassing the LangChain tool wrapper)
        completeness = assess_data_completeness.func(app_id)
        _log_event(app_id, "orchestrator", "DATA_COMPLETENESS_CHECK", completeness)
        if not completeness.get("can_proceed", True):
            # Blocking data gaps — halt pipeline and request more documents
            missing = completeness.get("missing_documents", [])
            logger.warning(f"[{app_id}] Blocking data gaps: {[m['doc'] for m in missing if m.get('blocking')]} — status → DATA_REQUIRED")
            db.update_status(app_id, "DATA_REQUIRED")
            required_docs = [m for m in missing if m.get("blocking")]
            decision_id = str(uuid.uuid4())
            result = {
                "decision_id": decision_id,
                "application_id": app_id,
                "ai_recommendation": "DATA_REQUIRED",
                "data_completeness": completeness,
                "required_documents": required_docs,
                "officer_narrative": (
                    "Application cannot be processed due to missing mandatory data: "
                    + ", ".join(m["doc"] for m in required_docs)
                    + ". Please upload the required documents and resubmit."
                ),
                "processing_time_ms": round((time.time() - t0) * 1000, 1),
            }
            db.save_decision(decision_id, app_id, result)
            return result
        logger.info(f"[{app_id}] Data completeness OK (score={completeness.get('data_completeness_score', '?')})")
    except Exception as e:
        logger.warning(f"[{app_id}] Data completeness check failed (non-blocking): {e}")

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
