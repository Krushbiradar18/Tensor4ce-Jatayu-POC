"""
Credit Risk Assessment API - FastAPI Application
================================================
Endpoints:
  GET  /health              - Health check
  GET  /user/{pan}          - Fetch user profile by PAN
  GET  /sample-pans         - List sample PANs for testing
  POST /assess-risk         - Full loan risk assessment
  GET  /model/info          - Model metadata and feature importance
"""

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Optional
import time

from schemas import (
    LoanApplicationRequest,
    RiskScoreResponse,
    UserProfileResponse,
    UserProfileCreateRequest,
    HealthResponse,
    RiskCategory,
)
from db_repository import (
    get_user_by_pan,
    get_all_pans,
    list_all_users,
    create_user_profile,
    upsert_processed_result,
    list_processed_results,
)
from credit_risk_agent import credit_risk_graph
from inference import inference_service

# ─── App Setup ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Credit Risk Assessment API",
    description="Agentic AI-based credit risk assessment using LangGraph + ML + LLM",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "model_loaded": True,
        "model_accuracy": round(inference_service.model_accuracy * 100, 2),
        "version": "1.0.0",
    }


@app.get("/sample-pans", tags=["System"])
async def get_sample_pans():
    """Returns sample PAN numbers for testing."""
    return {
        "sample_pans": get_all_pans(),
        "note": "Use any of these PANs to test the /assess-risk endpoint.",
    }


@app.get("/db/users", tags=["Database"])
async def get_all_db_users():
    """Return all user profile rows from PostgreSQL."""
    users = list_all_users()
    return {
        "count": len(users),
        "users": users,
    }


@app.post("/db/users", tags=["Database"])
async def add_db_user(user: UserProfileCreateRequest):
    """Insert a new user profile row into PostgreSQL."""
    try:
        created = create_user_profile(user.model_dump())
        return {
            "message": "User profile created successfully.",
            "user": created,
        }
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.get("/db/processed", tags=["Database"])
async def get_all_processed_risk_results():
    """Return all persisted processed risk-assessment outputs from PostgreSQL."""
    records = list_processed_results()
    return {
        "count": len(records),
        "processed": records,
    }


@app.get("/user/{pan}", response_model=UserProfileResponse, tags=["User"])
async def get_user_profile(pan: str):
    """Fetch user profile from database by PAN number."""
    profile = get_user_by_pan(pan.upper())
    if not profile:
        return UserProfileResponse(
            found=False,
            pan=None, name=None, age=None, income=None, credit_score=None,
            message=f"No user found for PAN: {pan.upper()}"
        )
    return UserProfileResponse(
        found=True,
        pan=profile["pan"],
        name=profile["name"],
        age=profile["AGE"],
        income=profile["NETMONTHLYINCOME"],
        credit_score=profile["Credit_Score"],
        message="User found successfully.",
    )


@app.post("/assess-risk", tags=["Risk Assessment"])
async def assess_credit_risk(application: LoanApplicationRequest):
    """
    Full credit risk assessment via LangGraph agent.

    Fetches user profile by PAN, runs ML model, generates SHAP explanation,
    and provides LLM-powered narrative analysis.
    """
    _t0 = time.perf_counter()
    state = credit_risk_graph.invoke({
        "pan_number": application.pan_number,
        "loan_amount": application.loan_amount,
        "loan_type": application.loan_type.value,
        "loan_tenure_months": application.loan_tenure_months,
        "declared_monthly_income": application.declared_monthly_income,
    })

    result = state.get("final_result", {})

    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])

    if result.get("validation_errors"):
        raise HTTPException(status_code=422, detail={
            "message": "Validation failed",
            "errors": result["validation_errors"]
        })

    result["processing_time_ms"] = round((time.perf_counter() - _t0) * 1000, 2)
    upsert_processed_result(application.pan_number, result)
    return JSONResponse(content=result)


@app.post("/assess-risk-with-docs", tags=["Risk Assessment"])
async def assess_with_documents(
    pan_number: str = Form(...),
    loan_amount: float = Form(...),
    loan_type: str = Form(...),
    loan_tenure_months: int = Form(...),
    declared_monthly_income: Optional[float] = Form(None),
    aadhaar_doc: Optional[UploadFile] = File(None),
    pan_doc: Optional[UploadFile] = File(None),
    bank_statement: Optional[UploadFile] = File(None),
):
    """
    Risk assessment with optional document uploads (Aadhaar, PAN, Bank Statement).
    Documents are accepted for future OCR/verification pipeline integration.
    Currently runs risk assessment using DB profile + loan application data.
    """
    uploaded_docs = []
    for doc_name, doc_file in [
        ("aadhaar", aadhaar_doc),
        ("pan_card", pan_doc),
        ("bank_statement", bank_statement)
    ]:
        if doc_file:
            content = await doc_file.read()
            uploaded_docs.append({
                "name": doc_name,
                "filename": doc_file.filename,
                "size_bytes": len(content),
                "status": "received"
            })

    _t0 = time.perf_counter()
    state = credit_risk_graph.invoke({
        "pan_number": pan_number,
        "loan_amount": loan_amount,
        "loan_type": loan_type,
        "loan_tenure_months": loan_tenure_months,
        "declared_monthly_income": declared_monthly_income,
    })

    result = state.get("final_result", {})

    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])

    if result.get("validation_errors"):
        raise HTTPException(status_code=422, detail={
            "message": "Validation failed",
            "errors": result["validation_errors"]
        })

    result["processing_time_ms"] = round((time.perf_counter() - _t0) * 1000, 2)
    upsert_processed_result(pan_number, result)
    result["uploaded_documents"] = uploaded_docs
    return JSONResponse(content=result)


@app.get("/model/info", tags=["Model"])
async def get_model_info():
    """Returns model metadata, feature importance, and performance metrics."""
    top_features = list(inference_service.feature_importance.items())[:15]
    return {
        "model_type": "GradientBoostingClassifier",
        "training_accuracy": round(inference_service.model_accuracy * 100, 2),
        "num_features": len(inference_service.features),
        "risk_categories": ["Low Risk", "Medium-Low Risk", "Medium-High Risk", "High Risk"],
        "approved_flags": {
            "P4": "Low Risk - Strong approval",
            "P3": "Medium-Low Risk - Approve with review",
            "P2": "Medium-High Risk - Conditional approval",
            "P1": "High Risk - Decline",
        },
        "top_features_by_importance": [
            {"feature": k, "importance": round(v * 100, 3)}
            for k, v in top_features
        ],
    }


# ─── Entry Point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
