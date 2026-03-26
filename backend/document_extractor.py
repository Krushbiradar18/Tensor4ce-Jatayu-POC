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


def _get_ocr():
    global _ocr
    if _ocr is None:
        from paddleocr import PaddleOCR
        _ocr = PaddleOCR(lang="en")
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
    for img in images:
        result = ocr.predict(img)
        if not result:
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

    return {
        "name": name,
        "aadhaar_number": _find_aadhaar(lines),
        "raw_lines": lines,
    }


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

    return {
        "name": name,
        "pan_number": _find_pan(lines),
        "raw_lines": lines,
    }
