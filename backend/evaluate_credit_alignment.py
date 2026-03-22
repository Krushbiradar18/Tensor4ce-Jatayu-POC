"""
Evaluate credit-agent prediction alignment on real dataset labels.

Usage:
  backend/jatayu/Scripts/python.exe evaluate_credit_alignment.py --count 20
"""
from __future__ import annotations

import argparse
import json
from collections import Counter

from dil import load_static_data, run_dil_pipeline
import dataset_loader
from agent_adapters import call_credit_agent


CATEGORY_TO_FLAG = {
    "Low Risk": "P1",
    "Medium-Low Risk": "P2",
    "Medium-High Risk": "P3",
    "High Risk": "P4",
}


def _sample_cases(count: int) -> list[dict]:
    cibil_df = dataset_loader._CIBIL_DATA
    if cibil_df is None or cibil_df.empty:
        return []

    df = cibil_df.copy()
    df = df[df["Approved_Flag"].isin(["P1", "P2", "P3", "P4"])]
    if df.empty:
        return []

    per_class = max(1, count // 4)
    picked = []
    for label in ["P1", "P2", "P3", "P4"]:
        part = df[df["Approved_Flag"] == label]
        if part.empty:
            continue
        n = min(per_class, len(part))
        picked.append(part.sample(n=n, random_state=42))

    sampled = picked[0]
    for part in picked[1:]:
        sampled = sampled._append(part, ignore_index=True)

    if len(sampled) < count:
        remaining = df[~df["PAN"].isin(sampled["PAN"])].sample(
            n=min(count - len(sampled), max(0, len(df) - len(sampled))), random_state=99
        )
        sampled = sampled._append(remaining, ignore_index=True)

    sampled = sampled.head(count)

    rows = []
    for _, row in sampled.iterrows():
        monthly_income = float(row.get("NETMONTHLYINCOME", 50000))
        annual_income = monthly_income * 12
        rows.append(
            {
                "pan": str(row["PAN"]),
                "approved_flag": str(row["Approved_Flag"]),
                "credit_score": float(row.get("Credit_Score", 0)),
                "form_data": {
                    "applicant_name": f"Eval User {row.get('PROSPECTID', 'NA')}",
                    "pan_number": str(row["PAN"]),
                    "aadhaar_last4": "1234",
                    "date_of_birth": "1990-01-01",
                    "gender": "MALE",
                    "employment_type": "SALARIED",
                    "employer_name": "Eval Corp",
                    "annual_income": annual_income,
                    "employment_tenure_years": 3.0,
                    "loan_amount_requested": max(100000, monthly_income * 8),
                    "loan_tenure_months": 60,
                    "loan_purpose": "PERSONAL",
                    "existing_emi_monthly": 0,
                    "residential_assets_value": 0,
                    "mobile_number": "9876543210",
                    "email": "eval@example.com",
                    "address": {
                        "line1": "Eval Street",
                        "city": "Mumbai",
                        "state": "Maharashtra",
                        "pincode": "400001",
                    },
                },
                "ip_metadata": {
                    "ip_address": "103.21.1.1",
                    "form_fill_seconds": 180,
                    "device_fingerprint": "eval_device",
                    "user_agent": "Mozilla/5.0",
                },
            }
        )

    return rows


def evaluate(count: int) -> dict:
    load_static_data("data")
    dataset_loader.load_datasets("../dataset")

    rows = _sample_cases(count)
    if not rows:
        return {"error": "No evaluation rows available from dataset."}

    details = []
    correct = 0
    pred_counter = Counter()
    truth_counter = Counter()

    for idx, row in enumerate(rows, start=1):
        app_id = f"EVAL-{idx:04d}"
        ctx = run_dil_pipeline(app_id, row["form_data"], row["ip_metadata"])
        out = call_credit_agent(ctx)

        predicted_flag = CATEGORY_TO_FLAG.get(out.get("model_risk_category"))
        truth_flag = row["approved_flag"]
        is_correct = predicted_flag == truth_flag
        if is_correct:
            correct += 1

        pred_counter[predicted_flag or "UNKNOWN"] += 1
        truth_counter[truth_flag] += 1

        details.append(
            {
                "application_id": app_id,
                "pan": row["pan"],
                "credit_score_raw": row["credit_score"],
                "truth_flag": truth_flag,
                "predicted_flag": predicted_flag,
                "model_risk_category": out.get("model_risk_category"),
                "model_risk_score": out.get("model_risk_score"),
                "risk_band": out.get("risk_band"),
                "prediction_source": out.get("prediction_source"),
                "data_source": out.get("data_source"),
                "correct": is_correct,
            }
        )

    accuracy = correct / len(details)
    return {
        "count": len(details),
        "correct": correct,
        "accuracy": round(accuracy, 4),
        "truth_distribution": dict(truth_counter),
        "prediction_distribution": dict(pred_counter),
        "details": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate credit alignment on real dataset labels")
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--output", type=str, default="credit_alignment_results.json")
    args = parser.parse_args()

    result = evaluate(args.count)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    if "error" in result:
        print(json.dumps(result, indent=2))
        return 1

    print(json.dumps({
        "count": result["count"],
        "correct": result["correct"],
        "accuracy": result["accuracy"],
        "truth_distribution": result["truth_distribution"],
        "prediction_distribution": result["prediction_distribution"],
        "output": args.output,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
