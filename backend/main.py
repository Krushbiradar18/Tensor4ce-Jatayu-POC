"""
main.py — FastAPI Application (Refactored v3.1)
=================================================
5-Layer Architecture per Tensor4ce Stage 2 Solutioning v3.1:

  Layer 1: Frontend (React) — served as static files
  Layer 2: API Gateway — this file (FastAPI, JWT auth stub, background tasks)
  Layer 3: Verification & Profile — wired via orchestration/crew.py → dil.py
  Layer 4: Agentic Orchestration — CrewAI crew + 4 LangGraph A2A sub-apps
  Layer 5: Data Persistence — db.py (SQLite for PoC, PostgreSQL in prod)

A2A Agent mounts:
  /agents/credit-risk/...   ← CreditRisk LangGraph FastAPI sub-app
  /agents/fraud/...         ← Fraud LangGraph FastAPI sub-app
  /agents/compliance/...    ← Compliance LangGraph FastAPI sub-app
  /agents/portfolio/...     ← Portfolio LangGraph FastAPI sub-app

Run: uvicorn main:app --reload --port 8000
"""
from __future__ import annotations
import os
import json
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from schemas import SubmitRequest, OfficerAction


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR  = Path(__file__).resolve().parent


# ── Environment loading ────────────────────────────────────────────────────────

def _load_local_env() -> None:
    env_path = Path(__file__).with_name(".env")
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key   = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_local_env()

import db


# ── Utilities ──────────────────────────────────────────────────────────────────

def _resolve_config_path(raw_path: str, default_base: Path) -> str:
    path = Path(raw_path)
    if path.is_absolute():
        return str(path)
    for candidate in [
        (default_base / path).resolve(),
        (BACKEND_DIR / path).resolve(),
        (PROJECT_ROOT / path).resolve(),
    ]:
        if candidate.exists():
            return str(candidate)
    return str((default_base / path).resolve())


def _runtime_mode() -> str:
    llm_mode  = os.environ.get("LLM_USAGE_MODE", "FULL").upper()
    has_gemini = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    crewai_enabled = os.environ.get("ENABLE_CREWAI_MANAGER", "false").strip().lower() in {"1", "true", "yes", "on"}
    if llm_mode == "FALLBACK" or not has_gemini or not crewai_enabled:
        return "Direct A2A Pipeline (LangGraph agents)"
    return "CrewAI Hierarchical + LangGraph A2A Agents"


def _derive_processing_stage(status: str, audit_log: list[dict]) -> str:
    if status.startswith("OFFICER_"):
        return "Final decision completed"
    if status == "DECIDED_PENDING_OFFICER":
        return "Awaiting officer action"
    if status == "DIL_PROCESSING":
        return "DIL / document verification in progress"
    if status == "PENDING":
        return "Queued for processing"
    if status == "ERROR":
        return "Processing error"
    if status == "AGENTS_RUNNING":
        agent_map = {
            "credit_risk_graph": "Credit Risk Agent",
            "fraud_graph":       "Fraud Agent",
            "compliance_graph":  "Compliance Agent",
            "portfolio_graph":   "Portfolio Agent",
            "orchestrator":      "Orchestrator",
        }
        for event in reversed(audit_log):
            agent_name = str(event.get("agent_name", "") or "")
            stage_name = agent_map.get(agent_name)
            if not stage_name:
                continue
            payload = event.get("payload", {})
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except Exception:
                    payload = {}
            node = payload.get("node") if isinstance(payload, dict) else None
            return f"{stage_name} ({node})" if node else stage_name
        return "Specialist agents running"
    return "In progress"


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ── Lifespan (startup/shutdown) ────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    data_dir = _resolve_config_path(os.environ.get("DATA_DIR", "data"), BACKEND_DIR)
    from dil import load_static_data
    from agents_base import load_compliance_rules, load_portfolio
    from dataset_loader import load_datasets, get_dataset_stats

    load_static_data(data_dir)
    load_compliance_rules(f"{data_dir}/compliance_rules.yaml")
    load_portfolio(f"{data_dir}/portfolio_loans.csv")

    preload_datasets = os.environ.get("PRELOAD_DATASETS", "true").strip().lower() in {"1", "true", "yes", "on"}
    dataset_dir = _resolve_config_path(os.environ.get("DATASET_DIR", "dataset"), PROJECT_ROOT)
    os.environ["DATASET_DIR"] = dataset_dir

    if preload_datasets:
        logger.info("Loading datasets from Excel files...")
        load_datasets(dataset_dir)
        stats = get_dataset_stats()
        logger.info(f"✓ Datasets loaded: CIBIL={stats['cibil_records']}, Bank={stats['bank_records']}, Merged={stats['merged_records']}")
    else:
        logger.info("Skipping dataset preload (PRELOAD_DATASETS=false)")

    mode = _runtime_mode()
    logger.info(f"✓ System ready | Mode: {mode}")
    yield


# ── App & Middleware ───────────────────────────────────────────────────────────

app = FastAPI(title="Tensor4ce Credit AI", version="3.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── Mount A2A Agent Sub-Apps (Layer 4) ────────────────────────────────────────
# Each LangGraph specialist agent is a FastAPI sub-app with:
#   GET  /.well-known/agent.json   → Agent Card
#   POST /a2a/tasks/send           → Execute agent pipeline

try:
    from agents.credit_risk.app import app as credit_risk_app
    app.mount("/agents/credit-risk", credit_risk_app)
    logger.info("✓ Credit Risk Agent mounted at /agents/credit-risk")
except Exception as e:
    logger.warning(f"Credit Risk Agent not mounted: {e}")

try:
    from agents.fraud.app import app as fraud_app
    app.mount("/agents/fraud", fraud_app)
    logger.info("✓ Fraud Agent mounted at /agents/fraud")
except Exception as e:
    logger.warning(f"Fraud Agent not mounted: {e}")

try:
    from agents.compliance.app import app as compliance_app
    app.mount("/agents/compliance", compliance_app)
    logger.info("✓ Compliance Agent mounted at /agents/compliance")
except Exception as e:
    logger.warning(f"Compliance Agent not mounted: {e}")

try:
    from agents.portfolio.app import app as portfolio_app
    app.mount("/agents/portfolio", portfolio_app)
    logger.info("✓ Portfolio Agent mounted at /agents/portfolio")
except Exception as e:
    logger.warning(f"Portfolio Agent not mounted: {e}")


# ── Mount Mock APIs ────────────────────────────────────────────────────────────

try:
    from mock_apis.portfolio import router as portfolio_mock_router
    app.include_router(portfolio_mock_router)
    logger.info("✓ Portfolio mock API mounted at /mock/bank/portfolio-summary")
except Exception as e:
    logger.warning(f"Portfolio mock API not mounted: {e}")


# ── Serve Frontend ─────────────────────────────────────────────────────────────

frontend_dir = Path(__file__).parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

    @app.get("/", include_in_schema=False)
    async def root():
        return FileResponse(str(frontend_dir / "index.html"))


# ── API Endpoints ──────────────────────────────────────────────────────────────

@app.post("/api/apply")
async def submit_application(req: SubmitRequest, background_tasks: BackgroundTasks):
    import uuid
    from datetime import datetime
    from verification.verifier import run_preliminary_identity_precheck

    app_id = f"APP-{uuid.uuid4().hex[:8].upper()}"
    req.form_data["application_id"] = app_id
    db.save_application(app_id, req.form_data, req.ip_metadata)

    # Preliminary identity gate before orchestration/agents:
    # name (simple check) + PAN + Aadhaar against mock_bureau_records.
    passed, reason, mismatch_flags = run_preliminary_identity_precheck(req.form_data)
    if not passed:
        db.save_officer_action(app_id, "system_precheck", "REJECTED", reason)
        db.log_event(
            app_id,
            "system",
            "PRECHECK_REJECTED",
            {
                "reason": reason,
                "mismatch_flags": mismatch_flags,
            },
        )
        precheck_decision = {
            "decision_id": f"DEC-{uuid.uuid4().hex[:10].upper()}",
            "application_id": app_id,
            "ai_recommendation": "REJECT",
            "decision_matrix_row": "R0_PRECHECK_IDENTITY_MISMATCH",
            "conditions": [],
            "max_approvable_amount": None,
            "credit_risk": {},
            "fraud": {},
            "compliance": {},
            "portfolio": {},
            "officer_summary": reason,
            "processing_time_ms": 0,
            "precheck_mismatch_flags": mismatch_flags,
            "decided_at": datetime.utcnow().isoformat(),
        }
        db.save_decision(precheck_decision["decision_id"], app_id, precheck_decision)
        return {
            "application_id": app_id,
            "status": "REJECTED",
            "message": reason,
            "reason": reason,
            "mismatch_flags": mismatch_flags,
        }

    db.log_event(app_id, "system", "PRECHECK_PASSED", {})
    background_tasks.add_task(_run_bg, app_id, req.form_data, req.ip_metadata)
    return {
        "application_id": app_id,
        "status": "PENDING",
        "message": "Application received. Processing started.",
    }


async def _run_bg(app_id: str, form_data: dict, ip_meta: dict):
    try:
        # Use the new CrewAI orchestration layer
        from orchestration.crew import run_crew_pipeline
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, run_crew_pipeline, app_id, form_data, ip_meta)
    except Exception as e:
        logger.exception(f"Pipeline error for {app_id}: {e}")
        db.update_status(app_id, "ERROR")
        db.log_event(app_id, "system", "ERROR", {"error": str(e)})


@app.get("/api/status/{app_id}")
async def get_status(app_id: str):
    row = db.get_application(app_id)
    if not row:
        raise HTTPException(404, "Application not found")
    status = row["status"]
    messages = {
        "PENDING":                "Application received. We will review it shortly.",
        "DIL_PROCESSING":         "We are verifying your submitted documents. This usually takes a few minutes.",
        "AGENTS_RUNNING":         "Your application is being assessed by our credit team. This typically takes 2–4 hours.",
        "DECIDED_PENDING_OFFICER": "Your assessment is complete. A loan officer will review shortly.",
        "OFFICER_ESCALATED":      "Your application requires additional specialist review. We will update you within 24 hours.",
        "VERIFICATION_FAILED":    "We were unable to verify your identity documents. Please contact our helpline.",
        "ERROR":                  "We encountered an issue. Please contact support.",
    }
    result = {"application_id": app_id, "status": status}
    if status.startswith("OFFICER_"):
        action = db.get_officer_action(app_id)
        if action:
            result["officer_decision"] = action["decision"]
            result["officer_reason"]   = action["reason"]
            result["actioned_at"]      = action["acted_at"]
    else:
        result["message"] = messages.get(status, "Processing your application.")
    return result


@app.get("/api/officer/queue")
async def officer_queue():
    apps = db.list_applications(50)
    for a in apps:
        d = db.get_decision(a["application_id"])
        a["ai_recommendation"] = d.get("ai_recommendation") if d else None
        a["processing_ms"]     = d.get("processing_time_ms") if d else None
        try:
            audit_log = db.get_audit_log(a["application_id"])
        except Exception:
            audit_log = []
        a["processing_stage"] = _derive_processing_stage(a.get("status", ""), audit_log)
    return apps


@app.get("/api/officer/decision/{app_id}")
async def get_full_decision(app_id: str):
    row = db.get_application(app_id)
    if not row:
        raise HTTPException(404, "Application not found")
    return {
        "application": json.loads(row["raw_payload"]),
        "status":      row["status"],
        "decision":    db.get_decision(app_id),
        "audit_log":   db.get_audit_log(app_id),
    }


@app.post("/api/officer/action/{app_id}")
async def officer_action(app_id: str, action: OfficerAction):
    row = db.get_application(app_id)
    if not row:
        raise HTTPException(404, "Application not found")
    valid = {"APPROVED", "REJECTED", "CONDITIONAL", "ESCALATED"}
    if action.decision.upper() not in valid:
        raise HTTPException(400, f"Decision must be one of {valid}")
    db.save_officer_action(app_id, action.officer_id, action.decision.upper(), action.reason)
    db.log_event(app_id, "officer", "OFFICER_ACTION",
                 {"decision": action.decision, "officer": action.officer_id})
    return {"success": True, "application_id": app_id, "decision": action.decision}


@app.get("/api/health")
async def health():
    from dil import _BLACKLIST
    from agents_base import _PORTFOLIO, _RULES
    from dataset_loader import get_dataset_stats
    from llm_config import get_llm_stats, get_llm_usage_mode

    # Skip synchronous self-calls in health check to avoid deadlocks on single-worker uvicorn
    agent_cards = {"credit_risk": "mounted", "fraud": "mounted", "compliance": "mounted", "portfolio": "mounted"}

    response = {
        "status":            "ok",
        "mode":              _runtime_mode(),
        "blacklist_pans":    len(_BLACKLIST),
        "portfolio_loans":   len(_PORTFOLIO),
        "compliance_rules":  len(_RULES),
        "a2a_agents":        agent_cards,
    }

    try:
        response["datasets"] = get_dataset_stats()
    except Exception:
        response["datasets"] = {"error": "Dataset loader not initialized"}

    try:
        response["llm_usage"] = get_llm_stats()
    except Exception:
        response["llm_usage"] = {"mode": get_llm_usage_mode()}

    return response
