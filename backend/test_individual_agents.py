"""
test_individual_agents.py — Run curated cases against credit, fraud, compliance, or all.

Usage:
    python test_individual_agents.py --agent credit
    python test_individual_agents.py --agent fraud --limit 10
    python test_individual_agents.py --agent compliance
    python test_individual_agents.py --agent all --output individual_agent_results.json
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import types
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = Path(__file__).resolve().parent

os.environ.setdefault("LLM_USAGE_MODE", "FALLBACK")

sys.path.insert(0, str(BACKEND_DIR))
sys.path.append(str(ROOT / "compliance_agent"))
sys.path.append(str(ROOT / "Fraud-Agent"))
sys.path.append(str(ROOT / "credit_backend"))

import dataset_loader
from generate_agent_testcases import build_cases


def _load_module(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


compliance_schemas = _load_module("compliance_schemas_for_tests", ROOT / "compliance_agent" / "schemas.py")
ApplicationFormData = compliance_schemas.ApplicationFormData
BankStatementData = compliance_schemas.BankStatementData
CreditAgentOutput = compliance_schemas.CreditAgentOutput
FraudAgentOutput = compliance_schemas.FraudAgentOutput
MacroConfigData = compliance_schemas.MacroConfigData


def _load_compliance_runner():
    previous_schemas = sys.modules.get("schemas")
    sys.modules["schemas"] = compliance_schemas
    try:
        module = _load_module("compliance_agent_runner_for_tests", ROOT / "compliance_agent" / "agent.py")
        return module.run_compliance_agent
    finally:
        if previous_schemas is not None:
            sys.modules["schemas"] = previous_schemas
        else:
            sys.modules.pop("schemas", None)


DEFAULT_CASES = BACKEND_DIR / "agent_testcases.json"


def load_cases(limit: int | None = None) -> list[dict]:
    if DEFAULT_CASES.exists():
        cases = json.loads(DEFAULT_CASES.read_text(encoding="utf-8"))
    else:
        cases = build_cases()
    return cases[:limit] if limit else cases


def ensure_datasets_loaded() -> None:
    dataset_loader.load_datasets(str(ROOT / "dataset"))


def credit_input(case: dict) -> dict:
    return {
        "pan_number": case["pan"],
        "loan_amount": float(case["loan_amount_requested"]),
        "loan_type": case.get("loan_purpose", "PERSONAL"),
        "loan_tenure_months": int(case.get("loan_tenure_months", 60)),
        "declared_monthly_income": float(case["monthly_income"]),
    }


def fraud_input(case: dict) -> dict:
    fast_fill = 25 if case["label"] in {"high_enquiries", "elevated_enquiries"} else 180
    if case["label"] in {"severe_delinquency", "very_low_score"}:
        fast_fill = 40
    ip_address = "8.8.8.8" if case["label"] in {"high_enquiries", "mixed_delinquency"} else "103.21.1.1"

    return {
        "application_id": f"AGENT-TEST-{case['prospect_id']}",
        "pan_number": case["pan"],
        "annual_income": float(case["annual_income"]),
        "loan_amount_requested": float(case["loan_amount_requested"]),
        "address": {
            "state": "Maharashtra",
            "city": "Mumbai",
            "pincode": "400001",
        },
        "ip_metadata": {
            "ip_address": ip_address,
            "form_fill_seconds": fast_fill,
            "device_fingerprint": f"device_{case['prospect_id']}_new" if case["label"] in {"high_enquiries", "mixed_delinquency"} else f"device_{case['prospect_id']}",
            "user_agent": "Mozilla/5.0",
        },
    }


def _credit_to_compliance(credit_result: dict) -> CreditAgentOutput:
    model_score = credit_result.get("risk_score", 50.0)
    risk_category = credit_result.get("risk_category", "Medium-Low Risk")
    band_map = {
        "Low Risk": "LOW",
        "Medium-Low Risk": "MEDIUM",
        "Medium-High Risk": "HIGH",
        "High Risk": "VERY_HIGH",
    }
    return CreditAgentOutput(
        risk_score=float(model_score),
        risk_band=band_map.get(risk_category, "MEDIUM"),
        foir=0.42,
        dti_ratio=0.32,
        macro_adjusted=False,
    )


def _fraud_to_compliance(fraud_result: dict) -> FraudAgentOutput:
    level = fraud_result.get("fraud_level", "LOW_RISK")
    if level == "LOW_RISK":
        level = "CLEAN"
    return FraudAgentOutput(
        fraud_level=level,
        fraud_probability=float(fraud_result.get("fraud_probability", 0.0)),
        kyc_verified=fraud_result.get("identity_consistency", "LOW") == "LOW",
        triggered_rules=fraud_result.get("fired_hard_rules", []) + fraud_result.get("fired_soft_signals", []),
    )


def _application_for_compliance(case: dict) -> ApplicationFormData:
    age = int(case["age"])
    return ApplicationFormData(
        pan_number=case["pan"],
        date_of_birth=date(date.today().year - age, 1, 1),
        employment_type=case.get("employment_type", "SALARIED"),
        annual_income=float(case["annual_income"]),
        loan_amount_requested=float(case["loan_amount_requested"]),
        loan_tenure_months=int(case.get("loan_tenure_months", 60)),
        loan_purpose="PERSONAL",
        existing_emi_monthly=5000.0,
        uploaded_docs=["pan_card", "form_16", "salary_slip"],
        employer_name="Agent Test Employer",
        gender="MALE",
        marital_status="SINGLE",
    )


def _bank_for_case(case: dict) -> BankStatementData:
    bank = dataset_loader.get_bank_data(case["pan"]) or {}
    return BankStatementData(
        avg_monthly_credit=float(bank.get("avg_monthly_credit", case["monthly_income"] * 0.95)),
        emi_bounce_count=int(bank.get("emi_bounce_count", 0 if case["label"] not in {"mixed_delinquency", "severe_delinquency"} else 3)),
        salary_credit_regularity=float(bank.get("salary_regularity", 0.92)),
    )


def _macro() -> MacroConfigData:
    return MacroConfigData(
        stress_scenario="NORMAL",
        rbi_repo_rate=6.5,
        sector_npa_rates={"PERSONAL": 0.038},
    )


def run_credit_case(case: dict) -> dict:
    try:
        from credit_risk_agent import credit_risk_graph
        state = credit_risk_graph.invoke(credit_input(case))
        return state.get("final_result", {})
    except Exception as exc:
        return {
            "error": str(exc),
            "testing_note": "Credit agent requires credit_backend PostgreSQL profile DB to be reachable.",
        }


def run_fraud_case(case: dict) -> dict:
    from fraud_agent import run_fraud_agent
    return run_fraud_agent(fraud_input(case))


def run_compliance_case(case: dict) -> dict:
    run_compliance_agent = _load_compliance_runner()
    credit_result = run_credit_case(case)
    fraud_result = run_fraud_case(case)

    if credit_result.get("error"):
        derived_band = "LOW"
        if case["credit_score"] < 620:
            derived_band = "VERY_HIGH"
        elif case["credit_score"] < 660:
            derived_band = "HIGH"
        elif case["credit_score"] < 720:
            derived_band = "MEDIUM"

        credit_output = CreditAgentOutput(
            risk_score=max(1.0, min(99.0, 900 - float(case["credit_score"])) / 5),
            risk_band=derived_band,
            foir=0.42,
            dti_ratio=0.32,
            macro_adjusted=False,
        )
    else:
        credit_output = _credit_to_compliance(credit_result)

    result = run_compliance_agent(
        application=_application_for_compliance(case),
        credit_output=credit_output,
        fraud_output=_fraud_to_compliance(fraud_result),
        bank_data=_bank_for_case(case),
        macro_data=_macro(),
    )
    payload = result.model_dump(mode="json")
    if credit_result.get("error"):
        payload["testing_note"] = "Used case-derived credit input because direct credit agent DB dependency is unavailable."
    return payload


def summarize(agent: str, case: dict, result: dict) -> str:
    if agent == "credit":
        if result.get("error"):
            return f"{case['label']}: ERROR {result['error']}"
        return f"{case['label']}: risk_category={result.get('risk_category')} risk_score={result.get('risk_score')} llm={result.get('llm_status', 'n/a')}"
    if agent == "fraud":
        return f"{case['label']}: fraud_level={result.get('fraud_level')} prob={result.get('fraud_probability')} hard={len(result.get('fired_hard_rules', []))} soft={len(result.get('fired_soft_signals', []))}"
    return f"{case['label']}: compliance_status={result.get('compliance_status')} llm={result.get('llm_status')} flags={len(result.get('compliance_flags', []))}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run curated cases on individual agents")
    parser.add_argument("--agent", choices=["credit", "fraud", "compliance", "all"], default="all")
    parser.add_argument("--limit", type=int, default=15)
    parser.add_argument("--output", help="Write full results to JSON")
    args = parser.parse_args()

    ensure_datasets_loaded()
    cases = load_cases(args.limit)
    results: list[dict] = []

    for case in cases:
        case_result = {"label": case["label"], "pan": case["pan"]}
        if args.agent in {"credit", "all"}:
            credit_result = run_credit_case(case)
            case_result["credit"] = credit_result
            print(summarize("credit", case, credit_result))
        if args.agent in {"fraud", "all"}:
            fraud_result = run_fraud_case(case)
            case_result["fraud"] = fraud_result
            print(summarize("fraud", case, fraud_result))
        if args.agent in {"compliance", "all"}:
            compliance_result = run_compliance_case(case)
            case_result["compliance"] = compliance_result
            print(summarize("compliance", case, compliance_result))
        results.append(case_result)
        print("-" * 60)

    if args.output:
        Path(args.output).write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"Wrote full results to {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
