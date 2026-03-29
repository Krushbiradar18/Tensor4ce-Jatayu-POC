"""
main.py — FastAPI Application (Refactored v3.1)
=================================================
Developed by Team Tensor4ce:
Yash Agrawal, Karan Panchal, Nesar Wagannawar, Krushnali Biradar


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

# Silence LiteLLM console spam
os.environ["LITELLM_LOG"] = "ERROR"

from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File
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
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# Suppress noise from libraries
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("litellm").setLevel(logging.WARNING)
logging.getLogger("crewai").setLevel(logging.INFO)
logging.getLogger("matplotlib").setLevel(logging.WARNING)


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
    allow_file_fallback = os.environ.get("ALLOW_RUNTIME_FILE_FALLBACK", "false").strip().lower() in {"1", "true", "yes", "on"}
    if allow_file_fallback:
        load_portfolio(f"{data_dir}/portfolio_loans.csv")
        logger.info("Runtime file fallback enabled: loaded portfolio CSV")
    else:
        logger.info("Runtime file fallback disabled: portfolio lookups will use DB only")

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

    # Pre-warm PaddleOCR so the first /api/extract-documents request is fast.
    # PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK skips the slow connectivity probe.
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    try:
        from document_extractor import _get_ocr
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _get_ocr)
        logger.info("✓ PaddleOCR warmed up")
    except Exception as e:
        logger.warning(f"PaddleOCR warm-up skipped: {e}")

    mode = _runtime_mode()
    logger.info(f"✓ System ready | Mode: {mode}")
    yield


# ── App & Middleware ───────────────────────────────────────────────────────────

app = FastAPI(title="ARIA AI (Agentic Risk Intelligence and Analytics)", version="2.4.0", lifespan=lifespan)
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
def submit_application(req: SubmitRequest, background_tasks: BackgroundTasks):
    import uuid
    from datetime import datetime
    from verification.verifier import run_preliminary_identity_precheck

    app_id = f"APP-{uuid.uuid4().hex[:8].upper()}"
    req.form_data["application_id"] = app_id
    
    # Log application submission event
    db.save_application(app_id, req.form_data, req.ip_metadata)
    
    # Check if frontend reported OCR extraction issues
    if req.document_data and req.document_data.get("extraction_failed"):
        db.log_event(app_id, "system", "OCR_EXTRACTION_FAILED", {
            "message": "Frontend reported OCR extraction failure or data mismatch.",
            "error": req.document_data.get("extraction_error", "Unknown error")
        })

    # ── Document identity check (when OCR data is provided) ──────────────────
    if req.document_data:
        from verification.verifier import run_document_identity_check
        doc_passed, doc_reason, doc_flags = run_document_identity_check(
            req.form_data, req.document_data
        )
        if not doc_passed:
            db.log_event(app_id, "system", "DOCUMENT_CHECK_FAILED", {
                "reason": doc_reason, "mismatch_flags": doc_flags,
            })
            doc_decision = {
                "decision_id": f"DEC-{uuid.uuid4().hex[:10].upper()}",
                "application_id": app_id,
                "ai_recommendation": "REJECT",
                "decision_matrix_row": "R0_DOCUMENT_IDENTITY_MISMATCH",
                "conditions": [],
                "max_approvable_amount": None,
                "credit_risk": {}, "fraud": {}, "compliance": {}, "portfolio": {},
                "officer_summary": doc_reason,
                "processing_time_ms": 0,
                "precheck_mismatch_flags": doc_flags,
                "decided_at": datetime.utcnow().isoformat(),
            }
            db.save_decision(doc_decision["decision_id"], app_id, doc_decision)
            db.save_officer_action(app_id, "system_document_check", "REJECTED", doc_reason)
            return {
                "application_id": app_id,
                "status": "REJECTED",
                "message": doc_reason,
                "reason": doc_reason,
                "mismatch_flags": doc_flags,
            }
        db.log_event(app_id, "system", "DOCUMENT_CHECK_PASSED", {})

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



@app.post("/api/test/sample")
def submit_sample_application(background_tasks: BackgroundTasks):
    """
    Submits a sample high-quality application for testing.
    Uses a known-good PAN (RRKDN2234M) to ensure system flow results in Approval/Clearance.
    """
    import uuid
    
    app_id = f"APP-TEST-{uuid.uuid4().hex[:6].upper()}"
    
    # High quality sample data from the dataset
    form_data = {
        "applicant_name": "Aditya Sharma",
        "pan_number": "RRKDN2234M", # Good record in dataset (700+ cibil, low DPD)
        "aadhaar_last4": "5566",
        "date_of_birth": "1990-05-15",
        "gender": "MALE",
        "employment_type": "SALARIED",
        "employer_name": "TCS Ltd",
        "annual_income": 1800000.0,
        "employment_tenure_years": 5.0,
        "loan_amount_requested": 500000.0,
        "loan_tenure_months": 36,
        "loan_purpose": "PERSONAL",
        "existing_emi_monthly": 10000.0,
        "residential_assets_value": 2500000.0,
        "address": {
            "line1": "Flat 402, Sunshine Apts",
            "city": "Mumbai",
            "state": "Maharashtra",
            "pincode": "400001"
        }
    }
    
    ip_metadata = {
        "ip_address": "122.161.10.45",
        "form_fill_seconds": 450.0,
        "device_fingerprint": "dev-test-browser",
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Test/1.0"
    }
    
    db.save_application(app_id, form_data, ip_metadata)
    db.log_event(app_id, "system", "TEST_SAMPLE_SUBMITTED", {"is_test": True})
    
    background_tasks.add_task(_run_bg, app_id, form_data, ip_metadata)
    
    return {
        "success": True,
        "application_id": app_id,
        "status": "PENDING",
        "message": "Sample application (designed for Approval) was submitted successfully.",
        "instructions": f"Check status at /api/status/{app_id} or refresh the Officer Queue."
    }



@app.post("/api/test/rejected")
def submit_rejected_sample_application(background_tasks: BackgroundTasks):
    """
    Submits a sample application designed to be REJECTED.
    Uses a blacklisted PAN defined in dil.py.
    """
    import uuid
    from datetime import datetime
    from verification.verifier import run_preliminary_identity_precheck
    
    app_id = f"APP-TEST-REJECT-{uuid.uuid4().hex[:6].upper()}"
    
    # Fraudulent sample data
    form_data = {
        "applicant_name": "Fraudulent Applicant",
        "pan_number": "ABCDE1234F", # Not in mock bureau records -> will fail pre-check
        "aadhaar_last4": "0000",
        "date_of_birth": "1995-10-10",
        "gender": "MALE",
        "employment_type": "SELF_EMPLOYED",
        "employer_name": "Ghost Comp",
        "annual_income": 300000.0,
        "employment_tenure_years": 0.5,
        "loan_amount_requested": 2000000.0,
        "loan_tenure_months": 12,
        "loan_purpose": "AUTO",
        "existing_emi_monthly": 50000.0,
        "residential_assets_value": 0.0,
        "address": {
            "line1": "Fake St 123",
            "city": "Unknown",
            "state": "Unknown",
            "pincode": "000000"
        }
    }
    
    ip_meta = {
        "ip_address": "1.1.1.1",
        "form_fill_seconds": 10.0,
        "device_fingerprint": "bot-test",
    }
    
    db.save_application(app_id, form_data, ip_meta)
    db.log_event(app_id, "system", "TEST_REJECTED_SUBMITTED", {"is_test": True})

    # Trigger preliminary identity gate:
    passed, reason, mismatch_flags = run_preliminary_identity_precheck(form_data)
    if not passed:
        db.save_officer_action(app_id, "system_precheck", "REJECTED", reason)
        db.log_event(app_id, "system", "PRECHECK_REJECTED", {"reason": reason, "mismatch_flags": mismatch_flags})
        
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
            "decided_at": datetime.utcnow().isoformat(),
        }
        db.save_decision(precheck_decision["decision_id"], app_id, precheck_decision)
        
        return {
            "success": True,
            "application_id": app_id,
            "status": "REJECTED",
            "message": f"Sample REJECTED: {reason}",
            "reason": reason,
            "mismatch_flags": mismatch_flags,
        }
    
    # Fallback in case it somehow passes (e.g. if the PAN was added to mock bureau)
    background_tasks.add_task(_run_bg, app_id, form_data, ip_meta)
    
    return {
        "success": True,
        "application_id": app_id,
        "status": "PENDING",
        "message": "Sample application submitted. Processing started.",
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
def get_status(app_id: str):
    row = db.get_application(app_id)
    if not row:
        raise HTTPException(404, "Application not found")
    status = row["status"]
    messages = {
        "PENDING":                "Application received. We are initializing the verification process.",
        "DIL_PROCESSING":         "Document verification is currently in progress.",
        "AGENTS_RUNNING":         "Our team is performing a comprehensive credit assessment.",
        "DECIDED_PENDING_OFFICER": "Assessment complete. Awaiting final authorization from a loan officer.",
        "OFFICER_ESCALATED":      "Your application requires additional review by our senior underwriters.",
        "VERIFICATION_FAILED":    "We were unable to verify your identity documents. Please contact support.",
        "ERROR":                  "A transmission error occurred. Our team has been notified.",
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
def officer_queue():
    """
    Returns the latest applications for the officer dashboard.
    Synchronous definition allows FastAPI to run it in a threadpool, 
    preventing event-loop starvation during intensive background processing.
    """
    apps = db.list_applications_extended(50)
    app_ids = [a["application_id"] for a in apps]
    bulk_logs = db.get_bulk_audit_logs(app_ids)
    
    for a in apps:
        audit_log = bulk_logs.get(a["application_id"], [])
        a["processing_stage"] = _derive_processing_stage(a.get("status", ""), audit_log)
    return apps



@app.get("/api/officer/decision/{app_id}")
def get_full_decision(app_id: str):
    row = db.get_application(app_id)
    if not row:
        raise HTTPException(404, "Application not found")
    return {
        "application": json.loads(row["raw_payload"]),
        "status":      row["status"],
        "decision":    db.get_decision(app_id),
        "audit_log":   db.get_audit_log(app_id),
    }


@app.post("/api/extract-documents")
async def extract_documents(
    aadhaar: UploadFile = File(None),
    pan: UploadFile = File(None),
):
    """
    Upload Aadhaar and/or PAN PDFs and extract name, Aadhaar number, and PAN number.
    Accepts multipart/form-data with optional fields: aadhaar (PDF), pan (PDF).
    """
    import tempfile, os
    from document_extractor import extract_from_aadhaar_pdf, extract_from_pan_pdf

    result: dict = {"name": None, "aadhaar_number": None, "pan_number": None}
    errors: list[str] = []

    async def _save_upload(upload: UploadFile) -> str:
        """Save an uploaded file to a temp file and return its path."""
        suffix = Path(upload.filename).suffix if upload.filename else ".pdf"
        fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        try:
            os.close(fd)
            content = await upload.read()
            Path(tmp_path).write_bytes(content)
        except Exception:
            os.unlink(tmp_path)
            raise
        return tmp_path

    if not aadhaar and not pan:
        raise HTTPException(status_code=400, detail="Upload at least one file: aadhaar or pan")

    loop = asyncio.get_event_loop()

    # ── Process Aadhaar ───────────────────────────────────────────────────────
    if aadhaar is not None:
        tmp = None
        try:
            tmp = await _save_upload(aadhaar)
            # Run blocking OCR in thread pool so event loop stays responsive
            out = await loop.run_in_executor(None, extract_from_aadhaar_pdf, tmp)
            result["aadhaar_number"] = out.get("aadhaar_number")
            if out.get("name"):
                result["name"] = out["name"]
        except Exception as e:
            logger.exception("Aadhaar extraction failed")
            errors.append(f"aadhaar: {e}")
        finally:
            if tmp and Path(tmp).exists():
                os.unlink(tmp)

    # ── Process PAN ───────────────────────────────────────────────────────────
    if pan is not None:
        tmp = None
        try:
            tmp = await _save_upload(pan)
            out = await loop.run_in_executor(None, extract_from_pan_pdf, tmp)
            result["pan_number"] = out.get("pan_number")
            # PAN name takes precedence (cleaner on most cards)
            if out.get("name"):
                result["name"] = out["name"]
        except Exception as e:
            logger.exception("PAN extraction failed")
            errors.append(f"pan: {e}")
        finally:
            if tmp and Path(tmp).exists():
                os.unlink(tmp)

    return {**result, "errors": errors}



@app.post("/api/officer/action/{app_id}")
def officer_action(app_id: str, action: OfficerAction):
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



@app.post("/api/officer/login")
def login(credentials: dict):
    email = credentials.get("email")
    password = credentials.get("password")
    
    # Simple hardcoded check for PoC
    if email == "admin" and password == "admin123":
        return {
            "success": True, 
            "token": "fake-jwt-token-for-poc",
            "user": {"email": email, "name": "Admin Officer", "role": "Loan Officer"}
        }
    
    raise HTTPException(status_code=401, detail="Invalid credentials")


@app.get("/api/health")
def health():
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
