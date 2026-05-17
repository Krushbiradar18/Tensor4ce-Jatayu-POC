"""
data_masking.py — simple PII redaction utilities for quick guardrails
"""
from __future__ import annotations

import re
from typing import Any

# Basic regexes
_RE_EMAIL = re.compile(r"([\w.+-]+)@([\w.-]+)")
_RE_DIGITS = re.compile(r"\d+")


def mask_email(email: str) -> str:
    m = _RE_EMAIL.match(email)
    if not m:
        return email
    local, domain = m.group(1), m.group(2)
    if len(local) <= 2:
        masked_local = local[0] + "*"
    else:
        masked_local = local[0] + "*" * (len(local) - 2) + local[-1]
    return f"{masked_local}@{domain}"


def mask_pan(pan: str) -> str:
    # Keep last 4 digits, mask the rest
    digits = re.sub(r"\D", "", pan)
    if len(digits) < 6:
        return pan
    return "*" * (len(digits) - 4) + digits[-4:]


def mask_ssn(ssn: str) -> str:
    digits = re.sub(r"\D", "", ssn)
    if len(digits) < 4:
        return ssn
    return "*" * (len(digits) - 4) + digits[-4:]


def _redact_string(s: str) -> str:
    # Redact emails
    s = _RE_EMAIL.sub(lambda m: mask_email(m.group(0)), s)
    # Redact long digit sequences (likely PAN / card numbers)
    def _mask_digits(match: re.Match) -> str:
        d = match.group(0)
        if len(d) >= 12:
            return mask_pan(d)
        if len(d) == 9:
            return mask_ssn(d)
        return d

    s = _RE_DIGITS.sub(_mask_digits, s)
    return s


def redact_pii(value: Any) -> Any:
    """Recursively redact PII from simple Python structures.

    - strings: mask emails and long digit sequences
    - dict/list/tuple: recurse
    - others: returned unchanged
    """
    if value is None:
        return None
    if isinstance(value, str):
        return _redact_string(value)
    if isinstance(value, dict):
        return {k: redact_pii(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_pii(v) for v in value]
    if isinstance(value, tuple):
        return tuple(redact_pii(v) for v in value)
    return value
