"""
compliance_router.py — APIRouter for compliance mock endpoints.
This module exposes the same routes that were previously in mock_api.py
but as a standalone APIRouter so it can be mounted by any FastAPI app.

Routes:
  POST /mock/bank/statement-summary   — synthetic bank statement
  GET  /mock/macro/current            — macroeconomic indicators
"""
import asyncio
import random

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["Mock APIs — Compliance"])


class StatementSummaryRequest(BaseModel):
    account_number: str
    months: int


@router.post("/mock/bank/statement-summary")
async def mock_bank_statement_summary(payload: StatementSummaryRequest) -> dict:
    """Synthetic bank statement derived deterministically from account number."""
    digits = "".join(ch for ch in payload.account_number if ch.isdigit())
    seed_income = int(digits[-6:]) if digits else 1200000
    annual_income = max(180000.0, float(seed_income))
    base_monthly_income = annual_income / 12.0
    noise_multiplier = random.uniform(0.90, 1.10)
    avg_monthly_credit = base_monthly_income * noise_multiplier

    emi_bounce_count = 3 if payload.account_number.endswith("999") else 0

    salary_credit_regularity = (
        0.92 if payload.account_number.upper().startswith("SAL") else 0.60
    )

    avg_monthly_debit = avg_monthly_credit * random.uniform(0.55, 0.80)
    min_monthly_balance = max(0.0, avg_monthly_credit * random.uniform(0.08, 0.20))
    max_monthly_balance = avg_monthly_credit * random.uniform(1.10, 1.80)
    emi_to_income_ratio = (
        min(1.0, avg_monthly_debit / avg_monthly_credit) if avg_monthly_credit else 0.0
    )

    await asyncio.sleep(0.1)

    return {
        "avg_monthly_credit": round(avg_monthly_credit, 2),
        "avg_monthly_debit": round(avg_monthly_debit, 2),
        "min_monthly_balance": round(min_monthly_balance, 2),
        "max_monthly_balance": round(max_monthly_balance, 2),
        "emi_bounce_count": emi_bounce_count,
        "salary_credit_regularity": salary_credit_regularity,
        "emi_to_income_ratio": round(emi_to_income_ratio, 4),
    }


@router.get("/mock/macro/current")
async def mock_macro_current() -> dict:
    """Real-time macroeconomic indicators (static mock for PoC)."""
    return {
        "rbi_repo_rate": 6.50,
        "inflation_rate": 4.80,
        "sector_npa_rates": {
            "HOME": 0.021,
            "PERSONAL": 0.038,
            "AUTO": 0.018,
            "SME": 0.062,
        },
        "gdp_growth_rate": 6.8,
        "stress_scenario": "NORMAL",
    }
