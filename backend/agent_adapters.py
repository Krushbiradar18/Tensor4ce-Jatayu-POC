"""
agent_adapters.py — Transform data between main orchestration and individual agents
===================================================================================
Each adapter function:
1. Takes ApplicationContext from the main DIL system
2. Transforms to the agent's expected input format
3. Calls the agent's LangGraph
4. Transforms output back to the orchestrator's schema
"""
from __future__ import annotations
import importlib.util
import sys
import logging
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logger = logging.getLogger(__name__)

_FRAUD_AGENT_MODULE = None


def _load_fraud_agent_module():
    global _FRAUD_AGENT_MODULE
    if _FRAUD_AGENT_MODULE is not None:
        return _FRAUD_AGENT_MODULE

    fraud_dir = ROOT / "backend" / "agents" / "fraud"
    fraud_file = fraud_dir / "agent.py"
    if str(fraud_dir) not in sys.path:
        sys.path.insert(0, str(fraud_dir))

    # The module name and file path for the fraud specialist
    spec = importlib.util.spec_from_file_location("agents.fraud.agent", fraud_file)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load fraud agent module from {fraud_file}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _FRAUD_AGENT_MODULE = module
    return module


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _normalize_gender(value: Any, fallback: str = "M") -> str:
    text = str(value or "").strip().upper()
    if text in {"M", "MALE"}:
        return "M"
    if text in {"F", "FEMALE"}:
        return "F"
    return fallback


def _normalize_marital_status(value: Any, fallback: str = "Single") -> str:
    text = str(value or "").strip().upper()
    if text in {"MARRIED", "MAR"}:
        return "Married"
    if text in {"SINGLE", "UNMARRIED", "UNMAR"}:
        return "Single"
    return fallback


def _normalize_education(value: Any, fallback: str = "GRADUATE") -> str:
    text = str(value or "").strip().upper()
    allowed = {
        "12TH", "GRADUATE", "OTHERS", "POST-GRADUATE", "PROFESSIONAL", "SSC", "UNDER GRADUATE",
    }
    if text in allowed:
        return text
    if text in {"POST GRADUATE", "POSTGRADUATE"}:
        return "POST-GRADUATE"
    if text in {"UNDERGRADUATE", "UNDER-GRADUATE"}:
        return "UNDER GRADUATE"
    return fallback


def _build_credit_agent_profile(ctx: Any, profile: dict | None) -> dict:
    form = ctx.form
    features = ctx.features

    cibil_score = _safe_int(
        (profile or {}).get("Credit_Score", (profile or {}).get("cibil_score", getattr(features, "cibil_score", 0))),
        650,
    )
    enquiries_6m = _safe_int((profile or {}).get("enq_L6m", getattr(features, "num_hard_enquiries_6m", 0)))
    dpd_30 = _safe_int((profile or {}).get("num_times_30p_dpd", getattr(features, "dpd_30_count", 0)))
    dpd_90 = _safe_int((profile or {}).get("num_times_60p_dpd", getattr(features, "dpd_90_count", 0)))
    total_delinquency = _safe_int((profile or {}).get("num_times_delinquent", dpd_30 + dpd_90))
    active_loans = max(_safe_int(getattr(features, "num_active_loans", 1), 1), 1)
    cc_utilization = _safe_float((profile or {}).get("CC_utilization", getattr(features, "credit_utilization_pct", 0.3)), 0.3)
    pl_utilization = _safe_float((profile or {}).get("PL_utilization", cc_utilization), 0.3)
    income = _safe_float((profile or {}).get("NETMONTHLYINCOME", form.annual_income / 12.0), form.annual_income / 12.0)
    employment_months = max(
        _safe_int((profile or {}).get("Time_With_Curr_Empr", getattr(features, "employment_tenure_years", 1.0) * 12), 12),
        1,
    )
    highest_delinquency = 2 if dpd_90 > 0 else 1 if dpd_30 > 0 else 0
    total_enquiries = max(_safe_int((profile or {}).get("tot_enq", enquiries_6m), enquiries_6m), enquiries_6m)
    enquiry_gap = 24 if enquiries_6m == 0 else max(1, 12 - min(enquiries_6m, 11))
    sub_accounts = max(1 if dpd_30 > 0 else 0, _safe_int((profile or {}).get("num_sub", 0)))
    doubtful_accounts = max(1 if dpd_90 > 0 else 0, _safe_int((profile or {}).get("num_dbt", 0)))

    source_marital = (profile or {}).get("MARITALSTATUS")
    if source_marital is None:
        source_marital = getattr(form, "marital_status", None)

    source_gender = (profile or {}).get("GENDER")
    if source_gender is None:
        source_gender = getattr(form, "gender", "MALE")

    source_education = (profile or {}).get("EDUCATION", "GRADUATE")

    return {
        "name": getattr(form, "applicant_name", None) or (profile or {}).get("name") or "Applicant",
        "pan": form.pan_number.upper().strip(),
        "AGE": _safe_int((profile or {}).get("AGE", getattr(features, "applicant_age", 30)), 30),
        "GENDER": _normalize_gender(source_gender, "M"),
        "MARITALSTATUS": _normalize_marital_status(source_marital, "Single"),
        "EDUCATION": _normalize_education(source_education, "GRADUATE"),
        "NETMONTHLYINCOME": max(income, 1.0),
        "Time_With_Curr_Empr": employment_months,
        "Credit_Score": cibil_score,
        "num_times_delinquent": total_delinquency,
        "recent_level_of_deliq": _safe_int((profile or {}).get("recent_level_of_deliq", highest_delinquency), highest_delinquency),
        "num_deliq_6mts": _safe_int((profile or {}).get("num_deliq_6mts", min(total_delinquency, max(dpd_30, dpd_90))), min(total_delinquency, max(dpd_30, dpd_90))),
        "num_deliq_12mts": _safe_int((profile or {}).get("num_deliq_12mts", total_delinquency), total_delinquency),
        "num_times_30p_dpd": dpd_30,
        "num_times_60p_dpd": dpd_90,
        "num_std": max(_safe_int((profile or {}).get("num_std", active_loans - sub_accounts - doubtful_accounts), active_loans), 0),
        "num_sub": sub_accounts,
        "num_dbt": doubtful_accounts,
        "num_lss": _safe_int((profile or {}).get("num_lss", 0), 0),
        "tot_enq": total_enquiries,
        "enq_L12m": _safe_int((profile or {}).get("enq_L12m", total_enquiries), total_enquiries),
        "enq_L6m": enquiries_6m,
        "time_since_recent_enq": _safe_int((profile or {}).get("time_since_recent_enq", enquiry_gap), enquiry_gap),
        "CC_utilization": cc_utilization,
        "PL_utilization": pl_utilization,
        "max_unsec_exposure_inPct": _safe_float((profile or {}).get("max_unsec_exposure_inPct", cc_utilization), cc_utilization),
        "pct_of_active_TLs_ever": _safe_float((profile or {}).get("pct_of_active_TLs_ever", min(1.0, active_loans / max(active_loans + 1, 1))), 0.5),
        "pct_currentBal_all_TL": _safe_float((profile or {}).get("pct_currentBal_all_TL", cc_utilization), cc_utilization),
    }


def _credit_risk_band_from_category(risk_category: str) -> str:
    band_map = {
        "Low Risk": "LOW",
        "Medium-Low Risk": "MEDIUM",
        "Medium-High Risk": "HIGH",
        "High Risk": "VERY_HIGH",
        "P1": "LOW",
        "P2": "MEDIUM",
        "P3": "HIGH",
        "P4": "VERY_HIGH",
    }
    return band_map.get(risk_category, "MEDIUM")


# ═══════════════════════════════════════════════════════════════════════════════
# CREDIT RISK AGENT ADAPTER
# ═══════════════════════════════════════════════════════════════════════════════

def call_credit_agent(ctx: Any) -> dict:
    """
    Call the real credit risk agent (credit_backend).

    Input: ApplicationContext from DIL
    Output: Dict matching CreditRiskOutput schema
    """
    try:
        from agents.credit_risk.agent import get_graph
        credit_risk_graph = get_graph()
        from dataset_loader import get_merged_customer_profile

        # Build input for credit agent
        pan = ctx.form.pan_number.upper().strip()
        loan_amount = float(ctx.form.loan_amount_requested)
        loan_type = ctx.form.loan_purpose.value  # HOME/AUTO/PERSONAL/EDUCATION
        tenure = int(ctx.form.loan_tenure_months)
        monthly_income = ctx.form.annual_income / 12.0

        # Try to get profile from dataset
        profile = get_merged_customer_profile(pan)

        if profile:
            logger.info(f"[Credit Agent] Using dataset-backed profile for PAN {pan}")
        else:
            logger.warning(f"[Credit Agent] PAN {pan} not in dataset, synthesizing profile from DIL features")

        # Build input for credit agent
        # The specialist agent's run_credit_risk_graph only needs application_id
        # but we can also use the get_graph().invoke(initial) pattern if needed.
        from agents.credit_risk.agent import run_credit_risk_graph
        
        logger.info(f"[Credit Agent] Invoking Specialist LangGraph for {ctx.application_id}")
        result_out = run_credit_risk_graph(ctx.application_id)

        # The specialist returns the 'output' dict directly from run_credit_risk_graph
        final_result = result_out

        if not final_result or "error" in final_result:
            # Fallback: use DIL-computed PD if agent fails
            logger.warning("[Credit Agent] Agent returned error or empty, using DIL fallback")
            from tools import _compute_pd, _get_features, _get_macro_config
            features = _get_features(ctx.application_id)
            macro = _get_macro_config()
            score_result = _compute_pd(features, macro)
            return _fallback_credit_output(ctx.application_id, features, score_result)

        # Map agent output to orchestrator schema
        risk_score = float(final_result.get("model_risk_score", 0.0) or (final_result.get("credit_score", 0.05) * 100))
        risk_band = final_result.get("risk_band", "MEDIUM")
        ml_pd_proxy = float(final_result.get("credit_score", 0.05))

        output = {
            "application_id": ctx.application_id,
            "credit_score": ml_pd_proxy,
            "model_risk_score": round(risk_score, 2),
            "model_risk_category": final_result.get("model_risk_category", risk_band),
            "model_confidence": final_result.get("model_confidence", 0.8),
            "risk_band": risk_band,
            "foir": final_result.get("foir", ctx.features.foir),
            "dti_ratio": final_result.get("dti_ratio", ctx.features.dti_ratio),
            "ltv_ratio": final_result.get("ltv_ratio", ctx.features.ltv_ratio),
            "net_monthly_surplus": final_result.get("net_monthly_surplus", ctx.features.net_monthly_surplus),
            "proposed_emi": final_result.get("proposed_emi", ctx.features.proposed_emi),
            "macro_adjusted": final_result.get("macro_adjusted", False),
            "stress_scenario": final_result.get("stress_scenario", "NORMAL"),
            "alternative_score_used": final_result.get("alternative_score_used", False),
            "top_factors": final_result.get("top_factors", []),
            "officer_narrative": final_result.get("officer_narrative", "Assessment completed."),
            "customer_narrative": final_result.get("customer_narrative", ""),
            "agent_execution_mode": "langgraph_specialist",
            "prediction_source": "trained_model",
        }

        logger.info(f"[Credit Agent] ✓ Completed for {ctx.application_id}: {risk_band} (score={risk_score:.4f})")
        return output

    except Exception as e:
        logger.exception(f"[Credit Agent] Error calling credit agent: {e}")
        # Fallback to DIL rule-based scoring
        from tools import _compute_pd, _get_features, _get_macro_config
        features = _get_features(ctx.application_id)
        macro = _get_macro_config()
        score_result = _compute_pd(features, macro)
        return _fallback_credit_output(ctx.application_id, features, score_result)


def _fallback_credit_output(app_id: str, features: dict, score_result: dict) -> dict:
    """Fallback credit output when ML agent fails."""
    return {
        "application_id": app_id,
        "credit_score": score_result.get("pd", 0.05),
        "model_risk_score": None,
        "model_risk_category": None,
        "model_confidence": None,
        "model_class_probabilities": {},
        "risk_band": score_result.get("risk_band", "MEDIUM"),
        "foir": features.get("foir", 0),
        "dti_ratio": features.get("dti_ratio", 0),
        "ltv_ratio": features.get("ltv_ratio", 0),
        "net_monthly_surplus": features.get("net_monthly_surplus", 0),
        "proposed_emi": features.get("proposed_emi", 0),
        "macro_adjusted": score_result.get("macro_adjusted", False),
        "stress_scenario": score_result.get("stress_scenario", "NORMAL"),
        "alternative_score_used": False,
        "top_factors": score_result.get("shap_factors", []),
        "officer_narrative": f"Rule-based assessment: {score_result.get('risk_band')} risk.",
        "customer_narrative": "Your application has been assessed.",
        "agent_execution_mode": "fallback_rules",
        "prediction_source": "dil_rule_based",
        "data_source": "dil_features",
        "llm_status": "not_called",
        "llm_provider_error": "",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# FRAUD DETECTION AGENT ADAPTER
# ═══════════════════════════════════════════════════════════════════════════════

def call_fraud_agent(ctx: Any) -> dict:
    """
    Call the real fraud detection agent (Fraud-Agent).

    Input: ApplicationContext from DIL
    Output: Dict matching FraudOutput schema
    """
    try:
        fraud_agent_module = _load_fraud_agent_module()

        # Build input for fraud agent
        application = {
            "application_id": ctx.application_id,
            "pan_number": ctx.form.pan_number,
            "annual_income": ctx.form.annual_income,
            "loan_amount_requested": ctx.form.loan_amount_requested,
            "address": {
                "state": ctx.form.address.state,
                "city": ctx.form.address.city,
                "pincode": ctx.form.address.pincode,
            },
            "ip_metadata": {
                "ip_address": ctx.ip_meta.ip_address,
                "form_fill_seconds": ctx.ip_meta.form_fill_seconds,
                "device_fingerprint": ctx.ip_meta.device_fingerprint,
                "user_agent": ctx.ip_meta.user_agent,
            },
        }

        # Call the agent (the specialist's run_fraud_graph or run_fraud_agent)
        logger.info(f"[Fraud Agent] Invoking LangGraph for {ctx.application_id}")
        if hasattr(fraud_agent_module, "run_fraud_agent"):
            fraud_output = fraud_agent_module.run_fraud_agent(application)
        else:
            fraud_output = fraud_agent_module.run_fraud_graph(ctx.application_id)

        # Map agent output to orchestrator schema
        fraud_level_map = {
            "LOW_RISK": "CLEAN",
            "SUSPICIOUS": "SUSPICIOUS",
            "HIGH_RISK": "HIGH_RISK",
        }

        output = {
            "application_id": ctx.application_id,
            "fraud_probability": fraud_output.get("fraud_probability", 0.0),
            "fraud_level": fraud_level_map.get(fraud_output.get("fraud_level", "LOW_RISK"), "CLEAN"),
            "isolation_forest_score": fraud_output.get("isolation_forest_score", 0.0),
            "fired_hard_rules": fraud_output.get("fired_hard_rules", []),
            "fired_soft_signals": fraud_output.get("fired_soft_signals", []),
            "ip_risk_score": fraud_output.get("ip_risk_score", 0.0),
            "ip_country_mismatch": fraud_output.get("ip_country_mismatch", False),
            "application_velocity": fraud_output.get("application_velocity", 0),
            "identity_consistency": fraud_output.get("identity_consistency", "LOW"),
            "explanation": fraud_output.get("explanation", ""),
            "recommend_kyc_recheck": fraud_output.get("recommend_kyc_recheck", False),
            "shap_top_features": fraud_output.get("shap_top_features", []),
            "llm_explanation": fraud_output.get("llm_explanation", ""),
            "kyc_verified": fraud_output.get("identity_consistency", "LOW") == "LOW",
            "agent_execution_mode": "langgraph_agent",
            "prediction_source": "fraud_agent_model",
            "llm_status": fraud_output.get("llm_status", "not_exposed"),
            "llm_provider_error": fraud_output.get("llm_provider_error", ""),
        }

        logger.info(f"[Fraud Agent] ✓ Completed for {ctx.application_id}: {output['fraud_level']}")
        return output

    except Exception as e:
        logger.exception(f"[Fraud Agent] Error calling fraud agent: {e}")
        # Fallback to DIL rule-based fraud checks
        from tools import _run_fraud_checks
        features = ctx.features.model_dump()
        result = _run_fraud_checks(features)
        result["application_id"] = ctx.application_id
        result["agent_execution_mode"] = "fallback_rules"
        result["prediction_source"] = "dil_rule_based"
        result["llm_status"] = "not_called"
        result["llm_provider_error"] = ""
        return result


# ═══════════════════════════════════════════════════════════════════════════════
# COMPLIANCE AGENT ADAPTER
# ═══════════════════════════════════════════════════════════════════════════════

def call_compliance_agent(ctx: Any, credit_output: dict, fraud_output: dict) -> dict:
    """
    Call the real compliance agent (compliance_agent).

    Input: ApplicationContext + outputs from credit and fraud agents
    Output: Dict matching ComplianceOutput schema
    """
    try:
        # Build input schemas for compliance agent
        # The specialist agent's run_compliance_graph only needs application_id
        # and it handles its own data fetching from the feature store.
        from agents.compliance.agent import run_compliance_graph
        
        logger.info(f"[Compliance Agent] Invoking Specialist LangGraph for {ctx.application_id}")
        compliance_result = run_compliance_graph(ctx.application_id)

        # Transform output
        status_map = {
            "PASS": "PASS",
            "PASS_WITH_WARNINGS": "PASS_WITH_WARNINGS",
            "BLOCK_FAIL": "BLOCK_FAIL",
        }
        
        # The specialist returns the 'output' dict directly from run_compliance_graph
        res = compliance_result

        output = {
            "application_id": ctx.application_id,
            "overall_status": status_map.get(res.get("overall_status"), "PASS_WITH_WARNINGS"),
            "rbi_compliant": res.get("all_blocks_passed", True),
            "kyc_complete": res.get("kyc_complete", True),
            "foir_check": "PASS" if res.get("all_blocks_passed", True) else "FAIL",
            "aml_review_required": res.get("aml_review_required", False),
            "block_flags": res.get("block_flags", []),
            "warn_flags": res.get("warn_flags", []),
            "cot_reasoning": res.get("cot_reasoning", ""),
            "narrative": res.get("cot_reasoning", ""),
            "agent_execution_mode": "langgraph_specialist",
            "prediction_source": "compliance_logic",
        }

        logger.info(f"[Compliance Agent] ✓ Completed for {ctx.application_id}: {compliance_result.compliance_status}")
        return output

    except Exception as e:
        logger.exception(f"[Compliance Agent] Error calling compliance agent: {e}")
        # Fallback to DIL rule-based compliance checks
        from tools import _run_compliance_rules
        features = ctx.features.model_dump()
        form = ctx.form.model_dump()
        result = _run_compliance_rules(features, form)
        result["agent_execution_mode"] = "fallback_rules"
        result["prediction_source"] = "dil_rule_based"
        result["llm_status"] = "not_called"
        result["llm_provider_error"] = ""
        return result


# ═══════════════════════════════════════════════════════════════════════════════
# PORTFOLIO INTELLIGENCE AGENT ADAPTER
# ═══════════════════════════════════════════════════════════════════════════════

def call_portfolio_agent(ctx: Any, credit_output: dict) -> dict:
    """
    Call the proper Portfolio Intelligence LangGraph agent via A2A HTTP protocol.

    Input: ApplicationContext + outputs from credit agent
    Output: Dict matching PortfolioOutput schema
    """
    try:
        from orchestration.a2a_client import call_agent
        logger.info(f"[Portfolio Agent] Invoking A2A HTTP call for {ctx.application_id}")
        
        # Payload includes credit risk output for EL calculation
        result = call_agent(
            agent_name="portfolio",
            application_id=ctx.application_id,
            payload={"credit_risk_output": credit_output}
        )
        return result

    except Exception as e:
        logger.exception(f"[Portfolio Agent] A2A call failed: {e}")
        # Fallback to direct bridge if HTTP call fails
        try:
            from graphs import run_portfolio_graph
            return run_portfolio_graph(ctx.application_id, credit_output)
        except Exception:
            return {
                "application_id": ctx.application_id,
                "portfolio_recommendation": "ACCEPT",
                "error": str(e),
                "agent_execution_mode": "fallback_bridge"
            }
