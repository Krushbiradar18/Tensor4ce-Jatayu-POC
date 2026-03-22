#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_with_actual_data.py — Test loan applications using real dataset PANs
==========================================================================
This script extracts PANs from your datasets and submits test applications
to verify the system works end-to-end with real data.

Usage:
    # Test 5 random applications
    python test_with_actual_data.py

    # Test specific number
    python test_with_actual_data.py --count 10

    # Export results to CSV
    python test_with_actual_data.py --output results.csv
"""
import sys
import io

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import os
import requests
import json
import time
from pathlib import Path
from typing import List, Dict, Optional
import argparse
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Base URL for API
API_BASE = "http://localhost:8000"


def load_test_pans(dataset_path: str, limit: int = 10) -> List[Dict]:
    """Load PANs and associated data from dataset for testing."""
    # Use dataset_loader instead of loading directly
    from dataset_loader import load_datasets, get_sample_test_cases

    print(f"📂 Loading test data from datasets...")

    try:
        # Load datasets
        dataset_dir = Path(dataset_path).parent if dataset_path else Path("../dataset")
        load_datasets(str(dataset_dir))

        # Get sample test cases
        test_cases = get_sample_test_cases(limit)

        if not test_cases:
            print(f"❌ No test cases found")
            return []

        # Convert to expected format
        formatted_cases = []
        for tc in test_cases:
            formatted_cases.append({
                "pan": tc['pan'],
                "name": f"Test User {tc['prospect_id']}",
                "age": tc['age'],
                "income": tc['income'],
                "cibil_score": tc['credit_score'],
                "loan_amount": 500000,  # Default loan amount
                "loan_type": "PERSONAL",
            })

        print(f"✅ Loaded {len(formatted_cases)} test cases")
        return formatted_cases

    except Exception as e:
        print(f"❌ Error loading test data: {e}")
        import traceback
        traceback.print_exc()
        return []


def submit_application(test_case: Dict) -> Optional[Dict]:
    """Submit a loan application, poll for completion, return full decision."""
    form_data = {
        "applicant_name": test_case["name"],
        "pan_number": test_case["pan"],
        "aadhaar_last4": "1234",
        "date_of_birth": "1990-01-01",
        "gender": "MALE",
        "employment_type": "SALARIED",
        "employer_name": "Test Company",
        "annual_income": int(test_case["income"]),
        "employment_tenure_years": 2.0,
        "loan_amount_requested": int(test_case["loan_amount"]),
        "loan_tenure_months": 60,
        "loan_purpose": test_case.get("loan_type", "PERSONAL"),
        "existing_emi_monthly": 0,
        "residential_assets_value": 0,
        "mobile_number": "9876543210",
        "email": "test@example.com",
        "address": {
            "line1": "123 Test Street",
            "city": "Mumbai",
            "state": "Maharashtra",
            "pincode": "400001"
        }
    }

    ip_metadata = {
        "ip_address": "203.0.113.1",
        "form_fill_seconds": 180,
        "device_fingerprint": "test_device_001",
        "user_agent": "Mozilla/5.0"
    }

    payload = {"form_data": form_data, "ip_metadata": ip_metadata}

    try:
        # Step 1: Submit application
        print(f"  Submitting for PAN: {test_case['pan']}...")
        resp = requests.post(f"{API_BASE}/api/apply", json=payload, timeout=30)
        if resp.status_code != 200:
            print(f"  ERROR {resp.status_code}: {resp.text}")
            return None

        app_id = resp.json()["application_id"]

        # Step 2: Poll for completion (up to 120s)
        terminal = {"DECIDED_PENDING_OFFICER", "OFFICER_APPROVED", "OFFICER_REJECTED",
                    "OFFICER_CONDITIONAL", "OFFICER_ESCALATED", "ERROR"}
        for attempt in range(60):  # 60 x 2s = 120s max
            time.sleep(2)
            status_resp = requests.get(f"{API_BASE}/api/status/{app_id}", timeout=10)
            if status_resp.status_code == 200:
                status = status_resp.json().get("status", "")
                if status in terminal:
                    break
                if attempt % 5 == 0:
                    print(f"  ... {status} ({attempt * 2}s)")
        else:
            print(f"  TIMEOUT: Application {app_id} did not complete in 120s")
            return None

        # Step 3: Fetch full decision
        decision_resp = requests.get(f"{API_BASE}/api/officer/decision/{app_id}", timeout=10)
        if decision_resp.status_code != 200:
            print(f"  ERROR fetching decision: {decision_resp.status_code}")
            return None

        full = decision_resp.json()
        decision = full.get("decision", {})
        recommendation = decision.get("ai_recommendation", "UNKNOWN")
        print(f"  Application {app_id}: {recommendation}")
        return {"application_id": app_id, **decision}

    except requests.RequestException as e:
        print(f"  Request failed: {e}")
        return None


def extract_key_metrics(result: Dict) -> Dict:
    """Extract key metrics from decision result."""
    if not result:
        return {}

    # DB stores keys as: credit_risk, fraud, compliance, portfolio
    credit_out = result.get("credit_risk", result.get("credit_output", {})) or {}
    fraud_out = result.get("fraud", result.get("fraud_output", {})) or {}
    compliance_out = result.get("compliance", result.get("compliance_output", {})) or {}

    return {
        "application_id": result.get("application_id"),
        "decision": result.get("ai_recommendation"),
        "decision_row": result.get("decision_matrix_row", ""),
        "credit_score": credit_out.get("credit_score"),
        "risk_band": credit_out.get("risk_band"),
        "foir": credit_out.get("foir"),
        "fraud_level": fraud_out.get("fraud_level"),
        "fraud_probability": fraud_out.get("fraud_probability"),
        "compliance_status": compliance_out.get("overall_status"),
        "processing_time_ms": result.get("processing_time_ms"),
    }


def run_tests(test_cases: List[Dict], output_file: Optional[str] = None, delay: float = 1.0):
    """Run all test cases and collect results."""
    print(f"\n🚀 Starting test run with {len(test_cases)} cases...")
    print("=" * 70)

    results = []
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n[{i}/{len(test_cases)}] Testing PAN: {test_case['pan']}")
        print(f"  Name: {test_case['name']}")
        print(f"  Income: ₹{test_case['income']:,.0f}/yr")
        print(f"  Loan: ₹{test_case['loan_amount']:,.0f}")
        print(f"  CIBIL: {test_case['cibil_score']:.0f}")

        result = submit_application(test_case)

        if result:
            metrics = extract_key_metrics(result)
            metrics["test_pan"] = test_case["pan"]
            metrics["test_income"] = test_case["income"]
            metrics["test_cibil"] = test_case["cibil_score"]
            results.append(metrics)

            # Print summary
            cs = metrics.get('credit_score')
            fp = metrics.get('fraud_probability')
            cs_str = f"{cs:.4f}" if cs is not None else "N/A"
            fp_str = f"{fp:.2%}" if fp is not None else "N/A"
            print(f"  Credit Risk : {metrics.get('risk_band')} ({cs_str})")
            print(f"  Fraud       : {metrics.get('fraud_level')} ({fp_str})")
            print(f"  Compliance  : {metrics.get('compliance_status')}")
            print(f"  Decision    : {metrics.get('decision')}")
            ms = metrics.get('processing_time_ms')
            if ms:
                print(f"  Processing  : {ms}ms")

        # Rate limiting: wait between requests
        if i < len(test_cases):
            time.sleep(delay)

    # Summary statistics
    print("\n" + "=" * 70)
    print("📈 TEST SUMMARY")
    print("=" * 70)
    print(f"Total Tests: {len(results)}")

    if results:
        decisions = {}
        for r in results:
            dec = r.get("decision", "UNKNOWN")
            decisions[dec] = decisions.get(dec, 0) + 1

        print("\nDecision Distribution:")
        for dec, count in sorted(decisions.items()):
            print(f"  {dec}: {count} ({count/len(results)*100:.1f}%)")

        avg_time = sum(r.get("processing_time_ms", 0) for r in results) / len(results)
        print(f"\nAverage Processing Time: {avg_time:.0f}ms")

        # Risk distribution
        risk_bands = {}
        for r in results:
            rb = r.get("risk_band", "UNKNOWN")
            risk_bands[rb] = risk_bands.get(rb, 0) + 1

        print("\nRisk Band Distribution:")
        for rb, count in sorted(risk_bands.items()):
            print(f"  {rb}: {count}")

    # Export to CSV if requested
    if output_file and results:
        import pandas as pd
        df = pd.DataFrame(results)
        df.to_csv(output_file, index=False)
        print(f"\n✅ Results exported to: {output_file}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Test loan applications with real dataset PANs")
    parser.add_argument("--count", type=int, default=5, help="Number of test cases to run")
    parser.add_argument("--output", type=str, help="Output CSV file path")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests (seconds)")

    args = parser.parse_args()

    # Check if server is running
    try:
        response = requests.get(f"{API_BASE}/api/health", timeout=5)
        if response.status_code != 200:
            print("❌ Server is not responding correctly. Is it running on port 8000?")
            return 1
    except requests.RequestException:
        print("❌ Cannot connect to server. Please start it with:")
        print("   cd backend && uvicorn main:app --reload --port 8000")
        return 1

    print("✅ Server is running")

    # Load test cases (dataset_path not needed anymore)
    test_cases = load_test_pans("", args.count)

    if not test_cases:
        print("❌ No test cases loaded. Check dataset path.")
        return 1

    # Run tests
    results = run_tests(test_cases, args.output, args.delay)

    print(f"\n✅ Testing complete! {len(results)} applications processed.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
