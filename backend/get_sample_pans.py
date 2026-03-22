#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
get_sample_pans.py — Extract sample PANs from datasets for manual testing
==========================================================================
Quick script to get PANs from your datasets that you can use to test
the application through the web UI.

Usage:
    python get_sample_pans.py [--count 10]
"""
import sys
import argparse
from pathlib import Path
import io

# Fix Windows console encoding for emojis
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add parent to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dataset_loader import load_datasets, get_sample_test_cases

def main():
    parser = argparse.ArgumentParser(description="Extract sample PANs from datasets")
    parser.add_argument("--count", type=int, default=10, help="Number of samples to show")
    args = parser.parse_args()

    print("=" * 70)
    print("📋 SAMPLE TEST PANs FROM YOUR DATASETS")
    print("=" * 70)

    # Load datasets
    try:
        dataset_dir = Path(__file__).parent.parent / "dataset"
        load_datasets(str(dataset_dir))
    except Exception as e:
        print(f"❌ Error loading datasets: {e}")
        return 1

    # Get sample test cases
    try:
        samples = get_sample_test_cases(args.count)

        if not samples:
            print("\n⚠️  No data found in datasets")
            print("Make sure these files exist in ../dataset/:")
            print("  - External_Cibil_Dataset.xlsx")
            print("  - Internal_Bank_Dataset.xlsx")
            return 1

        print(f"\n📊 {len(samples)} Sample Test Cases")
        print("-" * 70)
        print(f"{'PAN':<16} {'CIBIL':<8} {'Income/mo':<15} {'Age':<6} {'DPD90':<6}")
        print("-" * 70)

        for sample in samples:
            pan = sample['pan']
            cibil = sample['credit_score']
            income = sample['monthly_income']
            age = sample['age']
            dpd90 = sample['dpd_90']

            print(f"{pan:<16} {cibil:<8.0f} ₹{income:>12,.0f}  {age:<6} {dpd90:<6}")

        # Print usage instructions
        print("\n" + "=" * 70)
        print("🎯 HOW TO TEST:")
        print("=" * 70)
        print("1. Start the server:")
        print("   cd backend && uvicorn main:app --reload --port 8000")
        print("\n2. Open browser: http://localhost:8000")
        print("\n3. Click 'Apply for Loan' and use any PAN from above")
        print("\n4. Fill in the form (system will use real CIBIL data for these PANs)")
        print("\n5. Submit and check the decision result")

        # Print some interesting cases
        print("\n" + "=" * 70)
        print("💡 INTERESTING TEST CASES:")
        print("=" * 70)

        # High CIBIL
        high_cibil = [s for s in samples if s['credit_score'] > 750]
        if high_cibil:
            sample = high_cibil[0]
            print(f"\n✅ Good Credit Profile: {sample['pan']}")
            print(f"   CIBIL: {sample['credit_score']:.0f} (High)")
            print(f"   Income: ₹{sample['monthly_income']:,.0f}/month")
            print(f"   Expected: Likely APPROVE or CONDITIONAL")

        # Low CIBIL
        low_cibil = [s for s in samples if s['credit_score'] < 650]
        if low_cibil:
            sample = low_cibil[0]
            print(f"\n⚠️  Weak Credit Profile: {sample['pan']}")
            print(f"   CIBIL: {sample['credit_score']:.0f} (Low)")
            print(f"   Income: ₹{sample['monthly_income']:,.0f}/month")
            print(f"   Expected: Likely ESCALATE or REJECT")

        # High DPD
        high_dpd = [s for s in samples if s['dpd_90'] > 0]
        if high_dpd:
            sample = high_dpd[0]
            print(f"\n🚨 Payment Default History: {sample['pan']}")
            print(f"   CIBIL: {sample['credit_score']:.0f}")
            print(f"   DPD 90 days: {sample['dpd_90']}")
            print(f"   Expected: Likely ESCALATE or REJECT")

        # Low Income
        low_income = [s for s in samples if s['monthly_income'] < 30000]
        if low_income:
            sample = low_income[0]
            print(f"\n💰 Low Income Profile: {sample['pan']}")
            print(f"   Income: ₹{sample['monthly_income']:,.0f}/month")
            print(f"   CIBIL: {sample['credit_score']:.0f}")
            print(f"   Expected: Risk assessment depends on loan amount")

        print("\n" + "=" * 70)
        print("📝 TIP: You can also use the automated test script:")
        print("   python test_with_actual_data.py --count 5")
        print("=" * 70 + "\n")

        return 0

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
