"""
main.py — FastAPI Application
Run: uvicorn main:app --reload --port 8000
"""
from __future__ import annotations
import os, json, asyncio, logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from typing import Optional

from schemas import SubmitRequest, OfficerAction


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = Path(__file__).resolve().parent


def _load_local_env() -> None:
    """Load key=value pairs from backend/.env if present."""
    env_path = Path(__file__).with_name(".env")
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_local_env()

import db


def _resolve_config_path(raw_path: str, default_base: Path) -> str:
    path = Path(raw_path)
    if path.is_absolute():
        return str(path)

    candidates = [
        (default_base / path).resolve(),
        (BACKEND_DIR / path).resolve(),
        (PROJECT_ROOT / path).resolve(),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return str((default_base / path).resolve())


def _runtime_mode() -> str:
    llm_mode = os.environ.get("LLM_USAGE_MODE", "FULL").upper()
    has_gemini = bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    if llm_mode == "FALLBACK" or not has_gemini:
        return "Direct Real LangGraph Agents"
    return "CrewAI + Real LangGraph Agents"


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger(__name__)


def _derive_processing_stage(status: str, audit_log: list[dict]) -> str:
    """Return a human-readable current pipeline stage for officer dashboard use."""
    if status.startswith("OFFICER_"):
        return "Final decision completed"
    if status == "DECIDED_PENDING_OFFICER":
        return "Awaiting officer action"
    if status == "DIL_PROCESSING":
        return "DIL verification in progress"
    if status == "PENDING":
        return "Queued for processing"
    if status == "ERROR":
        return "Processing error"

    # For AGENTS_RUNNING, infer the latest active specialist from audit logs.
    if status == "AGENTS_RUNNING":
        agent_map = {
            "credit_risk_graph": "Credit Risk Agent",
            "fraud_graph": "Fraud Agent",
            "compliance_graph": "Compliance Agent",
            "portfolio_graph": "Portfolio Agent",
            "orchestrator": "Orchestrator",
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
            if node:
                return f"{stage_name} ({node})"
            return stage_name
        return "Specialist agents running"

    return "In progress"


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    data_dir = _resolve_config_path(os.environ.get("DATA_DIR", "data"), BACKEND_DIR)
    from dil import load_static_data
    from agents_base import load_compliance_rules, load_portfolio
    from dataset_loader import load_datasets, get_dataset_stats

    # Load static configs
    load_static_data(data_dir)
    load_compliance_rules(f"{data_dir}/compliance_rules.yaml")
    load_portfolio(f"{data_dir}/portfolio_loans.csv")

    # Load Excel datasets (CIBIL + Bank data) if preloading is enabled.
    preload_datasets = os.environ.get("PRELOAD_DATASETS", "true").strip().lower() in {"1", "true", "yes", "on"}
    dataset_dir = _resolve_config_path(os.environ.get("DATASET_DIR", "dataset"), PROJECT_ROOT)
    os.environ["DATASET_DIR"] = dataset_dir

    if preload_datasets:
        logger.info("Loading datasets from Excel files...")
        load_datasets(dataset_dir)
        stats = get_dataset_stats()
        logger.info(f"✓ Datasets loaded: CIBIL={stats['cibil_records']}, Bank={stats['bank_records']}, Merged={stats['merged_records']}")
    else:
        logger.info("Skipping dataset preload at startup (PRELOAD_DATASETS=false). Datasets will load on first access.")

    mode = _runtime_mode()
    logger.info(f"✓ System ready  |  Mode: {mode}")
    logger.info(f"✓ Using ML models: Credit Risk (RandomForest), Fraud Detection (IsolationForest)")
    yield


app = FastAPI(title="Tensor4ce Credit AI", version="3.0.0", lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Mount portfolio mock API router (GET /mock/bank/portfolio-summary)
try:
    from mock_apis.portfolio import router as portfolio_router
    app.include_router(portfolio_router)
    logger.info("✓ Portfolio mock API router mounted at /mock/bank/portfolio-summary")
except Exception as _portfolio_router_err:
    logger.warning(f"Portfolio mock API router not mounted: {_portfolio_router_err}")

frontend_dir = Path(__file__).parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

    @app.get("/")
    async def root():
        return FileResponse(str(frontend_dir / "index.html"))


@app.post("/api/apply")
async def submit_application(req: SubmitRequest, background_tasks: BackgroundTasks):
    import uuid
    app_id = f"APP-{uuid.uuid4().hex[:8].upper()}"
    req.form_data["application_id"] = app_id
    db.save_application(app_id, req.form_data, req.ip_metadata)
    background_tasks.add_task(_run_bg, app_id, req.form_data, req.ip_metadata)
    return {"application_id": app_id, "status": "PENDING",
            "message": "Application received. Processing started."}


async def _run_bg(app_id: str, form_data: dict, ip_meta: dict):
    try:
        from orchestrator import run_pipeline
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, run_pipeline, app_id, form_data, ip_meta)
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
        "PENDING": "Application received. We will review it shortly.",
        "DIL_PROCESSING": "We are processing your submitted information.",
        "AGENTS_RUNNING": "Your application is under review by our credit team.",
        "DECIDED_PENDING_OFFICER": "Your assessment is complete. A loan officer will review shortly.",
        "OFFICER_ESCALATED": "Your application requires additional specialist review. We will contact you within 24 hours.",
        "ERROR": "We encountered an issue. Please contact support.",
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
    valid = {"APPROVED","REJECTED","CONDITIONAL","ESCALATED"}
    if action.decision.upper() not in valid:
        raise HTTPException(400, f"Decision must be one of {valid}")
    db.save_officer_action(app_id, action.officer_id, action.decision.upper(), action.reason)
    db.log_event(app_id, "officer", "OFFICER_ACTION",
                 {"decision": action.decision, "officer": action.officer_id})
    return {"success": True, "application_id": app_id, "decision": action.decision}



# ── Document Upload & OCR ────────────────────────────────────────────────────
ALLOWED_DOC_TYPES = {"aadhaar", "pan", "bank_statement", "salary_slip", "form16"}
ALLOWED_MIMES     = {
    "application/pdf", "image/jpeg", "image/jpg", "image/png",
    "image/tiff", "image/webp",
}

@app.post("/api/upload/{app_id}")
async def upload_document(
    app_id: str,
    doc_type: str = Form(...),
    file: UploadFile = File(...),
):
    """
    Stage 1 + 2: Accept a document upload, run OCR/extraction pipeline.
    Returns extracted structured fields for the document.
    - doc_type: one of aadhaar | pan | bank_statement | salary_slip | form16
    """
    # Validate doc_type
    if doc_type.lower() not in ALLOWED_DOC_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid doc_type '{doc_type}'. Must be one of: {', '.join(ALLOWED_DOC_TYPES)}"
        )

    # Validate file presence
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    # Validate MIME type (use content_type if provided, else check extension)
    ct = (file.content_type or "").lower().split(";")[0].strip()
    ext = Path(file.filename).suffix.lower()
    if ct not in ALLOWED_MIMES and ext not in {".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".webp"}:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Please upload PDF or image files."
        )

    # Read file bytes (limit 10 MB)
    MAX_SIZE = 10 * 1024 * 1024
    file_bytes = await file.read()
    if len(file_bytes) > MAX_SIZE:
        raise HTTPException(status_code=413, detail="File too large. Maximum 10 MB allowed.")

    # Run processing pipeline in thread pool (CPU-bound OCR)
    import asyncio
    from doc_processor import process_document
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        process_document,
        file_bytes,
        file.filename,
        doc_type,
    )

    # Persist upload record to DB
    try:
        db.save_document(app_id, doc_type, file.filename, result)
    except Exception as e:
        logger.warning(f"Could not persist document metadata for {app_id}: {e}")

    return {
        "application_id":   app_id,
        "doc_type":         doc_type,
        "filename":         file.filename,
        "extraction_method": result.get("extraction_method"),
        "extracted_fields": result.get("extracted_fields", {}),
        "raw_text_preview": result.get("raw_text_preview", ""),
        "status":           "processed",
    }


@app.get("/api/upload/{app_id}")
async def get_uploaded_documents(app_id: str):
    """List all documents uploaded for an application."""
    app_row = db.get_application(app_id)
    if not app_row:
        raise HTTPException(status_code=404, detail=f"Application {app_id} not found")

    try:
        docs = db.get_documents(app_id)
    except Exception:
        docs = []

    return {"application_id": app_id, "documents": docs}


@app.get("/api/health")
async def health():
    from dil import _BLACKLIST
    from agents_base import _PORTFOLIO, _RULES
    from dataset_loader import get_dataset_stats
    from llm_config import get_llm_stats, get_llm_usage_mode

    response = {
        "status": "ok",
        "mode": _runtime_mode(),
        "blacklist_pans": len(_BLACKLIST),
        "portfolio_loans": len(_PORTFOLIO),
        "compliance_rules": len(_RULES),
    }

    # Add dataset stats
    try:
        dataset_stats = get_dataset_stats()
        response["datasets"] = dataset_stats
    except:
        response["datasets"] = {"error": "Dataset loader not initialized"}

    # Add LLM usage stats
    try:
        llm_stats = get_llm_stats()
        response["llm_usage"] = llm_stats
    except:
        response["llm_usage"] = {"mode": get_llm_usage_mode(), "tracking": "not initialized"}

    return response
