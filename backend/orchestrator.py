"""
orchestrator.py — CrewAI Orchestrator
=======================================
Architecture:
  CrewAI manager agent  → has AGENT RUNNER tools (each runs a LangGraph graph)
  LangGraph graphs      → nodes call DATA tools internally
  A2A store             → AGENT_OUTPUTS dict, shared between all graphs

How it works:
  1. CrewAI manager receives the application ID and task description
  2. Manager (LLM) autonomously decides to call agent runner tools one by one
  3. Each agent runner tool invokes the corresponding LangGraph StateGraph
  4. LangGraph graphs use data tools (feature fetch, bureau, macro, etc.) in their nodes
  5. Graph outputs are stored in AGENT_OUTPUTS (A2A store)
  6. Manager calls apply_decision_matrix_tool to get the final decision
  7. FinalDecision is returned

Fallback (no Gemini API key):
  Pipeline runs graphs directly in sequence without LLM orchestration.
  All agent outputs are still produced; only the manager reasoning step is skipped.
"""
from __future__ import annotations
import os, json, time, uuid, logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


def _has_gemini() -> bool:
    if os.environ.get("LLM_USAGE_MODE", "FULL").upper() == "FALLBACK":
        return False
    if os.environ.get("ENABLE_CREWAI_MANAGER", "false").strip().lower() not in {"1", "true", "yes", "on"}:
        return False
    provider = os.environ.get("CREWAI_LLM_PROVIDER", "gemini").strip().lower()
    if provider == "vertex":
        has_project = bool(os.environ.get("VERTEX_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT"))
        has_location = bool(os.environ.get("VERTEX_LOCATION") or os.environ.get("GOOGLE_CLOUD_LOCATION"))
        has_creds = bool(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"))
        return has_project and has_location and has_creds
    return bool(os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", ""))


def _build_llm():
    """Build the Gemini LLM for CrewAI."""
    from crewai import LLM

    provider = os.environ.get("CREWAI_LLM_PROVIDER", "gemini").strip().lower()
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash-exp")

    extra_kwargs = {}
    if provider == "vertex":
        if "/" not in model:
            model = f"vertex_ai/{model}"
        extra_kwargs["vertex_project"] = os.environ.get("VERTEX_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")
        extra_kwargs["vertex_location"] = os.environ.get("VERTEX_LOCATION") or os.environ.get("GOOGLE_CLOUD_LOCATION") or "us-central1"
    else:
        # CrewAI/LiteLLM expect explicit provider prefix for Gemini models.
        if "/" not in model:
            model = f"gemini/{model}"

    if api_key:
        os.environ.setdefault("GOOGLE_API_KEY", api_key)

    return LLM(
        model=model,
        api_key=api_key,
        temperature=0.1,
        **extra_kwargs,
    )


# ── CrewAI Orchestration (used when Gemini is available) ─────────────────────

def run_via_crewai(app_id: str) -> dict:
    """
    Run the full orchestration via CrewAI manager agent.
    The LLM manager autonomously decides when and how to call each specialist graph.
    """
    from crewai import Agent, Task, Crew, Process
    from tools import MANAGER_TOOLS, DATA_TOOLS, _log_event

    llm = _build_llm()

    # ── Manager Agent ─────────────────────────────────────────────────────────
    manager = Agent(
        role="Chief Credit Underwriting AI",
        goal=(
            "Thoroughly assess every loan application by coordinating specialist agents, "
            "synthesising their findings, and producing a fair, explainable, RBI-compliant decision."
        ),
        backstory=(
            "You are the Chief Credit Underwriting AI at a leading Indian bank. "
            "You have access to four specialist AI agents: Credit Risk, Fraud Detection, "
            "Compliance Verification, and Portfolio Analysis. Each is a LangGraph-powered "
            "specialist. You call them via tools, analyse their outputs, and make a final "
            "credit decision. You are methodical, fair, and fully RBI-compliant."
        ),
        tools=MANAGER_TOOLS,
        llm=llm,
        verbose=True,
        allow_delegation=False,
        max_iter=15,
    )

    # ── Orchestration Task ────────────────────────────────────────────────────
    task = Task(
        description=f"""
Assess loan application ID: {app_id}

You must call these tools in order:
1. run_credit_risk_assessment(application_id="{app_id}")
2. run_fraud_detection(application_id="{app_id}")
3. run_compliance_check(application_id="{app_id}")
4. run_portfolio_analysis(application_id="{app_id}")  [uses credit output via A2A]
5. apply_decision_matrix_tool(application_id="{app_id}")  [synthesises all outputs]

After calling all tools, return the JSON from apply_decision_matrix_tool as your final answer.

Decision rules (apply_decision_matrix_tool handles these automatically):
- Compliance BLOCK or Fraud HIGH_RISK or Credit VERY_HIGH → REJECT
- Credit HIGH risk → ESCALATE
- Fraud SUSPICIOUS → ESCALATE
- Compliance warnings / CAUTION → CONDITIONAL
- All clear → APPROVE

Log your start and completion using log_audit_tool.
""",
        expected_output=(
            "A JSON object containing the complete FinalDecision with fields: "
            "decision_id, application_id, ai_recommendation (APPROVE/CONDITIONAL/REJECT/ESCALATE), "
            "decision_matrix_row, conditions (list), credit_risk output, fraud output, "
            "compliance output, portfolio output, and officer_summary."
        ),
        agent=manager,
    )

    # ── Crew kickoff ──────────────────────────────────────────────────────────
    crew = Crew(
        agents=[manager],
        tasks=[task],
        process=Process.sequential,
        verbose=True,
    )

    _log_event(app_id, "orchestrator", "CREWAI_START", {"mode": "crewai_manager"})
    raw_result = crew.kickoff(inputs={"application_id": app_id})
    _log_event(app_id, "orchestrator", "CREWAI_COMPLETE", {})

    # Extract JSON from CrewAI's text output
    result_text = str(raw_result)
    try:
        # Try to find JSON block in the output
        json_match = None
        for pattern in [r'\{.*"ai_recommendation".*\}', r'\{.*"decision_id".*\}']:
            import re
            m = re.search(pattern, result_text, re.DOTALL)
            if m:
                json_match = m.group(0)
                break
        if json_match:
            return json.loads(json_match)
    except Exception:
        pass

    # If JSON parsing fails, build from A2A store directly
    logger.warning("Could not parse CrewAI JSON output — building from A2A store")
    from crew_runner import build_final_decision
    return build_final_decision(app_id)


# ── Direct Pipeline Fallback (no Gemini needed) ───────────────────────────────

def run_direct_pipeline(app_id: str) -> dict:
    """
    Run all specialist agents directly in sequence using REAL LangGraph agents.

    New Architecture:
    - Calls the actual LangGraph agents from separate folders
    - Credit Risk: credit_backend/credit_risk_agent.py (RandomForest + SHAP)
    - Fraud Detection: Fraud-Agent/fraud_agent.py (IsolationForest + Rules)
    - Compliance: compliance_agent/agent.py (RBI checks + AML + LLM)
    - Portfolio: Keep existing graph (unchanged)
    """
    from tools import _log_event, set_agent_output, get_agent_output
    from agent_adapters import (
        call_credit_agent, call_fraud_agent, call_compliance_agent, call_portfolio_agent
    )
    from crew_runner import build_final_decision
    from dil import get_context

    _log_event(app_id, "orchestrator", "DIRECT_START", {"mode": "real_langgraph_agents"})

    ctx = get_context(app_id)
    if not ctx:
        logger.error(f"[{app_id}] ApplicationContext not found in FeatureStore")
        raise ValueError(f"ApplicationContext not found for {app_id}")

    # ── 1. Credit Risk Agent (Real ML Model) ──────────────────────────────────
    logger.info(f"[{app_id}] Running Credit Risk Agent (RandomForest + Gemini LLM)...")
    try:
        credit_out = call_credit_agent(ctx)
        set_agent_output(app_id, "credit", credit_out)
        logger.info(f"[{app_id}] ✓ Credit: {credit_out.get('risk_band')} | Score={credit_out.get('credit_score', 0):.4f}")
    except Exception as e:
        logger.exception(f"[{app_id}] Credit agent failed: {e}")
        # Fallback is already handled in the adapter
        credit_out = get_agent_output(app_id, "credit") or {
            "application_id": app_id,
            "credit_score": 0.05,
            "risk_band": "MEDIUM",
            "error": str(e),
        }
        set_agent_output(app_id, "credit", credit_out)

    # ── 2. Fraud Detection Agent (Real IsolationForest) ──────────────────────
    logger.info(f"[{app_id}] Running Fraud Detection Agent (IsolationForest + SHAP)...")
    try:
        fraud_out = call_fraud_agent(ctx)
        set_agent_output(app_id, "fraud", fraud_out)
        logger.info(f"[{app_id}] ✓ Fraud: {fraud_out.get('fraud_level')} | Prob={fraud_out.get('fraud_probability', 0):.4f}")
    except Exception as e:
        logger.exception(f"[{app_id}] Fraud agent failed: {e}")
        fraud_out = {
            "application_id": app_id,
            "fraud_level": "CLEAN",
            "fraud_probability": 0.0,
            "error": str(e),
        }
        set_agent_output(app_id, "fraud", fraud_out)

    # ── 3. Compliance Agent (Real RBI Checks + Gemini) ───────────────────────
    logger.info(f"[{app_id}] Running Compliance Agent (RBI + AML + Fairness)...")
    try:
        comp_out = call_compliance_agent(ctx, credit_out, fraud_out)
        set_agent_output(app_id, "compliance", comp_out)
        logger.info(f"[{app_id}] ✓ Compliance: {comp_out.get('overall_status')}")
    except Exception as e:
        logger.exception(f"[{app_id}] Compliance agent failed: {e}")
        comp_out = {
            "application_id": app_id,
            "overall_status": "PASS",
            "error": str(e),
        }
        set_agent_output(app_id, "compliance", comp_out)

    # ── 4. Portfolio Agent (Proper A2A call) ──────────────────────────────
    logger.info(f"[{app_id}] Running Portfolio Agent via A2A adapter...")
    try:
        port_out = call_portfolio_agent(ctx, credit_out)
        set_agent_output(app_id, "portfolio", port_out)
        logger.info(f"[{app_id}] ✓ Portfolio: {port_out.get('portfolio_recommendation')}")
    except Exception as e:
        logger.exception(f"[{app_id}] Portfolio agent failed: {e}")
        port_out = {
            "application_id": app_id,
            "portfolio_recommendation": "ACCEPT",
            "error": str(e),
        }
        set_agent_output(app_id, "portfolio", port_out)

    # ── 5. Apply Decision Matrix ──────────────────────────────────────────────
    logger.info(f"[{app_id}] Applying decision matrix...")
    result = build_final_decision(app_id)

    _log_event(app_id, "orchestrator", "REAL_AGENTS_COMPLETE",
               {"decision": result.get("ai_recommendation")})
    return result


# ── Main Entry Point ──────────────────────────────────────────────────────────

def run_pipeline(app_id: str, form_data: dict, ip_meta: dict) -> dict:
    """
    Complete pipeline: DIL → [CrewAI+LangGraph | Direct LangGraph] → FinalDecision.

    If GEMINI_API_KEY is set:
        CrewAI manager agent (Gemini 2.0 Flash) autonomously orchestrates
        the 4 LangGraph specialist agents via MCP tool calls.
    Else:
        4 LangGraph graphs run directly in sequence (same output, no LLM manager).
    """
    import db
    from dil import run_dil_pipeline, load_static_data
    from agents_base import load_compliance_rules, load_portfolio

    t0 = time.time()

    # One-time data loading (idempotent)
    data_dir = os.environ.get("DATA_DIR", "data")
    load_static_data(data_dir)
    load_compliance_rules(f"{data_dir}/compliance_rules.yaml")
    load_portfolio(f"{data_dir}/portfolio_loans.csv")

    # Step 1: Data Intelligence Layer
    db.update_status(app_id, "DIL_PROCESSING")
    logger.info(f"[{app_id}] DIL starting...")
    ctx = run_dil_pipeline(app_id, form_data, ip_meta)
    logger.info(f"[{app_id}] DIL complete. Flags: {[f.flag_code for f in ctx.validation_flags]}")

    # Step 2: Agentic orchestration
    db.update_status(app_id, "AGENTS_RUNNING")

    if _has_gemini():
        logger.info(f"[{app_id}] Mode: CrewAI + LangGraph (Gemini available)")
        try:
            result = run_via_crewai(app_id)
        except Exception as e:
            logger.error(f"CrewAI failed ({e}), falling back to direct pipeline")
            result = run_direct_pipeline(app_id)
    else:
        logger.info(f"[{app_id}] Mode: Direct LangGraph (no Gemini key — set GEMINI_API_KEY for full agentic mode)")
        result = run_direct_pipeline(app_id)

    # Add timing
    result["processing_time_ms"] = round((time.time() - t0) * 1000, 1)

    # Persist
    db.save_decision(result["decision_id"], app_id, result)
    db.update_status(app_id, "DECIDED_PENDING_OFFICER")

    logger.info(f"[{app_id}] Pipeline complete: {result.get('ai_recommendation')} in {result['processing_time_ms']:.0f}ms")
    return result
