# 🏦 Agentic AI Credit Risk Assessment System

## Overview

A production-ready **LangGraph-powered Credit Risk Agent** that assesses loan applications in real-time using:
- **ML Model** (GradientBoosting, 99.45% accuracy) trained on CIBIL data
- **SHAP-style explainability** (leave-one-out feature attribution)
- **LLM narrative** (Claude API for human-readable risk explanations)
- **FastAPI** REST backend with document upload support
- **LangGraph state machine** orchestrating the full pipeline

---

## Architecture

```
Frontend (Submit Button)
        │
        ▼
   FastAPI Server
        │
        ├── GET /user/{pan}        ← Fetch user from Mock DB
        └── POST /assess-risk      ← Trigger LangGraph Agent
                │
                ▼
        LangGraph Agent (State Machine)
        ┌────────────────────────────┐
        │  Node 1: fetch_user_profile│ ← Mock DB (real: PostgreSQL)
        │  Node 2: validate_inputs   │ ← DTI check, field validation
        │  Node 3: run_ml_scoring    │ ← GBM Model + SHAP approx.
        │  Node 4: generate_explanation│ ← Claude LLM
        │  Node 5: compile_result   │ ← Final JSON response
        └────────────────────────────┘
```

---

## Risk Score Mapping

| Flag | Label | Risk Score Range | Action |
|------|-------|-----------------|--------|
| P1   | Low Risk | 0–20 | ✅ Approve |
| P2   | Medium-Low Risk | 21–40 | ✅ Approve with review |
| P3   | Medium-High Risk | 41–70 | ⚠️ Conditional approval |
| P4   | High Risk | 71–100 | ❌ Decline |

---

## Project Structure

```
credit_risk_backend/
├── main.py                          # FastAPI app + all routes
├── requirements.txt
├── models_artifacts/
│   ├── risk_model.pkl               # Trained GBM model
│   ├── scaler.pkl                   # StandardScaler
│   └── model_metadata.json          # Feature list, encoders, importance
└── app/
    ├── agents/
    │   └── credit_risk_agent.py     # LangGraph state machine
    ├── services/
    │   ├── inference.py             # ML inference + SHAP approximation
    │   └── llm_service.py           # Claude LLM explanation
    ├── db/
    │   └── mock_db.py               # Mock user database
    └── models/
        └── schemas.py               # Pydantic request/response models
```

---

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Set API key (optional, for LLM explanations)
```bash
export ANTHROPIC_API_KEY=your_key_here
```

### 3. Run the server
```bash
cd credit_risk_backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Test the API
```bash
# Health check
curl http://localhost:8000/health

# Get sample PANs
curl http://localhost:8000/sample-pans

# Assess risk
curl -X POST http://localhost:8000/assess-risk \
  -H "Content-Type: application/json" \
  -d '{
    "pan_number": "PQRST5678G",
    "loan_amount": 500000,
    "loan_type": "Personal Loan",
    "loan_tenure_months": 36
  }'
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check + model accuracy |
| GET | `/sample-pans` | List sample PAN numbers |
| GET | `/user/{pan}` | Fetch user profile by PAN |
| POST | `/assess-risk` | JSON-based risk assessment |
| POST | `/assess-risk-with-docs` | Multipart with document uploads |
| GET | `/model/info` | Model metadata + feature importance |
| GET | `/docs` | Interactive Swagger UI |

---

## Model Features (26 total)

### Demographic
- AGE, GENDER, MARITALSTATUS, EDUCATION

### Financial
- NETMONTHLYINCOME, Time_With_Curr_Empr, Credit_Score

### Delinquency History
- num_times_delinquent, recent_level_of_deliq
- num_deliq_6mts, num_deliq_12mts
- num_times_30p_dpd, num_times_60p_dpd

### Account Quality
- num_std (standard), num_sub (sub-standard)
- num_dbt (doubtful), num_lss (loss)

### Enquiry Behavior
- tot_enq, enq_L12m, enq_L6m
- time_since_recent_enq

### Utilization & Exposure
- CC_utilization, PL_utilization
- max_unsec_exposure_inPct

### Trade Line Health
- pct_of_active_TLs_ever
- pct_currentBal_all_TL

---

## Mock DB - Sample Users

| PAN | Name | Credit Score | Profile |
|-----|------|-------------|---------|
| ABCDE1234F | Rahul Sharma | 720 | Good - Low Risk |
| PQRST5678G | Priya Mehta | 760 | Excellent - Low Risk |
| XYZAB9012H | Vijay Kumar | 580 | Poor - High Risk |
| LMNOP3456I | Anita Singh | 690 | Moderate - Medium Risk |

---

## Frontend Integration

```javascript
// Submit loan application
const response = await fetch('/assess-risk', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    pan_number: panInput,
    loan_amount: loanAmount,
    loan_type: loanType,
    loan_tenure_months: tenure,
  })
});

const result = await response.json();
// result.risk_score, result.risk_category, result.llm_explanation, etc.
```

### With documents (multipart)
```javascript
const formData = new FormData();
formData.append('pan_number', pan);
formData.append('loan_amount', amount);
formData.append('loan_type', loanType);
formData.append('loan_tenure_months', tenure);
formData.append('aadhaar_doc', aadhaarFile);
formData.append('bank_statement', bankFile);

await fetch('/assess-risk-with-docs', { method: 'POST', body: formData });
```

---

## Next Steps (CrewAI Integration)

```python
# credit_risk_tool.py (for CrewAI)
from crewai import Tool

credit_risk_tool = Tool(
    name="CreditRiskAssessment",
    description="Assess credit risk for a loan application using PAN number",
    func=lambda pan, amount, loan_type, tenure: 
        credit_risk_graph.invoke({
            "pan_number": pan,
            "loan_amount": amount,
            "loan_type": loan_type,
            "loan_tenure_months": tenure,
        })["final_result"]
)
```
