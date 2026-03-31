# ARIA — Agentic Risk Intelligence & Analytics

**Agentic Credit Risk Assessment & Loan Approval System**  
Team Tensor4ce

ARIA is an autonomous multi-agent AI system for end-to-end loan underwriting. Four specialist AI agents (Credit Risk, Fraud Detection, Compliance, Portfolio) are coordinated by a CrewAI orchestrator powered by Google Gemini. A React-based officer dashboard provides the human-in-the-loop review layer.

---

## Table of Contents

- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Setup](#setup)
- [Configuration](#configuration)
- [Running the App](#running-the-app)
- [Key Modules](#key-modules)
- [API Reference](#api-reference)
- [Agent Protocol (A2A)](#agent-protocol-a2a)
- [Database Schema](#database-schema)
- [Team](#team)

---

## Architecture

```
Frontend (React + Vite)
    │
    ▼  REST / JSON
FastAPI Backend (main.py)
    │
    ├── Document OCR  ──────────────────  PaddleOCR (Aadhaar / PAN PDFs)
    ├── Identity Gate ──────────────────  verification/verifier.py
    │
    ▼  (async background task)
Data Intelligence Layer  (dil.py)
    │   Bureau enrichment · Feature engineering · FeatureStore
    ▼
CrewAI Orchestrator  (orchestrator.py)
    │   Gemini 2.5 Flash — plans & dispatches agents via MCP tools
    │
    ├──► Credit Risk Agent    /agents/credit-risk   (LangGraph + XGBoost + SHAP)
    ├──► Fraud Detection Agent /agents/fraud         (LangGraph + IsolationForest)
    ├──► Compliance Agent     /agents/compliance    (LangGraph + RBI rules + LLM)
    └──► Portfolio Agent      /agents/portfolio     (LangGraph + portfolio API)
    │
    ▼  A2A output store → decision matrix
FinalDecision  ──────────────────────────  crew_runner.py
    │
    ▼
PostgreSQL  (applications · decisions · officer_actions · audit_log)
```

Each specialist agent is a self-contained FastAPI sub-app mounted at `/agents/<name>`, implementing the A2A protocol (`/.well-known/agent.json` + `/a2a/tasks/send`).

**Execution modes:**

| Mode | When | Behaviour |
|---|---|---|
| **Full Agentic** | `GEMINI_API_KEY` set + `ENABLE_CREWAI_MANAGER=true` | CrewAI LLM manager autonomously dispatches agents |
| **Direct LangGraph** | No LLM key | All 4 agents run sequentially; same outputs, no LLM manager |

---

## Tech Stack

**Backend**

| Package | Purpose |
|---|---|
| `fastapi` + `uvicorn` | REST API server; hosts all A2A sub-apps |
| `crewai` | LLM orchestrator (manager agent) |
| `langgraph` + `langchain-core` | Specialist agent state machines |
| `langchain-google-genai` + `litellm` | Gemini / Vertex AI LLM integration |
| `xgboost` + `shap` | Credit scoring + feature attribution |
| `scikit-learn` | IsolationForest fraud detection |
| `paddleocr` + `pymupdf` | Document OCR (Aadhaar, PAN PDFs) |
| `sqlalchemy` + `psycopg2-binary` | PostgreSQL ORM + driver |
| `pydantic` v2 | Schema validation (ApplicationContext, FeatureVector) |
| `pyyaml` | Compliance rules config |
| `pandas` + `openpyxl` | CIBIL dataset loading |
| `python-jose` | JWT auth for officer routes |

**Frontend**

| Package | Purpose |
|---|---|
| `react` 18 + `typescript` | UI framework |
| `vite` 5 | Dev server / build tool |
| `tailwindcss` + `shadcn/ui` | Styling + component library |
| `react-router-dom` 6 | Routing |
| `@tanstack/react-query` | Server state management |
| `react-hook-form` + `zod` | Form validation |
| `recharts` | Analytics charts |

---

## Project Structure

```
final_code/
├── backend/
│   ├── main.py                 # FastAPI app — routes, startup, A2A sub-app mounts
│   ├── orchestrator.py         # Pipeline runner: CrewAI mode + direct LangGraph fallback
│   ├── dil.py                  # Data Intelligence Layer (8-stage enrichment pipeline)
│   ├── agent_adapters.py       # Bridges orchestrator ↔ specialist agents
│   ├── agents_base.py          # Shared state: compliance rules, portfolio data
│   ├── crew_runner.py          # Decision matrix → FinalDecision builder
│   ├── tools.py                # MCP tools exposed to the CrewAI manager
│   ├── graphs.py               # LangGraph graphs (used in direct execution mode)
│   ├── schemas.py              # Pydantic models: ApplicationContext, FeatureVector, etc.
│   ├── db.py                   # All DB operations (PostgreSQL via SQLAlchemy)
│   ├── llm_client.py           # LLM abstraction layer
│   ├── llm_config.py           # LLM mode detection (FULL / FALLBACK)
│   ├── auth.py                 # JWT creation + verification
│   ├── document_extractor.py   # PaddleOCR: extract name, Aadhaar no., PAN no. from PDFs
│   ├── dataset_loader.py       # Loads CIBIL + bank statement Excel datasets into memory
│   ├── get_db_schema.py        # DB schema introspection (used by chatbot for context)
│   │
│   ├── agents/
│   │   ├── credit_risk/
│   │   │   ├── app.py          # FastAPI A2A sub-app (agent card + tasks/send)
│   │   │   ├── agent.py        # LangGraph agent definition
│   │   │   ├── inference.py    # XGBoost model inference + SHAP attribution
│   │   │   ├── train_model.py  # Offline training script (run once)
│   │   │   └── models_artifacts/  # Saved model files (.json, .pkl)
│   │   ├── fraud/
│   │   │   ├── app.py          # FastAPI A2A sub-app
│   │   │   └── agent.py        # LangGraph agent: IsolationForest + rule signals
│   │   ├── compliance/
│   │   │   ├── app.py          # FastAPI A2A sub-app
│   │   │   └── agent.py        # LangGraph agent: RBI rule checks + LLM narrative
│   │   └── portfolio/
│   │       ├── app.py          # FastAPI A2A sub-app
│   │       └── agent.py        # LangGraph agent: portfolio exposure analysis
│   │
│   ├── orchestration/
│   │   ├── crew.py             # CrewAI crew assembly, task definition, kickoff
│   │   ├── a2a_client.py       # HTTP client for sending tasks to A2A endpoints
│   │   └── mcp_tools.py        # Tool wrappers for CrewAI manager agent
│   │
│   ├── verification/
│   │   └── verifier.py         # Pre-agent identity gate (document + bureau check)
│   ├── mock_apis/
│   │   └── portfolio.py        # Mock bank portfolio summary API
│   ├── data/                   # fraud_blacklist.json, macro_config.json, compliance_rules.yaml
│   ├── dataset/                # CIBIL + bank statement Excel files (not committed)
│   └── requirements.txt
│
└── frontend/
    ├── src/
    │   ├── App.tsx
    │   ├── pages/
    │   │   ├── LandingPage.tsx
    │   │   ├── ApplyPage.tsx           # Multi-step form + Aadhaar/PAN OCR upload
    │   │   ├── TrackPage.tsx           # Status polling by application ID
    │   │   ├── SuccessPage.tsx
    │   │   └── officer/
    │   │       ├── OfficerLoginPage.tsx
    │   │       ├── OfficerDashboardPage.tsx
    │   │       ├── OfficerApplicationsPage.tsx
    │   │       ├── OfficerApplicationDetailPage.tsx  # Full AI report + action panel
    │   │       └── OfficerAnalyticsPage.tsx
    │   ├── lib/
    │   │   ├── api.ts           # Typed fetch wrappers for all backend endpoints
    │   │   └── types.ts
    │   └── components/
    ├── package.json
    └── vite.config.ts
```

---

## Prerequisites

- Python 3.11+
- Node.js 18+ (or Bun)
- PostgreSQL 14+
- Google Cloud project with Vertex AI **or** a Gemini API key

---

## Setup

### Backend

```bash
cd backend

python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS / Linux

pip install -r requirements.txt
```

### Frontend

```bash
cd frontend
npm install       # or: bun install
```

### Database

PostgreSQL must be running. The app **auto-creates** the `aria` database and all tables on first startup via `db.init_db()` — no migrations needed.

---

## Configuration

Create `backend/.env`:

```env
# LLM — pick one

# Option A: Google AI Studio
GOOGLE_API_KEY=your_key
GEMINI_MODEL=gemini-2.0-flash-exp

# Option B: Vertex AI
CREWAI_LLM_PROVIDER=vertex
VERTEX_PROJECT=your_gcp_project_id
VERTEX_LOCATION=us-central1

# Agentic mode
LLM_USAGE_MODE=FULL              # FULL | FALLBACK
ENABLE_CREWAI_MANAGER=true       # true = CrewAI orchestrator, false = direct pipeline

# Data paths
DATA_DIR=data
DATASET_DIR=dataset
PRELOAD_DATASETS=true            # Load CIBIL Excel on startup
ALLOW_RUNTIME_FILE_FALLBACK=false

# PostgreSQL
PG_USER=postgres
PG_PASSWORD=123456
PG_HOST=localhost
PG_PORT=5432
PG_DB=aria
```

> Without an LLM key, the system runs in **Direct LangGraph** mode — all four agents still execute and produce full outputs; the CrewAI manager step is skipped.

---

## Running the App

**Backend**
```bash
cd backend
uvicorn main:app --reload --port 8000
```
API: `http://localhost:8000`  
Swagger UI: `http://localhost:8000/docs`

**Frontend**
```bash
cd frontend
npm run dev       # or: bun run dev
```
App: `http://localhost:5173`

**Officer login (demo)**
```
Username: admin
Password: admin123
```

---

## Key Modules

| File | What it does |
|---|---|
| `main.py` | Entry point. Mounts A2A agent sub-apps, registers routes, runs DB init and data pre-load on startup |
| `dil.py` | Data Intelligence Layer. Transforms raw form input → enriched `ApplicationContext` in 8 stages (bureau lookup, feature engineering, fraud signals, flag generation) |
| `orchestrator.py` | Runs the full pipeline. Calls `run_via_crewai()` if Gemini available, else `run_direct_pipeline()` |
| `orchestration/crew.py` | Assembles the CrewAI crew (manager agent + task), kicks off, parses JSON output |
| `agent_adapters.py` | Thin adapters that call each agent and normalise their output for the orchestrator |
| `crew_runner.py` | `build_final_decision()` — reads A2A store, applies decision matrix, returns `FinalDecision` |
| `tools.py` | MCP tools registered on the CrewAI manager: `run_credit_risk_assessment`, `run_fraud_detection`, `run_compliance_check`, `run_portfolio_analysis`, `apply_decision_matrix_tool`, `log_audit_tool` |
| `agents/*/agent.py` | LangGraph `StateGraph` definitions for each specialist agent |
| `agents/*/app.py` | FastAPI sub-apps implementing the A2A protocol for each agent |
| `agents/credit_risk/inference.py` | Loads saved XGBoost model, runs prediction, computes SHAP values |
| `verification/verifier.py` | Runs identity pre-checks before the agent pipeline starts |
| `document_extractor.py` | PaddleOCR wrapper for Aadhaar and PAN PDFs |
| `db.py` | All database operations (save application, save decision, officer action, audit log, queue query) |
| `auth.py` | `create_access_token()` + `get_current_officer()` FastAPI dependency |
| `dataset_loader.py` | Loads CIBIL Excel dataset into memory; used by DIL for real bureau lookups |

---

## API Reference

Base URL: `http://localhost:8000`

### Public

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/apply` | Submit loan application |
| `GET` | `/api/status/{app_id}` | Poll application status |
| `POST` | `/api/extract-documents` | OCR extraction from Aadhaar / PAN PDF uploads |
| `GET` | `/api/health` | System health (agents, datasets, LLM mode) |

### Officer (Bearer JWT required)

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/officer/login` | Authenticate, receive JWT |
| `GET` | `/api/officer/queue` | Latest 50 applications with AI recommendation |
| `GET` | `/api/officer/decision/{app_id}` | Full agentic report for one application |
| `POST` | `/api/officer/action/{app_id}` | Submit officer decision |

### Test

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/test/sample` | Inject a well-qualified test application |
| `POST` | `/api/test/rejected` | Inject a fraudulent test application |

---

## Agent Protocol (A2A)

Each agent sub-app exposes two endpoints:

```
GET  /agents/{name}/.well-known/agent.json   # Agent capability card
POST /agents/{name}/a2a/tasks/send           # Execute agent on an application
```

| Agent | Mount path |
|---|---|
| Credit Risk | `/agents/credit-risk` |
| Fraud Detection | `/agents/fraud` |
| Compliance | `/agents/compliance` |
| Portfolio | `/agents/portfolio` |

Agents read shared input from the `FeatureStore` (keyed by `application_id`) and write their outputs to the in-memory A2A store. The orchestrator reads the A2A store after all agents complete to run the decision matrix.

---

## Database Schema

Tables auto-created by `db.init_db()` on startup.

**`applications`** — one row per submission  
**`decisions`** — full agent output payload per application  
**`officer_actions`** — officer approve / reject / escalate actions  
**`audit_log`** — immutable event log (one row per agent event, tool call, or status change)

Application status lifecycle:
```
PENDING → DIL_PROCESSING → AGENTS_RUNNING → DECIDED_PENDING_OFFICER → OFFICER_<DECISION>
```

---

## Team

**Team Tensor4ce**

| Name | Area |
|---|---|
| Yash Agrawal | Agentic ML pipeline, Credit Risk Agent, XGBoost + SHAP |
| Karan Panchal | Backend architecture, FastAPI, CrewAI orchestration |
| Nesar Wagannawar | LangGraph agents, A2A protocol, Fraud & Portfolio agents |
| Krushnali Biradar | Frontend (React / TypeScript), Officer Dashboard, UI/UX |

---

*ARIA — Agentic Risk Intelligence & Analytics · Team Tensor4ce*
