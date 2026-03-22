"""test_agent.py — Isolated end-to-end test runner for the Portfolio Intelligence Agent.

Usage (always activate venv first):
  source jatayu_vnev/bin/activate          # macOS/Linux
  jatayu_vnev\\Scripts\\activate.bat       # Windows

  # Print portfolio stats loaded from Excel dataset
  python portfolio_agent/test_agent.py --seed

  # Run all 5 test scenarios
  python portfolio_agent/test_agent.py --test

  # Both seed + test
  python portfolio_agent/test_agent.py --seed --test

Run from project root: Tensor4ce-Jatayu-POC/
"""
from __future__ import annotations

import os
import sys
import json
import argparse
import logging

# Make sure project root is on the Python path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)


from portfolio_agent.portfolio_db import get_portfolio_stats_from_file
from portfolio_agent.agent import run_portfolio_agent
from portfolio_agent.schemas import (
    ApplicationFormData,
    CreditAgentOutput,
    FraudAgentOutput,
    ComplianceAgentOutput,
    BankStatementData,
    MacroConfigData,
    PortfolioStats,
)


# ── Portfolio stats from Excel ────────────────────────────────────────────────

def get_live_portfolio_stats() -> PortfolioStats:
    raw = get_portfolio_stats_from_file()
    logger.info(
        f"Portfolio stats: {raw['total_loans']} loans, "
        f"exposure ₹{raw['total_exposure_inr']/1e7:.1f}Cr, "
        f"weighted PD {raw['portfolio_weighted_avg_pd']:.2%}, "
        f"source: {raw.get('data_source', 'unknown')}"
    )
    return PortfolioStats(**{k: v for k, v in raw.items() if k != "data_source"})


# ── Test Scenarios ────────────────────────────────────────────────────────────

TEST_CASES = [
    {
        "label": "1. CLEAN_ACCEPT — Good applicant, healthy portfolio (NORMAL stress)",
        "application": ApplicationFormData(
            loan_purpose="PERSONAL",
            loan_amount_requested=300_000,
            loan_tenure_months=36,
            employment_type="SALARIED",
            annual_income=900_000,
            employer_name="Wipro Ltd",
            applicant_state="Karnataka",
            applicant_city="Bengaluru",
        ),
        "credit": CreditAgentOutput(
            risk_band="LOW", predicted_pd=0.03, credit_score=0.03,
            foir=0.35, macro_adjusted=False
        ),
        "fraud": FraudAgentOutput(fraud_level="CLEAN", fraud_probability=0.05),
        "compliance": ComplianceAgentOutput(overall_status="PASS"),
        "bank": BankStatementData(avg_monthly_credit=78_000, emi_bounce_count=0),
        "macro": MacroConfigData(
            stress_scenario="NORMAL", rbi_repo_rate=6.5,
            sector_npa_rates={"PERSONAL": 0.038},
            gdp_growth_rate=6.8, inflation_rate=4.8,
        ),
    },
    {
        "label": "2. HIGH_RISK — Should trigger risk band concentration (NORMAL stress)",
        "application": ApplicationFormData(
            loan_purpose="PERSONAL",
            loan_amount_requested=800_000,
            loan_tenure_months=60,
            employment_type="SELF_EMPLOYED",
            annual_income=600_000,
            employer_name="Self",
            applicant_state="Maharashtra",
            applicant_city="Mumbai",
        ),
        "credit": CreditAgentOutput(
            risk_band="VERY_HIGH", predicted_pd=0.25, credit_score=0.25,
            foir=0.52, macro_adjusted=False
        ),
        "fraud": FraudAgentOutput(fraud_level="SUSPICIOUS", fraud_probability=0.55),
        "compliance": ComplianceAgentOutput(overall_status="PASS_WITH_WARNINGS"),
        "bank": BankStatementData(avg_monthly_credit=45_000, emi_bounce_count=3),
        "macro": MacroConfigData(
            stress_scenario="NORMAL", rbi_repo_rate=6.5,
            sector_npa_rates={"PERSONAL": 0.038},
            gdp_growth_rate=6.8, inflation_rate=4.8,
        ),
    },
    {
        "label": "3. HIGH_STRESS macro — thresholds tighten to 60% of normal",
        "application": ApplicationFormData(
            loan_purpose="PERSONAL",
            loan_amount_requested=400_000,
            loan_tenure_months=48,
            employment_type="SALARIED",
            annual_income=800_000,
            employer_name="Infosys Ltd",
            applicant_state="Tamil Nadu",
            applicant_city="Chennai",
        ),
        "credit": CreditAgentOutput(
            risk_band="MEDIUM", predicted_pd=0.07, credit_score=0.07,
            foir=0.41, macro_adjusted=True
        ),
        "fraud": FraudAgentOutput(fraud_level="LOW_RISK", fraud_probability=0.12),
        "compliance": ComplianceAgentOutput(overall_status="PASS"),
        "bank": BankStatementData(avg_monthly_credit=67_000, emi_bounce_count=1),
        "macro": MacroConfigData(
            stress_scenario="HIGH_STRESS", rbi_repo_rate=7.5,
            sector_npa_rates={"PERSONAL": 0.062},
            gdp_growth_rate=4.2, inflation_rate=7.1,
        ),
    },
    {
        "label": "4. EMPLOYER CONCENTRATION — TCS is a top employer in the portfolio",
        "application": ApplicationFormData(
            loan_purpose="PERSONAL",
            loan_amount_requested=250_000,
            loan_tenure_months=24,
            employment_type="SALARIED",
            annual_income=700_000,
            employer_name="TCS",
            applicant_state="Maharashtra",
            applicant_city="Pune",
        ),
        "credit": CreditAgentOutput(
            risk_band="LOW", predicted_pd=0.02, credit_score=0.02,
            foir=0.30, macro_adjusted=False
        ),
        "fraud": FraudAgentOutput(fraud_level="CLEAN", fraud_probability=0.03),
        "compliance": ComplianceAgentOutput(overall_status="PASS"),
        "bank": BankStatementData(avg_monthly_credit=60_000, emi_bounce_count=0),
        "macro": MacroConfigData(
            stress_scenario="NORMAL", rbi_repo_rate=6.5,
            sector_npa_rates={"PERSONAL": 0.038},
            gdp_growth_rate=6.8, inflation_rate=4.8,
        ),
    },
    {
        "label": "5. HIGH EL IMPACT — large loan, high PD (MILD_STRESS)",
        "application": ApplicationFormData(
            loan_purpose="PERSONAL",
            loan_amount_requested=2_500_000,
            loan_tenure_months=84,
            employment_type="SELF_EMPLOYED",
            annual_income=1_200_000,
            employer_name="Self",
            applicant_state="Delhi",
            applicant_city="New Delhi",
        ),
        "credit": CreditAgentOutput(
            risk_band="HIGH", predicted_pd=0.14, credit_score=0.14,
            foir=0.48, macro_adjusted=False
        ),
        "fraud": FraudAgentOutput(fraud_level="LOW_RISK", fraud_probability=0.18),
        "compliance": ComplianceAgentOutput(overall_status="PASS"),
        "bank": BankStatementData(avg_monthly_credit=95_000, emi_bounce_count=1),
        "macro": MacroConfigData(
            stress_scenario="MILD_STRESS", rbi_repo_rate=6.75,
            sector_npa_rates={"PERSONAL": 0.045},
            gdp_growth_rate=5.8, inflation_rate=5.5,
        ),
    },
]


# ── Runner ────────────────────────────────────────────────────────────────────

def run_seed():
    """Print portfolio stats loaded from the Excel dataset."""
    print("\n" + "=" * 70)
    print("PORTFOLIO STATS (from Internal_Bank_Dataset.xlsx)")
    print("=" * 70)
    raw = get_portfolio_stats_from_file(force_reload=True)
    # Pretty print, excluding internal fields
    display = {k: v for k, v in raw.items()}
    print(json.dumps(display, indent=2, default=str))
    print("=" * 70 + "\n")
    return raw


def run_tests(portfolio_stats: PortfolioStats):
    """Run all 5 test scenarios and print results."""
    print("\n" + "=" * 70)
    print("RUNNING 5 TEST SCENARIOS")
    print("=" * 70)

    results = []
    for i, tc in enumerate(TEST_CASES):
        print(f"\n{'─' * 60}")
        print(f"SCENARIO {tc['label']}")
        print("─" * 60)

        try:
            result = run_portfolio_agent(
                application=tc["application"],
                credit_output=tc["credit"],
                fraud_output=tc["fraud"],
                compliance_output=tc["compliance"],
                bank_data=tc["bank"],
                macro_data=tc["macro"],
                portfolio_stats=portfolio_stats,
            )

            # Summary line
            rec = result["portfolio_recommendation"]
            el_impact = result.get("expected_loss_impact", result.get("el_impact_inr", 0))
            el_pct = result.get("el_increase_pct", 0)
            flags = result.get("concentration_flags", [])

            print(f"  Recommendation:  {rec}")
            print(f"  EL Impact:       ₹{el_impact:,.0f}  ({el_pct:.2f}% portfolio EL increase)")
            print(f"  Sector (post):   {result.get('post_approval_sector_pct', result.get('sector_concentration_new', 0)):.1%}")
            print(f"  Flags fired:     {flags if flags else ['none']}")
            print(f"  Narrative:       {result.get('narrative', result.get('cot_reasoning', ''))[:120]}...")

            # Validate non-zero EL for non-compliance-block cases
            if result.get("concentration_flags") != ["compliance_block_fail"]:
                assert el_impact > 0, f"Expected non-zero EL impact, got {el_impact}"

            results.append({"label": tc["label"], "result": result, "status": "PASS"})
            print(f"  ✓ PASS")

        except Exception as exc:
            logger.exception(f"Scenario {i+1} failed: {exc}")
            results.append({"label": tc["label"], "error": str(exc), "status": "FAIL"})
            print(f"  ✗ FAIL: {exc}")

    print("\n" + "=" * 70)
    passed = sum(1 for r in results if r["status"] == "PASS")
    print(f"RESULTS: {passed}/{len(results)} scenarios passed")
    print("=" * 70 + "\n")

    # Full JSON output for debugging
    print("\nFULL JSON OUTPUT (first scenario for inspection):")
    if results and results[0]["status"] == "PASS":
        # Remove heavy items for cleaner display
        display = {k: v for k, v in results[0]["result"].items() if k != "post_approval_risk_distribution"}
        print(json.dumps(display, indent=2, default=str))

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Portfolio Intelligence Agent — Test Runner"
    )
    parser.add_argument("--seed", action="store_true",
                        help="Print portfolio stats from Excel dataset")
    parser.add_argument("--test", action="store_true",
                        help="Run all 5 test scenarios")
    args = parser.parse_args()

    if not args.seed and not args.test:
        parser.print_help()
        print("\n⚠ Please specify --seed, --test, or both.")
        sys.exit(1)

    ps_dict = None
    if args.seed:
        ps_dict = run_seed()

    if args.test:
        if ps_dict is None:
            ps_dict = get_portfolio_stats_from_file()
        portfolio_stats = PortfolioStats(**{k: v for k, v in ps_dict.items() if k != "data_source"})
        run_tests(portfolio_stats)


if __name__ == "__main__":
    main()
