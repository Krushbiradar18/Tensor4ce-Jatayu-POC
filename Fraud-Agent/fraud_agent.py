"""Fraud Risk Agent — LangGraph StateGraph producing FraudOutput + FastAPI server."""

from __future__ import annotations
import json, glob
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional
from typing import TypedDict

from fastapi import FastAPI
from pydantic import BaseModel
from langgraph.graph import StateGraph, END

from fraud_model import (
    extract_features, ip_lookup, load_model, predict, shap_explain,
    BLACKLIST, FRAUD_FEATURES,
)

ROOT = Path(__file__).resolve().parent.parent


# ── enums & output schema ─────────────────────────────────────────────────
class FraudLevel(str, Enum):
    LOW_RISK = "LOW_RISK"
    SUSPICIOUS = "SUSPICIOUS"
    HIGH_RISK = "HIGH_RISK"


class IdentityRisk(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass
class FraudOutput:
    fraud_probability: float = 0.0
    fraud_level: FraudLevel = FraudLevel.LOW_RISK
    isolation_forest_score: float = 0.0
    fired_hard_rules: list[str] = field(default_factory=list)
    fired_soft_signals: list[str] = field(default_factory=list)
    ip_risk_score: float = 0.0
    ip_country_mismatch: bool = False
    application_velocity: int = 0
    identity_consistency: IdentityRisk = IdentityRisk.LOW
    explanation: str = ""
    recommend_kyc_recheck: bool = False
    shap_top_features: list[dict] = field(default_factory=list)
    llm_explanation: str = ""


# ── agent state ───────────────────────────────────────────────────────────
class AgentState(TypedDict, total=False):
    application: dict
    features: dict
    ip_info: dict
    fraud_prob: float
    hard_rules: list[str]
    soft_signals: list[str]
    shap_top_features: list[dict]
    llm_explanation: str
    output: dict


# ── node functions ────────────────────────────────────────────────────────
MODEL = load_model()


def extract(state: AgentState) -> AgentState:
    app = state["application"]
    feats = extract_features(app)
    ip_info = ip_lookup(app["ip_metadata"]["ip_address"])
    return {**state, "features": feats, "ip_info": ip_info}


def run_model(state: AgentState) -> AgentState:
    prob = predict(MODEL, state["features"])
    return {**state, "fraud_prob": prob}


def compute_shap(state: AgentState) -> AgentState:
    """Compute SHAP feature contributions for the prediction."""
    try:
        top_feats = shap_explain(MODEL, state["features"], top_k=5)
    except Exception as e:
        print(f"[shap] warning: {e}")
        top_feats = []
    return {**state, "shap_top_features": top_feats}


def _ollama_explain(fired_rules: list[str], soft_signals: list[str],
                    shap_features: list[dict], fraud_prob: float) -> str:
    """Call Ollama qwen2.5:0.5b to produce a 2-sentence CoT fraud explanation."""
    import requests

    shap_summary = "; ".join(
        f"{f['feature']}={f['feature_value']} ({f['direction']}, shap={f['shap_value']:.4f})"
        for f in shap_features[:5]
    )
    prompt = (
        "You are a fraud analyst reviewing a loan application. "
        f"Model fraud probability: {fraud_prob:.2f}. "
        f"Hard rules fired: {fired_rules or 'none'}. "
        f"Soft signals: {soft_signals or 'none'}. "
        f"Top SHAP features driving the score: {shap_summary}. "
        "In exactly 2 sentences, explain why this application is suspicious "
        "and what the key risk factors are. Be specific and concise."
    )
    try:
        resp = requests.post(
            "http://localhost:11434/api/generate",
            json={"model": "qwen2.5:0.5b", "prompt": prompt, "stream": False},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except Exception as e:
        return f"[LLM unavailable: {e}]"


def apply_rules(state: AgentState) -> AgentState:
    """
    Real fraud-analyst logic. Two tiers:

    HARD rules  → any single one = instant HIGH_RISK (reject/block)
      These are things no legitimate applicant should ever trigger.

    SOFT signals → individually just suspicious, but they compound.
      ≥ 2 soft signals  = SUSPICIOUS (escalate to officer)
      ≥ 4 soft signals  = treated as HIGH_RISK even without a hard rule
    """
    f = state["features"]
    app = state["application"]
    hard, soft = [], []

    # ────────────── HARD RULES (instant reject) ──────────────────────────
    # 1. Blacklisted PAN — known fraud / AML / FIR-linked identity
    if app["pan_number"] in BLACKLIST:
        hard.append("pan_blacklisted: PAN found in fraud registry")

    # 2. Bot / script submission — no human fills a loan form in < 15 sec
    if f["form_fill_time_seconds"] < 15:
        hard.append(f"bot_submission: form filled in {int(f['form_fill_time_seconds'])}s (<15s)")

    # 3. Foreign VPN/datacenter IP — Aadhaar is Indian, non-IN datacenter = stolen identity
    if f["ip_risk_score"] >= 1.0 and f["ip_country_mismatch"]:
        hard.append("foreign_proxy_ip: VPN/datacenter IP from outside India")

    # 4. Severe credit delinquency + enquiry churning = serial defaulter re-applying
    if f["dpd_90_count"] >= 2 and f["num_hard_enquiries_6m"] >= 4:
        hard.append(f"serial_defaulter: {f['dpd_90_count']} DPD-90s + {f['num_hard_enquiries_6m']} enquiries")

    # 5. Absurd loan-to-income ratio — asking 10x+ income screams fabricated application
    loan = float(app.get("loan_amount_requested", 0))
    income = float(app.get("annual_income", 1))
    lti_ratio = loan / income if income > 0 else 99
    if lti_ratio > 10:
        hard.append(f"extreme_lti: loan/income ratio {lti_ratio:.1f}x (>10x)")

    # 6. Combination: VPN IP + fast form fill + new device = coordinated fraud attempt
    if f["ip_risk_score"] >= 1.0 and f["form_fill_time_seconds"] < 45 and f["device_fingerprint_new"]:
        hard.append("coordinated_fraud: VPN + fast form + new device")

    # ────────────── SOFT SIGNALS (individually suspicious) ───────────────
    # Each one alone has a legit explanation, but they stack up.

    # Fast form fill (15-60s) — potentially scripted or pre-filled behavior
    if 15 <= f["form_fill_time_seconds"] < 60:
        soft.append(f"fast_form_fill: {int(f['form_fill_time_seconds'])}s (faster than typical)")

    # VPN/proxy IP from India — could be corp VPN, still warrants check
    if f["ip_risk_score"] >= 1.0 and not f["ip_country_mismatch"]:
        soft.append(f"domestic_vpn_ip: proxy/VPN detected (ip_risk={f['ip_risk_score']})")

    # Elevated IP risk (cloud hosting, etc.) but not full proxy
    if 0 < f["ip_risk_score"] < 1.0:
        soft.append(f"elevated_ip_risk: score={f['ip_risk_score']}")

    # New/unseen device fingerprint
    if f["device_fingerprint_new"]:
        soft.append("new_device: first-time device fingerprint")

    # Address state doesn't match IP geolocation state
    if f["address_pincode_mismatch"]:
        soft.append("geo_mismatch: Aadhaar address state ≠ IP location state")

    # High loan-to-income (5-10x) — not absurd but aggressive
    if f["income_loan_ratio_outlier"] and lti_ratio <= 10:
        soft.append(f"high_lti_ratio: loan/income={lti_ratio:.1f}x (>5x)")

    # Enquiry spike — 5+ hard pulls in 6 months = shopping or desperation
    if f["enquiry_spike_flag"]:
        soft.append(f"enquiry_spike: {f['num_hard_enquiries_6m']} hard enquiries in 6 months")

    # Any DPD-90 (even 1) is a red flag, just not an instant reject alone
    if f["dpd_90_count"] >= 1:
        soft.append(f"dpd_90_flag: {f['dpd_90_count']} accounts 90+ days past due")

    # Multiple DPD-30s — pattern of late payments
    if f["dpd_30_count"] >= 3:
        soft.append(f"chronic_late_payer: {f['dpd_30_count']} accounts 30+ days past due")

    # EMI bounces — actual payment failures
    if f["emi_bounce_count"] >= 1:
        soft.append(f"emi_bounces: {f['emi_bounce_count']} bounced EMI payments")

    # Low salary regularity — irregular credits suggest unstable/fake employment
    if f["salary_regularity"] < 0.5:
        soft.append(f"irregular_salary: regularity={f['salary_regularity']} (<0.50)")

    # Low income stability
    if f["income_stability_score"] < 0.5:
        soft.append(f"unstable_income: stability={f['income_stability_score']} (<0.50)")

    # Very low CIBIL alone is a yellow flag from fraud perspective
    if f["cibil_score"] < 550:
        soft.append(f"very_low_cibil: {f['cibil_score']} (<550)")

    # Multiple hard enquiries (3-4) — not a spike but elevated
    if 3 <= f["num_hard_enquiries_6m"] < 5:
        soft.append(f"elevated_enquiries: {f['num_hard_enquiries_6m']} in 6 months")

    # IP country mismatch alone (without VPN flag) — could be roaming
    if f["ip_country_mismatch"] and f["ip_risk_score"] < 1.0:
        soft.append("foreign_ip_no_vpn: IP country ≠ IN (possible roaming)")

    # ─── COMPOUND: too many soft signals = effective hard rule ────────────
    if len(soft) >= 4 and not hard:
        hard.append(f"compound_risk: {len(soft)} simultaneous risk signals detected")

    return {**state, "hard_rules": hard, "soft_signals": soft}


def build_output(state: AgentState) -> AgentState:
    """
    Decision matrix:
      HIGH_RISK  → any hard rule fired, OR model prob ≥ 0.75
      SUSPICIOUS → model prob ≥ 0.45, OR ≥ 2 soft signals
      LOW_RISK   → everything else (clean application, proceed)
    """
    f = state["features"]
    prob = state["fraud_prob"]
    hard = state["hard_rules"]
    soft = state["soft_signals"]

    # ── determine fraud level ─────────────────────────────────────────────
    if hard:
        level = FraudLevel.HIGH_RISK
        prob = max(prob, 0.85)
    elif prob >= 0.75:
        level = FraudLevel.HIGH_RISK
    elif prob >= 0.45 or len(soft) >= 2:
        level = FraudLevel.SUSPICIOUS
        prob = max(prob, 0.45)
    else:
        level = FraudLevel.LOW_RISK

    # ── identity consistency ──────────────────────────────────────────────
    id_flags = sum([
        any("pan_blacklisted" in r for r in hard),
        bool(f["address_pincode_mismatch"]),
        bool(f["ip_country_mismatch"]),
        bool(f["device_fingerprint_new"] and f["ip_risk_score"] >= 1.0),
    ])
    id_risk = IdentityRisk.HIGH if id_flags >= 2 else (
        IdentityRisk.MEDIUM if id_flags == 1 else IdentityRisk.LOW
    )

    # ── human-readable explanation ────────────────────────────────────────
    if level == FraudLevel.HIGH_RISK:
        reasons = hard if hard else [f"model anomaly score {prob:.2f} ≥ 0.75"]
        expl = (
            f"REJECT — {len(hard)} hard rule(s) fired: {'; '.join(reasons)}. "
            f"Additionally {len(soft)} soft signal(s). "
            "Application must be blocked or sent to fraud investigation."
        )
    elif level == FraudLevel.SUSPICIOUS:
        expl = (
            f"ESCALATE - {len(soft)} risk signal(s): {'; '.join(soft[:3])}. "
            f"Model fraud score {prob:.2f}. "
            "Manual review required before approval."
        )
    else:
        if soft:
            expl = (
                f"PROCEED - Low fraud risk. "
                f"{len(soft)} advisory signal(s) noted ({soft[0]}). "
                "No fraud block needed."
            )
        else:
            expl = "PROCEED - No material fraud signals detected."

    out = FraudOutput(
        fraud_probability=round(prob, 4),
        fraud_level=level,
        isolation_forest_score=round(state["fraud_prob"], 4),
        fired_hard_rules=hard,
        fired_soft_signals=soft,
        ip_risk_score=f["ip_risk_score"],
        ip_country_mismatch=bool(f["ip_country_mismatch"]),
        application_velocity=f["application_velocity"],
        identity_consistency=id_risk,
        explanation=expl,
        recommend_kyc_recheck=level != FraudLevel.LOW_RISK,
        shap_top_features=state.get("shap_top_features", []),
        llm_explanation="",
    )

    # Ollama CoT explanation for SUSPICIOUS and HIGH_RISK cases
    if level in (FraudLevel.SUSPICIOUS, FraudLevel.HIGH_RISK):
        out.llm_explanation = _ollama_explain(hard, soft, out.shap_top_features, prob)

    return {**state, "output": asdict(out)}


# ── build graph ───────────────────────────────────────────────────────────
def build_fraud_graph() -> StateGraph:
    g = StateGraph(AgentState)
    g.add_node("extract", extract)
    g.add_node("run_model", run_model)
    g.add_node("compute_shap", compute_shap)
    g.add_node("apply_rules", apply_rules)
    g.add_node("build_output", build_output)
    g.set_entry_point("extract")
    g.add_edge("extract", "run_model")
    g.add_edge("run_model", "compute_shap")
    g.add_edge("compute_shap", "apply_rules")
    g.add_edge("apply_rules", "build_output")
    g.add_edge("build_output", END)
    return g.compile()


# ── run on a single application ───────────────────────────────────────────
def run_fraud_agent(application: dict) -> dict:
    graph = build_fraud_graph()
    result = graph.invoke({"application": application})
    return result["output"]


# ── FastAPI ───────────────────────────────────────────────────────────────
class IpMetadata(BaseModel):
    ip_address: str
    form_fill_seconds: str
    device_fingerprint: str
    user_agent: Optional[str] = None

class Address(BaseModel):
    line1: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None

class ApplicationRequest(BaseModel):
    application_id: str = "MANUAL-001"
    pan_number: str
    annual_income: float
    loan_amount_requested: float
    address: Address = Address()
    ip_metadata: IpMetadata
    # optional fields the model doesn't strictly need
    applicant_name: Optional[str] = None
    aadhaar_last4: Optional[str] = None
    date_of_birth: Optional[str] = None
    employment_type: Optional[str] = None
    loan_purpose: Optional[str] = None

    model_config = {"extra": "allow"}  # pass through any extra fields from test-case JSONs

app = FastAPI(title="Fraud Risk Agent", version="1.0")

@app.post("/predict")
def predict_fraud(req: ApplicationRequest):
    return run_fraud_agent(req.model_dump())

@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("fraud_agent:app", host="0.0.0.0", port=8000, reload=True)
