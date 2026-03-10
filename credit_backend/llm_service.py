"""
LLM Explanation Service - Generates human-readable credit risk explanations
using the Google Gemini API.
"""

import json
import os
import urllib.request
import urllib.error
from typing import Dict, Any, List
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = "gemini-2.5-flash"


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

    return f"""You are a senior credit risk analyst at an Indian bank. Based on the ML model's SHAP-derived factor analysis below, write a concise, structured assessment for the loan officer.

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

Output EXACTLY between 5 and 7 numbered points. Each point must be one clear, specific sentence grounded in the SHAP data above. Cover:
• Overall risk verdict (reference the risk score and CIBIL score)
• The 2 most important risk drivers from SHAP and why they matter
• The 2 most important positive signals from SHAP and why they help
• EMI affordability relative to income
• Final recommendation (Approve / Approve with Conditions / Decline) with one-line justification

Format strictly as:
1. <sentence>
2. <sentence>
...

Rules:
- Each point is ONE sentence only, no sub-bullets.
- Use Indian financial context (₹, CIBIL, etc).
- Do NOT include any headers, preamble, or closing remarks — output the numbered list only.
- Total response must stay under 250 words."""


def get_llm_explanation(prompt: str) -> str:
    """Call Google Gemini API to generate explanation."""
    if not GEMINI_API_KEY:
        return _fallback_explanation(prompt)

    payload = json.dumps({
        "contents": [
            {"parts": [{"text": prompt}]}
        ],
        "generationConfig": {
            "maxOutputTokens": 5000
        }
    }).encode("utf-8")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={GEMINI_API_KEY}"

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
            return data["candidates"][0]["content"]["parts"][0]["text"]
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="ignore")
        return _fallback_explanation_from_context(prompt, f"HTTP {e.code}: {error_body[:200]}")
    except Exception as e:
        return _fallback_explanation_from_context(prompt, str(e))


def _fallback_explanation(prompt: str) -> str:
    """Fallback when no API key is set - generates rule-based explanation."""
    return (
        "LLM explanation unavailable (GEMINI_API_KEY not set). "
        "Please set the environment variable to enable AI-powered explanations. "
        "The risk score and factor analysis above provide the quantitative assessment."
    )


def _fallback_explanation_from_context(prompt: str, error: str) -> str:
    return (
        f"Could not reach LLM API ({error}). "
        "The model-based risk score and SHAP factor analysis provide the full assessment. "
        "Please review the top risk factors and positive factors for detailed insights."
    )


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
