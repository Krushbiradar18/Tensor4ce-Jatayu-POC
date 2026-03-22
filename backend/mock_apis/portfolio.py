"""backend/mock_apis/portfolio.py — Portfolio summary mock API endpoint.

Provides GET /mock/bank/portfolio-summary which returns pre-aggregated
portfolio statistics derived from Internal_Bank_Dataset.xlsx.

This router is mounted in backend/main.py:
  from mock_apis.portfolio import router as portfolio_router
  app.include_router(portfolio_router)
"""
from __future__ import annotations

import asyncio
import logging
import sys
import os
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_portfolio_stats() -> dict:
    """
    Load portfolio stats. Tries portfolio_agent package first.
    Falls back to agents_base._PORTFOLIO CSV data if import fails.
    """
    # Add project root to path so portfolio_agent can be imported from backend context
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    try:
        from portfolio_agent.portfolio_db import get_portfolio_stats_from_file
        return get_portfolio_stats_from_file()
    except Exception as exc:
        logger.warning(f"portfolio_agent not available ({exc}) — using agent_base fallback")

    # Fallback: use existing _PORTFOLIO data from agents_base
    try:
        from agents_base import _PORTFOLIO, LGD_MAP
        if _PORTFOLIO:
            from tools import _get_portfolio_data
            stats = _get_portfolio_data("PERSONAL", "Maharashtra", 0)
            return {
                "total_loans": stats.get("active_loan_count", 0),
                "total_exposure_inr": stats.get("total_outstanding", 0.0),
                "sector_distribution": {"PERSONAL": stats.get("sector_current", 0.28)},
                "risk_band_distribution": stats.get("risk_band_dist", {"LOW": 0.45, "MEDIUM": 0.38, "HIGH": 0.12, "VERY_HIGH": 0.05}),
                "geographic_distribution": {"Maharashtra": stats.get("geo_current", 0.22)},
                "employer_top_10": [],
                "portfolio_weighted_avg_pd": 0.05,
                "portfolio_el_total": stats.get("total_outstanding", 0) * 0.05 * 0.45,
                "self_employed_pct": 0.22,
            }
    except Exception:
        pass

    # Last resort defaults
    return {
        "total_loans": 500,
        "total_exposure_inr": 187_500_000.0,
        "sector_distribution": {"PERSONAL": 0.28, "HOME": 0.45, "AUTO": 0.18, "EDUCATION": 0.09},
        "risk_band_distribution": {"LOW": 0.45, "MEDIUM": 0.38, "HIGH": 0.12, "VERY_HIGH": 0.05},
        "geographic_distribution": {
            "Maharashtra": 0.22, "Karnataka": 0.18, "Tamil Nadu": 0.14,
            "Delhi": 0.11, "Telangana": 0.09,
        },
        "employer_top_10": [
            {"employer": "TCS", "count": 28, "pct": 0.056},
            {"employer": "Infosys Ltd", "count": 24, "pct": 0.048},
        ],
        "portfolio_weighted_avg_pd": 0.048,
        "portfolio_el_total": 4_050_000.0,
        "self_employed_pct": 0.22,
    }


@router.get("/mock/bank/portfolio-summary")
async def get_portfolio_summary():
    """
    Returns pre-aggregated portfolio statistics.

    Caller: CrewAI Orchestrator (DIL layer) — not individual agents.
    Data source: Derived from Internal_Bank_Dataset.xlsx via portfolio_agent.portfolio_db.
    Cache: Results are cached in memory after first load (see portfolio_db.py).
    """
    await asyncio.sleep(0.2)   # latency simulation
    return _get_portfolio_stats()
