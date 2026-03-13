# Jatayu Credit Risk Backend

## Overview

This backend provides a LangGraph-based credit risk assessment API backed by PostgreSQL.

It combines:
- FastAPI for HTTP APIs
- LangGraph for agent orchestration
- A trained RandomForest credit risk model
- LLM-generated narrative explanations through Gemini
- PostgreSQL storage for applicant profiles and processed assessment results

The backend now uses real database tables instead of the old in-memory mock layer.

## Current Architecture

```text
credit_frontend
    |
    | HTTP
    v
FastAPI app (main.py)
    |
    +-- GET /db/users
    +-- POST /db/users
    +-- GET /db/processed
    +-- GET /db/processed/{pan}
    +-- GET /user/{pan}
    +-- POST /assess-risk
    +-- POST /assess-risk-with-docs
    |
    v
LangGraph credit_risk_graph
    |
    +-- fetch_user_profile
    +-- validate_inputs
    +-- run_ml_scoring
    +-- generate_explanation
    +-- compile_result
    |
    v
PostgreSQL
    +-- user_profiles
    +-- risk_processed
```

## Project Files

```text
credit_backend/
├── main.py
├── credit_risk_agent.py
├── inference.py
├── llm_service.py
├── schemas.py
├── db.py
├── db_models.py
├── db_repository.py
├── requirements.txt
├── .env
└── models_artifacts/
    ├── risk_model.pkl
    ├── scaler.pkl
    └── model_metadata.json
```

## Database Tables

### `user_profiles`
Stores the applicant profile and ML feature fields used during assessment.

### `risk_processed`
Stores the final processed assessment result JSON after a successful risk evaluation.

A row is written only after `/assess-risk` or `/assess-risk-with-docs` completes successfully.

## Prerequisites

- Python 3.10 recommended
- Conda environment optional but recommended
- PostgreSQL running locally or remotely
- Database named `jatayu`
- Gemini API key if you want LLM explanations

## Environment Setup

### 1. Activate Python environment

If you already use the existing environment:

```powershell
conda activate jatayu_vnev
```

### 2. Install dependencies

From the workspace root:

```powershell
conda run -n jatayu_vnev pip install -r credit_backend/requirements.txt
```

Or from inside `credit_backend`:

```powershell
pip install -r requirements.txt
```

## Environment Variables

Configure `credit_backend/.env`.

Example:

```env
GEMINI_API_KEY=your_gemini_api_key
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/jatayu
```

Notes:
- `DATABASE_URL` must point to a reachable PostgreSQL instance.
- The backend creates required tables automatically on startup.
- If the configured PostgreSQL server is reachable, the code also attempts to create the target database if it does not exist.

## Run the Backend

From the workspace root:

```powershell
uvicorn main:app --app-dir credit_backend --host 0.0.0.0 --port 8000 --reload
```

Or from inside `credit_backend`:

```powershell
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

If you want to force the conda environment explicitly:

```powershell
conda run -n jatayu_vnev uvicorn main:app --app-dir credit_backend --host 0.0.0.0 --port 8000 --reload
```

## Verify Backend

### Health check

```powershell
curl http://localhost:8000/health
```

### Fetch all DB users

```powershell
curl http://localhost:8000/db/users
```

### Fetch processed results

```powershell
curl http://localhost:8000/db/processed
```

### Fetch one processed result by PAN

```powershell
curl http://localhost:8000/db/processed/ABCDE1234F
```

## Main API Endpoints

### System

- `GET /health`
- `GET /sample-pans`
- `GET /model/info`

### User profile database

- `GET /db/users`
  - Returns all rows from `user_profiles`
- `POST /db/users`
  - Inserts a new applicant row into `user_profiles`
- `GET /user/{pan}`
  - Returns a lightweight profile response by PAN

### Processed assessment database

- `GET /db/processed`
  - Returns all stored processed assessments from `risk_processed`
- `GET /db/processed/{pan}`
  - Returns the stored processed assessment for one PAN

### Risk assessment

- `POST /assess-risk`
- `POST /assess-risk-with-docs`

On success, these endpoints both:
- run the LangGraph workflow
- return the assessment response
- persist the final result into `risk_processed`

## Example Create User Request

```json
{
  "pan": "AGPTW0547M",
  "name": "Nesar",
  "aadhaar_last4": "5689",
  "phone": "7738446159",
  "email": "nesar2004@gmail.com",
  "AGE": 21,
  "GENDER": "M",
  "MARITALSTATUS": "Single",
  "EDUCATION": "GRADUATE",
  "NETMONTHLYINCOME": 560000,
  "Time_With_Curr_Empr": 3,
  "Credit_Score": 800,
  "num_times_delinquent": 0,
  "recent_level_of_deliq": 0,
  "num_deliq_6mts": 0,
  "num_deliq_12mts": 0,
  "num_times_30p_dpd": 0,
  "num_times_60p_dpd": 0,
  "num_std": 5,
  "num_sub": 0,
  "num_dbt": 0,
  "num_lss": 0,
  "tot_enq": 3,
  "enq_L12m": 2,
  "enq_L6m": 1,
  "time_since_recent_enq": 4,
  "CC_utilization": 25,
  "PL_utilization": 10,
  "max_unsec_exposure_inPct": 30,
  "pct_of_active_TLs_ever": 85,
  "pct_currentBal_all_TL": 40
}
```

## Example Risk Assessment Request

```json
{
  "pan_number": "ABCDE1234F",
  "loan_amount": 360000,
  "loan_type": "Personal Loan",
  "loan_tenure_months": 36,
  "declared_monthly_income": null
}
```

## Notes for Developers

- The backend no longer uses `mock_db.py`.
- The canonical data path is now `db_repository.py`.
- The frontend applications page reads users from `GET /db/users` and processed results from `GET /db/processed`.
- After a submit action, the frontend now fetches only `GET /db/processed/{pan}` for the updated row.

## Known Runtime Warnings

You may still see scikit-learn pickle version warnings if the saved model artifacts were created with a slightly different sklearn version than the current environment.

The safest options are:
- align sklearn to the artifact version, or
- retrain/regenerate model artifacts in the current environment

## Swagger Docs

Open:

```text
http://localhost:8000/docs
```
