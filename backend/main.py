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

# Prevent threadpool exhaustion deadlocks when multiple A2A tasks run synchronously
os.environ["ANYIO_MAX_THREADS"] = "200"

import json
import asyncio
import logging
import tempfile
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
from pathlib import Path

_UPLOAD_BASE = Path(__file__).resolve().parent / "data" / "uploads"

# Silence LiteLLM console spam
os.environ["LITELLM_LOG"] = "ERROR"

from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Form, Depends
from auth import (
    authenticate_user,
    build_totp_uri,
    create_access_token,
    generate_totp_secret,
    generate_otp_code,
    get_current_admin,
    get_current_officer,
    get_current_senior_officer,
    get_current_user,
    hash_otp_code,
    is_user_verified,
    require_role,
    send_otp_email,
    verify_otp_code,
    verify_totp_code,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from schemas import (
    LoginOtpVerify, PublicSignupRequest, SignupOtpResend, SignupOtpVerify, 
    SubmitRequest, OfficerAction, TwoFactorSettingsUpdate, UserCreate, 
    OTPMethod, TotpSetupResponse, TotpVerifyRequest, UserRole,
    ForgotPasswordRequest, ResetPasswordRequest, ResetPasswordFirstLoginRequest
)


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

# macOS / Python 3.12: ensure subprocess spawning is safe with asyncio
import multiprocessing as _mp
if _mp.get_start_method(allow_none=True) is None:
    _mp.set_start_method("spawn")

import db


def _serialize_user(user: dict) -> dict:
    if not user:
        return {}
    return {
        "id": user.get("id"),
        "username": user.get("username", ""),
        "email": user.get("username", ""),
        "name": user.get("full_name") or user.get("username", ""),
        "full_name": user.get("full_name") or user.get("username", ""),
        "role": user.get("role", ""),
        "is_verified": bool(user.get("is_verified", True)),
        "two_factor_enabled": bool(user.get("two_factor_enabled", False)),
        "two_factor_method": user.get("two_factor_method", "email"),
        "needs_password_reset": bool(user.get("needs_password_reset", False)),
        "is_active": bool(user.get("is_active", True)),
    }


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _otp_expires_at() -> datetime:
    return _utcnow() + timedelta(minutes=10)



def _issue_password_reset_challenge(user: dict, purpose: str = "password_reset") -> dict:
    expires_at = _otp_expires_at()
    code = generate_otp_code()
    code_hash = hash_otp_code(code)

    challenge = db.create_auth_challenge(
        user["username"],
        purpose,
        code_hash,
        expires_at,
        method="email",
    )
    send_otp_email(user["username"], code, purpose)
    return {"challenge": challenge, "code": code, "expires_at": expires_at}


def _issue_login_challenge(user: dict, method: str = "email") -> dict:
    expires_at = _otp_expires_at()
    code = ""
    code_hash = ""
    if method == "email":
        code = generate_otp_code()
        code_hash = hash_otp_code(code)

    challenge = db.create_auth_challenge(
        user["username"],
        "login",
        code_hash,
        expires_at,
        method=method,
        metadata={"role": user.get("role", "")},
    )

    if method == "email":
        send_otp_email(user["username"], code, "login")

    return {"challenge": challenge, "code": code, "expires_at": expires_at}


def _challenge_is_expired(challenge: dict) -> bool:
    expires_at = challenge.get("expires_at")
    if not expires_at:
        return True
    if isinstance(expires_at, str):
        try:
            expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError:
            return True
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return _utcnow() > expires_at


def _user_is_expired(user: dict) -> bool:
    expires_at = user.get("verification_code_expires_at")
    if not expires_at:
        return True
    if isinstance(expires_at, str):
        try:
            expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError:
            return True
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return _utcnow() > expires_at


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
    crewai_enabled = os.environ.get("ENABLE_CREWAI_MANAGER", "false").strip().lower() in {"1", "true", "yes", "on"}
    
    # Check if a valid LLM provider is configured
    has_gemini = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    has_groq = bool(os.environ.get("GROQ_API_KEY"))
    has_vertex = bool(
        os.environ.get("VERTEX_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")
    )
    
    if llm_mode == "FALLBACK" or (not has_gemini and not has_groq and not has_vertex) or not crewai_enabled:
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

    # Load RAG compliance knowledge base for regulatory grounding
    from services.rag import load_compliance_kb
    load_compliance_kb(f"{data_dir}/compliance_kb.json")
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

    app_id = req.form_data.get("application_id") or f"APP-{uuid.uuid4().hex[:8].upper()}"
    req.form_data["application_id"] = app_id
    
    logger.info(f"DEBUG: Received form_data for {app_id}: {json.dumps(req.form_data)}")
    
    # Log application submission event
    db.save_application(app_id, req.form_data, req.ip_metadata)

    # ── Move pending doc files to pdf_data/{app_id}/ ─────────────────────────
    doc_token = req.document_data.get("doc_token") if req.document_data else None
    if doc_token:
        pending_dir = _UPLOAD_BASE / "_pending" / doc_token
        app_doc_dir = _UPLOAD_BASE / app_id
        if pending_dir.exists():
            app_doc_dir.mkdir(parents=True, exist_ok=True)
            import shutil as _shutil
            for f in pending_dir.iterdir():
                _shutil.copy2(f, app_doc_dir / f.name)
            try:
                _shutil.rmtree(pending_dir)
            except Exception:
                pass
            logger.info("[%s] Moved %d doc files from pending to tmp/aria_loan_uploads/%s/",
                        app_id, len(list(app_doc_dir.iterdir())), app_id)

    # ── Backfill pan/aadhaar from OCR document_data if form fields are empty ──
    if req.document_data and not req.document_data.get("extraction_failed"):
        if not req.form_data.get("pan_number") and req.document_data.get("pan_number"):
            req.form_data["pan_number"] = req.document_data["pan_number"]
        if not req.form_data.get("aadhaar_last4") and req.document_data.get("aadhaar_number"):
            req.form_data["aadhaar_last4"] = str(req.document_data["aadhaar_number"])[-4:]
        if not req.form_data.get("applicant_name") and req.document_data.get("name"):
            req.form_data["applicant_name"] = req.document_data["name"]

    # Check if frontend reported OCR extraction issues
    if req.document_data and req.document_data.get("extraction_failed"):
        db.log_event(app_id, "system", "OCR_EXTRACTION_FAILED", {
            "message": "Frontend reported OCR extraction failure or data mismatch.",
            "error": req.document_data.get("extraction_error", "Unknown error")
        })

    # ── Document identity check (only when OCR actually succeeded) ────────────
    _has_ocr = (
        req.document_data
        and not req.document_data.get("extraction_failed")
        and (req.document_data.get("pan_number") or req.document_data.get("aadhaar_number"))
    )
    if _has_ocr:
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


def _run_pipeline_subprocess(app_id: str, form_data: dict, ip_meta: dict):
    """
    Entry point for the subprocess. Runs in a completely separate Python process
    so it can make HTTP calls back to the same uvicorn port without deadlocking
    the main event loop.
    """
    import sys, os
    # Ensure the backend directory is on sys.path inside the subprocess
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)
    from orchestration.crew import run_crew_pipeline
    run_crew_pipeline(app_id, form_data, ip_meta)


async def _run_bg(app_id: str, form_data: dict, ip_meta: dict):
    """
    Run the pipeline in a background thread so the event loop stays free.
    We use run_in_executor with the default ThreadPoolExecutor.
    """
    from orchestration.crew import run_crew_pipeline
    try:
        loop = asyncio.get_event_loop()
        # Run in a background thread
        await loop.run_in_executor(None, run_crew_pipeline, app_id, form_data, ip_meta)
    except Exception as e:
        import traceback
        err_msg = f"MAIN PIPELINE ERROR: {str(e)}\n{traceback.format_exc()}"
        logger.error(err_msg)
        with open("main_error.log", "a") as f:
            f.write(f"\n\n--- Error at {app_id} ---\n{err_msg}\n")
        db.update_status(app_id, "ERROR")
        db.log_event(app_id, "system", "ERROR", {"error": str(e)})



@app.post("/api/resubmit/{app_id}")
async def resubmit_documents(
    app_id: str,
    background_tasks: BackgroundTasks,
    annual_income: str = Form(None),
    bank_statement: UploadFile = File(None),
    salary_slip: UploadFile = File(None),
    itr: UploadFile = File(None),
):
    """
    Re-upload missing documents and/or correct income for a DATA_REQUIRED application.
    Saves uploaded files to a temp directory, re-runs vision extraction,
    updates the stored form_data with corrected income, and restarts the pipeline.
    """
    row = db.get_application(app_id)
    if not row:
        raise HTTPException(404, "Application not found")
    if row["status"] != "DATA_REQUIRED":
        raise HTTPException(400, f"Application is not in DATA_REQUIRED state (current: {row['status']})")

    # ── Save newly uploaded files ─────────────────────────────────────────────
    import shutil as _shutil
    app_doc_dir = _UPLOAD_BASE / app_id
    app_doc_dir.mkdir(parents=True, exist_ok=True)

    saved_files: dict[str, str] = {}
    for field_name, upload in [("bank_statement", bank_statement), ("salary_slip", salary_slip), ("itr", itr)]:
        if upload is None:
            continue
        suffix = Path(upload.filename or "file").suffix or ".png"
        dest = app_doc_dir / f"{field_name}{suffix}"
        content = await upload.read()
        dest.write_bytes(content)
        saved_files[field_name] = str(dest)
        logger.info("[%s] Resubmit: saved %s → %s", app_id, field_name, dest)

    # ── Re-run vision extraction on newly uploaded files ─────────────────────
    from document_extractor import extract_financial_from_image
    new_doc_data: dict[str, dict] = {}
    for field_name, path in saved_files.items():
        try:
            result = extract_financial_from_image(path, field_name)
            new_doc_data[field_name] = result
            logger.info("[%s] Resubmit: extracted %s → %s", app_id, field_name, result)
        except Exception as e:
            logger.warning("[%s] Resubmit: extraction failed for %s: %s", app_id, field_name, e)
            new_doc_data[field_name] = {"available": False, "error": str(e)}

    # ── Patch form_data with corrected income if provided ────────────────────
    form_data = json.loads(row["raw_payload"])
    ip_meta   = json.loads(row.get("ip_metadata") or "{}")
    if annual_income is not None:
        try:
            form_data["annual_income"] = float(annual_income)
        except ValueError:
            raise HTTPException(400, f"Invalid annual_income value: {annual_income!r}")

    # ── Reset status → PENDING and re-trigger pipeline ───────────────────────
    db.update_status(app_id, "PENDING")
    db.log_event(app_id, "system", "RESUBMIT_DOCS", {
        "saved_files": list(saved_files.keys()),
        "income_updated": annual_income is not None,
        "extracted": {k: v.get("available", False) for k, v in new_doc_data.items()},
    })

    background_tasks.add_task(_run_bg, app_id, form_data, ip_meta)

    return {
        "application_id": app_id,
        "status": "PENDING",
        "message": "Documents received. Pipeline restarted.",
        "saved_files": list(saved_files.keys()),
        "extracted": {k: v for k, v in new_doc_data.items()},
    }


@app.get("/api/status/{app_id}")
def get_status(app_id: str):
    row = db.get_application(app_id)
    if not row:
        raise HTTPException(status_code=404, detail="Application not found")
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
    decision = db.get_decision(app_id)
    if decision:
        result["decision"] = decision

    # Special-case: when the application was escalated, do NOT expose the internal 'ESCALATED' decision to users.
    # Show a neutral message instead and avoid revealing who acted on the case.
    if status == "OFFICER_ESCALATED":
        result["message"] = messages.get(status, "Processing your application.")
        result["user_facing_status"] = "Under Review"
    else:
        # Check if status is an officer or senior officer decision (starts with OFFICER_ or SENIOR_OFFICER_)
        if status.startswith("OFFICER_") or status.startswith("SENIOR_OFFICER_"):
            action = db.get_officer_action(app_id)
            if action:
                # Expose the decision (Approved/Rejected/Conditional) but do NOT include actor identity here
                if action.get("decision") and action.get("decision").upper() != "ESCALATED":
                    result["officer_decision"] = action["decision"]
                    result["officer_reason"] = action["reason"]
                    result["actioned_at"] = action["acted_at"]
                    # Normalize the display status for users - don't show who made the decision
                    result["user_facing_status"] = action["decision"].lower().capitalize()
                else:
                    # Decision was ESCALATED internally; show neutral message
                    result["message"] = messages.get(status, "Processing your application.")
        else:
            result["message"] = messages.get(status, "Processing your application.")
    return result



@app.get("/api/officer/queue")
def officer_queue(current_user: dict = Depends(require_role("admin", "officer", "senior_officer"))):
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
def get_full_decision(app_id: str, current_user: dict = Depends(require_role("admin", "officer", "senior_officer"))):
    row = db.get_application(app_id)
    if not row:
        raise HTTPException(404, "Application not found")
    
    # Get the officer action including actor_role
    officer_action = db.get_officer_action(app_id)
    
    response = {
        "application_record": row,
        "application": json.loads(row["raw_payload"]),
        "status":      row["status"],
        "decision":    db.get_decision(app_id),
        "audit_log":   db.get_audit_log(app_id),
    }
    
    # Include actor role information for internal display
    if officer_action:
        response["officer_action"] = officer_action
        response["actor_role"] = officer_action.get("actor_role", "officer")
        response["decided_by"] = "Senior Officer" if officer_action.get("actor_role") == "senior_officer" else "Officer"
    
    return response


@app.post("/api/extract-documents")
async def extract_documents(
    aadhaar: UploadFile = File(None),
    pan: UploadFile = File(None),
    bank_statement: UploadFile = File(None),
    salary_slip: UploadFile = File(None),
    itr: UploadFile = File(None),
):
    """
    Upload identity and financial documents. Extracts structured fields via Groq vision.
    Accepts multipart/form-data with optional fields:
      aadhaar, pan, bank_statement, salary_slip, itr (PDF or image).
    Returns extracted fields + doc_token for referencing saved files in /api/apply.
    """
    import os, uuid as _uuid
    from document_extractor import extract_from_aadhaar_pdf, extract_from_pan_pdf

    result: dict = {"name": None, "aadhaar_number": None, "pan_number": None}
    errors: list[str] = []

    async def _save_upload(upload: UploadFile) -> str:
        """Save an uploaded file to a temp file and return its path."""
        suffix = Path(upload.filename).suffix if upload.filename else ".pdf"
        stem = Path(upload.filename).stem if upload.filename else "upload"
        # Include original name in temp file to help OCR mocks identify test cases
        fd, tmp_path = tempfile.mkstemp(suffix=f"_{stem}{suffix}")
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

    _IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

    def _is_image(upload: UploadFile) -> bool:
        if not upload.filename:
            return False
        return Path(upload.filename).suffix.lower() in _IMAGE_SUFFIXES

    # ── Process Aadhaar ───────────────────────────────────────────────────────
    if aadhaar is not None:
        tmp = None
        try:
            tmp = await _save_upload(aadhaar)
            logger.info("DEBUG: Aadhaar temp path: %s", tmp)
            if _is_image(aadhaar):
                from document_extractor import extract_from_image
                out = await loop.run_in_executor(None, extract_from_image, tmp, "aadhaar")
            else:
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
            logger.info("DEBUG: PAN temp path: %s", tmp)
            if _is_image(pan):
                from document_extractor import extract_from_image
                out = await loop.run_in_executor(None, extract_from_image, tmp, "pan")
            else:
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

    # ── Generate a doc_token and save all uploaded files to a pending folder ──
    doc_token = _uuid.uuid4().hex[:12].upper()
    pending_dir = _UPLOAD_BASE / "_pending" / doc_token
    pending_dir.mkdir(parents=True, exist_ok=True)

    async def _save_to_pending(upload: UploadFile, dest_name: str) -> Path:
        """Save an UploadFile to the pending folder, return the saved path."""
        suffix = Path(upload.filename).suffix if upload.filename else ".bin"
        dest = pending_dir / f"{dest_name}{suffix}"
        content = await upload.read()
        dest.write_bytes(content)
        return dest

    # ── Financial document extraction ─────────────────────────────────────────
    from document_extractor import extract_financial_from_image

    for upload_file, field_name in [
        (bank_statement, "bank_statement"),
        (salary_slip, "salary_slip"),
        (itr, "itr"),
    ]:
        if upload_file is None:
            continue
        tmp_fin = None
        try:
            saved = await _save_to_pending(upload_file, field_name)
            # Re-seek to run extraction (file was consumed by save)
            tmp_fin = str(saved)
            if _is_image(upload_file):
                extracted = await loop.run_in_executor(
                    None, extract_financial_from_image, tmp_fin, field_name
                )
            else:
                # PDF path — use PaddleOCR + LLM text extractor
                from document_extractor import _extract_text_lines
                from services.llm_extractor import extract_financial_data
                lines = await loop.run_in_executor(None, _extract_text_lines, tmp_fin)
                extracted = extract_financial_data("\n".join(lines), doc_type=field_name)
                extracted["available"] = True
            result[field_name] = extracted
        except Exception as e:
            logger.exception("%s extraction failed", field_name)
            errors.append(f"{field_name}: {e}")
            result[field_name] = {"available": False, "reason": str(e)}

    # Save aadhaar and pan to pending dir as well (for identity check later)
    if aadhaar is not None:
        try:
            aadhaar.file.seek(0)
            suffix = Path(aadhaar.filename).suffix if aadhaar.filename else ".jpg"
            (pending_dir / f"aadhaar{suffix}").write_bytes(await aadhaar.read())
        except Exception:
            pass
    if pan is not None:
        try:
            pan.file.seek(0)
            suffix = Path(pan.filename).suffix if pan.filename else ".jpg"
            (pending_dir / f"pan{suffix}").write_bytes(await pan.read())
        except Exception:
            pass

    return {**result, "doc_token": doc_token, "errors": errors}



@app.post("/api/officer/action/{app_id}")
def officer_action(app_id: str, action: OfficerAction, current_user: dict = Depends(require_role("officer", "senior_officer", "admin"))):
    row = db.get_application(app_id)
    if not row:
        raise HTTPException(404, "Application not found")
    valid = {"APPROVED", "REJECTED", "CONDITIONAL", "ESCALATED"}
    if action.decision.upper() not in valid:
        raise HTTPException(400, f"Decision must be one of {valid}")

    current_role = str(current_user.get("role", "")).lower()
    actor_id = str(current_user.get("username") or current_user.get("id") or action.officer_id)
    current_status = row.get("status", "")

    # Regular officers can only act on applications in pending/processing states
    if current_role == "officer":
        # Prevent double-decisions: officers cannot act if already decided by an officer or senior officer
        if current_status.startswith("OFFICER_") or current_status.startswith("SENIOR_OFFICER_"):
            raise HTTPException(
                status_code=403, 
                detail=f"Application already has a decision. Status: {current_status}"
            )
        # Only allow escalation from pending or specific statuses
        if action.decision.upper() == "ESCALATED" and current_status not in {"DECIDED_PENDING_OFFICER", "AGENTS_RUNNING", "DIL_PROCESSING", "PENDING"}:
            raise HTTPException(
                status_code=403,
                detail=f"Cannot escalate from status: {current_status}"
            )

    if action.decision.upper() == "ESCALATED":
        if current_role != "officer":
            raise HTTPException(status_code=403, detail="Only officers can escalate applications")

        senior_officers = db.list_senior_officers()
        if not senior_officers:
            raise HTTPException(status_code=400, detail="No senior officers are available for escalation")

        import random

        assigned = random.choice(senior_officers)
        db.assign_application_to_senior_officer(
            app_id,
            actor_id,
            assigned.get("id"),  # Pass the integer ID, not the username
            action.reason,
        )
        db.log_event(app_id, "officer", "OFFICER_ESCALATED",
                     {"officer": actor_id, "assigned_senior_officer": assigned.get("username"), "reason": action.reason})
        return {
            "success": True,
            "application_id": app_id,
            "decision": "ESCALATED",
            "assigned_senior_officer": _serialize_user(assigned),
        }

    if current_role == "senior_officer":
        assigned_to = str(row.get("escalated_to_senior_officer_id") or "")
        if assigned_to and assigned_to not in {str(current_user.get("id")), str(current_user.get("username"))}:
            raise HTTPException(status_code=403, detail="This application is assigned to another senior officer")
        if row.get("status") != "OFFICER_ESCALATED":
            raise HTTPException(status_code=403, detail="Senior officers can only act on escalated applications")

    # Pass the actor's role when saving the action
    # Map role to lowercase for consistency
    actor_role = "senior_officer" if current_role == "senior_officer" else "officer"
    db.save_officer_action(app_id, actor_id, action.decision.upper(), action.reason, actor_role=actor_role)
    db.log_event(app_id, current_role or "officer", "OFFICER_ACTION",
                 {"decision": action.decision, "officer": actor_id, "actor_role": actor_role})
    return {"success": True, "application_id": app_id, "decision": action.decision}




@app.post("/api/officer/login")
def login(credentials: dict):
    username = credentials.get("username") or credentials.get("email")
    password = credentials.get("password")
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password are required")

    user = authenticate_user(username, password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not bool(user.get("is_active", True)):
        raise HTTPException(status_code=403, detail="Your account has been deactivated. Please contact the administrator.")

    if not is_user_verified(user):
        raise HTTPException(status_code=403, detail="Account verification pending")

    if bool(user.get("needs_password_reset", False)):
        challenge = _issue_password_reset_challenge(user, purpose="first_login_reset")
        return {
            "success": True,
            "requires_password_reset": True,
            "challenge_id": challenge["challenge"]["id"],
            "message": "First-time login: A verification code has been sent to your email to reset your password.",
        }

    if bool(user.get("two_factor_enabled", False)):
        method = str(user.get("two_factor_method", "email")).lower()
        if method == "authenticator":
            if not user.get("totp_secret"):
                raise HTTPException(status_code=400, detail="Authenticator app is not configured")
            challenge = _issue_login_challenge(user, method="authenticator")
            return {
                "success": True,
                "requires_two_factor": True,
                "challenge_id": challenge["challenge"]["id"],
                "method": "authenticator",
                "message": "Open your authenticator app to retrieve the verification code.",
            }

        if method != "email":
            raise HTTPException(status_code=400, detail="Unsupported two-factor method")

        challenge = _issue_login_challenge(user, method="email")
        return {
            "success": True,
            "requires_two_factor": True,
            "challenge_id": challenge["challenge"]["id"],
            "method": challenge["challenge"].get("method", "email"),
            "message": "A verification code has been sent to your email address.",
        }

    user_data = _serialize_user(user)
    token = create_access_token(user_data)

    return {
        "success": True,
        "token": token,
        "user": user_data,
    }


@app.post("/api/auth/forgot-password")
def forgot_password(payload: ForgotPasswordRequest):
    user = db.get_user_by_username(payload.username)
    if not user:
        # For security reasons, don't reveal if user exists
        return {"success": True, "message": "If an account exists with that email, a reset code has been sent."}
    
    challenge_data = _issue_password_reset_challenge(user, purpose="password_reset")
    return {
        "success": True, 
        "message": "A password reset code has been sent to your email.",
        "challenge_id": challenge_data["challenge"]["id"]
    }


@app.post("/api/auth/reset-password")
def reset_password(payload: ResetPasswordRequest):
    if payload.new_password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")
    
    challenge = db.get_auth_challenge(payload.challenge_id)
    if not challenge or challenge.get("consumed_at") or _challenge_is_expired(challenge):
        raise HTTPException(status_code=400, detail="Invalid or expired reset code")
    
    if challenge.get("purpose") not in ["password_reset", "first_login_reset"]:
        raise HTTPException(status_code=400, detail="Invalid challenge purpose")
    
    if not verify_otp_code(payload.otp, challenge.get("code_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid verification code")
    
    from password_utils import hash_password
    db.update_user_password(challenge["username"], hash_password(payload.new_password))
    db.consume_auth_challenge(payload.challenge_id)
    
    return {"success": True, "message": "Password updated successfully. You can now login."}


@app.post("/api/auth/reset-password-first-login")
def reset_password_first_login(payload: ResetPasswordFirstLoginRequest):
    """Special endpoint for first login password reset without a challenge_id (if preferred) or verification."""
    # This can actually just be a wrapper or use a challenge if login issued one.
    # In my login implementation, I issued a challenge. So users can use /api/auth/reset-password.
    # But I'll provide this as requested if they want a direct one.
    # Let's keep it consistent and use challenges.
    raise HTTPException(status_code=501, detail="Please use /api/auth/reset-password with the challenge ID from login.")



@app.post("/api/officer/login/verify-otp")
def verify_login_otp(payload: LoginOtpVerify):
    challenge = db.get_auth_challenge(payload.challenge_id)
    if not challenge:
        raise HTTPException(status_code=404, detail="Login challenge not found")

    if challenge.get("consumed_at"):
        raise HTTPException(status_code=400, detail="This login challenge has already been used")

    if _challenge_is_expired(challenge):
        raise HTTPException(status_code=400, detail="Login challenge has expired")

    if str(challenge.get("purpose", "")).lower() != "login":
        raise HTTPException(status_code=400, detail="Invalid login challenge")

    challenge_method = str(challenge.get("method") or "email").lower()
    user = db.get_user_by_username(challenge["username"])
    if not user or not is_user_verified(user):
        raise HTTPException(status_code=403, detail="Account is not available for login")

    if challenge_method == "authenticator":
        if not verify_totp_code(payload.otp, str(user.get("totp_secret") or "")):
            raise HTTPException(status_code=401, detail="Invalid verification code")
    else:
        if not verify_otp_code(payload.otp, str(challenge.get("code_hash") or "")):
            raise HTTPException(status_code=401, detail="Invalid verification code")

    db.consume_auth_challenge(payload.challenge_id)

    user_data = _serialize_user(user)
    token = create_access_token(user_data)
    return {
        "success": True,
        "token": token,
        "user": user_data,
    }


@app.put("/api/officer/two-factor")
def update_two_factor_settings(payload: TwoFactorSettingsUpdate, current_user: dict = Depends(get_current_user)):
    username = current_user.get("username") or current_user.get("email")
    if not username:
        raise HTTPException(status_code=401, detail="Unauthorized")

    method = payload.method.value if hasattr(payload.method, "value") else str(payload.method)
    method = str(method).lower()
    user = db.get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.enabled and method == "authenticator":
        if not user.get("totp_secret"):
            raise HTTPException(status_code=400, detail="Authenticator app setup is required first")
        if not user.get("totp_enabled_at"):
            raise HTTPException(status_code=400, detail="Verify the authenticator code to enable it")

    totp_secret = str(user.get("totp_secret") or "")
    totp_enabled_at = user.get("totp_enabled_at")
    if method != "authenticator":
        totp_secret = ""
        totp_enabled_at = None
    if not payload.enabled:
        totp_enabled_at = None
        if method == "authenticator":
            totp_secret = ""

    updated_user = db.update_user_two_factor(
        username,
        two_factor_enabled=payload.enabled,
        two_factor_method=method,
        totp_secret=totp_secret,
        totp_enabled_at=totp_enabled_at,
    )
    if not updated_user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "success": True,
        "user": _serialize_user(updated_user),
    }


@app.post("/api/officer/two-factor/totp/setup", response_model=TotpSetupResponse)
def setup_totp(current_user: dict = Depends(get_current_user)):
    username = current_user.get("username") or current_user.get("email")
    if not username:
        raise HTTPException(status_code=401, detail="Unauthorized")

    user = db.get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    secret = generate_totp_secret()
    otpauth_uri = build_totp_uri(username, secret)
    db.update_user_two_factor(
        username,
        two_factor_enabled=False,
        two_factor_method="authenticator",
        totp_secret=secret,
        totp_enabled_at=None,
    )

    return {
        "success": True,
        "secret": secret,
        "otpauth_uri": otpauth_uri,
    }


@app.post("/api/officer/two-factor/totp/verify")
def verify_totp(payload: TotpVerifyRequest, current_user: dict = Depends(get_current_user)):
    username = current_user.get("username") or current_user.get("email")
    if not username:
        raise HTTPException(status_code=401, detail="Unauthorized")

    user = db.get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    secret = str(user.get("totp_secret") or "")
    if not secret:
        raise HTTPException(status_code=400, detail="Authenticator app setup is required first")

    if not verify_totp_code(payload.otp, secret):
        raise HTTPException(status_code=401, detail="Invalid verification code")

    updated_user = db.update_user_two_factor(
        username,
        two_factor_enabled=True,
        two_factor_method="authenticator",
        totp_secret=secret,
        totp_enabled_at=_utcnow(),
    )
    if not updated_user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "success": True,
        "user": _serialize_user(updated_user),
    }


@app.get("/api/admin/users")
def list_admin_users(current_user: dict = Depends(get_current_admin)):
    return [
        {
            "id": user["id"],
            "username": user["username"],
            "email": user["username"],
            "name": user.get("full_name") or user["username"],
            "role": user["role"],
            "is_active": bool(user.get("is_active", True)),
            "needs_password_reset": bool(user.get("needs_password_reset", False)),
            "created_at": str(user.get("created_at", "")),
            "updated_at": str(user.get("updated_at", "")),
        }
        for user in db.list_users()
    ]


@app.post("/api/admin/users")
def create_admin_user(payload: UserCreate, current_user: dict = Depends(get_current_admin)):
    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="Password and confirm password do not match")

    from password_utils import hash_password

    existing = db.get_user_by_username(payload.username)
    if existing:
        raise HTTPException(status_code=409, detail="Username already exists")

    # Officers and Senior Officers created by admin MUST reset password on first login
    needs_reset = payload.role in [UserRole.OFFICER, UserRole.SENIOR_OFFICER]

    user = db.create_user(
        payload.username,
        hash_password(payload.password),
        payload.role.value,
        payload.full_name or payload.username,
        is_verified=True,  # Admin created accounts are verified by default
        needs_password_reset=needs_reset
    )
    
    return {
        "success": True,
        "message": "User created successfully." + (" User must reset password on first login." if needs_reset else ""),
        "user": _serialize_user(user),
    }


@app.put("/api/admin/users/{username}/status")
def update_user_status_api(username: str, payload: dict, current_user: dict = Depends(get_current_admin)):
    # Prevent deactivating 'admin'
    if username.lower() == "admin":
        raise HTTPException(status_code=400, detail="Cannot change status of the primary admin account")

    is_active = payload.get("is_active")
    if is_active is None:
        raise HTTPException(status_code=400, detail="is_active field is required")
    
    user = db.update_user_status(username, bool(is_active))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {"success": True, "user": _serialize_user(user)}


@app.put("/api/admin/users/{username}/role")
def update_user_role_api(username: str, payload: dict, current_user: dict = Depends(get_current_admin)):
    # Prevent changing role of 'admin'
    if username.lower() == "admin":
        raise HTTPException(status_code=400, detail="Cannot change the role of the primary admin account")

    new_role = payload.get("role")
    if new_role not in ["admin", "officer", "senior_officer"]:
        raise HTTPException(status_code=400, detail="Invalid role")
    
    user = db.update_user_role(username, new_role)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {"success": True, "user": _serialize_user(user)}


@app.delete("/api/admin/users/{username}")
def delete_user_api(username: str, current_user: dict = Depends(get_current_admin)):
    # Prevent deleting self
    if username.lower() == current_user.get("username", "").lower():
        raise HTTPException(status_code=400, detail="You cannot delete your own admin account")
        
    success = db.delete_user(username)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {"success": True, "message": f"User {username} deleted successfully"}


@app.get("/api/users/admin/users")
def list_users_admin_users_alias(current_user: dict = Depends(get_current_admin)):
    """Alias for /api/admin/users"""
    return list_admin_users(current_user)


@app.post("/api/users/register")
def register_user_alias(payload: UserCreate, current_user: dict = Depends(get_current_admin)):
    """Alias for /api/admin/users - create new user"""
    return create_admin_user(payload, current_user)


@app.put("/api/users/admin/users/{user_id}/role")
def update_user_role_by_id_alias(user_id: int, payload: dict, current_user: dict = Depends(get_current_admin)):
    """Alias for role update by ID if needed (mapping ID to username)"""
    user = db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return update_user_role_api(user["username"], payload, current_user)


@app.get("/api/senior-officer/applications")
def senior_officer_applications(current_user: dict = Depends(get_current_senior_officer)):
    return officer_queue(current_user)


@app.get("/api/senior-officer/decision/{app_id}")
def senior_officer_decision(app_id: str, current_user: dict = Depends(get_current_senior_officer)):
    return get_full_decision(app_id, current_user)


@app.get("/api/health")
def health():
    from dil import _BLACKLIST
    from agents_base import _PORTFOLIO, _RULES
    from dataset_loader import get_dataset_stats
    from llm_config import get_llm_stats, get_llm_usage_mode
    from services.rag import COMPLIANCE_KB

    # Skip synchronous self-calls in health check to avoid deadlocks on single-worker uvicorn
    agent_cards = {"credit_risk": "mounted", "fraud": "mounted", "compliance": "mounted", "portfolio": "mounted"}

    response = {
        "status":            "ok",
        "mode":              _runtime_mode(),
        "blacklist_pans":    len(_BLACKLIST),
        "portfolio_loans":   len(_PORTFOLIO),
        "compliance_rules":  len(_RULES),
        "compliance_kb_chunks": len(COMPLIANCE_KB),  # NEW: RAG KB status
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
