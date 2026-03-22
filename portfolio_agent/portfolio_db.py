"""portfolio_db.py — Portfolio statistics loader for the Portfolio Intelligence Agent.

Two modes:
  1. Excel-based (default) — reads Internal_Bank_Dataset.xlsx from the dataset/ folder,
     treats each row as a synthetic portfolio loan, and computes aggregate stats with pandas.
  2. PostgreSQL (optional) — seeds from Excel into portfolio_loans table and queries with
     SQLAlchemy. Falls back to Excel mode if DB connection is unavailable.

The key public function is get_portfolio_stats_from_file() which is called by:
  - portfolio_agent/agent.py (during test runs)
  - backend/mock_apis/portfolio.py (/mock/bank/portfolio-summary endpoint)
  - portfolio_agent/test_agent.py (--seed and --test flags)
"""
from __future__ import annotations
import os
import logging
import random
from pathlib import Path
from typing import Optional
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv optional — env vars set directly or via backend .env loading
logger = logging.getLogger(__name__)

# ── Default portfolio stats (used when no dataset is available) ───────────────

_DEFAULT_STATS = {
    "total_loans": 500,
    "total_exposure_inr": 187_500_000.0,
    "sector_distribution": {"PERSONAL": 0.28, "HOME": 0.45, "AUTO": 0.18, "EDUCATION": 0.09},
    "risk_band_distribution": {"LOW": 0.45, "MEDIUM": 0.38, "HIGH": 0.12, "VERY_HIGH": 0.05},
    "geographic_distribution": {
        "Maharashtra": 0.22, "Karnataka": 0.18, "Tamil Nadu": 0.14,
        "Delhi": 0.11, "Telangana": 0.09, "Gujarat": 0.08,
        "Rajasthan": 0.05, "West Bengal": 0.05, "Uttar Pradesh": 0.04, "Madhya Pradesh": 0.04,
    },
    "employer_top_10": [
        {"employer": "TCS", "count": 28, "pct": 0.056},
        {"employer": "Infosys Ltd", "count": 24, "pct": 0.048},
        {"employer": "Wipro Ltd", "count": 20, "pct": 0.040},
        {"employer": "HCL Technologies", "count": 18, "pct": 0.036},
        {"employer": "Cognizant", "count": 16, "pct": 0.032},
        {"employer": "Self", "count": 40, "pct": 0.080},
        {"employer": "HDFC Bank", "count": 14, "pct": 0.028},
        {"employer": "ICICI Bank", "count": 12, "pct": 0.024},
        {"employer": "Accenture", "count": 10, "pct": 0.020},
        {"employer": "Tech Mahindra", "count": 9, "pct": 0.018},
    ],
    "portfolio_weighted_avg_pd": 0.048,
    "portfolio_el_total": 4_050_000.0,
    "self_employed_pct": 0.22,
    "data_source": "defaults",
}

# ── Cached stats (loaded once per process) ────────────────────────────────────
_CACHED_STATS: Optional[dict] = None


def _find_dataset_path() -> Optional[Path]:
    """Find Internal_Bank_Dataset.xlsx relative to this file or env var."""
    # Try env var first
    dataset_dir = os.environ.get("DATASET_DIR", "")
    if dataset_dir:
        p = Path(dataset_dir) / "Internal_Bank_Dataset.xlsx"
        if p.exists():
            return p

    # Try relative to this file (portfolio_agent/../dataset/)
    here = Path(__file__).resolve().parent
    candidates = [
        here.parent / "dataset" / "Internal_Bank_Dataset.xlsx",
        here.parent.parent / "dataset" / "Internal_Bank_Dataset.xlsx",
        Path("dataset") / "Internal_Bank_Dataset.xlsx",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def _build_stats_from_excel(excel_path: Path) -> dict:
    """
    Load Internal_Bank_Dataset.xlsx and synthesize portfolio stats.
    Each row is treated as a portfolio loan for demonstration purposes.
    """
    import pandas as pd
    import numpy as np

    logger.info(f"Loading portfolio stats from {excel_path}...")
    df = pd.read_excel(excel_path)
    logger.info(f"  Loaded {len(df)} rows, columns: {list(df.columns)}")

    total_loans = len(df)
    if total_loans == 0:
        logger.warning("Empty dataset — using defaults")
        return _DEFAULT_STATS.copy()

    # ── Derive outstanding_amount ──────────────────────────────────────────────
    # Use NETMONTHLYINCOME × loan_multiplier as synthetic loan amount
    income_col = next((c for c in df.columns if "NETMONTHLYINCOME" in c.upper() or "NET_MONTHLY" in c.upper()), None)
    if income_col:
        df["_income"] = pd.to_numeric(df[income_col], errors="coerce").fillna(30000)
    else:
        df["_income"] = 30000.0

    # Synthetic loan amount: 8–24 × monthly income (realistic personal loan range)
    rng = np.random.default_rng(seed=42)
    df["_loan_amount"] = df["_income"] * rng.uniform(8, 24, size=len(df))
    df["_outstanding"] = df["_loan_amount"] * rng.uniform(0.3, 0.9, size=len(df))

    total_exposure = float(df["_outstanding"].sum())

    # ── Risk band from credit score or delinquency ─────────────────────────────
    score_col = next((c for c in df.columns if "CREDIT_SCORE" in c.upper() or c.upper() == "CREDIT_SCORE"), None)

    if score_col:
        df["_pd"] = pd.to_numeric(df[score_col], errors="coerce").fillna(0)
        # Treat score as PD if 0-1, or convert from 300-900 range
        if df["_pd"].max() > 1.0:
            # It's a CIBIL-style score: higher = lower PD
            df["_pd"] = ((900 - df["_pd"].clip(300, 900)) / 600 * 0.3).clip(0.005, 0.35)
        else:
            df["_pd"] = df["_pd"].clip(0.005, 0.95)
    else:
        # Use delinquency columns to estimate PD
        dpd_col = next((c for c in df.columns if "DPD" in c.upper() or "DELINQ" in c.upper()), None)
        if dpd_col:
            dpd = pd.to_numeric(df[dpd_col], errors="coerce").fillna(0)
            df["_pd"] = (0.03 + dpd * 0.05).clip(0.005, 0.60)
        else:
            df["_pd"] = rng.uniform(0.02, 0.20, size=len(df))

    def _pd_to_band(pd_val: float) -> str:
        if pd_val < 0.02:
            return "LOW"
        elif pd_val < 0.08:
            return "MEDIUM"
        elif pd_val < 0.18:
            return "HIGH"
        else:
            return "VERY_HIGH"

    df["_risk_band"] = df["_pd"].apply(_pd_to_band)

    # ── Risk band distribution ──────────────────────────────────────────────
    band_counts = df["_risk_band"].value_counts()
    risk_band_distribution = {
        band: round(band_counts.get(band, 0) / total_loans, 4)
        for band in ["LOW", "MEDIUM", "HIGH", "VERY_HIGH"]
    }

    # ── Sector distribution — all PERSONAL for this PoC ─────────────────────
    sector_distribution = {"PERSONAL": 0.28, "HOME": 0.45, "AUTO": 0.18, "EDUCATION": 0.09}

    # ── Geographic distribution ─────────────────────────────────────────────
    # Try to find a state column
    state_col = next((c for c in df.columns if "STATE" in c.upper()), None)
    if state_col:
        state_counts = df[state_col].value_counts().head(10)
        geographic_distribution = {
            str(state): round(count / total_loans, 4)
            for state, count in state_counts.items()
        }
    else:
        geographic_distribution = _DEFAULT_STATS["geographic_distribution"]

    # ── Employer top 10 ─────────────────────────────────────────────────────
    emp_col = next((c for c in df.columns if "EMPLOYER" in c.upper() or "COMPANY" in c.upper()), None)
    if emp_col:
        emp_counts = df[emp_col].value_counts().head(10)
        employer_top_10 = [
            {"employer": str(emp), "count": int(cnt), "pct": round(cnt / total_loans, 4)}
            for emp, cnt in emp_counts.items()
        ]
    else:
        employer_top_10 = _DEFAULT_STATS["employer_top_10"]

    # ── SELF_EMPLOYED % ─────────────────────────────────────────────────────
    emp_type_col = next((c for c in df.columns if "EMP_TYPE" in c.upper() or "EMPLOYMENT" in c.upper()), None)
    if emp_type_col:
        is_se = df[emp_type_col].astype(str).str.upper().str.contains("SELF")
        self_employed_pct = round(is_se.sum() / total_loans, 4)
    else:
        self_employed_pct = 0.22  # 22% default

    # ── Weighted average PD ──────────────────────────────────────────────────
    wa_pd = float((df["_pd"] * df["_outstanding"]).sum() / max(total_exposure, 1))

    # ── Portfolio EL total: EL = SUM(pd × 0.45 × outstanding) ───────────────
    portfolio_el_total = float((df["_pd"] * 0.45 * df["_outstanding"]).sum())

    stats = {
        "total_loans": total_loans,
        "total_exposure_inr": round(total_exposure, 2),
        "sector_distribution": sector_distribution,
        "risk_band_distribution": risk_band_distribution,
        "geographic_distribution": geographic_distribution,
        "employer_top_10": employer_top_10,
        "portfolio_weighted_avg_pd": round(wa_pd, 6),
        "portfolio_el_total": round(portfolio_el_total, 2),
        "self_employed_pct": self_employed_pct,
        "data_source": str(excel_path),
    }
    logger.info(
        f"  Portfolio stats built: {total_loans} loans, "
        f"exposure ₹{total_exposure/1e7:.1f}Cr, "
        f"EL ₹{portfolio_el_total/1e5:.1f}L"
    )
    return stats


# ── Persistent JSON cache ──────────────────────────────────────────────────────
import json
from datetime import datetime, timedelta

_CACHE_FILE = Path(__file__).resolve().parent / "portfolio_cache.json"
_CACHE_TTL_HOURS = 24


def _is_cache_valid() -> bool:
    """Return True if cache file exists and is less than TTL hours old."""
    if not _CACHE_FILE.exists():
        return False
    mtime = datetime.fromtimestamp(_CACHE_FILE.stat().st_mtime)
    return datetime.now() - mtime < timedelta(hours=_CACHE_TTL_HOURS)


def _read_cache() -> Optional[dict]:
    """Read cached stats from JSON file. Returns None on any error."""
    try:
        with open(_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.info(f"✓ Portfolio stats loaded from cache ({_CACHE_FILE.name})")
        return data
    except Exception as exc:
        logger.warning(f"Cache read failed: {exc} — rebuilding")
        return None


def _write_cache(stats: dict) -> None:
    """Write stats dict to JSON cache file. Silently ignores write errors."""
    try:
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(stats, f, default=str)
        logger.info(f"✓ Portfolio stats cached to {_CACHE_FILE.name}")
    except Exception as exc:
        logger.warning(f"Cache write failed (non-fatal): {exc}")


def get_portfolio_stats_from_file(force_reload: bool = False) -> dict:
    """
    Return pre-aggregated portfolio statistics.

    Cache hierarchy (fastest → slowest):
      1. In-memory _CACHED_STATS               — instant (same process)
      2. portfolio_cache.json  (< 24h old)     — file read (~1ms)
      3. Internal_Bank_Dataset.xlsx            — full pandas load (~3-5s)
      4. _DEFAULT_STATS                        — fallback (no dataset)

    Called by:
      - backend/mock_apis/portfolio.py  (GET /mock/bank/portfolio-summary)
      - portfolio_agent/agent.py        (when test runner builds PortfolioStats)
      - portfolio_agent/test_agent.py   (--seed / --test)
    """
    global _CACHED_STATS

    # 1. In-memory cache (same process, fastest)
    if _CACHED_STATS is not None and not force_reload:
        return _CACHED_STATS

    # 2. Persistent JSON file cache (survives restarts, < 24h TTL)
    if not force_reload and _is_cache_valid():
        cached = _read_cache()
        if cached is not None:
            _CACHED_STATS = cached
            return _CACHED_STATS

    # 3. Load from Excel (slow path — only on first run or forced reload)
    excel_path = _find_dataset_path()
    if excel_path is None:
        logger.warning("Internal_Bank_Dataset.xlsx not found — using default portfolio stats")
        _CACHED_STATS = _DEFAULT_STATS.copy()
    else:
        try:
            _CACHED_STATS = _build_stats_from_excel(excel_path)
            _write_cache(_CACHED_STATS)   # persist so next restart is fast
        except Exception as exc:
            logger.warning(f"Failed to build stats from {excel_path}: {exc} — using defaults")
            _CACHED_STATS = _DEFAULT_STATS.copy()

    return _CACHED_STATS


def get_portfolio_stats_cached() -> dict:
    """
    Alias for get_portfolio_stats_from_file() — used by mock API.
    Name emphasises that this is the cache-aware version.
    """
    return get_portfolio_stats_from_file()


def invalidate_cache() -> None:
    """Delete the JSON cache file and clear in-memory cache. Forces full reload on next call."""
    global _CACHED_STATS
    _CACHED_STATS = None
    if _CACHE_FILE.exists():
        _CACHE_FILE.unlink()
        logger.info(f"Cache invalidated: {_CACHE_FILE.name} deleted")



# ── Optional PostgreSQL seeding (uses SQLAlchemy) ────────────────────────────

def _get_engine():
    from sqlalchemy import create_engine
    db_url = os.getenv("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/jatayu")
    return create_engine(db_url, pool_pre_ping=True)


def seed_portfolio_to_db(excel_path: Optional[str] = None) -> int:
    """
    Optional: seed portfolio_loans table from Excel dataset.
    Returns number of rows inserted. Idempotent — skips if rows already exist.
    """
    try:
        from sqlalchemy import Column, String, Float, Integer, Date, text
        from sqlalchemy.orm import declarative_base, Session
        import pandas as pd
        import numpy as np

        Base = declarative_base()

        class PortfolioLoan(Base):  # type: ignore[misc]
            __tablename__ = "portfolio_loans"
            loan_id = Column(String(50), primary_key=True)
            loan_purpose = Column(String(20), default="PERSONAL")
            loan_amount_sanctioned = Column(Float)
            outstanding_amount = Column(Float)
            risk_band = Column(String(10))
            predicted_pd = Column(Float)
            employment_type = Column(String(20))
            employer_name = Column(String(100))
            applicant_state = Column(String(50))
            applicant_city = Column(String(100))
            annual_income_band = Column(String(20))

        engine = _get_engine()
        Base.metadata.create_all(engine)

        with Session(engine) as session:
            existing = session.execute(text("SELECT COUNT(*) FROM portfolio_loans")).scalar()
            if existing and existing > 0:
                logger.info(f"portfolio_loans already has {existing} rows — skipping seed")
                return 0

        path = Path(excel_path) if excel_path else _find_dataset_path()
        if path is None or not path.exists():
            logger.warning("Excel file not found — cannot seed DB")
            return 0

        df = pd.read_excel(path)
        rng = np.random.default_rng(seed=42)

        income_col = next((c for c in df.columns if "NETMONTHLYINCOME" in c.upper()), None)
        df["_income"] = pd.to_numeric(df[income_col], errors="coerce").fillna(30000) if income_col else 30000.0
        df["_loan_amount"] = df["_income"] * rng.uniform(8, 24, size=len(df))
        df["_outstanding"] = df["_loan_amount"] * rng.uniform(0.3, 0.9, size=len(df))

        score_col = next((c for c in df.columns if "CREDIT_SCORE" in c.upper()), None)
        if score_col:
            raw = pd.to_numeric(df[score_col], errors="coerce").fillna(0)
            df["_pd"] = ((900 - raw.clip(300, 900)) / 600 * 0.3).clip(0.005, 0.35)
        else:
            df["_pd"] = rng.uniform(0.02, 0.20, size=len(df))

        def pd_to_band(pd_val: float) -> str:
            if pd_val < 0.02: return "LOW"
            elif pd_val < 0.08: return "MEDIUM"
            elif pd_val < 0.18: return "HIGH"
            else: return "VERY_HIGH"

        df["_risk_band"] = df["_pd"].apply(pd_to_band)

        def income_to_band(inc: float) -> str:
            ann = inc * 12
            if ann < 300000: return "<3L"
            elif ann < 600000: return "3L-6L"
            elif ann < 1200000: return "6L-12L"
            else: return "12L+"

        rows_added = 0
        with Session(engine) as session:
            for i, row in df.iterrows():
                loan = PortfolioLoan(
                    loan_id=f"PL-{i:05d}",
                    loan_purpose="PERSONAL",
                    loan_amount_sanctioned=round(float(row["_loan_amount"]), 2),
                    outstanding_amount=round(float(row["_outstanding"]), 2),
                    risk_band=row["_risk_band"],
                    predicted_pd=round(float(row["_pd"]), 6),
                    employment_type="SALARIED",
                    employer_name="Unknown",
                    applicant_state="Maharashtra",
                    applicant_city="Mumbai",
                    annual_income_band=income_to_band(float(row["_income"])),
                )
                session.add(loan)
                rows_added += 1
            session.commit()

        logger.info(f"Seeded {rows_added} portfolio loans to DB")
        return rows_added

    except Exception as exc:
        logger.warning(f"DB seeding skipped: {exc}")
        return 0
