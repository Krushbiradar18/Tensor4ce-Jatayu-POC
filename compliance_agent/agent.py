import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from langgraph.graph import END, StateGraph

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

try:
    from .schemas import (
        ApplicationFormData,
        BankStatementData,
        ComplianceOutput,
        ComplianceState,
        CreditAgentOutput,
        FraudAgentOutput,
        MacroConfigData,
    )
except ImportError:
    from schemas import (
        ApplicationFormData,
        BankStatementData,
        ComplianceOutput,
        ComplianceState,
        CreditAgentOutput,
        FraudAgentOutput,
        MacroConfigData,
    )


load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))


def _get_api_key() -> str:
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""


def _get_model() -> str:
    return os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")


def _classify_llm_error(error: str) -> str:
    lowered = error.lower()
    if "429" in lowered or "rate limit" in lowered or "quota" in lowered or "resource exhausted" in lowered:
        return "rate_limited"
    if "api key" in lowered or "permission" in lowered or "authentication" in lowered:
        return "auth_error"
    return "error"


def _llm_disabled() -> bool:
    return os.environ.get("LLM_USAGE_MODE", "FULL").upper() == "FALLBACK"


def _vertex_stream_url(model_name: str, api_key: str) -> str:
    return (
        "https://aiplatform.googleapis.com/v1/"
        f"publishers/google/models/{model_name}:streamGenerateContent?key={api_key}"
    )


def _extract_text_from_vertex_stream(raw_text: str) -> str:
    text = (raw_text or "").strip()
    if not text:
        return ""

    def _collect_chunks(obj: dict) -> list[str]:
        out: list[str] = []
        candidates = obj.get("candidates") or []
        for candidate in candidates:
            parts = ((candidate.get("content") or {}).get("parts") or [])
            for part in parts:
                part_text = part.get("text")
                if part_text:
                    out.append(part_text)
        return out

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return "\n".join(_collect_chunks(parsed)).strip()
        if isinstance(parsed, list):
            chunks: list[str] = []
            for item in parsed:
                if isinstance(item, dict):
                    chunks.extend(_collect_chunks(item))
            return "\n".join(chunks).strip()
    except json.JSONDecodeError:
        pass

    chunks = []
    for line in text.splitlines():
        line = line.strip()
        if not line or not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            continue
        try:
            obj = json.loads(payload)
            if isinstance(obj, dict):
                chunks.extend(_collect_chunks(obj))
        except json.JSONDecodeError:
            continue
    return "\n".join(chunks).strip()


def _call_vertex_llm(prompt: str) -> str:
    api_key = _get_api_key()
    model = _get_model()

    if not api_key:
        raise ValueError("GEMINI_API_KEY/GOOGLE_API_KEY not set for Vertex AI")

    payload = json.dumps(
        {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {"maxOutputTokens": 350},
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        _vertex_stream_url(model, api_key),
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8", errors="ignore")
    text = _extract_text_from_vertex_stream(raw)
    if not text:
        raise ValueError("Empty response from Vertex streamGenerateContent")
    return text


def _age_years(dob: date, reference_date: date) -> int:
    return reference_date.year - dob.year - ((reference_date.month, reference_date.day) < (dob.month, dob.day))


def _fallback_narratives(state: ComplianceState) -> tuple[str, str]:
    flags = ", ".join(state["compliance_flags"]) if state["compliance_flags"] else "no flags"
    narrative = (
        f"Compliance status is {state['compliance_status']}. "
        f"Key checks: RBI compliant={state['rbi_compliant']}, KYC complete={state['kyc_complete']}, "
        f"AML flagged={state['aml_flagged']}, AML check required={state['aml_check_required']}. "
        f"Triggered flags: {flags}."
    )
    audit_narrative = (
        "Automated fallback narrative generated because LLM was unavailable or disabled. "
        f"Status={state['compliance_status']}; RBI compliant={state['rbi_compliant']}; "
        f"KYC complete={state['kyc_complete']}; flags={flags}."
    )
    return narrative, audit_narrative


def node_eligibility_check(state: ComplianceState) -> dict:
    application = state["application"]
    flags = state["compliance_flags"]

    today = date.today()
    current_age = _age_years(application.date_of_birth, today)

    maturity_year = today.year + (application.loan_tenure_months // 12)
    maturity_month = today.month + (application.loan_tenure_months % 12)
    if maturity_month > 12:
        maturity_year += 1
        maturity_month -= 12
    maturity_date = date(maturity_year, maturity_month, today.day if today.day <= 28 else 28)
    age_at_maturity = _age_years(application.date_of_birth, maturity_date)

    age_eligible = (21 <= current_age <= 65) and (age_at_maturity <= 65)
    if not age_eligible:
        flags.append("age_ineligible")

    monthly_income = application.annual_income / 12.0
    income_eligible = monthly_income >= 15000
    if not income_eligible:
        flags.append("income_below_minimum")

    income_docs = {"form_16", "salary_slip", "itr"}
    uploaded_docs_set = {doc.lower() for doc in application.uploaded_docs}
    has_income_doc = any(doc in uploaded_docs_set for doc in income_docs)
    pan_format_valid = bool(re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]$", application.pan_number))
    kyc_complete = pan_format_valid and ("pan_card" in uploaded_docs_set) and has_income_doc
    if not kyc_complete:
        flags.append("kyc_incomplete")

    purpose_valid = application.loan_purpose == "PERSONAL"

    compliance_status = state["compliance_status"]
    if not all([age_eligible, income_eligible, kyc_complete]):
        compliance_status = "FAIL"

    return {
        "age_eligible": age_eligible,
        "income_eligible": income_eligible,
        "kyc_complete": kyc_complete,
        "purpose_valid": purpose_valid,
        "compliance_status": compliance_status,
        "compliance_flags": flags,
    }


def node_rbi_policy_check(state: ComplianceState) -> dict:
    if state["compliance_status"] == "FAIL":
        return {}

    application = state["application"]
    credit_output = state["credit_output"]
    flags = state["compliance_flags"]

    foir_within_limit = credit_output.foir <= 0.50
    if not foir_within_limit:
        flags.append("foir_exceeds_rbi_limit")

    max_allowed = 20.0 * (application.annual_income / 12.0)
    loan_amount_eligible = application.loan_amount_requested <= max_allowed
    if not loan_amount_eligible:
        flags.append("loan_amount_exceeds_policy_cap")

    tenure_within_limit = application.loan_tenure_months <= 84
    if not tenure_within_limit:
        flags.append("tenure_exceeds_maximum")

    prepayment_penalty_applicable = False
    rbi_compliant = all([foir_within_limit, loan_amount_eligible, tenure_within_limit])

    compliance_status = state["compliance_status"]
    if (not rbi_compliant) and compliance_status != "FAIL":
        compliance_status = "FAIL"

    return {
        "foir_within_limit": foir_within_limit,
        "loan_amount_eligible": loan_amount_eligible,
        "tenure_within_limit": tenure_within_limit,
        "prepayment_penalty_applicable": prepayment_penalty_applicable,
        "rbi_compliant": rbi_compliant,
        "compliance_status": compliance_status,
        "compliance_flags": flags,
    }


def node_aml_kyc_check(state: ComplianceState) -> dict:
    if state["compliance_status"] == "FAIL":
        return {}

    fraud_output = state["fraud_output"]
    bank_data = state["bank_data"]
    macro_data = state["macro_data"]
    application = state["application"]
    flags = state["compliance_flags"]

    compliance_status = state["compliance_status"]
    aml_flagged = state["aml_flagged"]
    aml_check_required = state["aml_check_required"]
    kyc_complete = state["kyc_complete"]

    if fraud_output.fraud_level == "HIGH_RISK":
        aml_flagged = True
        compliance_status = "FAIL"
        flags.append("aml_block_high_risk_fraud")
        return {
            "aml_flagged": aml_flagged,
            "compliance_status": compliance_status,
            "compliance_flags": flags,
        }

    if fraud_output.fraud_level == "SUSPICIOUS" and fraud_output.fraud_probability > 0.40:
        aml_check_required = True
        if compliance_status != "FAIL":
            compliance_status = "ESCALATE"
        flags.append("aml_escalation_suspicious_profile")

    if not fraud_output.kyc_verified:
        kyc_complete = False
        flags.append("kyc_failed_fraud_check")
        if compliance_status != "FAIL":
            compliance_status = "FAIL"

    declared_monthly = application.annual_income / 12.0
    threshold = 0.70 * declared_monthly
    income_mismatch = bank_data.avg_monthly_credit < threshold
    if income_mismatch:
        flags.append("income_mismatch_bank_vs_declared")

    repayment_history_concern = bank_data.emi_bounce_count > 2
    if repayment_history_concern:
        flags.append("emi_bounce_count_elevated")

    if income_mismatch and repayment_history_concern and compliance_status != "FAIL":
        compliance_status = "ESCALATE"

    if macro_data.stress_scenario == "HIGH_STRESS":
        if macro_data.sector_npa_rates.get("PERSONAL", 0.0) > 0.05:
            flags.append("high_stress_sector_npa_review_required")

    return {
        "aml_flagged": aml_flagged,
        "aml_check_required": aml_check_required,
        "kyc_complete": kyc_complete,
        "income_mismatch": income_mismatch,
        "repayment_history_concern": repayment_history_concern,
        "compliance_status": compliance_status,
        "compliance_flags": flags,
    }


def node_fairness_audit(state: ComplianceState) -> dict:
    if state["compliance_status"] == "FAIL":
        return {}

    application = state["application"]
    credit_output = state["credit_output"]
    flags = state["compliance_flags"]

    fairness_flag = state["fairness_flag"]
    if application.employment_type == "SELF_EMPLOYED":
        salaried_baseline_score = 50.0
        if credit_output.risk_score > (salaried_baseline_score + 15):
            fairness_flag = True
            flags.append("employment_type_bias_detected")

    gender_logged_only = True
    geographic_bias_flag = False

    return {
        "fairness_flag": fairness_flag,
        "gender_logged_only": gender_logged_only,
        "geographic_bias_flag": geographic_bias_flag,
        "compliance_flags": flags,
    }


def node_llm_narrative(state: ComplianceState) -> dict:
    prompt = f"""
You are a compliance officer at an Indian bank reviewing a personal loan application.
Based on the compliance check results below, generate TWO concise narratives.

--- COMPLIANCE RESULTS ---
Status: {state['compliance_status']}
RBI Compliant: {state['rbi_compliant']}
KYC Complete: {state['kyc_complete']}
Age Eligible: {state['age_eligible']}
Income Eligible: {state['income_eligible']}
FOIR Within Limit: {state['foir_within_limit']} (FOIR value: {state['credit_output'].foir})
Loan Amount Eligible: {state['loan_amount_eligible']}
Tenure Within Limit: {state['tenure_within_limit']}
AML Flagged: {state['aml_flagged']}
AML Check Required: {state['aml_check_required']}
Income Mismatch: {state['income_mismatch']}
Fairness Flag: {state['fairness_flag']}
Compliance Flags Triggered: {state['compliance_flags']}
Fraud Level: {state['fraud_output'].fraud_level}
Macro Stress Scenario: {state['macro_data'].stress_scenario}

--- OUTPUT REQUIRED ---
Generate:
1. NARRATIVE: 2-3 short lines for the credit officer explaining pass/fail and immediate action.
2. AUDIT_NARRATIVE: 1-2 short formal sentences with key rule basis only.

Keep total output under 90 words and avoid repetition.

Respond ONLY in this exact JSON format (no markdown, no extra text):
{{
  "narrative": "...",
  "audit_narrative": "..."
}}
"""

    narrative, audit_narrative = _fallback_narratives(state)
    llm_status = "fallback"
    llm_provider_error = ""

    if _llm_disabled():
        return {
            "narrative": narrative,
            "audit_narrative": audit_narrative,
            "audit_ready": True,
            "llm_status": "disabled",
            "llm_provider_error": "LLM_USAGE_MODE=FALLBACK",
        }

    if not _get_api_key():
        return {
            "narrative": narrative,
            "audit_narrative": audit_narrative,
            "audit_ready": True,
            "llm_status": "no_api_key",
            "llm_provider_error": "GEMINI_API_KEY/GOOGLE_API_KEY not set for Vertex AI",
        }

    try:
        content = _call_vertex_llm(prompt)
        stripped = content.strip()
        if stripped.startswith("```"):
            stripped = re.sub(r"^```[a-zA-Z]*", "", stripped).strip()
            stripped = re.sub(r"```$", "", stripped).strip()

        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            narrative = str(parsed.get("narrative", narrative))
            audit_narrative = str(parsed.get("audit_narrative", audit_narrative))
            llm_status = "success"
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="ignore")
        llm_provider_error = f"HTTP {exc.code}: {error_body[:300]}"
        llm_status = _classify_llm_error(llm_provider_error)
    except Exception as exc:
        llm_provider_error = str(exc)
        llm_status = _classify_llm_error(llm_provider_error)

    return {
        "narrative": narrative,
        "audit_narrative": audit_narrative,
        "audit_ready": True,
        "llm_status": llm_status,
        "llm_provider_error": llm_provider_error,
    }


graph = StateGraph(ComplianceState)

graph.add_node("eligibility_check", node_eligibility_check)
graph.add_node("rbi_policy_check", node_rbi_policy_check)
graph.add_node("aml_kyc_check", node_aml_kyc_check)
graph.add_node("fairness_audit", node_fairness_audit)
graph.add_node("llm_narrative", node_llm_narrative)

graph.set_entry_point("eligibility_check")
graph.add_edge("eligibility_check", "rbi_policy_check")
graph.add_edge("rbi_policy_check", "aml_kyc_check")
graph.add_edge("aml_kyc_check", "fairness_audit")
graph.add_edge("fairness_audit", "llm_narrative")
graph.add_edge("llm_narrative", END)

compliance_graph = graph.compile()


def run_compliance_agent(
    application: ApplicationFormData,
    credit_output: CreditAgentOutput,
    fraud_output: FraudAgentOutput,
    bank_data: BankStatementData,
    macro_data: MacroConfigData,
) -> ComplianceOutput:
    initial_state: ComplianceState = {
        "application": application,
        "credit_output": credit_output,
        "fraud_output": fraud_output,
        "bank_data": bank_data,
        "macro_data": macro_data,
        "age_eligible": False,
        "income_eligible": False,
        "kyc_complete": False,
        "purpose_valid": False,
        "foir_within_limit": False,
        "loan_amount_eligible": False,
        "tenure_within_limit": False,
        "prepayment_penalty_applicable": False,
        "aml_flagged": False,
        "aml_check_required": False,
        "income_mismatch": False,
        "repayment_history_concern": False,
        "fairness_flag": False,
        "gender_logged_only": False,
        "geographic_bias_flag": False,
        "compliance_flags": [],
        "compliance_status": "PASS",
        "rbi_compliant": False,
        "audit_ready": False,
        "narrative": "",
        "audit_narrative": "",
        "llm_status": "not_called",
        "llm_provider_error": "",
    }

    final_state = compliance_graph.invoke(initial_state)

    return ComplianceOutput(
        compliance_status=final_state["compliance_status"],
        rbi_compliant=final_state["rbi_compliant"],
        kyc_complete=final_state["kyc_complete"],
        age_eligible=final_state["age_eligible"],
        income_eligible=final_state["income_eligible"],
        foir_within_limit=final_state["foir_within_limit"],
        loan_amount_eligible=final_state["loan_amount_eligible"],
        tenure_within_limit=final_state["tenure_within_limit"],
        aml_flagged=final_state["aml_flagged"],
        aml_check_required=final_state["aml_check_required"],
        income_mismatch=final_state["income_mismatch"],
        fairness_flag=final_state["fairness_flag"],
        compliance_flags=final_state["compliance_flags"],
        audit_ready=final_state["audit_ready"],
        narrative=final_state["narrative"],
        audit_narrative=final_state["audit_narrative"],
        llm_status=final_state["llm_status"],
        llm_provider_error=final_state["llm_provider_error"],
    )
