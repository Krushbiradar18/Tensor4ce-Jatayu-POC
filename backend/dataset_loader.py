"""
dataset_loader.py — Load and serve data from Excel datasets
============================================================
Loads the three Excel files and provides MCP-style tool functions
for accessing CIBIL bureau data and internal bank data by PAN.
"""
from __future__ import annotations
import json
import logging
import os
import threading
from pathlib import Path
from typing import Optional
import pandas as pd

logger = logging.getLogger(__name__)

# ── Global DataFrames (loaded once at startup) ─────────────────────────────
_CIBIL_DATA: Optional[pd.DataFrame] = None
_BANK_DATA: Optional[pd.DataFrame] = None
_MERGED_DATA: Optional[pd.DataFrame] = None
_UNSEEN_DATA: Optional[pd.DataFrame] = None
_DATASETS_LOADED: bool = False
_DATASETS_LOADING: bool = False
_LOAD_LOCK = threading.Lock()


def _cache_enabled() -> bool:
    return os.environ.get("DATASET_CACHE_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}


def _cache_only_mode() -> bool:
    return os.environ.get("DATASET_CACHE_ONLY", "false").strip().lower() in {"1", "true", "yes", "on"}


def _cache_dir(base: Path) -> Path:
    configured = os.environ.get("DATASET_CACHE_DIR", "").strip()
    return Path(configured) if configured else (base / ".cache")


def _dataset_files(base: Path) -> dict[str, Path]:
    return {
        "cibil": base / "External_Cibil_Dataset.xlsx",
        "bank": base / "Internal_Bank_Dataset.xlsx",
        "unseen": base / "Unseen_Dataset.xlsx",
    }


def _file_signature(path: Path) -> dict:
    if not path.exists():
        return {"exists": False}
    stat = path.stat()
    return {
        "exists": True,
        "size": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
    }


def _source_signature(files: dict[str, Path]) -> dict:
    return {name: _file_signature(path) for name, path in files.items()}


def _load_cached_datasets(base: Path, files: dict[str, Path], validate_sources: bool = True) -> bool:
    """Try restoring preprocessed DataFrames from cache if source files are unchanged."""
    global _CIBIL_DATA, _BANK_DATA, _MERGED_DATA, _UNSEEN_DATA, _DATASETS_LOADED

    if not _cache_enabled():
        return False

    cache = _cache_dir(base)
    meta_path = cache / "dataset_cache_meta.json"
    cibil_cache = cache / "cibil.pkl"
    bank_cache = cache / "bank.pkl"
    merged_cache = cache / "merged.pkl"
    unseen_cache = cache / "unseen.pkl"

    if not (meta_path.exists() and cibil_cache.exists() and bank_cache.exists() and merged_cache.exists() and unseen_cache.exists()):
        return False

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if validate_sources:
            expected = meta.get("source_signature", {})
            current = _source_signature(files)
            if expected != current:
                logger.info("Dataset cache stale (source files changed); rebuilding from Excel.")
                return False

        _CIBIL_DATA = pd.read_pickle(cibil_cache)
        _BANK_DATA = pd.read_pickle(bank_cache)
        _MERGED_DATA = pd.read_pickle(merged_cache)
        _UNSEEN_DATA = pd.read_pickle(unseen_cache)
        _DATASETS_LOADED = True
        logger.info("✓ Dataset cache restored from %s", cache)
        return True
    except Exception as exc:
        logger.warning("Failed to load dataset cache; rebuilding from Excel (%s)", exc)
        return False


def _save_cached_datasets(base: Path, files: dict[str, Path]) -> None:
    """Persist preprocessed DataFrames for fast startup on next restart."""
    if not _cache_enabled():
        return

    cache = _cache_dir(base)
    cache.mkdir(parents=True, exist_ok=True)

    cibil_cache = cache / "cibil.pkl"
    bank_cache = cache / "bank.pkl"
    merged_cache = cache / "merged.pkl"
    unseen_cache = cache / "unseen.pkl"
    meta_path = cache / "dataset_cache_meta.json"

    try:
        (_CIBIL_DATA if _CIBIL_DATA is not None else pd.DataFrame()).to_pickle(cibil_cache)
        (_BANK_DATA if _BANK_DATA is not None else pd.DataFrame()).to_pickle(bank_cache)
        (_MERGED_DATA if _MERGED_DATA is not None else pd.DataFrame()).to_pickle(merged_cache)
        (_UNSEEN_DATA if _UNSEEN_DATA is not None else pd.DataFrame()).to_pickle(unseen_cache)

        meta = {
            "cache_version": 1,
            "source_signature": _source_signature(files),
        }
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        logger.info("✓ Dataset cache saved to %s", cache)
    except Exception as exc:
        logger.warning("Could not save dataset cache (%s)", exc)


def _first_present(row: dict, keys: list[str], default=None):
    """Return the first present, non-null value from candidate keys."""
    for key in keys:
        if key in row:
            value = row.get(key)
            if pd.notna(value):
                return value
    return default

def _prospect_id_to_pan(prospect_id: int) -> str:
    """Convert numeric PROSPECTID to synthetic PAN format."""
    # Format: PROSP + 5-digit ID + check letter
    # Example: PROSPECTID 1 → PROSP00001X
    check_letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    check = check_letters[prospect_id % 26]
    return f"PROSP{prospect_id:05d}{check}"


def _pan_to_prospect_id(pan: str) -> Optional[int]:
    """Convert synthetic PAN back to PROSPECTID."""
    pan = pan.upper().strip()

    # Extract numeric part from legacy PROSP00001X format.
    if pan.startswith("PROSP") and len(pan) >= 11:
        try:
            return int(pan[5:10])  # Extract 5 digits
        except ValueError:
            pass

    # Best-effort parse for short PROSP0001X format.
    if pan.startswith("PROSP") and len(pan) == 10:
        try:
            return int(pan[5:9])  # Extract 4 digits
        except ValueError:
            pass

    return None


def _find_pan_match(df: pd.DataFrame, pan: str) -> pd.DataFrame:
    """Find PAN row supporting both 11-char and short 10-char PROSP aliases."""
    if df is None or df.empty or 'PAN' not in df.columns:
        return pd.DataFrame()

    normalized_pan = str(pan).upper().strip()
    pan_series = df['PAN'].astype(str).str.upper().str.strip()

    # Exact PAN match first.
    exact_match = df[pan_series == normalized_pan]
    if not exact_match.empty:
        return exact_match

    # Support short UI PAN format: PROSP####X.
    # Legacy dataset PAN is PROSP#####X, where short form drops the first digit.
    if normalized_pan.startswith("PROSP") and len(normalized_pan) == 10:
        suffix = normalized_pan[5:]  # ####X
        short_alias_match = df[
            pan_series.str.startswith("PROSP")
            & (pan_series.str.len() == 11)
            & (pan_series.str[6:] == suffix)
        ]
        if not short_alias_match.empty:
            if len(short_alias_match) > 1:
                logger.warning(
                    "PAN %s matched multiple legacy rows (%s). Using first match.",
                    normalized_pan,
                    len(short_alias_match),
                )
            return short_alias_match.head(1)

    return pd.DataFrame()


def load_datasets(dataset_dir: str = "dataset"):
    """Load all Excel datasets into memory. Call this once at startup."""
    global _CIBIL_DATA, _BANK_DATA, _MERGED_DATA, _UNSEEN_DATA, _DATASETS_LOADED, _DATASETS_LOADING

    with _LOAD_LOCK:
        if _DATASETS_LOADED:
            return
        _DATASETS_LOADING = True

    try:
        base = Path(dataset_dir)
        files = _dataset_files(base)

        cache_only = _cache_only_mode()

        if _load_cached_datasets(base, files, validate_sources=not cache_only):
            return

        if cache_only:
            raise RuntimeError(
                "DATASET_CACHE_ONLY=true but no valid cache found. "
                "Run once with Excel datasets available to build cache first."
            )

        # External CIBIL Dataset
        cibil_path = files["cibil"]
        if cibil_path.exists():
            logger.info(f"Loading CIBIL dataset from {cibil_path}...")
            _CIBIL_DATA = pd.read_excel(cibil_path)

            # Datasets use PROSPECTID (numeric) instead of PAN
            # Create synthetic PAN column for compatibility
            if 'PROSPECTID' in _CIBIL_DATA.columns:
                _CIBIL_DATA['PAN'] = _CIBIL_DATA['PROSPECTID'].apply(_prospect_id_to_pan)
                logger.info(f"✓ CIBIL data loaded: {len(_CIBIL_DATA)} records (using PROSPECTID)")
            else:
                # Try to find PAN column if it exists
                pan_cols = [c for c in _CIBIL_DATA.columns if 'pan' in c.lower()]
                if pan_cols:
                    _CIBIL_DATA.rename(columns={pan_cols[0]: 'PAN'}, inplace=True)
                    _CIBIL_DATA['PAN'] = _CIBIL_DATA['PAN'].str.upper().str.strip()
                    logger.info(f"✓ CIBIL data loaded: {len(_CIBIL_DATA)} records")
                else:
                    logger.warning("No PROSPECTID or PAN column found in CIBIL dataset")
                    _CIBIL_DATA = pd.DataFrame()
        else:
            logger.warning(f"CIBIL dataset not found at {cibil_path}")
            _CIBIL_DATA = pd.DataFrame()

        # Internal Bank Dataset
        bank_path = files["bank"]
        if bank_path.exists():
            logger.info(f"Loading internal bank dataset from {bank_path}...")
            _BANK_DATA = pd.read_excel(bank_path)

            # Create synthetic PAN from PROSPECTID
            if 'PROSPECTID' in _BANK_DATA.columns:
                _BANK_DATA['PAN'] = _BANK_DATA['PROSPECTID'].apply(_prospect_id_to_pan)
                logger.info(f"✓ Bank data loaded: {len(_BANK_DATA)} records (using PROSPECTID)")
            else:
                # Try to find PAN column if it exists
                pan_cols = [c for c in _BANK_DATA.columns if 'pan' in c.lower()]
                if pan_cols:
                    _BANK_DATA.rename(columns={pan_cols[0]: 'PAN'}, inplace=True)
                    _BANK_DATA['PAN'] = _BANK_DATA['PAN'].str.upper().str.strip()
                    logger.info(f"✓ Bank data loaded: {len(_BANK_DATA)} records")
                else:
                    logger.warning("No PROSPECTID or PAN column found in Bank dataset")
                    _BANK_DATA = pd.DataFrame()
        else:
            logger.warning(f"Bank dataset not found at {bank_path}")
            _BANK_DATA = pd.DataFrame()

        # Merge datasets if both exist
        if not _CIBIL_DATA.empty and not _BANK_DATA.empty:
            logger.info("Merging CIBIL and Bank datasets on PAN...")
            _MERGED_DATA = pd.merge(
                _BANK_DATA, _CIBIL_DATA,
                on='PAN', how='left', suffixes=('_bank', '_cibil')
            )
            logger.info(f"✓ Merged dataset created: {len(_MERGED_DATA)} records")
        else:
            _MERGED_DATA = _BANK_DATA if not _BANK_DATA.empty else _CIBIL_DATA

        # Unseen test dataset
        unseen_path = files["unseen"]
        if unseen_path.exists():
            _UNSEEN_DATA = pd.read_excel(unseen_path)
            if 'PROSPECTID' in _UNSEEN_DATA.columns:
                _UNSEEN_DATA['PAN'] = _UNSEEN_DATA['PROSPECTID'].apply(_prospect_id_to_pan)
            logger.info(f"✓ Unseen test data loaded: {len(_UNSEEN_DATA)} records")
        else:
            logger.warning(f"Unseen dataset not found at {unseen_path}")
            _UNSEEN_DATA = pd.DataFrame()

        _DATASETS_LOADED = True
        _save_cached_datasets(base, files)
    finally:
        _DATASETS_LOADING = False


def start_background_dataset_preload(dataset_dir: str = "dataset") -> bool:
    """Start async background preload once; returns True only when new thread starts."""
    global _DATASETS_LOADING
    with _LOAD_LOCK:
        if _DATASETS_LOADED or _DATASETS_LOADING:
            return False
        _DATASETS_LOADING = True

    def _worker() -> None:
        try:
            logger.info("Background dataset preload started...")
            load_datasets(dataset_dir)
            logger.info("Background dataset preload completed.")
        except Exception:
            logger.exception("Background dataset preload failed")

    thread = threading.Thread(target=_worker, daemon=True, name="dataset-preload")
    thread.start()
    return True


def _ensure_datasets_loaded() -> None:
    """Lazy-load datasets on first access when startup preloading is disabled."""
    if _DATASETS_LOADED:
        return

    import os

    dataset_dir = os.environ.get("DATASET_DIR", "dataset")
    logger.info("Datasets not ready yet; loading now on demand...")
    load_datasets(dataset_dir)


def get_cibil_data(pan: str) -> Optional[dict]:
    """
    Get CIBIL bureau data for a PAN from External_Cibil_Dataset.xlsx.
    Returns dict with keys: cibil_score, num_hard_enquiries_6m, dpd_30_count, etc.
    """
    _ensure_datasets_loaded()

    if _CIBIL_DATA is None or _CIBIL_DATA.empty:
        return None

    pan = pan.upper().strip()
    match = _find_pan_match(_CIBIL_DATA, pan)

    if match.empty:
        return None

    row = match.iloc[0].to_dict()

    # Map columns to expected bureau schema
    # Adjust column names based on actual CIBIL dataset structure
    return {
        "cibil_score": float(row.get("CIBIL_Score", row.get("Credit_Score", 0))),
        "num_hard_enquiries_6m": int(row.get("No_of_Inquiries", row.get("num_enquiries", 0))),
        "dpd_30_count": int(row.get("DPD_30", row.get("dpd_30_count", 0))),
        "dpd_90_count": int(row.get("DPD_90", row.get("dpd_90_count", 0))),
        "payment_history_score": float(row.get("Payment_History_Score", 50)),
        "credit_utilization_pct": float(row.get("Credit_Utilization", row.get("utilization_pct", 0.3))),
        "oldest_account_age_years": float(row.get("Age_of_Oldest_Account", row.get("oldest_account_years", 1.0))),
        "total_outstanding_debt": float(row.get("Total_Outstanding", row.get("outstanding_debt", 0))),
        "num_active_loans": int(row.get("Num_Active_Loans", row.get("active_loans", 0))),
        "bureau_unavailable": False,
    }


def get_bank_data(pan: str) -> Optional[dict]:
    """
    Get internal bank data for a PAN from Internal_Bank_Dataset.xlsx.
    Returns dict with bank statement fields, EMI history, etc.
    """
    _ensure_datasets_loaded()

    if _BANK_DATA is None or _BANK_DATA.empty:
        return None

    pan = pan.upper().strip()
    match = _find_pan_match(_BANK_DATA, pan)

    if match.empty:
        return None

    row = match.iloc[0].to_dict()

    # Map columns to expected bank schema
    return {
        "avg_monthly_credit": float(row.get("Avg_Monthly_Credit", row.get("monthly_credit", 0))),
        "avg_monthly_debit": float(row.get("Avg_Monthly_Debit", row.get("monthly_debit", 0))),
        "min_eod_balance": float(row.get("Min_EOD_Balance", row.get("min_balance", 0))),
        "avg_eod_balance": float(row.get("Avg_EOD_Balance", row.get("avg_balance", 0))),
        "emi_bounce_count": int(row.get("EMI_Bounce_Count", row.get("bounces", 0))),
        "salary_regularity": float(row.get("Salary_Regularity", row.get("regularity", 1.0))),
        "cash_flow_volatility": float(row.get("Cash_Flow_Volatility", 0.15)),
        "debit_credit_ratio": float(row.get("Debit_Credit_Ratio", 0.75)),
        "balance_utilization": float(row.get("Balance_Utilization", 0.3)),
    }


def get_merged_customer_profile(pan: str) -> Optional[dict]:
    """
    Get complete customer profile merging CIBIL + Bank data.
    This is useful for credit risk agent that needs comprehensive view.
    """
    _ensure_datasets_loaded()

    if _MERGED_DATA is None or _MERGED_DATA.empty:
        # Fallback: merge on the fly
        cibil = get_cibil_data(pan)
        bank = get_bank_data(pan)
        if cibil is None and bank is None:
            return None
        profile = {}
        if cibil:
            profile.update(cibil)
        if bank:
            profile.update(bank)
        profile['pan_number'] = pan
        return profile

    pan = pan.upper().strip()
    match = _find_pan_match(_MERGED_DATA, pan)

    if match.empty:
        return None

    row = match.iloc[0].to_dict()

    # Return profile fields aligned to the credit model training schema.
    profile = {
        "pan_number": pan,
        "name": _first_present(row, ["Name", "Applicant_Name", "name"], "Unknown"),

        # Core training features (exact names expected by credit model)
        "Credit_Score": float(_first_present(row, ["Credit_Score", "Credit_Score_cibil", "CIBIL_Score_cibil"], 0) or 0),
        "num_times_delinquent": int(_first_present(row, ["num_times_delinquent", "num_times_delinquent_cibil", "DPD_90"], 0) or 0),
        "recent_level_of_deliq": int(_first_present(row, ["recent_level_of_deliq", "recent_level_of_deliq_cibil"], 0) or 0),
        "num_deliq_6mts": int(_first_present(row, ["num_deliq_6mts", "num_deliq_6mts_cibil", "DPD_30"], 0) or 0),
        "num_deliq_12mts": int(_first_present(row, ["num_deliq_12mts", "num_deliq_12mts_cibil", "DPD_30"], 0) or 0),
        "num_times_30p_dpd": int(_first_present(row, ["num_times_30p_dpd", "num_times_30p_dpd_cibil", "DPD_30"], 0) or 0),
        "num_times_60p_dpd": int(_first_present(row, ["num_times_60p_dpd", "num_times_60p_dpd_cibil", "DPD_90"], 0) or 0),
        "num_std": int(_first_present(row, ["num_std", "num_std_cibil"], 0) or 0),
        "num_sub": int(_first_present(row, ["num_sub", "num_sub_cibil"], 0) or 0),
        "num_dbt": int(_first_present(row, ["num_dbt", "num_dbt_cibil"], 0) or 0),
        "num_lss": int(_first_present(row, ["num_lss", "num_lss_cibil"], 0) or 0),
        "tot_enq": int(_first_present(row, ["tot_enq", "tot_enq_cibil", "No_of_Inquiries"], 0) or 0),
        "enq_L12m": int(_first_present(row, ["enq_L12m", "enq_L12m_cibil", "No_of_Inquiries"], 0) or 0),
        "enq_L6m": int(_first_present(row, ["enq_L6m", "enq_L6m_cibil", "No_of_Inquiries"], 0) or 0),
        "time_since_recent_enq": int(_first_present(row, ["time_since_recent_enq", "time_since_recent_enq_cibil"], 0) or 0),
        "CC_utilization": float(_first_present(row, ["CC_utilization", "CC_utilization_cibil", "CC_Utilization", "Credit_Utilization"], 0) or 0),
        "PL_utilization": float(_first_present(row, ["PL_utilization", "PL_utilization_cibil", "PL_Utilization"], 0) or 0),
        "max_unsec_exposure_inPct": float(_first_present(row, ["max_unsec_exposure_inPct", "max_unsec_exposure_inPct_cibil", "Max_Unsec_Exposure_Pct"], 0) or 0),
        "pct_of_active_TLs_ever": float(_first_present(row, ["pct_of_active_TLs_ever", "pct_of_active_TLs_ever_cibil"], 0) or 0),
        "pct_currentBal_all_TL": float(_first_present(row, ["pct_currentBal_all_TL", "pct_currentBal_all_TL_cibil"], 0) or 0),
        "AGE": int(_first_present(row, ["AGE", "Age_bank", "Age"], 30) or 30),
        "NETMONTHLYINCOME": float(_first_present(row, ["NETMONTHLYINCOME", "Net_Monthly_Income_bank"], 0) or 0),
        "Time_With_Curr_Empr": float(_first_present(row, ["Time_With_Curr_Empr", "Employment_Tenure"], 1.0) or 1.0),
        "MARITALSTATUS": str(_first_present(row, ["MARITALSTATUS", "MARITALSTATUS_cibil"], "Single")),
        "EDUCATION": str(_first_present(row, ["EDUCATION", "EDUCATION_cibil"], "GRADUATE")),
        "GENDER": str(_first_present(row, ["GENDER", "GENDER_cibil"], "M")),
        "Approved_Flag": _first_present(row, ["Approved_Flag", "Approved_Flag_cibil"], None),

        # Convenience aliases used elsewhere
        "cibil_score": float(_first_present(row, ["Credit_Score", "Credit_Score_cibil", "CIBIL_Score_cibil"], 0) or 0),
        "num_hard_enquiries_6m": int(row.get("No_of_Inquiries", 0)),
        "dpd_30_count": int(row.get("DPD_30", 0)),
        "dpd_90_count": int(row.get("DPD_90", 0)),

        # Bank fields
        "avg_monthly_credit": float(_first_present(row, ["Avg_Monthly_Credit", "avg_monthly_credit"], 0) or 0),
        "avg_monthly_debit": float(_first_present(row, ["Avg_Monthly_Debit", "avg_monthly_debit"], 0) or 0),
        "emi_bounce_count": int(_first_present(row, ["EMI_Bounce_Count", "emi_bounce_count"], 0) or 0),
        "salary_regularity": float(_first_present(row, ["Salary_Regularity", "salary_regularity"], 1.0) or 1.0),
    }

    return profile


def get_credit_ground_truth(pan: str) -> Optional[dict]:
    """Return model-training ground truth label fields for a PAN, if available."""
    _ensure_datasets_loaded()

    if _CIBIL_DATA is None or _CIBIL_DATA.empty:
        return None

    pan = pan.upper().strip()
    match = _find_pan_match(_CIBIL_DATA, pan)
    if match.empty:
        return None

    row = match.iloc[0].to_dict()
    approved_flag = row.get("Approved_Flag")
    if pd.isna(approved_flag):
        approved_flag = None

    return {
        "pan": pan,
        "approved_flag": approved_flag,
        "credit_score": float(row.get("Credit_Score", 0) or 0),
    }


def list_available_pans(limit: int = 10) -> list[str]:
    """Return list of PANs available in the dataset for testing."""
    _ensure_datasets_loaded()

    if _MERGED_DATA is not None and not _MERGED_DATA.empty:
        return _MERGED_DATA['PAN'].head(limit).tolist()
    elif _BANK_DATA is not None and not _BANK_DATA.empty:
        return _BANK_DATA['PAN'].head(limit).tolist()
    elif _CIBIL_DATA is not None and not _CIBIL_DATA.empty:
        return _CIBIL_DATA['PAN'].head(limit).tolist()
    return []


def get_sample_test_cases(count: int = 10) -> list[dict]:
    """
    Get sample test cases from dataset with complete information.
    Returns list of dicts with PAN, CIBIL score, income, age, etc.
    """
    _ensure_datasets_loaded()

    if _CIBIL_DATA is None or _CIBIL_DATA.empty:
        return []

    # Sample random records
    sample = _CIBIL_DATA.sample(n=min(count, len(_CIBIL_DATA)))

    test_cases = []
    for _, row in sample.iterrows():
        pan = row.get('PAN', 'UNKNOWN')
        prospect_id = row.get('PROSPECTID', 0)

        test_case = {
            "pan": pan,
            "prospect_id": int(prospect_id),
            "credit_score": float(row.get("Credit_Score", 700)),
            "age": int(row.get("AGE", 30)),
            "income": float(row.get("NETMONTHLYINCOME", 50000)) * 12,  # Annual
            "monthly_income": float(row.get("NETMONTHLYINCOME", 50000)),
            "dpd_30": int(row.get("num_times_30p_dpd", 0)),
            "dpd_90": int(row.get("num_times_60p_dpd", 0)),
            "enquiries_6m": int(row.get("enq_L6m", 0)),
            "cc_utilization": float(row.get("CC_utilization", 0.3)),
            "education": row.get("EDUCATION", "Unknown"),
            "marital_status": row.get("MARITALSTATUS", "Unknown"),
        }
        test_cases.append(test_case)

    return test_cases


def get_dataset_stats() -> dict:
    """Return statistics about loaded datasets."""
    _ensure_datasets_loaded()

    cibil_records = len(_CIBIL_DATA) if _CIBIL_DATA is not None else 0
    bank_records = len(_BANK_DATA) if _BANK_DATA is not None else 0
    merged_records = len(_MERGED_DATA) if _MERGED_DATA is not None else 0
    unseen_records = len(_UNSEEN_DATA) if _UNSEEN_DATA is not None else 0
    return {
        "cibil_records": cibil_records,
        "bank_records": bank_records,
        "merged_records": merged_records,
        "unseen_records": unseen_records,
        "datasets_loaded": any([cibil_records, bank_records, merged_records, unseen_records]),
    }
