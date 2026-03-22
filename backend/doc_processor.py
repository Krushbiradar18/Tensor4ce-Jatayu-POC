"""
doc_processor.py — Stage 1 & 2: Document Ingestion + Data Extraction

Stage 1: OCR pipeline per document type
   - pdfplumber structured text / table extraction first
   - pdf2image + pytesseract fallback for scanned PDFs
   - Aadhaar gets greyscale + binary threshold preprocessing

Stage 2: Regex + Gemini hybrid parsing
   - PAN card  : regex for PAN/DOB/name
   - Aadhaar   : regex for number/pincode + Gemini for address
   - Bank stmt : pdfplumber table rows → derived cash-flow metrics
   - Salary/F16: Gemini 2.0 Flash structured JSON extraction
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Optional heavy imports (gracefully degrade) ───────────────────────────────
try:
    import pdfplumber          # type: ignore
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False
    logger.warning("pdfplumber not installed — PDF text extraction disabled")

try:
    from pdf2image import convert_from_bytes  # type: ignore
    HAS_PDF2IMAGE = True
except ImportError:
    HAS_PDF2IMAGE = False
    logger.warning("pdf2image not installed — OCR fallback disabled")

try:
    import pytesseract          # type: ignore
    from PIL import Image       # type: ignore
    HAS_OCR = True
except ImportError:
    HAS_OCR = False
    logger.warning("pytesseract/Pillow not installed — OCR disabled")

try:
    import cv2                  # type: ignore
    import numpy as np          # type: ignore
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False
    logger.warning("opencv not installed — image pre-processing disabled")

try:
    from deskew import determine_skew  # type: ignore
    from scipy.ndimage import rotate   # type: ignore
    HAS_DESKEW = True
except ImportError:
    HAS_DESKEW = False


# ── Supported document types ──────────────────────────────────────────────────
DOC_TYPES = {
    "aadhaar":        "AADHAAR",
    "pan":            "PAN",
    "bank_statement": "BANK_STATEMENT",
    "salary_slip":    "SALARY_SLIP",
    "form16":         "FORM_16",
}


# ──────────────────────────────────────────────────────────────────────────────
# Stage 1 helpers — text / table extraction
# ──────────────────────────────────────────────────────────────────────────────

def _extract_with_pdfplumber(file_bytes: bytes) -> tuple[str, list]:
    """Returns (raw_text, tables) extracted by pdfplumber."""
    if not HAS_PDFPLUMBER:
        return "", []
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            texts, tables = [], []
            for page in pdf.pages:
                # Use tighter tolerance for better character grouping
                t = page.extract_text(x_tolerance=2, y_tolerance=3) or ""
                texts.append(t)
                for tbl in (page.extract_tables() or []):
                    if tbl:
                        tables.append(tbl)
            return "\n".join(texts), tables
    except Exception as e:
        logger.warning(f"pdfplumber extraction failed: {e}")
        return "", []


def _preprocess_image(pil_img, doc_type: str = ""):
    """Denoise + sharpen + threshold for all document types. Aadhaar gets extra binary threshold."""
    if not HAS_CV2:
        return pil_img
    img_arr = np.array(pil_img.convert("RGB"))
    grey = cv2.cvtColor(img_arr, cv2.COLOR_RGB2GRAY)
    # Upscale if image is small (improves tesseract accuracy significantly)
    h, w = grey.shape
    if h < 1200 or w < 1200:
        scale = max(1200 / h, 1200 / w, 1.5)
        grey = cv2.resize(grey, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)
    # Denoise
    grey = cv2.fastNlMeansDenoising(grey, h=10)
    # Sharpen
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
    grey = cv2.filter2D(grey, -1, kernel)
    if doc_type in ("AADHAAR", "PAN"):
        # Binary threshold — better for card-style docs
        _, binary = cv2.threshold(grey, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    else:
        # Adaptive threshold — better for printed docs / bank statements
        binary = cv2.adaptiveThreshold(grey, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                       cv2.THRESH_BINARY, 31, 10)
    if HAS_DESKEW:
        try:
            angle = determine_skew(binary)
            if abs(angle or 0) > 0.5:
                from scipy.ndimage import rotate as sci_rotate
                binary = sci_rotate(binary, angle, reshape=False, cval=255).astype(np.uint8)
        except Exception:
            pass
    return Image.fromarray(binary)


# keep old name as alias for any code that references it
_preprocess_image_for_aadhaar = _preprocess_image


# Tesseract config: OEM 3 (LSTM), PSM 6 (assume uniform block of text)
_TSS_CFG_DEFAULT = "--oem 3 --psm 6"
_TSS_CFG_CARD    = "--oem 3 --psm 4"   # single column — better for ID cards


def _tess_config(doc_type: str) -> str:
    return _TSS_CFG_CARD if doc_type in ("AADHAAR", "PAN") else _TSS_CFG_DEFAULT


def _ocr_from_pdf(file_bytes: bytes, doc_type: str) -> tuple[str, str]:
    """Convert PDF pages to images, run OCR. Returns (text, method)."""
    if not (HAS_PDF2IMAGE and HAS_OCR):
        return "", "unavailable"
    try:
        images = convert_from_bytes(file_bytes, dpi=400)
        parts = []
        for img in images:
            img = _preprocess_image(img, doc_type)
            text = pytesseract.image_to_string(img, lang="eng", config=_tess_config(doc_type))
            parts.append(text)
        return "\n".join(parts), "tesseract_ocr"
    except Exception as e:
        logger.warning(f"PDF OCR failed: {e}")
        return "", "failed"


def _ocr_from_image(file_bytes: bytes, mime_type: str, doc_type: str) -> tuple[str, str]:
    """OCR directly from an uploaded image file."""
    if not HAS_OCR:
        return "", "unavailable"
    try:
        img = Image.open(io.BytesIO(file_bytes))
        img = _preprocess_image(img, doc_type)
        text = pytesseract.image_to_string(img, lang="eng", config=_tess_config(doc_type))
        return text, "tesseract_ocr"
    except Exception as e:
        logger.warning(f"Image OCR failed: {e}")
        return "", "failed"


# ──────────────────────────────────────────────────────────────────────────────
# Stage 1 — Document Ingestion (per type)
# ──────────────────────────────────────────────────────────────────────────────

def ingest_document(file_bytes: bytes, filename: str, doc_type: str) -> dict:
    """
    Stage 1: Ingest one document.
    Returns: {document_type, raw_text, tables, extraction_method}
    """
    doc_type = doc_type.upper()
    ext = Path(filename).suffix.lower()
    is_pdf = ext == ".pdf"
    tables: list = []
    raw_text = ""
    method = "none"

    if is_pdf:
        # Try pdfplumber first (structured PDFs)
        raw_text, tables = _extract_with_pdfplumber(file_bytes)
        if len(raw_text.strip()) >= 50:
            method = "pdfplumber"
        else:
            # Scanned PDF — fall through to OCR
            raw_text, method = _ocr_from_pdf(file_bytes, doc_type)
    else:
        # Image file — direct OCR
        mime = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
        raw_text, method = _ocr_from_image(file_bytes, mime, doc_type)

    logger.info(f"[Stage1] {doc_type} | method={method} | chars={len(raw_text)} | tables={len(tables)}")
    if raw_text:
        logger.debug(f"[Stage1] raw_text preview:\n{raw_text[:500]}")

    return {
        "document_type": doc_type,
        "raw_text": raw_text,
        "tables": tables,
        "extraction_method": method,
        "filename": filename,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Stage 2 — Data Extraction (Parsing)
# ──────────────────────────────────────────────────────────────────────────────

# -- PAN card -----------------------------------------------------------------

_RE_PAN = re.compile(r"\b([A-Z]{5}[0-9]{4}[A-Z])\b")
_RE_DOB_DDMMYYYY = re.compile(r"\b(\d{2}/\d{2}/\d{4})\b")
_RE_DOB_DDMMYY   = re.compile(r"\b(\d{2}/\d{2}/\d{2})\b")


# PAN fields for Gemini
_PAN_GEMINI_FIELDS = [
    "pan_number", "name", "father_name", "date_of_birth",
]


def _extract_pan(ingested: dict) -> dict:
    text = ingested["raw_text"]

    # ── Gemini first-pass ────────────────────────────────────────────────────
    result: dict = {}
    if _gemini_available():
        result = _gemini_extract_json(text, _PAN_GEMINI_FIELDS, "Indian PAN card")

    # ── Regex fallbacks ──────────────────────────────────────────────────────
    pan_match = _RE_PAN.search(text.upper())
    if not result.get("pan_number") and pan_match:
        result["pan_number"] = pan_match.group(1)

    if not result.get("date_of_birth"):
        m = _RE_DOB_DDMMYYYY.search(text)
        if m:
            result["date_of_birth"] = m.group(1)

    if not result.get("name"):
        # Heuristic: look for lines above PAN that are all-caps words (name on PAN card)
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        pan_number = result.get("pan_number", "")
        for i, line in enumerate(lines):
            if pan_number and pan_number in line.upper():
                # Name is usually 1-2 lines above the PAN number line
                for j in range(max(0, i - 3), i):
                    candidate = lines[j].strip()
                    # Name lines are typically all letters + spaces, 3+ chars
                    if re.match(r'^[A-Z][A-Za-z .]{2,}$', candidate) and len(candidate) > 3:
                        result["name"] = candidate
                        break
                break

    result["confidence"] = "high" if result.get("pan_number") else "low"
    return result


# -- Aadhaar card ------------------------------------------------------------

_RE_AADHAAR = re.compile(r"\b(\d{4}[\s\-]\d{4}[\s\-]\d{4})\b")
_RE_PINCODE = re.compile(r"\b(\d{6})\b")
_RE_GENDER  = re.compile(r"\b(MALE|FEMALE|TRANSGENDER)\b", re.IGNORECASE)

STATES_IN = [
    "Andhra Pradesh","Arunachal Pradesh","Assam","Bihar","Chhattisgarh",
    "Goa","Gujarat","Haryana","Himachal Pradesh","Jharkhand","Karnataka",
    "Kerala","Madhya Pradesh","Maharashtra","Manipur","Meghalaya","Mizoram",
    "Nagaland","Odisha","Punjab","Rajasthan","Sikkim","Tamil Nadu","Telangana",
    "Tripura","Uttar Pradesh","Uttarakhand","West Bengal","Delhi",
    "Jammu and Kashmir","Ladakh","Chandigarh","Puducherry",
]


# Aadhaar fields for Gemini
_AADHAAR_GEMINI_FIELDS = [
    "name", "date_of_birth", "gender", "aadhaar_number",
    "address", "pincode", "city", "state", "district",
]


def _extract_aadhaar(ingested: dict) -> dict:
    text = ingested["raw_text"]

    # ── Gemini first-pass with an Aadhaar-specific prompt ───────────────────
    result: dict = {}
    if _gemini_available():
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI  # type: ignore
            from langchain_core.messages import HumanMessage           # type: ignore

            llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0, max_tokens=512)
            prompt = (
                "You are parsing an Indian Aadhaar card OCR text.\n"
                "Extract these fields as a JSON object: "
                "name, date_of_birth, gender, aadhaar_number, address, pincode, city, state, district.\n"
                "IMPORTANT rules:\n"
                "- name: return ONLY the English/Latin-script name (Roman alphabets). "
                "Aadhaar cards often show the name in both English AND a regional script (Hindi/Tamil/etc.) "
                "— ignore the regional-script line entirely and return only the English one.\n"
                "- aadhaar_number: the 12-digit number (can be masked like XXXX XXXX 1234, "
                "return it as-is).\n"
                "- date_of_birth: DD/MM/YYYY format.\n"
                "- gender: MALE, FEMALE, or TRANSGENDER.\n"
                "- Return ONLY valid JSON, no markdown, no explanation.\n"
                "- Use null for missing fields.\n\n"
                f"Aadhaar OCR text:\n{text[:6000]}"
            )
            resp = llm.invoke([HumanMessage(content=prompt)])
            raw = resp.content.strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.M).strip()
            raw = re.sub(r"```\s*$",  "", raw, flags=re.M).strip()
            result = json.loads(raw)
        except Exception as e:
            logger.warning(f"Aadhaar Gemini extraction failed: {e}")
            result = {}

    # ── Mask/derive Aadhaar number ───────────────────────────────────────────
    raw_aadhaar = result.get("aadhaar_number", "")
    if not raw_aadhaar:
        m = _RE_AADHAAR.search(text)
        raw_aadhaar = m.group(1) if m else ""

    digits = re.sub(r"\D", "", str(raw_aadhaar))
    last4  = digits[-4:] if len(digits) >= 4 else None
    result["aadhaar_last4"]  = last4
    result["aadhaar_masked"] = f"XXXX XXXX {last4}" if last4 else None
    result.pop("aadhaar_number", None)   # don't store full number

    # ── Regex fallbacks ──────────────────────────────────────────────────────
    if not result.get("gender"):
        m2 = _RE_GENDER.search(text)
        result["gender"] = m2.group(1).upper() if m2 else None

    if not result.get("pincode"):
        m3 = _RE_PINCODE.search(text)
        result["pincode"] = m3.group(1) if m3 else None

    if not result.get("state"):
        for st in STATES_IN:
            if st.lower() in text.lower():
                result["state"] = st
                break

    if not result.get("address"):
        result["address"] = _regex_extract_address(text)

    result["confidence"] = "high" if last4 else "low"
    return result


def _regex_extract_address(text: str) -> str:
    """Simple regex fallback to extract multi-word address."""
    lines = text.splitlines()
    addr_lines = []
    capture = False
    for line in lines:
        l = line.strip()
        if any(kw in l.upper() for kw in ("ADDRESS", "ADDR", "S/O", "D/O", "W/O", "VILLAGE", "DISTRICT", "DIST")):
            capture = True
        if capture and l:
            addr_lines.append(l)
        if capture and len(addr_lines) >= 5:
            break
    return " ".join(addr_lines) if addr_lines else ""


# -- Bank statement ----------------------------------------------------------

_RE_DEBIT_CREDIT = re.compile(
    r"(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\s+(.+?)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)"
)

_SALARY_KEYWORDS   = re.compile(r"\b(SALARY|SAL|NEFT CR|IMPS CR|SALRY|PAY CREDIT)\b", re.I)
_EMI_KEYWORDS      = re.compile(r"\b(EMI|LOAN|ECS|NACH|HDFC LOAN|SBI LOAN)\b", re.I)
_BOUNCE_KEYWORDS   = re.compile(r"\b(RETURN|DISHONOUR|BOUNCE|INSUFFICIENT|INSFNT)\b", re.I)


def _parse_amount(s: str) -> float:
    try:
        return float(s.replace(",", "").strip())
    except Exception:
        return 0.0


def _extract_bank_statement(ingested: dict) -> dict:
    text  = ingested["raw_text"]
    tables = ingested.get("tables", [])

    transactions = []

    # Prefer table rows from pdfplumber
    for table in tables:
        for row in table:
            if not row or len(row) < 4:
                continue
            row_str = " ".join(str(c) for c in row if c)
            date_m = re.search(r"\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}", row_str)
            desc   = str(row[1] or row[0] or "").strip()
            # find numeric columns — last 3 are typically debit, credit, balance
            nums   = [_parse_amount(str(c)) for c in row if c and re.match(r"^[\d,]+\.?\d*$", str(c).strip())]
            if date_m and len(nums) >= 2:
                transactions.append({
                    "date":    date_m.group(0),
                    "desc":    desc,
                    "debit":   nums[-3] if len(nums) >= 3 else 0.0,
                    "credit":  nums[-2] if len(nums) >= 2 else 0.0,
                    "balance": nums[-1],
                })

    # Fallback — regex scan on raw text
    if not transactions:
        for m in _RE_DEBIT_CREDIT.finditer(text):
            transactions.append({
                "date":    m.group(1),
                "desc":    m.group(2).strip(),
                "debit":   _parse_amount(m.group(3)),
                "credit":  _parse_amount(m.group(4)),
                "balance": _parse_amount(m.group(5)),
            })

    salary_credits  = [t for t in transactions if _SALARY_KEYWORDS.search(t["desc"])]
    emi_debits      = [t for t in transactions if _EMI_KEYWORDS.search(t["desc"])]
    bounce_txns     = [t for t in transactions if _BOUNCE_KEYWORDS.search(t["desc"])]

    credits = [t["credit"] for t in transactions if t["credit"] > 0]
    debits  = [t["debit"]  for t in transactions if t["debit"]  > 0]
    balances= [t["balance"] for t in transactions if t["balance"] > 0]

    return {
        "transaction_count":         len(transactions),
        "salary_credits_count":      len(salary_credits),
        "avg_salary_credit":         round(sum(t["credit"] for t in salary_credits) / max(len(salary_credits), 1), 2),
        "avg_monthly_credit":        round(sum(credits) / max(len(credits), 1), 2),
        "avg_monthly_debit":         round(sum(debits)  / max(len(debits),  1), 2),
        "min_eod_balance":           round(min(balances, default=0), 2),
        "avg_eod_balance":           round(sum(balances) / max(len(balances), 1), 2),
        "emi_debit_count":           len(emi_debits),
        "emi_bounce_count":          len(bounce_txns),
        "sample_transactions":       transactions[:20],
        "confidence":                "high" if transactions else "low",
    }


# -- Salary slip / Form 16 ---------------------------------------------------

_SALARY_FIELDS = [
    "employer_name", "employee_name", "gross_salary", "basic_salary",
    "hra", "hra_exemption", "pf_deduction", "tds_deducted",
    "net_salary", "pay_period", "month", "year",
]

_F16_FIELDS = [
    "employer_name", "employee_name", "gross_salary", "basic_salary",
    "hra_exemption", "standard_deduction", "net_taxable_income",
    "tds_deducted", "assessment_year",
]


def _gemini_available() -> bool:
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))


def _gemini_extract_json(text: str, fields: list[str], doc_label: str) -> dict:
    """Call Gemini to extract structured fields. Sends up to 6000 chars."""
    if not _gemini_available():
        return {}
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI  # type: ignore
        from langchain_core.messages import HumanMessage           # type: ignore

        llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            temperature=0,
            max_tokens=1024,
        )
        field_list = ", ".join(fields)
        prompt = (
            f"You are an expert document data extractor. "
            f"Extract the following fields from this {doc_label} document text.\n"
            f"Fields: {field_list}\n"
            f"Rules:\n"
            f"- Return ONLY a valid JSON object — no markdown, no explanation, no code fences.\n"
            f"- If a field is not found, set its value to null.\n"
            f"- For amounts/numbers, return numeric values only (no currency symbols).\n"
            f"- For dates, use DD/MM/YYYY format.\n"
            f"- Be precise — do not guess or hallucinate values.\n\n"
            f"Document text:\n{text[:6000]}"
        )
        resp = llm.invoke([HumanMessage(content=prompt)])
        raw = resp.content.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.M).strip()
        raw = re.sub(r"```\s*$", "", raw, flags=re.M).strip()
        return json.loads(raw)
    except Exception as e:
        logger.warning(f"Gemini extraction failed for {doc_label}: {e}")
        return {}


def _gemini_extract_address(text: str) -> str:
    if not _gemini_available():
        return ""
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI  # type: ignore
        from langchain_core.messages import HumanMessage           # type: ignore

        llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0, max_tokens=300)
        resp = llm.invoke([HumanMessage(
            content=(
                "Extract the complete residential address from this Aadhaar OCR text. "
                "Return ONLY the address as a single line string. Do not include the name, "
                "Aadhaar number, or any other field. If not found return empty string.\n\n"
                + text[:2000]
            )
        )])
        return resp.content.strip()
    except Exception as e:
        logger.warning(f"Gemini address extraction failed: {e}")
        return ""


def _extract_salary_slip(ingested: dict) -> dict:
    text = ingested["raw_text"]
    result = _gemini_extract_json(text, _SALARY_FIELDS, "salary slip")

    # Regex fallbacks for key numeric fields
    if not result.get("net_salary"):
        m = re.search(r"(?:net|take.?home|net pay)[^\d]*([\d,]+)", text, re.I)
        if m:
            result["net_salary"] = _parse_amount(m.group(1))

    if not result.get("gross_salary"):
        m = re.search(r"(?:gross)[^\d]*([\d,]+)", text, re.I)
        if m:
            result["gross_salary"] = _parse_amount(m.group(1))

    result["confidence"] = "high" if result.get("net_salary") else "low"
    return result


def _extract_form16(ingested: dict) -> dict:
    import datetime
    text = ingested["raw_text"]
    result = _gemini_extract_json(text, _F16_FIELDS, "Form 16 / ITR document")

    # Validate assessment year
    fy = result.get("assessment_year", "")
    current_year = datetime.date.today().year
    if fy:
        yr_m = re.search(r"(\d{4})", str(fy))
        if yr_m:
            doc_year = int(yr_m.group(1))
            if current_year - doc_year > 2:
                result["_warning"] = f"Document may be outdated (assessment year: {fy})"

    result["confidence"] = "high" if result.get("net_taxable_income") else "low"
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Stage 2 — Dispatcher
# ──────────────────────────────────────────────────────────────────────────────

_EXTRACTORS = {
    "PAN":            _extract_pan,
    "AADHAAR":        _extract_aadhaar,
    "BANK_STATEMENT": _extract_bank_statement,
    "SALARY_SLIP":    _extract_salary_slip,
    "FORM_16":        _extract_form16,
}


def extract_document_data(ingested: dict) -> dict:
    """
    Stage 2: Parse extracted text/tables into structured fields.
    Returns: {document_type, extracted_fields, extraction_method, raw_text (truncated)}
    """
    doc_type = ingested.get("document_type", "UNKNOWN")
    extractor = _EXTRACTORS.get(doc_type)

    if extractor:
        try:
            fields = extractor(ingested)
        except Exception as e:
            logger.error(f"Extraction failed for {doc_type}: {e}", exc_info=True)
            fields = {"error": str(e)}
    else:
        fields = {"error": f"No extractor for document type: {doc_type}"}

    return {
        "document_type":       doc_type,
        "filename":            ingested.get("filename", ""),
        "extraction_method":   ingested.get("extraction_method", "unknown"),
        "extracted_fields":    fields,
        "raw_text_preview":    ingested.get("raw_text", "")[:500],
    }


# ──────────────────────────────────────────────────────────────────────────────
# Top-level entry point
# ──────────────────────────────────────────────────────────────────────────────

def process_document(file_bytes: bytes, filename: str, doc_type: str) -> dict:
    """
    Full pipeline: Stage 1 (ingestion/OCR) → Stage 2 (extraction/parsing).
    Returns a complete result dict ready to be persisted / returned via API.
    """
    ingested  = ingest_document(file_bytes, filename, doc_type)
    extracted = extract_document_data(ingested)
    return extracted
