"""
llm_config.py — LLM Usage Control for Rate Limiting
=====================================================
Provides a centralized way to control LLM call frequency
to avoid hitting Gemini API rate limits.

Usage:
    from llm_config import should_call_llm, get_llm_or_fallback

    if should_call_llm(decision_type="HIGH"):
        result = call_gemini(prompt)
    else:
        result = fallback_text
"""
import os
import logging

logger = logging.getLogger(__name__)

# LLM Usage Modes
LLM_USAGE_MODES = {
    "FULL": "Call LLM for all narratives",
    "MINIMAL": "Only call LLM for critical cases (REJECT/ESCALATE)",
    "FALLBACK": "Never call LLM, always use fallback"
}


def get_llm_usage_mode() -> str:
    """Get current LLM usage mode from environment."""
    mode = os.environ.get("LLM_USAGE_MODE", "FULL").upper()
    if mode not in LLM_USAGE_MODES:
        logger.warning(f"Invalid LLM_USAGE_MODE '{mode}', defaulting to FULL")
        return "FULL"
    return mode


def should_call_llm(decision_type: str = "NORMAL", risk_band: str = "MEDIUM") -> bool:
    """
    Determine if LLM should be called based on current usage mode.

    Args:
        decision_type: One of APPROVE, CONDITIONAL, ESCALATE, REJECT
        risk_band: One of LOW, MEDIUM, HIGH, VERY_HIGH, CLEAN, SUSPICIOUS, HIGH_RISK

    Returns:
        True if LLM should be called, False if fallback should be used
    """
    mode = get_llm_usage_mode()

    if mode == "FALLBACK":
        return False

    if mode == "FULL":
        return True

    if mode == "MINIMAL":
        # Only call for critical/escalation cases
        critical_decisions = {"REJECT", "ESCALATE"}
        critical_risks = {"HIGH", "VERY_HIGH", "HIGH_RISK", "SUSPICIOUS"}

        return (
            decision_type in critical_decisions or
            risk_band in critical_risks
        )

    return True  # Default to calling LLM


def get_llm_or_fallback(llm_func, fallback: str, **kwargs) -> str:
    """
    Helper to call LLM function or return fallback based on mode.

    Args:
        llm_func: Function that makes the LLM call (e.g., _call_gemini)
        fallback: Fallback text if LLM not called
        **kwargs: Additional args like decision_type, risk_band

    Returns:
        LLM response or fallback text
    """
    decision_type = kwargs.get("decision_type", "NORMAL")
    risk_band = kwargs.get("risk_band", "MEDIUM")

    if should_call_llm(decision_type, risk_band):
        try:
            return llm_func()
        except Exception as e:
            logger.warning(f"LLM call failed, using fallback: {e}")
            return fallback
    else:
        logger.debug(f"Skipping LLM call (mode={get_llm_usage_mode()}), using fallback")
        return fallback


# Stats tracking (optional - for monitoring)
_llm_call_count = 0
_llm_skip_count = 0


def track_llm_call(called: bool):
    """Track LLM call statistics."""
    global _llm_call_count, _llm_skip_count
    if called:
        _llm_call_count += 1
    else:
        _llm_skip_count += 1


def get_llm_stats() -> dict:
    """Get LLM usage statistics."""
    total = _llm_call_count + _llm_skip_count
    return {
        "llm_calls": _llm_call_count,
        "llm_skips": _llm_skip_count,
        "total_requests": total,
        "call_rate": round(_llm_call_count / max(total, 1), 2),
        "mode": get_llm_usage_mode()
    }
