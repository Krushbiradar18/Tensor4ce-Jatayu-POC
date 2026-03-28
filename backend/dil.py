"""
dil.py — Data Intelligence Layer (Stages 1-8)
Transforms raw form input into a typed ApplicationContext.
No OCR dependencies required — uses form data directly for PoC.
"""
from __future__ import annotations
import os, re, json, math, hashlib, logging
from datetime import date, datetime
from pathlib import Path
from typing import Optional
from schemas import (
    ApplicationContext, LoanApplicationIn, IPMetaIn, FeatureVector,
    ValidationFlag, LoanProduct
)

logger = logging.getLogger(__name__)

# ── Static data loaded once at startup ───────────────────────────────────────
_BLACKLIST: set[str] = set()
_MACRO: dict = {}
_PRODUCT_LIMITS: dict = {}

LOAN_PRODUCT_RISK = {"HOME": 0.30, "AUTO": 0.40, "PERSONAL": 0.70, "EDUCATION": 0.50}
LOAN_PRODUCT_CODE = {"HOME": 0, "AUTO": 1, "PERSONAL": 2, "EDUCATION": 3}
EFFECTIVE_RATES   = {"HOME": 9.0, "AUTO": 9.5, "PERSONAL": 12.0, "EDUCATION": 10.0}
LGD_MAP           = {"HOME": 0.25, "AUTO": 0.40, "PERSONAL": 0.65, "EDUCATION": 0.55}


def load_static_data(data_dir: str = "data"):
    global _BLACKLIST, _MACRO, _PRODUCT_LIMITS
    d = Path(data_dir)

    # Fraud blacklist
    bl_path = d / "fraud_blacklist.json"
    if bl_path.exists():
        bl = json.loads(bl_path.read_text())
        _BLACKLIST = {e["pan"] for e in bl.get("blacklisted_pans", [])}
    else:
        _BLACKLIST = {"FRAUD1234F", "BLKLT5678G", "TESTFRAUD0"}
    logger.info(f"DIL: loaded {len(_BLACKLIST)} blacklisted PANs")

    # Macro config
    mc_path = d / "macro_config.json"
    if mc_path.exists():
        _MACRO = json.loads(mc_path.read_text())
    else:
        _MACRO = {
            "rbi_repo_rate": 6.50, "stress_scenario": "NORMAL",
            "stress_multipliers": {"NORMAL": 0.0, "MILD_STRESS": 0.5, "HIGH_STRESS": 1.2},
            "sector_npa_rates": {"HOME": 0.032, "AUTO": 0.038, "PERSONAL": 0.061, "EDUCATION": 0.045},
            "effective_rates": EFFECTIVE_RATES,
        }

    # Product limits
    pl_path = d / "product_limits.json"
    if pl_path.exists():
        _PRODUCT_LIMITS = json.loads(pl_path.read_text())
    else:
        _PRODUCT_LIMITS = {
            "HOME":      {"max_ltv": 0.80, "max_foir": 0.55, "min_income": 300000, "min_cibil": 650},
            "AUTO":      {"max_ltv": 0.85, "max_foir": 0.55, "min_income": 250000, "min_cibil": 620},
            "PERSONAL":  {"max_ltv": 0.00, "max_foir": 0.50, "min_income": 300000, "min_cibil": 680},
            "EDUCATION": {"max_ltv": 0.00, "max_foir": 0.45, "min_income": 0,      "min_cibil": 0},
        }


# ── In-memory FeatureStore ────────────────────────────────────────────────────
_FEATURE_STORE: dict[str, ApplicationContext] = {}

def store_context(ctx: ApplicationContext):
    _FEATURE_STORE[ctx.application_id] = ctx

def get_context(app_id: str) -> Optional[ApplicationContext]:
    return _FEATURE_STORE.get(app_id)

def get_features(app_id: str, group: str = "all") -> Optional[dict]:
    ctx = _FEATURE_STORE.get(app_id)
    if not ctx:
        return None
    return ctx.features.model_dump()


# ── Bureau mock ───────────────────────────────────────────────────────────────

def get_bureau_data(pan: str) -> dict:
    """Get bureau response - tries real dataset first, fallback to mock."""
    # Try to get real data from loaded dataset
    try:
        from dataset_loader import get_cibil_data
        # 1. Try DB first
        db_row = get_cibil_data(pan)
        if db_row:
            logger.info(f"[DIL] Using REAL bureau DB data for PAN {pan}")
            # Sanitize/Clamp slightly to ensure UI perfection
            raw_util = db_row.get("credit_utilization_pct", 0.2)
            if raw_util > 1.0: # If it was expressed as 43 instead of 0.43
                 raw_util /= 100.0
            db_row["credit_utilization_pct"] = max(0.05, min(0.95, raw_util))
            return db_row
    except Exception as e:
        logger.warning(f"[DIL] DB lookup failed for bureau data: {e}")

    # 2. Try Manual overrides json
    data_dir = os.environ.get("DATA_DIR", "data")
    overrides_path = Path(data_dir) / "bureau_overrides.json"
    if overrides_path.exists():
        rules = json.loads(overrides_path.read_text())
        override = rules.get("pan_overrides", {}).get(pan.upper())
        if override:
            logger.info(f"[DIL] Using bureau override for PAN {pan}")
            return override

    # Fallback to deterministic hash-based mock
    logger.info(f"[DIL] Using hash-based mock bureau data for PAN {pan}")
    h = int(hashlib.md5(pan.upper().encode()).hexdigest(), 16)
    cibil = (h % 600) + 300
    return {
        "cibil_score":              float(cibil),
        "num_active_loans":         max(0, int(4 - cibil / 200)),
        "num_hard_enquiries_6m":    max(0, int(4 - cibil / 200)),
        "payment_history_score":    float(int(80 * (cibil - 300) / 600 + 20)),
        "dpd_30_count":             max(0, int((650 - cibil) / 80)) if cibil < 650 else 0,
        "dpd_90_count":             max(0, int((550 - cibil) / 80)) if cibil < 550 else 0,
        "credit_utilization_pct":   max(0.05, min(0.95, round(0.2 + (0.6 * (900 - cibil) / 600), 2))),
        "oldest_account_age_years": round(1 + (8 * (cibil - 300) / 600), 1),
        "total_outstanding_debt":   float((h % 500000) + 50000),
        "bureau_unavailable":       cibil == 0,
    }


# ── IP mock ───────────────────────────────────────────────────────────────────

def get_ip_data(ip: str) -> dict:
    ip_map_path = Path("data/ip_mock_map.json")
    if ip_map_path.exists():
        patterns = json.loads(ip_map_path.read_text()).get("patterns", [])
        for p in patterns:
            if ip.startswith(p["prefix"]):
                return p
    vpn = ip.startswith("10.") or ip.startswith("172.16.") or ip.startswith("104.")
    return {
        "country": "IN" if not vpn else "US",
        "proxy": vpn, "hosting": vpn,
        "ip_risk_score": 1.0 if vpn else 0.0,
    }


# ── EMI calculation ───────────────────────────────────────────────────────────

def compute_emi(loan_amount: float, tenure_months: int, annual_rate_pct: float) -> float:
    if tenure_months <= 0:
        return loan_amount
    r = (annual_rate_pct / 100) / 12
    if r == 0:
        return loan_amount / tenure_months
    return loan_amount * r * ((1 + r) ** tenure_months) / (((1 + r) ** tenure_months) - 1)


def compute_age(dob_str: str) -> int:
    try:
        dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
        today = date.today()
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    except Exception:
        return 30


# ── Main DIL pipeline ─────────────────────────────────────────────────────────

def run_dil_pipeline(
    application_id: str,
    form_data: dict,
    ip_meta_data: dict,
) -> ApplicationContext:
    """
    Run all 8 DIL stages and return an ApplicationContext.
    Stores result in the in-memory FeatureStore.
    """
    from datetime import datetime as dt
    notes: list[str] = []
    flags: list[ValidationFlag] = []

    # Parse inputs
    form = LoanApplicationIn(**form_data)
    ip   = IPMetaIn(**ip_meta_data)

    # ── Stage 3: Bureau call ──────────────────────────────────────────────────
    bureau = get_bureau_data(form.pan_number)
    ip_geo = get_ip_data(ip.ip_address)

    # ── Stage 4: Cross-validation ─────────────────────────────────────────────
    if form.pan_number.upper() in _BLACKLIST:
        flags.append(ValidationFlag(flag_code="PAN_BLACKLISTED", severity="BLOCK",
                                     description=f"PAN {form.pan_number} is on the fraud registry"))

    if not re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]$", form.pan_number.upper()):
        flags.append(ValidationFlag(flag_code="INVALID_PAN", severity="BLOCK",
                                     description=f"PAN format invalid: {form.pan_number}"))

    # Age check
    age = compute_age(form.date_of_birth)
    if not (21 <= age <= 65):
        flags.append(ValidationFlag(flag_code="AGE_INELIGIBLE", severity="BLOCK",
                                     description=f"Applicant age {age} outside eligible range 21-65"))

    # ── Stage 5: Feature engineering ─────────────────────────────────────────
    product     = form.loan_purpose.value
    rate        = _MACRO.get("effective_rates", EFFECTIVE_RATES).get(product, 10.0)
    monthly_inc = form.annual_income / 12
    prop_emi    = compute_emi(form.loan_amount_requested, form.loan_tenure_months, rate)
    total_oblig = form.existing_emi_monthly + prop_emi

    foir        = total_oblig / monthly_inc if monthly_inc > 0 else 1.0
    dti         = (bureau.get("total_outstanding_debt", 0) + form.loan_amount_requested) / max(form.annual_income, 1)
    collateral  = form.residential_assets_value
    ltv         = form.loan_amount_requested / max(collateral, 1) if collateral > 0 else 0.0
    surplus     = monthly_inc - form.existing_emi_monthly - prop_emi

    # FOIR warning
    max_foir = _PRODUCT_LIMITS.get(product, {}).get("max_foir", 0.55)
    if foir > max_foir:
        flags.append(ValidationFlag(flag_code="FOIR_EXCEEDED", severity="BLOCK",
                                     description=f"FOIR {foir:.1%} exceeds limit {max_foir:.0%} for {product}"))

    # Fraud signals
    ip_risk   = ip_geo.get("ip_risk_score", 0.0)
    app_vel   = 1   # default; would query DB for real velocity
    loan_inc_ratio = form.loan_amount_requested / max(form.annual_income, 1)
    outlier_z = (loan_inc_ratio - 3.5) / 1.5

    # Credit utilization-based salary regularity proxy
    salary_reg = 1.0 if form.employment_type.value == "SALARIED" else 0.5
    cibil_score = bureau.get("cibil_score", 0.0)
    inc_stability = (salary_reg * 0.5 + min(bureau.get("payment_history_score",50)/100, 1.0) * 0.5)

    fv = FeatureVector(
        # Bureau
        cibil_score             = cibil_score,
        num_active_loans        = bureau.get("num_active_loans", 0),
        num_hard_enquiries_6m   = bureau.get("num_hard_enquiries_6m", 0),
        payment_history_score   = bureau.get("payment_history_score", 50),
        dpd_30_count            = bureau.get("dpd_30_count", 0),
        dpd_90_count            = bureau.get("dpd_90_count", 0),
        credit_utilization_pct  = bureau.get("credit_utilization_pct", 0.3),
        oldest_account_age_years= bureau.get("oldest_account_age_years", 1.0),
        total_outstanding_debt  = bureau.get("total_outstanding_debt", 0),
        bureau_unavailable      = bureau.get("bureau_unavailable", False),
        bureau_check_done       = not bureau.get("bureau_unavailable", False),
        # Ratios
        annual_income_verified  = form.annual_income,
        foir                    = round(foir, 4),
        dti_ratio               = round(dti, 4),
        proposed_emi            = round(prop_emi, 2),
        emi_to_income_ratio     = round(prop_emi / monthly_inc, 4) if monthly_inc > 0 else 1.0,
        net_monthly_surplus     = round(surplus, 2),
        income_stability_score  = round(inc_stability, 4),
        # Collateral
        ltv_ratio               = round(min(ltv, 2.0), 4),
        loan_amount_requested   = form.loan_amount_requested,
        loan_tenure_months      = form.loan_tenure_months,
        loan_to_income_ratio    = round(loan_inc_ratio, 4),
        loan_purpose_risk_weight= LOAN_PRODUCT_RISK.get(product, 0.5),
        tenure_risk_score       = round(form.loan_tenure_months / 360, 4),
        collateral_coverage     = round(collateral / max(form.loan_amount_requested, 1), 4),
        # Cash-flow (derived — no real bank statement in PoC)
        avg_monthly_credit      = round(monthly_inc * 1.05, 2),
        avg_monthly_debit       = round(monthly_inc * 0.78, 2),
        min_eod_balance         = round(monthly_inc * 0.4, 2),
        avg_eod_balance         = round(monthly_inc * 1.1, 2),
        emi_bounce_count        = 0,
        salary_regularity       = salary_reg,
        cash_flow_volatility    = 0.12,
        debit_credit_ratio      = 0.75,
        balance_utilization     = 0.3,
        # Fraud
        ip_risk_score           = ip_risk,
        ip_country_mismatch     = ip_geo.get("country", "IN") != "IN",
        application_velocity    = app_vel,
        device_fingerprint_new  = True,
        form_fill_time_seconds  = ip.form_fill_seconds,
        address_pincode_mismatch= False,
        income_loan_ratio_outlier= round(outlier_z, 3),
        enquiry_spike_flag      = bureau.get("num_hard_enquiries_6m", 0) > 4,
        # Demographic
        applicant_age           = age,
        employment_tenure_years = form.employment_tenure_years,
        is_salaried             = form.employment_type.value == "SALARIED",
        state_code              = form.address.state,
        loan_product_code       = LOAN_PRODUCT_CODE.get(product, 0),
        # KYC
        kyc_pan_present         = bool(form.pan_number),
        kyc_aadhaar_present     = bool(form.aadhaar_last4),
        pan_blacklisted         = form.pan_number.upper() in _BLACKLIST,
        aml_declaration_present = False,
        income_proof_age_months = 12,
        bank_statement_months   = 6,
        name_match_score        = 1.0,
    )

    ctx = ApplicationContext(
        application_id   = application_id,
        form             = form,
        ip_meta          = ip,
        validation_flags = flags,
        features         = fv,
        macro_config     = _MACRO,
        processing_notes = notes,
        dil_completed_at = dt.utcnow().isoformat(),
    )

    store_context(ctx)
    logger.info(f"DIL completed for {application_id}: {len(flags)} flags, "
                f"CIBIL={cibil_score:.0f}, FOIR={foir:.1%}")
    return ctx
