"""
app.py — SINGLE ENTRY POINT for Tensor4ce Loan Approval System
================================================================
Run with:
  cd Tensor4ce-Jatayu-POC
  source jatayu_vnev/bin/activate
  uvicorn app:app --reload --host 0.0.0.0 --port 8000

Router Map (discovered 2026-03-22):
─────────────────────────────────────────────────────────────
SOURCE                              ROUTES MOUNTED
backend/main.py                     /api/apply  /api/status/*  /api/officer/*
                                    /mock/bank/portfolio-summary  (portfolio mock)
backend/graphs.py                   (called internally — not via HTTP in unified mode)
compliance_agent/compliance_router  POST /mock/bank/statement-summary
                                    GET  /mock/macro/current
─────────────────────────────────────────────────────────────
NOT MERGED (standalone microservices with local import trees):
  credit_backend/main.py      → run separately on any free port
  Fraud-Agent/fraud_agent.py  → run separately on any free port
─────────────────────────────────────────────────────────────

This file delegates 100% of the app object to backend/main.py (which owns
the lifespan, CORS middleware, DB init, and dataset preloading). The root
app.py exists ONLY as a convenience entry point so `uvicorn app:app` works
from the project root without cd-ing into backend/.

To run the backend directly (legacy):
  cd backend && uvicorn main:app --reload --port 8000
"""
import sys
import os
from pathlib import Path

# ── sys.path setup ─────────────────────────────────────────────────────────
# CRITICAL: backend/ must come BEFORE compliance_agent/ because both have
# a schemas.py. backend/schemas.py contains SubmitRequest; compliance_agent/
# schemas.py contains compliance-specific models. The import of `from schemas
# import SubmitRequest` in backend/main.py must resolve to backend/schemas.py.
_PROJECT_ROOT = Path(__file__).resolve().parent
_BACKEND_DIR = _PROJECT_ROOT / "backend"
_COMPLIANCE_DIR = _PROJECT_ROOT / "compliance_agent"
_PORTFOLIO_DIR = _PROJECT_ROOT / "portfolio_agent"

for p in [str(_PROJECT_ROOT), str(_BACKEND_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# compliance_agent appended AFTER backend to avoid schemas.py collision
for p in [str(_COMPLIANCE_DIR), str(_PORTFOLIO_DIR)]:
    if p not in sys.path:
        sys.path.append(p)

# ── Load .env from project root ─────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=_PROJECT_ROOT / ".env")
except ImportError:
    pass

# ── Import the core app from backend/main.py ────────────────────────────────
from main import app  # noqa: E402  (backend/ is on sys.path above)

# ── Mount compliance mock API routes ────────────────────────────────────────
# These routes were previously only in compliance_agent/mock_api.py (standalone).
# Mounting here makes them available from the unified server:
#   POST /mock/bank/statement-summary
#   GET  /mock/macro/current
try:
    from compliance_router import router as _compliance_router  # type: ignore[import]
    app.include_router(_compliance_router)
except Exception as _compliance_err:
    import logging as _logging
    _logging.getLogger(__name__).warning(
        f"Compliance mock router not mounted: {_compliance_err}"
    )

# ── /health endpoint at root level ─────────────────────────────────────────
@app.get("/health", tags=["System"])
def health_check():
    """Unified health check — returns ok if the server is running."""
    return {"status": "ok", "service": "Tensor4ce Loan API", "version": "2.0.0"}


# ── Allow `python app.py` for quick local testing ──────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
