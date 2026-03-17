# Fraud Risk Agent

## Overview

A **LangGraph-based Fraud Risk Agent** that uses an **Isolation Forest** anomaly-detection model, deterministic hard/soft rules, **SHAP explainability**, and **Ollama LLM chain-of-thought explanations** to score loan applications for fraud risk. Exposed via **FastAPI** on port 8000.

---

## Files

| File | Purpose |
|---|---|
| `fraud_model.py` | Feature extraction, IP/bureau mock lookups, Isolation Forest training + inference, SHAP explainability |
| `fraud_agent.py` | LangGraph `StateGraph` agent — wires extract → model → shap → rules → output; FastAPI server |
| `evaluate_model.py` | Evaluation metrics (accuracy, precision, recall, F1, ROC AUC) on synthetic test data |
| `isolation_forest.pkl` | Serialised trained model (auto-generated on first run) |
| `requirements.txt` | Python dependencies |

---

## Data Sources Used from the Codebase

| Source File | What We Use |
|---|---|
| `config/bureau_mock_rules.json` | PAN → CIBIL score, hard enquiries, DPD counts, payment history (overrides + deterministic hash fallback) |
| `static/ip_mock_map.json` | IP prefix → country, proxy/hosting flag, `ip_risk_score` for mock geolocation |
| `static/fraud_blacklist.json` | Set of blacklisted PAN numbers (immediate HIGH_RISK trigger) |
| `config/feature_selection.yaml` | Canonical list of 15 `fraud_features` used as the model's feature vector |
| `test_cases/tc_tc_2025_*.json` | 10 loan application JSONs used for end-to-end evaluation |

---

## Feature Vector (15 Features)

| # | Feature | Source | How It's Derived |
|---|---|---|---|
| 1 | `cibil_score` | Bureau mock | Direct lookup or `hash(PAN) % 600 + 300` |
| 2 | `num_hard_enquiries_6m` | Bureau mock | From bureau record |
| 3 | `dpd_30_count` | Bureau mock | Days-past-due 30+ count |
| 4 | `dpd_90_count` | Bureau mock | Days-past-due 90+ count |
| 5 | `emi_bounce_count` | Derived | `max(0, (650 − cibil) / 120)` |
| 6 | `salary_regularity` | Derived | `min(1.0, 0.5 + payment_history_score / 200)` |
| 7 | `income_stability_score` | Composite | `salary_reg × 0.8 + 0.2 × (1 − credit_util)` |
| 8 | `ip_risk_score` | IP mock map | 1.0 = proxy/hosting, 0.5 = non-IN, 0.0 = clean |
| 9 | `ip_country_mismatch` | IP lookup | 1 if country ≠ "IN" |
| 10 | `application_velocity` | Bureau enquiries | 2 if ≥5, 1 if ≥3, else 0 |
| 11 | `device_fingerprint_new` | Fingerprint suffix | 1 if ends with known test suffixes |
| 12 | `form_fill_time_seconds` | Application JSON | Raw value; <15s = bot, 15-60s = suspicious |
| 13 | `address_pincode_mismatch` | Aadhaar vs IP | 1 if address state ≠ IP region |
| 14 | `income_loan_ratio_outlier` | Computed | 1 if loan/income > 5.0 |
| 15 | `enquiry_spike_flag` | Bureau enquiries | 1 if ≥ 5 hard enquiries in 6 months |

---

## Model: Isolation Forest

### Hyperparameters

```python
Pipeline([
    ("scaler", StandardScaler()),
    ("iforest", IsolationForest(
        contamination=0.10,
        n_estimators=500,
        max_samples=0.7,
        max_features=1.0,
        random_state=42,
    )),
])
```

### Training Data

Synthetic data via `_generate_training_data()` (deterministic seed):

- **10,500 samples total**: 9,000 clean (85.7%) + 1,000 fraud (9.5%) + 500 borderline (4.8%)
- **Clean**: CIBIL ~750±35, zero DPDs, clean IPs, form fill 150-600s
- **Fraud**: CIBIL ~450±60, stacked risk indicators, bot-speed fill 5-35s
- **Borderline**: CIBIL ~640±30, mixed signals

### Inference

```
extract_features(app) → 15-float vector
    → StandardScaler.transform()
    → IsolationForest.decision_function() → raw_score
    → sigmoid(8 × raw_score) → fraud_probability ∈ [0, 1]
```

### Evaluation Metrics

On 2,400 unseen test samples (threshold ≥ 0.45):

| Metric | Value |
|---|---|
| Accuracy | 98.71% |
| Precision | 98.94% |
| Recall | 93.25% |
| F1 Score | 96.01% |
| ROC AUC | 99.95% |

---

## SHAP Explainability

Every prediction includes **SHAP feature contributions** computed via `shap.TreeExplainer` on the Isolation Forest.

### How It Works

1. The scaled feature vector is passed to `TreeExplainer(iforest)`
2. SHAP values are computed for all 15 features
3. Top 5 features (by absolute SHAP value) are returned
4. Each entry includes: feature name, raw value, SHAP value, and direction (`fraud` or `clean`)

### Example Output

```json
"shap_top_features": [
  {"feature": "address_pincode_mismatch", "shap_value": -3.3982, "feature_value": 1, "direction": "fraud"},
  {"feature": "device_fingerprint_new",   "shap_value": -3.0221, "feature_value": 1, "direction": "fraud"},
  {"feature": "ip_risk_score",            "shap_value": -2.3087, "feature_value": 1.0, "direction": "fraud"},
  {"feature": "form_fill_time_seconds",   "shap_value": -1.0624, "feature_value": 28.0, "direction": "fraud"},
  {"feature": "num_hard_enquiries_6m",    "shap_value": -0.3964, "feature_value": 1, "direction": "fraud"}
]
```

> Negative SHAP values push toward anomaly (fraud). The top features explain *why* the model scored this application as risky.

---

## Ollama LLM Explanations

For **SUSPICIOUS** and **HIGH_RISK** cases, the agent calls a local **Ollama** model (`qwen2.5:0.5b`) to generate a natural-language chain-of-thought explanation.

### How It Works

1. Fired rules, soft signals, and top SHAP features are formatted into a prompt
2. The prompt is sent to `http://localhost:11434/api/generate` with `qwen2.5:0.5b`
3. The LLM returns a 2-sentence explanation of why the application is risky
4. LOW_RISK cases skip the LLM call (nothing to explain)
5. If Ollama is unavailable, the field gracefully falls back to `"[LLM unavailable: ...]"`

### Example Output

```
"llm_explanation": "This loan application appears to be suspicious due to several key risk factors:
1. Address Pincode Mismatch — the application uses a different address or postal code,
indicating possible identity fraud. 2. Device fingerprint is new and IP risk is elevated,
suggesting a VPN or proxy is being used from an unfamiliar device."
```

### Requirements

- Ollama running locally (`brew install ollama && ollama serve`)
- Model pulled: `ollama pull qwen2.5:0.5b`

---

## Rule Engine

### Hard Rules → immediate HIGH_RISK (prob ≥ 0.85)

| Rule | Condition |
|---|---|
| `pan_blacklisted` | PAN in `fraud_blacklist.json` |
| `bot_submission` | Form filled in < 15 seconds |
| `foreign_proxy_ip` | VPN/datacenter IP from outside India |
| `serial_defaulter` | ≥ 2 DPD-90s AND ≥ 4 hard enquiries |
| `extreme_lti` | Loan/income ratio > 10x |
| `coordinated_fraud` | VPN + fast form (<45s) + new device |
| `compound_risk` | ≥ 4 simultaneous soft signals |

### Soft Signals → SUSPICIOUS if ≥ 2, or model prob ≥ 0.45

| Signal | Condition |
|---|---|
| `fast_form_fill` | 15–60 seconds |
| `domestic_vpn_ip` | Proxy detected, but country = IN |
| `elevated_ip_risk` | 0 < ip_risk_score < 1.0 |
| `new_device` | First-time device fingerprint |
| `geo_mismatch` | Address state ≠ IP location state |
| `high_lti_ratio` | Loan/income 5–10x |
| `enquiry_spike` | ≥ 5 hard enquiries in 6 months |
| `dpd_90_flag` | Any DPD-90 accounts |
| `chronic_late_payer` | ≥ 3 DPD-30 accounts |
| `emi_bounces` | Any bounced EMI payments |
| `irregular_salary` | Regularity < 0.50 |
| `unstable_income` | Stability < 0.50 |
| `very_low_cibil` | CIBIL < 550 |
| `elevated_enquiries` | 3–4 hard enquiries |
| `foreign_ip_no_vpn` | IP country ≠ IN without VPN flag |

### Decision Matrix

| Level | Condition |
|---|---|
| **HIGH_RISK** | Any hard rule fired, OR model prob ≥ 0.75 |
| **SUSPICIOUS** | Model prob ≥ 0.45, OR ≥ 2 soft signals |
| **LOW_RISK** | Everything else |

---

## LangGraph State Machine

```
┌──────────┐    ┌───────────┐    ┌──────────────┐    ┌─────────────┐    ┌──────────────┐
│ extract  │───▶│ run_model │───▶│ compute_shap │───▶│ apply_rules │───▶│ build_output │───▶ END
└──────────┘    └───────────┘    └──────────────┘    └─────────────┘    └──────────────┘
```

| Node | What It Does |
|---|---|
| `extract` | `extract_features()` + `ip_lookup()` → features & ip_info |
| `run_model` | Isolation Forest `predict()` → fraud_prob |
| `compute_shap` | SHAP TreeExplainer → top 5 feature contributions |
| `apply_rules` | Hard rules + soft signals against features |
| `build_output` | Combines score + rules + SHAP → `FraudOutput`; calls Ollama for SUSPICIOUS/HIGH_RISK |

---

## Output Schema — `FraudOutput`

```json
{
  "fraud_probability": 0.85,
  "fraud_level": "HIGH_RISK",
  "isolation_forest_score": 0.5881,
  "fired_hard_rules": ["coordinated_fraud: VPN + fast form + new device"],
  "fired_soft_signals": ["fast_form_fill: 28s", "domestic_vpn_ip", "new_device", "geo_mismatch"],
  "ip_risk_score": 1.0,
  "ip_country_mismatch": false,
  "application_velocity": 0,
  "identity_consistency": "HIGH",
  "explanation": "REJECT — 1 hard rule(s) fired: coordinated_fraud. Application must be blocked.",
  "recommend_kyc_recheck": true,
  "shap_top_features": [
    {"feature": "address_pincode_mismatch", "shap_value": -3.3982, "feature_value": 1, "direction": "fraud"},
    {"feature": "device_fingerprint_new", "shap_value": -3.0221, "feature_value": 1, "direction": "fraud"}
  ],
  "llm_explanation": "This application is flagged due to coordinated fraud indicators..."
}
```

---

## How to Run

### Setup

```bash
cd fraud_agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### FastAPI Server

```bash
python fraud_agent.py
# Server starts at http://localhost:8000
# Swagger docs at http://localhost:8000/docs
```

### API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/predict` | Run fraud analysis on an application JSON |
| GET | `/health` | Health check |
| GET | `/docs` | Swagger UI |

### cURL Example

```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d @../test_cases/tc_tc_2025_00005.json
```

### Programmatic Usage

```python
from fraud_agent import run_fraud_agent
import json

with open("../test_cases/tc_tc_2025_00005.json") as f:
    app = json.load(f)

result = run_fraud_agent(app)
```

---

## Dependencies

```
numpy>=1.24
scikit-learn>=1.3
langgraph>=0.2
fastapi>=0.110
uvicorn>=0.29
shap>=0.43
requests>=2.31
```

External: **Ollama** running locally with `qwen2.5:0.5b` model pulled.
