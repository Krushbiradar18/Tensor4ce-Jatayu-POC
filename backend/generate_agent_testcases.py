"""
generate_agent_testcases.py — Build a curated testcase pack for individual agents.

Usage:
    python generate_agent_testcases.py
    python generate_agent_testcases.py --output agent_testcases.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

import dataset_loader


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "agent_testcases.json"


def _valid_utilization(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").where(lambda s: s >= 0)


def _base_dataframe() -> pd.DataFrame:
    dataset_loader.load_datasets(str(ROOT / "dataset"))
    df = dataset_loader._CIBIL_DATA.copy()
    df["monthly_income"] = pd.to_numeric(df["NETMONTHLYINCOME"], errors="coerce").fillna(0)
    df["credit_score"] = pd.to_numeric(df["Credit_Score"], errors="coerce").fillna(0)
    df["dpd30"] = pd.to_numeric(df["num_times_30p_dpd"], errors="coerce").fillna(0)
    df["dpd60"] = pd.to_numeric(df["num_times_60p_dpd"], errors="coerce").fillna(0)
    df["enq6"] = pd.to_numeric(df["enq_L6m"], errors="coerce").fillna(0)
    df["cc_util"] = _valid_utilization(df["CC_utilization"])
    return df


def _pick_case(df: pd.DataFrame, label: str, description: str, condition) -> dict | None:
    filtered = df[condition(df)].copy()
    if filtered.empty:
        return None
    ascending = [False, False, True, True, True]
    if label in {"very_low_score"}:
        ascending = [True, False, True, True, True]
    elif label in {"single_delinquency", "mixed_delinquency", "severe_delinquency"}:
        ascending = [False, False, False, False, True]
    elif label in {"high_enquiries", "elevated_enquiries"}:
        ascending = [False, False, True, True, False]
    filtered = filtered.sort_values(
        by=["credit_score", "monthly_income", "dpd60", "dpd30", "enq6"],
        ascending=ascending,
    )
    row = filtered.iloc[0]
    monthly_income = float(row["monthly_income"])
    annual_income = round(monthly_income * 12, 2)
    loan_amount = max(100000, round(monthly_income * 8))
    if label in {"severe_delinquency", "very_low_score"}:
        loan_amount = max(150000, round(monthly_income * 12))
    if label in {"high_income_clean", "excellent_credit"}:
        loan_amount = max(500000, round(monthly_income * 15))

    return {
        "label": label,
        "description": description,
        "pan": row["PAN"],
        "prospect_id": int(row["PROSPECTID"]),
        "credit_score": int(row["credit_score"]),
        "age": int(row["AGE"]),
        "monthly_income": monthly_income,
        "annual_income": annual_income,
        "dpd_30": int(row["dpd30"]),
        "dpd_60": int(row["dpd60"]),
        "enquiries_6m": int(row["enq6"]),
        "cc_utilization": (None if pd.isna(row["cc_util"]) else float(row["cc_util"])),
        "loan_amount_requested": loan_amount,
        "loan_tenure_months": 60,
        "loan_purpose": "PERSONAL",
        "employment_type": "SALARIED",
    }


def build_cases() -> list[dict]:
    df = _base_dataframe()
    selectors = [
        ("excellent_credit", "Very strong clean applicant", lambda d: (d["credit_score"] >= 760) & (d["monthly_income"] >= 40000) & (d["dpd30"] == 0) & (d["dpd60"] == 0) & (d["enq6"] <= 1)),
        ("high_income_clean", "High income, clean repayment history", lambda d: (d["credit_score"] >= 720) & (d["monthly_income"] >= 80000) & (d["dpd30"] == 0) & (d["dpd60"] == 0)),
        ("strong_mid_income", "Good score, standard borrower", lambda d: (d["credit_score"].between(700, 730)) & (d["monthly_income"].between(25000, 45000)) & (d["dpd30"] == 0) & (d["dpd60"] == 0)),
        ("low_income_edge", "Near minimum-income eligibility", lambda d: (d["monthly_income"].between(15000, 17000)) & (d["dpd30"] == 0) & (d["dpd60"] == 0)),
        ("young_clean", "Young but otherwise clean applicant", lambda d: (d["AGE"] <= 23) & (d["credit_score"] >= 670) & (d["monthly_income"] >= 15000) & (d["dpd30"] == 0) & (d["dpd60"] == 0)),
        ("senior_clean", "Older clean applicant", lambda d: (d["AGE"] >= 55) & (d["credit_score"] >= 680) & (d["dpd30"] == 0) & (d["dpd60"] == 0)),
        ("high_enquiries", "Credit shopping / enquiry spike", lambda d: (d["enq6"] >= 5) & (d["dpd60"] == 0)),
        ("elevated_enquiries", "Moderately elevated enquiries", lambda d: d["enq6"].between(3, 4) & (d["dpd60"] == 0)),
        ("single_delinquency", "One late-payment signal", lambda d: (d["dpd30"] >= 1) & (d["dpd60"] == 0)),
        ("mixed_delinquency", "Repeated late-payment behaviour", lambda d: (d["dpd30"] >= 3) & (d["dpd60"] >= 1)),
        ("severe_delinquency", "Strong delinquency risk profile", lambda d: d["dpd60"] >= 3),
        ("very_low_score", "Very weak bureau score", lambda d: d["credit_score"] <= 600),
        ("high_utilization", "Heavy card utilization", lambda d: d["cc_util"].fillna(-1) >= 0.60),
        ("thin_income_clean", "Low-mid income but clean history", lambda d: (d["monthly_income"].between(18000, 22000)) & (d["dpd30"] == 0) & (d["dpd60"] == 0)),
        ("borderline_score", "Borderline bureau score", lambda d: d["credit_score"].between(640, 660) & (d["enq6"] <= 4)),
    ]

    selected: list[dict] = []
    used_pans: set[str] = set()
    for label, description, predicate in selectors:
        case = _pick_case(df[~df["PAN"].isin(used_pans)], label, description, predicate)
        if case:
            selected.append(case)
            used_pans.add(case["pan"])
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate curated agent testcases from the dataset")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output JSON path")
    args = parser.parse_args()

    cases = build_cases()
    output_path = Path(args.output)
    output_path.write_text(json.dumps(cases, indent=2), encoding="utf-8")
    print(f"Wrote {len(cases)} cases to {output_path}")
    for case in cases:
        print(f"{case['label']:<18} {case['pan']:<14} score={case['credit_score']:<4} income/mo={case['monthly_income']:<8.0f} dpd60={case['dpd_60']:<2} enq6={case['enquiries_6m']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
