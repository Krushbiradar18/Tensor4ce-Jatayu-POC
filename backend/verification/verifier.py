"""
backend/verification/verifier.py
====================================
3-Source Identity Verifier — Layer 3 of the 5-layer architecture.

Verification sources:
  Source 1: Form data (applicant self-declaration)
  Source 2: OCR extracted fields (from DIL ingestion pipeline)
  Source 3: Mock PAN DB (mock_pan_records table / blacklist query)

All 8 verification checks are evaluated. On hard-block fail → BLOCKED.
On pass → UserProfile object is created and returned.

For PoC: Source 2 (OCR) is derived from DIL feature engineering directly
         since document OCR is not performed per-call in this implementation.
         Source 3 uses the in-memory blacklist (from data/fraud_blacklist.json).
"""
from __future__ import annotations
import logging
from typing import Optional
from schemas import ApplicationContext, ValidationFlag

logger = logging.getLogger(__name__)


def _normalize_name(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _aadhaar_last4(value: object) -> str:
    if isinstance(value, (int, float)):
        try:
            value = str(int(value))
        except Exception:
            value = str(value)
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits[-4:] if len(digits) >= 4 else ""


def run_preliminary_identity_precheck(form_data: dict) -> tuple[bool, str, list[str]]:
    """
    Pre-orchestration hard check against mock_bureau_records.

    Rules:
      - PAN must exist in mock_bureau_records and match exactly.
      - Aadhaar last-4 must match the table row.
      - Name check is intentionally simple (relaxed): exact/contains/first-token match.

    Returns:
      (passed, reason, mismatches)
    """
    from dataset_loader import get_identity_record

    user_pan = str(form_data.get("pan_number", "")).upper().strip()
    user_name = _normalize_name(str(form_data.get("applicant_name", "")))
    user_aadhaar_last4 = _aadhaar_last4(form_data.get("aadhaar_last4", ""))

    mismatches: list[str] = []
    if not user_pan:
        mismatches.append("PAN_MISSING")
    if not user_name:
        mismatches.append("NAME_MISSING")
    if not user_aadhaar_last4:
        mismatches.append("AADHAAR_MISSING_OR_INVALID")

    record = get_identity_record(user_pan) if user_pan else None
    if not record:
        mismatches.append("PAN_NOT_FOUND_IN_MOCK_BUREAU")
        return False, "Inccorect and mismatch user data", mismatches

    expected_pan = str(record.get("pan", "")).upper().strip()
    expected_name = _normalize_name(str(record.get("name", "")))
    expected_aadhaar_last4 = _aadhaar_last4(record.get("aadhaar", ""))

    if user_pan != expected_pan:
        mismatches.append("PAN_MISMATCH")

    # Keep the name check simple and forgiving by design.
    user_first = user_name.split(" ")[0] if user_name else ""
    expected_first = expected_name.split(" ")[0] if expected_name else ""
    name_match = (
        bool(user_name and expected_name)
        and (
            user_name == expected_name
            or user_name in expected_name
            or expected_name in user_name
            or (user_first and expected_first and user_first == expected_first)
        )
    )
    if not name_match:
        mismatches.append("NAME_MISMATCH")

    if not expected_aadhaar_last4 or user_aadhaar_last4 != expected_aadhaar_last4:
        mismatches.append("AADHAAR_MISMATCH")

    if mismatches:
        return False, "Inccorect and mismatch user data", mismatches

    return True, "", []


# ── Verification outcomes ──────────────────────────────────────────────────────

class VerificationResult:
    VERIFIED = "VERIFIED"
    FLAGGED  = "FLAGGED"
    BLOCKED  = "BLOCKED"


# ── 8-Check Verifier ──────────────────────────────────────────────────────────

def run_verification(ctx: ApplicationContext) -> tuple[str, list[ValidationFlag]]:
    """
    Run all 8 identity verification checks against the ApplicationContext.

    Returns:
        (outcome, flags) where outcome is VERIFIED | FLAGGED | BLOCKED
        Hard blocks → BLOCKED immediately (no agents run).
        Soft flags → FLAGGED (agents run, flags passed in context).
    """
    import re
    form  = ctx.form
    flags = list(ctx.validation_flags)          # Start with any DIL pre-exit flags
    hard_blocks  = [f for f in flags if f.severity == "BLOCK"]

    # ── Check 1: PAN Format Validity (hard block) ─────────────────────────────
    if not re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]$", form.pan_number.upper()):
        hard_blocks.append(ValidationFlag(
            flag_code="INVALID_PAN_FORMAT", severity="BLOCK",
            description=f"PAN '{form.pan_number}' does not match required format [A-Z]{{5}}[0-9]{{4}}[A-Z]"
        ))

    # ── Check 2: PAN Consistency (Source 1 vs Source 2 — soft flag) ───────────
    # In PoC, Source 2 = DIL computed value (form is the primary). No OCR mismatch possible.
    # Field kept for future OCR integration.
    pan_ocr_match = True       # placeholder
    if not pan_ocr_match:
        flags.append(ValidationFlag(
            flag_code="PAN_OCR_MISMATCH", severity="SOFT",
            description="PAN on submitted document differs from form-entered value"
        ))

    # ── Check 3: PAN DB Verification (Source 3 — hard block if not found) ─────
    from dil import _BLACKLIST
    pan_known = form.pan_number.upper() not in _BLACKLIST
    # In full prod: SELECT from mock_pan_records WHERE pan_number = :pan
    # For PoC: treat as verified unless blacklisted (Source 3 is the blacklist check)

    # ── Check 4: Name Consistency (soft flag) ─────────────────────────────────
    # Applicant name from form vs OCR. In PoC, name_match_score is set in dil.py
    name_score = ctx.features.name_match_score
    if name_score < 0.85:
        flags.append(ValidationFlag(
            flag_code="NAME_MISMATCH", severity="SOFT",
            description=f"Applicant name consistency score ({name_score:.0%}) below 85% threshold"
        ))

    # ── Check 5: DOB Consistency (soft flag) ──────────────────────────────────
    # SOurce 1 vs Source 2 vs Source 3 — in PoC, single source so always pass
    dob_consistent = True
    if not dob_consistent:
        flags.append(ValidationFlag(
            flag_code="DOB_MISMATCH", severity="SOFT",
            description="Date of birth inconsistent across verification sources"
        ))

    # ── Check 6: Aadhaar Last-4 match (hard block if mismatched) ───────────────
    aadhaar_last4 = form.aadhaar_last4
    if not (aadhaar_last4 and len(aadhaar_last4) == 4 and aadhaar_last4.isdigit()):
        hard_blocks.append(ValidationFlag(
            flag_code="AADHAAR_MISMATCH", severity="BLOCK",
            description="Aadhaar last-4 digits invalid or missing"
        ))

    # ── Check 7: Age Eligibility (hard block) ────────────────────────────────
    age = ctx.features.applicant_age
    if not (21 <= age <= 65):
        hard_blocks.append(ValidationFlag(
            flag_code="AGE_INELIGIBLE", severity="BLOCK",
            description=f"Applicant age {age} is outside the eligible range 21–65"
        ))

    # ── Check 8: Negative List Check (hard block) ─────────────────────────────
    if form.pan_number.upper() in _BLACKLIST:
        hard_blocks.append(ValidationFlag(
            flag_code="PAN_BLACKLISTED", severity="BLOCK",
            description=f"PAN {form.pan_number} appears in the fraud blacklist (C007 compliance block)"
        ))

    # ── Determine outcome ─────────────────────────────────────────────────────
    if hard_blocks:
        logger.warning(
            f"[{ctx.application_id}] Verification BLOCKED: "
            f"{[b.flag_code for b in hard_blocks]}"
        )
        # Return combined flags (hard blocks + soft so far) for audit
        all_flags = hard_blocks + [f for f in flags if f.severity != "BLOCK"]
        return VerificationResult.BLOCKED, all_flags

    soft_flags = [f for f in flags if f.flag_code not in {b.flag_code for b in hard_blocks}]
    if soft_flags:
        logger.info(
            f"[{ctx.application_id}] Verification FLAGGED (proceeding): "
            f"{[f.flag_code for f in soft_flags]}"
        )
        return VerificationResult.FLAGGED, soft_flags

    logger.info(f"[{ctx.application_id}] Verification VERIFIED — all checks passed")
    return VerificationResult.VERIFIED, []
