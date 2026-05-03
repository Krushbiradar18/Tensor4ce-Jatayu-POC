"""
document_extractor.py — Extract name, Aadhaar number, and PAN number from PDFs.
================================================================================
Uses PaddleOCR for text recognition and pymupdf (fitz) for PDF-to-image conversion.

Public API:
    extract_from_aadhaar_pdf(pdf_path) -> {"name": ..., "aadhaar_number": ..., "raw_lines": [...]}
    extract_from_pan_pdf(pdf_path)     -> {"name": ..., "pan_number": ...,     "raw_lines": [...]}
"""
from __future__ import annotations

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Lazy-init OCR (avoids slow import at startup) ────────────────────────────
_ocr = None


import os
def _get_ocr():
    global _ocr
    if _ocr is None:
        from paddleocr import PaddleOCR
        # Control PaddleOCR's own internal logging level
        show_log = os.environ.get("LOG_LEVEL", "DEBUG").upper() == "DEBUG"
        _ocr = PaddleOCR(lang="en", use_angle_cls=True)
    return _ocr


# ── PDF → numpy image list ───────────────────────────────────────────────────

def _pdf_to_images(pdf_path: str) -> list:
    """Convert each PDF page to a numpy RGB array at 2× zoom for better OCR."""
    import fitz  # pymupdf
    import numpy as np

    doc = fitz.open(pdf_path)
    images = []
    for page in doc:
        mat = fitz.Matrix(1.5, 1.5)
        pix = page.get_pixmap(matrix=mat)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
            pix.height, pix.width, pix.n
        )
        if pix.n == 4:  # RGBA → RGB
            img = img[:, :, :3]
        images.append(img)
    doc.close()
    return images


def _extract_text_lines(pdf_path: str) -> list[str]:
    """Run PaddleOCR on all pages of a PDF; return a flat ordered list of text lines."""
    ocr = _get_ocr()
    images = _pdf_to_images(pdf_path)
    lines: list[str] = []
    logger.info("Running OCR on %d pages...", len(images))
    for i, img in enumerate(images):
        logger.debug("Processing page %d...", i + 1)
        result = ocr.ocr(img)  # cls=True moved to constructor
        if not result:
            logger.debug("No text found on page %d.", i + 1)
            continue
        for item in result:
            # PaddleOCR v3: item is a dict with 'rec_texts'
            if isinstance(item, dict) and "rec_texts" in item:
                for text in item["rec_texts"]:
                    t = (text or "").strip()
                    if t:
                        lines.append(t)
            # PaddleOCR v2 fallback: item is a list of [box, (text, conf)]
            elif isinstance(item, list):
                for box_data in item:
                    try:
                        t = box_data[1][0].strip()
                        if t:
                            lines.append(t)
                    except (IndexError, TypeError):
                        pass
    return lines


# ── Regex patterns ────────────────────────────────────────────────────────────

# PAN: 5 uppercase letters, 4 digits, 1 uppercase letter
_PAN_RE = re.compile(r'\b([A-Z]{5}[0-9]{4}[A-Z])\b')

# Aadhaar: 12-digit number, optionally space- or dash-separated in 4-4-4 groups
# First digit must be 2–9 (standard Aadhaar range)
_AADHAAR_RE = re.compile(r'\b([2-9][0-9]{3}[\s\-]?[0-9]{4}[\s\-]?[0-9]{4})\b')

_SKIP_NAME_WORDS = {
    "government", "india", "of", "aadhaar", "adhaar", "unique",
    "identification", "authority", "uid", "dob", "date", "birth",
    "male", "female", "address", "vid", "enrolment", "enrollment",
    "income", "tax", "department", "permanent", "account", "number",
    "signature", "sign",
}


# ── Field extractors ─────────────────────────────────────────────────────────

def _find_pan(lines: list[str]) -> Optional[str]:
    for line in lines:
        m = _PAN_RE.search(line.upper())
        if m:
            return m.group(1)
    return None


def _find_aadhaar(lines: list[str]) -> Optional[str]:
    for line in lines:
        m = _AADHAAR_RE.search(line)
        if m:
            digits = re.sub(r'[\s\-]', '', m.group(1))
            if len(digits) == 12:
                return digits
    return None


def _find_name_after_label(lines: list[str], label_pattern: str) -> Optional[str]:
    """
    Generic helper: look for a line matching label_pattern, then return
    the next non-empty line that looks like a person's name.
    """
    for i, line in enumerate(lines):
        if re.search(label_pattern, line, re.IGNORECASE):
            for j in range(i + 1, min(i + 5, len(lines))):
                candidate = lines[j].strip()
                if not candidate:
                    continue
                # Must be letters + spaces + dots only, at least 2 chars
                if not re.match(r'^[A-Za-z][A-Za-z\s\.]{1,50}$', candidate):
                    continue
                words = candidate.lower().split()
                if any(w in _SKIP_NAME_WORDS for w in words):
                    continue
                return candidate.title()
    return None


def _find_name_fallback(lines: list[str]) -> Optional[str]:
    """
    Heuristic fallback: the first multi-word all-letter line that doesn't
    look like a header or keyword.
    """
    for line in lines:
        stripped = line.strip()
        if not re.match(r'^[A-Za-z][A-Za-z\s\.]{3,50}$', stripped):
            continue
        words = stripped.lower().split()
        if len(words) < 2:
            continue
        if any(w in _SKIP_NAME_WORDS for w in words):
            continue
        return stripped.title()
    return None


# ── Public API ────────────────────────────────────────────────────────────────

def extract_from_aadhaar_pdf(pdf_path: str) -> dict:
    """
    Extract name and Aadhaar number from an Aadhaar PDF.

    Returns:
        {
            "name": str | None,
            "aadhaar_number": str | None,   # 12-digit string, no spaces
            "raw_lines": list[str]
        }
    """
    lines = _extract_text_lines(pdf_path)
    logger.debug("Aadhaar OCR lines: %s", lines)

    name = _find_name_after_label(lines, r'\bname\b')
    if name is None:
        name = _find_name_fallback(lines)

    result = {
        "name": name,
        "aadhaar_number": _find_aadhaar(lines),
        "raw_lines": lines,
    }
    logger.info("Aadhaar extraction complete: %s", {k: v for k, v in result.items() if k != 'raw_lines'})
    return result


def extract_from_pan_pdf(pdf_path: str) -> dict:
    """
    Extract name and PAN number from a PAN card PDF.

    Returns:
        {
            "name": str | None,
            "pan_number": str | None,   # e.g. "ABCDE1234F"
            "raw_lines": list[str]
        }
    """
    lines = _extract_text_lines(pdf_path)
    logger.debug("PAN OCR lines: %s", lines)

    # On PAN cards "Name" label precedes the cardholder name;
    # "Father's Name" or "Father Name" precedes the father's name — skip those.
    name = _find_name_after_label(
        lines,
        r'^name$|^name\s*:',  # exact "Name" or "Name:" line
    )
    if name is None:
        # Broader search but exclude father/mother labels
        for i, line in enumerate(lines):
            if re.search(r'\bname\b', line, re.IGNORECASE) and not re.search(
                r"father|mother|husband", line, re.IGNORECASE
            ):
                for j in range(i + 1, min(i + 5, len(lines))):
                    candidate = lines[j].strip()
                    if candidate and re.match(r'^[A-Za-z][A-Za-z\s\.]{1,50}$', candidate):
                        words = candidate.lower().split()
                        if not any(w in _SKIP_NAME_WORDS for w in words):
                            name = candidate.title()
                            break
                if name:
                    break

    if name is None:
        name = _find_name_fallback(lines)

    result = {
        "name": name,
        "pan_number": _find_pan(lines),
        "raw_lines": lines,
    }
    logger.info("PAN extraction complete: %s", {k: v for k, v in result.items() if k != 'raw_lines'})
    return result


# ── Vision-based extraction (Groq LLM) for image files ───────────────────────

def extract_from_image(image_path: str, doc_type: str = "aadhaar") -> dict:
    """
    Extract fields from a JPG/PNG identity document using Groq's vision API.

    Args:
        image_path: Path to the image file (jpg, jpeg, png).
        doc_type:   "aadhaar" or "pan"

    Returns:
        Same shape as extract_from_aadhaar_pdf / extract_from_pan_pdf.
    """
    import os, json, base64
    from pathlib import Path as _Path
    from groq import Groq

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        logger.warning("GROQ_API_KEY not set — skipping vision extraction")
        return {"name": None, "aadhaar_number": None, "pan_number": None, "raw_lines": []}

    suffix = _Path(image_path).suffix.lower()
    mime = "image/jpeg" if suffix in (".jpg", ".jpeg") else "image/png"

    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")

    if doc_type == "aadhaar":
        prompt = (
            "This is an Aadhaar card image. Extract and return ONLY valid JSON with keys:\n"
            '{"name": "<full name in English>", "aadhaar_number": "<12 digits, no spaces>"}\n'
            "If a field is not visible, use null."
        )
    else:
        prompt = (
            "This is a PAN card image. Extract and return ONLY valid JSON with keys:\n"
            '{"name": "<full name>", "pan_number": "<10-char PAN e.g. ABCDE1234F>"}\n'
            "If a field is not visible, use null."
        )

    try:
        client = Groq(api_key=api_key)
        model = os.environ.get("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
        response = client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
                    {"type": "text", "text": prompt},
                ],
            }],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        data = json.loads(response.choices[0].message.content)
        logger.info("Vision extraction (%s): %s", doc_type, data)

        if doc_type == "aadhaar":
            # Normalise: strip spaces from aadhaar number
            aadhaar = data.get("aadhaar_number") or ""
            aadhaar = re.sub(r"[\s\-]", "", str(aadhaar))
            return {"name": data.get("name"), "aadhaar_number": aadhaar or None, "raw_lines": []}
        else:
            pan = (data.get("pan_number") or "").upper().replace(" ", "")
            # Validate PAN format
            if not _PAN_RE.match(pan):
                pan = None
            return {"name": data.get("name"), "pan_number": pan, "raw_lines": []}

    except Exception as e:
        logger.error("Vision extraction failed for %s: %s", doc_type, e)
        return {"name": None, "aadhaar_number": None, "pan_number": None, "raw_lines": []}


# ── Vision-based financial extraction for bank statement / salary slip / ITR ──

def extract_financial_from_image(image_path: str, doc_type: str) -> dict:
    """
    Extract structured financial fields from an image using Groq vision.

    Args:
        image_path: Path to image file (jpg, jpeg, png).
        doc_type:   'bank_statement' | 'salary_slip' | 'itr'

    Returns:
        Structured dict matching the same schema as services/llm_extractor.
    """
    import os, json, base64
    from pathlib import Path as _Path
    from groq import Groq

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        logger.warning("GROQ_API_KEY not set — skipping financial vision extraction")
        return {"available": False, "reason": "GROQ_API_KEY not set"}

    suffix = _Path(image_path).suffix.lower()
    mime = "image/jpeg" if suffix in (".jpg", ".jpeg") else "image/png"

    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")

    prompts = {
        "bank_statement": (
            "This is a bank statement image. Extract and return ONLY valid JSON with these keys:\n"
            '{"avg_monthly_credit": <number>, "avg_monthly_balance": <number>, '
            '"min_eod_balance": <number>, "emi_bounce_count": <integer>, '
            '"salary_regularity": <float 0-1>, "total_credits": <number>, '
            '"total_debits": <number>, "account_holder": <string or null>}\n'
            "Use null for any field not visible."
        ),
        "salary_slip": (
            "This is a salary slip image. Extract and return ONLY valid JSON with these keys:\n"
            '{"gross_salary": <number>, "basic_pay": <number>, "deductions": <number>, '
            '"net_pay": <number>, "employer_name": <string or null>}\n'
            "Use null for any field not visible."
        ),
        "itr": (
            "This is an Income Tax Return (ITR) document image. Extract and return ONLY valid JSON with these keys:\n"
            '{"total_income": <number>, "income_from_salary": <number>, '
            '"tax_paid": <number>, "assessment_year": <string e.g. "2024-25">, '
            '"employer_name": <string or null>}\n'
            "Use null for any field not visible."
        ),
    }

    prompt = prompts.get(doc_type, prompts["bank_statement"])

    try:
        client = Groq(api_key=api_key)
        model = os.environ.get("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
        response = client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
                    {"type": "text", "text": prompt},
                ],
            }],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        data = json.loads(response.choices[0].message.content)
        logger.info("Financial vision extraction (%s): %s", doc_type, data)
        return {"available": True, **data}
    except Exception as e:
        logger.error("Financial vision extraction failed for %s: %s", doc_type, e)
        return {"available": False, "reason": str(e)}
