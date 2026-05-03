"""LLM-based structured data extraction from OCR text."""
from __future__ import annotations
import os
import json
import logging

logger = logging.getLogger(__name__)


def extract_financial_data(raw_text: str, doc_type: str) -> dict:
    """
    Send OCR-extracted text to Groq LLM for structured JSON extraction.

    Args:
        raw_text: Raw OCR text from the document.
        doc_type: One of 'bank_statement', 'salary_slip', 'itr'.

    Returns:
        Parsed dict with structured fields, or {'error': ...} on failure.
    """
    from groq import Groq

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return {"available": False, "reason": "GROQ_API_KEY not configured"}

    prompts = {
        "bank_statement": (
            "Extract the following fields from this bank statement text and return ONLY valid JSON:\n"
            "- monthly_credits (list of credit amounts)\n"
            "- monthly_debits (list of debit amounts)\n"
            "- avg_monthly_balance (number)\n"
            "- min_eod_balance (number)\n"
            "- emi_bounce_count (integer)\n"
            "- salary_credits (list of regular monthly salary amounts)\n"
            "- salary_regularity (float 0-1 score, 1 = perfectly regular)"
        ),
        "salary_slip": (
            "Extract the following fields from this salary slip and return ONLY valid JSON:\n"
            "- gross_salary (number)\n"
            "- basic_pay (number)\n"
            "- deductions (number)\n"
            "- net_pay (number)\n"
            "- employer_name (string)"
        ),
        "itr": (
            "Extract the following fields from this Income Tax Return document and return ONLY valid JSON:\n"
            "- total_income (number)\n"
            "- tax_paid (number)\n"
            "- assessment_year (string, e.g. '2023-24')\n"
            "- income_from_salary (number)\n"
            "- income_from_business (number)"
        ),
    }

    system_prompt = prompts.get(doc_type, prompts["bank_statement"])
    model = os.environ.get("GROQ_MODEL_NARRATIVE", "llama-3.1-8b-instant")
    # Strip groq/ prefix — Groq SDK uses bare model names
    if model.startswith("groq/"):
        model = model[5:]

    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": raw_text[:4000]},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        logger.error("LLM extraction failed for doc_type=%s: %s", doc_type, e)
        return {"available": False, "reason": str(e)}
