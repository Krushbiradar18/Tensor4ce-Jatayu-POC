import io
import json
import sys
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from agent import run_compliance_agent
from schemas import (
    ApplicationFormData,
    BankStatementData,
    CreditAgentOutput,
    FraudAgentOutput,
    MacroConfigData,
)


TEST_SCENARIOS = [
    {"label": "CLEAN_PASS", "filters": {"risk_band": "LOW", "fraud_level": "CLEAN"}},
    {"label": "FOIR_FAIL", "filters": {"foir": ">0.55"}},
    {"label": "AML_ESCALATE", "filters": {"fraud_level": "SUSPICIOUS", "fraud_probability": ">0.40"}},
    {"label": "AML_HARD_BLOCK", "filters": {"fraud_level": "HIGH_RISK"}},
    {"label": "INCOME_MISMATCH", "filters": {"income_mismatch_trigger": True}},
]


SCENARIO_CREDIT = {
    "CLEAN_PASS": CreditAgentOutput(
        risk_score=28.0,
        risk_band="LOW",
        foir=0.38,
        dti_ratio=2.1,
        macro_adjusted=False,
    ),
    "FOIR_FAIL": CreditAgentOutput(
        risk_score=54.0,
        risk_band="MEDIUM",
        foir=0.59,
        dti_ratio=3.3,
        macro_adjusted=False,
    ),
    "AML_ESCALATE": CreditAgentOutput(
        risk_score=61.0,
        risk_band="HIGH",
        foir=0.44,
        dti_ratio=3.9,
        macro_adjusted=False,
    ),
    "AML_HARD_BLOCK": CreditAgentOutput(
        risk_score=72.0,
        risk_band="HIGH",
        foir=0.44,
        dti_ratio=4.2,
        macro_adjusted=False,
    ),
    "INCOME_MISMATCH": CreditAgentOutput(
        risk_score=49.0,
        risk_band="MEDIUM",
        foir=0.41,
        dti_ratio=3.0,
        macro_adjusted=False,
    ),
}


SCENARIO_FRAUD = {
    "CLEAN_PASS": FraudAgentOutput(
        fraud_level="CLEAN",
        fraud_probability=0.05,
        kyc_verified=True,
        triggered_rules=[],
    ),
    "FOIR_FAIL": FraudAgentOutput(
        fraud_level="LOW_RISK",
        fraud_probability=0.12,
        kyc_verified=True,
        triggered_rules=[],
    ),
    "AML_ESCALATE": FraudAgentOutput(
        fraud_level="SUSPICIOUS",
        fraud_probability=0.65,
        kyc_verified=True,
        triggered_rules=["suspicious_pattern_detected"],
    ),
    "AML_HARD_BLOCK": FraudAgentOutput(
        fraud_level="HIGH_RISK",
        fraud_probability=0.85,
        kyc_verified=False,
        triggered_rules=["hard_enquiries_exceed_threshold", "emi_bounce_count_exceeded"],
    ),
    "INCOME_MISMATCH": FraudAgentOutput(
        fraud_level="LOW_RISK",
        fraud_probability=0.18,
        kyc_verified=True,
        triggered_rules=[],
    ),
}


def load_data_from_zip(zip_path: str, csv_filename: str) -> pd.DataFrame:
    with zipfile.ZipFile(zip_path, "r") as z:
        with z.open(csv_filename) as f:
            df = pd.read_csv(io.BytesIO(f.read()))
    return df


def resolve_zip_inputs(zip_path: Path) -> tuple[str, pd.DataFrame]:
    with zipfile.ZipFile(zip_path, "r") as z:
        names = z.namelist()
        csv_candidates = [name for name in names if name.lower().endswith(".csv")]
        if not csv_candidates:
            raise FileNotFoundError("No CSV file found inside synthetic_loans.zip")
        csv_filename = csv_candidates[0]
    return csv_filename, load_data_from_zip(str(zip_path), csv_filename)


def pick_column(df: pd.DataFrame, options: list[str]) -> str | None:
    for candidate in options:
        if candidate in df.columns:
            return candidate
    return None


def parse_date(raw_value: object) -> date:
    parsed = pd.to_datetime(raw_value, errors="coerce")
    if pd.isna(parsed):
        return date(1990, 1, 1)
    return parsed.date()


def normalize_employment(value: object) -> str:
    raw = str(value).strip().upper()
    if raw in {"SALARIED", "SALARIED_EMPLOYEE"}:
        return "SALARIED"
    if raw in {"SELF_EMPLOYED", "SELF-EMPLOYED", "SELF EMPLOYED"}:
        return "SELF_EMPLOYED"
    if "SELF" in raw:
        return "SELF_EMPLOYED"
    return "SALARIED"


def normalize_gender(value: object) -> str:
    raw = str(value).strip().upper()
    if raw in {"MALE", "FEMALE", "OTHER"}:
        return raw
    return "OTHER"


def normalize_marital(value: object) -> str:
    raw = str(value).strip().upper()
    if raw in {"SINGLE", "MARRIED", "DIVORCED"}:
        return raw
    return "SINGLE"


def row_to_application(row: pd.Series, colmap: dict[str, str | None]) -> ApplicationFormData:
    return ApplicationFormData(
        pan_number=str(row[colmap["pan"]]) if colmap["pan"] else "ABCDE1234F",
        date_of_birth=parse_date(row[colmap["dob"]]) if colmap["dob"] else date(1990, 1, 1),
        employment_type=normalize_employment(row[colmap["employment"]]) if colmap["employment"] else "SALARIED",
        annual_income=float(row[colmap["income"]]) if colmap["income"] else 1200000.0,
        loan_amount_requested=float(row[colmap["loan_amount"]]) if colmap["loan_amount"] else 500000.0,
        loan_tenure_months=int(row[colmap["tenure"]]) if colmap["tenure"] else 60,
        loan_purpose="PERSONAL",
        existing_emi_monthly=float(row[colmap["existing_emi"]]) if colmap["existing_emi"] else 10000.0,
        uploaded_docs=["pan_card", "bank_statement", "form_16"],
        employer_name=str(row[colmap["employer"]]) if colmap["employer"] else "Unknown Employer",
        gender=normalize_gender(row[colmap["gender"]]) if colmap["gender"] else "OTHER",
        marital_status=normalize_marital(row[colmap["marital"]]) if colmap["marital"] else "SINGLE",
    )


def _is_baseline_eligible(row: pd.Series, colmap: dict[str, str | None]) -> bool:
    dob_raw = row[colmap["dob"]] if colmap["dob"] else "1990-01-01"
    dob = parse_date(dob_raw)
    today = date.today()
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

    annual_income = float(row[colmap["income"]]) if colmap["income"] else 1200000.0
    monthly_income = annual_income / 12.0

    tenure = int(row[colmap["tenure"]]) if colmap["tenure"] else 60
    max_allowed = 20.0 * monthly_income
    loan_amount = float(row[colmap["loan_amount"]]) if colmap["loan_amount"] else 500000.0

    return (21 <= age <= 60) and (monthly_income >= 15000.0) and (tenure <= 84) and (loan_amount <= max_allowed)


def align_application_for_scenario(application: ApplicationFormData, scenario_label: str) -> ApplicationFormData:
    monthly_income = application.annual_income / 12.0
    max_allowed = 20.0 * monthly_income

    safe_loan_amount = min(application.loan_amount_requested, max_allowed * 0.85)
    safe_tenure = min(application.loan_tenure_months, 60)

    if scenario_label in {"CLEAN_PASS", "FOIR_FAIL", "AML_ESCALATE", "AML_HARD_BLOCK", "INCOME_MISMATCH"}:
        application = application.model_copy(
            update={
                "loan_amount_requested": safe_loan_amount,
                "loan_tenure_months": safe_tenure,
                "loan_purpose": "PERSONAL",
            }
        )

    return application


def build_colmap(df: pd.DataFrame) -> dict[str, str | None]:
    return {
        "pan": pick_column(df, ["PAN", "pan_number"]),
        "dob": pick_column(df, ["DOB", "date_of_birth"]),
        "employment": pick_column(df, ["Employment_Type"]),
        "income": pick_column(df, ["Annual_Income", "Income"]),
        "loan_amount": pick_column(df, ["Loan_Amount"]),
        "tenure": pick_column(df, ["Tenure", "Loan_Tenure_Months"]),
        "existing_emi": pick_column(df, ["Existing_EMI"]),
        "employer": pick_column(df, ["Employer"]),
        "gender": pick_column(df, ["Gender"]),
        "marital": pick_column(df, ["Marital_Status"]),
    }


def choose_row_for_scenario(df: pd.DataFrame, scenario_label: str, colmap: dict[str, str | None], index_seed: int) -> pd.Series:
    working_df = df.copy()
    baseline = working_df[working_df.apply(lambda r: _is_baseline_eligible(r, colmap), axis=1)]
    if not baseline.empty:
        working_df = baseline

    if scenario_label == "FOIR_FAIL" and colmap["existing_emi"] and colmap["income"]:
        income_monthly = pd.to_numeric(working_df[colmap["income"]], errors="coerce") / 12.0
        emi = pd.to_numeric(working_df[colmap["existing_emi"]], errors="coerce")
        ratio = emi / income_monthly.replace(0, pd.NA)
        filtered = working_df[ratio > 0.35]
        if not filtered.empty:
            working_df = filtered

    if scenario_label == "INCOME_MISMATCH" and colmap["income"]:
        income = pd.to_numeric(working_df[colmap["income"]], errors="coerce")
        filtered = working_df[income > income.median()]
        if not filtered.empty:
            working_df = filtered

    if working_df.empty:
        working_df = df

    return working_df.iloc[index_seed % len(working_df)]


def bank_data_for_scenario(application: ApplicationFormData, scenario_label: str) -> BankStatementData:
    declared_monthly = application.annual_income / 12.0

    if scenario_label == "INCOME_MISMATCH":
        return BankStatementData(
            avg_monthly_credit=declared_monthly * 0.55,
            emi_bounce_count=3,
            salary_credit_regularity=0.78,
        )

    if scenario_label == "AML_HARD_BLOCK":
        return BankStatementData(
            avg_monthly_credit=declared_monthly * 0.82,
            emi_bounce_count=4,
            salary_credit_regularity=0.60,
        )

    return BankStatementData(
        avg_monthly_credit=declared_monthly * 0.95,
        emi_bounce_count=0,
        salary_credit_regularity=0.92 if application.employment_type == "SALARIED" else 0.70,
    )


def macro_data_default() -> MacroConfigData:
    return MacroConfigData(
        stress_scenario="NORMAL",
        rbi_repo_rate=6.50,
        sector_npa_rates={"HOME": 0.021, "PERSONAL": 0.038, "AUTO": 0.018, "SME": 0.062},
    )


def main() -> None:
    zip_path = Path(__file__).resolve().parent / ".." / "data" / "synthetic_loans.zip"
    if not zip_path.exists():
        raise FileNotFoundError(f"ZIP file not found at {zip_path}")

    csv_filename, df = resolve_zip_inputs(zip_path)
    print(f"Loaded ZIP: {zip_path}")
    print(f"Using CSV inside ZIP: {csv_filename}")

    colmap = build_colmap(df)

    for index, scenario in enumerate(TEST_SCENARIOS):
        label = scenario["label"]
        selected_row = choose_row_for_scenario(df, label, colmap, index)
        application = align_application_for_scenario(row_to_application(selected_row, colmap), label)

        credit_output = SCENARIO_CREDIT[label]
        fraud_output = SCENARIO_FRAUD[label]
        bank_data = bank_data_for_scenario(application, label)
        macro_data = macro_data_default()

        result = run_compliance_agent(
            application=application,
            credit_output=credit_output,
            fraud_output=fraud_output,
            bank_data=bank_data,
            macro_data=macro_data,
        )

        print(f"\n=== Scenario: {label} ===")
        print(json.dumps(result.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    main()
