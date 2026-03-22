"""
LLM Explanation Service - Generates human-readable credit risk explanations
using the Google Gemini API.
"""

import json
import os
import re
import urllib.request
import urllib.error
from typing import Dict, Any, List
from dotenv import load_dotenv

load_dotenv()

_DANGLING_END_RE = re.compile(r"\b(with|as|and|or|to|for|of|in|on|at|from|by|that|which|because|while|if)$", re.IGNORECASE)


def _build_structured_fallback_from_prompt(prompt: str) -> str:
    """Generate a complete officer-readable explanation when LLM output is incomplete."""
    def _rx(pattern: str, default: str = "N/A") -> str:
        m = re.search(pattern, prompt)
        return m.group(1).strip() if m else default

    risk_score = _rx(r"Risk Score:\s*([0-9]+(?:\.[0-9]+)?/100|[0-9]+(?:\.[0-9]+)?)", "N/A")
    risk_category = _rx(r"Risk Category:\s*([^\n]+)", "Unknown")
    cibil = _rx(r"CIBIL SCORE:\s*([^\n]+)", "N/A")
    income = _rx(r"MONTHLY INCOME:\s*([^\n]+)", "N/A")
    if "/100" not in risk_score and risk_score != "N/A":
        risk_score = f"{risk_score}/100"

    return (
        f"1. The applicant is assessed as {risk_category} with a model risk score of {risk_score} and CIBIL {cibil}.\n"
        "2. SHAP risk drivers indicate elevated default pressure, while positive factors provide partial offset.\n"
        f"3. Affordability should be reviewed against monthly income of {income} and proposed EMI obligations.\n"
        "4. Recommendation should proceed with standard policy and documentation checks."
    )


def _is_incomplete_explanation(text: str) -> bool:
    clean = (text or "").strip()
    if not clean:
        return True
    numbered_lines = [ln for ln in clean.splitlines() if re.match(r"^\d+\.\s+", ln.strip())]
    if numbered_lines and len(numbered_lines) < 2:
        return True
    if clean.endswith(":"):
        return True
    if _DANGLING_END_RE.search(clean):
        return True
    return False


def _get_api_key() -> str:
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""


def _get_model() -> str:
    return os.environ.get("GEMINI_MODEL", "gemini-2.0-flash-exp")


def _llm_disabled() -> bool:
    return os.environ.get("LLM_USAGE_MODE", "FULL").upper() == "FALLBACK"


def _classify_llm_error(error: str) -> str:
    lowered = error.lower()
    if "429" in lowered or "rate limit" in lowered or "quota" in lowered or "resource exhausted" in lowered:
        return "rate_limited"
    return "error"


def _vertex_stream_url(model_name: str, api_key: str) -> str:
    """Build Vertex AI publisher-model streaming endpoint URL."""
    return (
        "https://aiplatform.googleapis.com/v1/"
        f"publishers/google/models/{model_name}:streamGenerateContent?key={api_key}"
    )


def _extract_text_from_vertex_stream(raw_text: str) -> str:
    """Extract model text from Vertex streamGenerateContent response payload."""
    text = (raw_text or "").strip()
    if not text:
        return ""

    def _collect_from_obj(obj: dict) -> list[str]:
        chunks = []
        candidates = obj.get("candidates", [])
        for candidate in candidates:
            parts = ((candidate.get("content") or {}).get("parts") or [])
            for part in parts:
                part_text = part.get("text")
                if part_text:
                    chunks.append(part_text)
        return chunks

    # Some Vertex responses return a JSON array of chunk objects.
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return "\n".join(_collect_from_obj(parsed)).strip()
        if isinstance(parsed, list):
            chunk_texts = []
            for item in parsed:
                if isinstance(item, dict):
                    chunk_texts.extend(_collect_from_obj(item))
            return "\n".join(chunk_texts).strip()
    except json.JSONDecodeError:
        pass

    # SSE-like fallback: lines may be prefixed with "data: ..." JSON chunks.
    chunk_texts = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("data:"):
            payload = line[5:].strip()
            if payload == "[DONE]":
                continue
            try:
                obj = json.loads(payload)
                if isinstance(obj, dict):
                    chunk_texts.extend(_collect_from_obj(obj))
            except json.JSONDecodeError:
                continue

    return "\n".join(chunk_texts).strip()


def build_explanation_prompt(
    applicant_name: str,
    loan_amount: float,
    loan_type: str,
    risk_score: float,
    risk_category: str,
    approved_flag: str,
    credit_score: int,
    income: float,
    risk_factors: List[Dict],
    positive_factors: List[Dict],
    class_probabilities: Dict[str, float],
) -> str:

    risk_factor_text = "\n".join(
        f"  - {r['description']}: contribution score {r['contribution']:.3f}"
        for r in risk_factors[:5]
    )
    positive_factor_text = "\n".join(
        f"  - {p['description']}: contribution score {p['contribution']:.3f}"
        for p in positive_factors[:5]
    )

    return f"""You are a senior credit risk analyst at an Indian bank. Write a clear assessment for a loan officer.

APPLICANT: {applicant_name}
LOAN REQUEST: ₹{loan_amount:,.0f} ({loan_type})
CIBIL SCORE: {credit_score}
MONTHLY INCOME: ₹{income:,.0f}

ML RISK ASSESSMENT:
- Risk Score: {risk_score:.1f}/100 (higher = riskier)
- Risk Category: {risk_category}
- Model Confidence: {max(class_probabilities.values()):.1f}%

SHAP-DERIVED RISK FACTORS (features that INCREASE default risk):
{risk_factor_text}

SHAP-DERIVED POSITIVE FACTORS (features that DECREASE default risk):
{positive_factor_text}

Output 4 to 6 numbered points.
Point 1: overall verdict with risk score + CIBIL.
Point 2: top 2 risk drivers from SHAP.
Point 3: top positive driver(s) that offset risk.
Point 4: affordability snapshot (income, EMI, FOIR if available).
Point 5+: final recommendation and any caution.

Format strictly as:
1. <sentence>
2. <sentence>
3. <sentence>
...

Rules:
- Keep each point concise (1 to 2 short sentences), no sub-bullets.
- Use Indian financial context (₹, CIBIL, etc).
- Do NOT include any headers, preamble, or closing remarks — output the numbered list only.
- Total response must stay under 180 words."""


def get_llm_explanation_details(prompt: str) -> Dict[str, str]:
    """Call Google Gemini API and return text plus execution metadata."""
    if _llm_disabled():
        return {
            "text": "LLM explanation disabled by configuration (LLM_USAGE_MODE=FALLBACK). "
                    "Switch to LLM_USAGE_MODE=FULL to enable Gemini explanations.",
            "llm_status": "disabled",
            "llm_provider_error": "LLM_USAGE_MODE=FALLBACK",
        }

    api_key = _get_api_key()
    model = _get_model()

    if not api_key:
        return {
            "text": _fallback_explanation(prompt),
            "llm_status": "no_api_key",
            "llm_provider_error": "GEMINI_API_KEY/GOOGLE_API_KEY not set",
        }

    payload = json.dumps({
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "maxOutputTokens": 300
        }
    }).encode("utf-8")

    url = _vertex_stream_url(model, api_key)

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
            text = _extract_text_from_vertex_stream(raw)
            if not text:
                raise ValueError("Empty response from Vertex streamGenerateContent")
            if _is_incomplete_explanation(text):
                return {
                    "text": _build_structured_fallback_from_prompt(prompt),
                    "llm_status": "low_quality_fallback",
                    "llm_provider_error": "Model response was incomplete or truncated",
                }
            return {
                "text": text,
                "llm_status": "success",
                "llm_provider_error": "",
            }
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="ignore")
        error = f"HTTP {e.code}: {error_body[:200]}"
        return {
            "text": _fallback_explanation_from_context(prompt, error),
            "llm_status": _classify_llm_error(error),
            "llm_provider_error": error,
        }
    except Exception as e:
        error = str(e)
        return {
            "text": _fallback_explanation_from_context(prompt, error),
            "llm_status": _classify_llm_error(error),
            "llm_provider_error": error,
        }


def get_llm_explanation(prompt: str) -> str:
    """Backward-compatible wrapper that returns only the text."""
    return get_llm_explanation_details(prompt)["text"]


def _fallback_explanation(prompt: str) -> str:
    """Fallback when no API key is set - generates rule-based explanation."""
    return _build_structured_fallback_from_prompt(prompt)


def _fallback_explanation_from_context(prompt: str, error: str) -> str:
    _ = error
    return _build_structured_fallback_from_prompt(prompt)


def generate_recommendation(risk_category: str, risk_score: float) -> str:
    """Generate a rule-based recommendation based on risk category."""
    if risk_category == "Low Risk":
        return "APPROVE - Strong credit profile. Proceed with standard documentation."
    elif risk_category == "Medium-Low Risk":
        return "APPROVE WITH REVIEW - Good profile with minor concerns. Verify income documents."
    elif risk_category == "Medium-High Risk":
        return "CONDITIONAL APPROVAL - Elevated risk. Consider co-applicant or reduced loan amount."
    else:
        return "DECLINE - High default risk. Recommend reapplication after 12 months of improved credit behavior."
