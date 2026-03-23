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

    fraud_dir = ROOT / "Fraud-Agent"
    fraud_file = fraud_dir / "fraud_agent.py"
    if str(fraud_dir) not in sys.path:
        sys.path.insert(0, str(fraud_dir))

    spec = importlib.util.spec_from_file_location("copilot_fraud_agent", fraud_file)
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
        from credit_backend.credit_risk_agent import credit_risk_graph
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

        agent_input = {
            "pan_number": pan,
            "loan_amount": loan_amount,
            "loan_type": loan_type,
            "loan_tenure_months": tenure,
            "declared_monthly_income": monthly_income,
            "user_profile": _build_credit_agent_profile(ctx, profile),
        }

        # Call the agent's LangGraph
        logger.info(f"[Credit Agent] Invoking LangGraph for {ctx.application_id}")
        result = credit_risk_graph.invoke(agent_input)

        # Transform output to match orchestrator schema
        final_result = result.get("final_result", {})

        if "error" in final_result or "validation_errors" in final_result:
            # Fallback: use DIL-computed PD if agent fails
            logger.warning("[Credit Agent] Agent returned error, using DIL fallback")
            from tools import _compute_pd, _get_features, _get_macro_config
            features = _get_features(ctx.application_id)
            macro = _get_macro_config()
            score_result = _compute_pd(features, macro)
            return _fallback_credit_output(ctx.application_id, features, score_result)

        # Map agent output to orchestrator schema
        risk_score = float(final_result.get("risk_score", 5.0))
        risk_category = final_result.get("risk_category", "MEDIUM")
        risk_band = _credit_risk_band_from_category(risk_category)
        ml_pd_proxy = round(max(0.0, min(1.0, risk_score / 100.0)), 6)

        # Extract both risk-increasing and risk-reducing factors for a balanced view.
        top_factors = []
        for factor in final_result.get("top_risk_factors", [])[:6]:
            contribution = float(factor.get("contribution", 0) or 0)
            top_factors.append({
                "feature": factor.get("feature", "unknown"),
                "value": factor.get("value", 0),
                "shap_value": contribution,
                "human_label": factor.get("human_name", factor.get("feature", "")),
                "direction": "NEGATIVE" if contribution > 0 else "POSITIVE",
            })

        for factor in final_result.get("top_positive_factors", [])[:4]:
            contribution = float(factor.get("contribution", 0) or 0)
            top_factors.append({
                "feature": factor.get("feature", "unknown"),
                "value": factor.get("value", 0),
                "shap_value": contribution,
                "human_label": factor.get("human_name", factor.get("feature", "")),
                "direction": "POSITIVE" if contribution < 0 else "NEGATIVE",
            })

        top_factors = sorted(top_factors, key=lambda f: abs(float(f.get("shap_value", 0) or 0)), reverse=True)[:8]

        output = {
            "application_id": ctx.application_id,
            "credit_score": ml_pd_proxy,
            "model_risk_score": round(risk_score, 2),
            "model_risk_category": risk_category,
            "model_confidence": final_result.get("confidence", 0.0),
            "model_class_probabilities": final_result.get("class_probabilities", {}),
            "risk_band": risk_band,
            "foir": ctx.features.foir,
            "dti_ratio": ctx.features.dti_ratio,
            "ltv_ratio": ctx.features.ltv_ratio,
            "net_monthly_surplus": ctx.features.net_monthly_surplus,
            "proposed_emi": ctx.features.proposed_emi,
            "macro_adjusted": False,  # ML model doesn't use macro overlay
            "stress_scenario": ctx.macro_config.get("stress_scenario", "NORMAL"),
            "alternative_score_used": False,  # ML model is the primary scorer
            "top_factors": top_factors,
            "officer_narrative": final_result.get("llm_explanation", "ML-based credit risk assessment completed."),
            "customer_narrative": final_result.get("recommendation", "Your application has been assessed."),
            "agent_execution_mode": "langgraph_agent",
            "prediction_source": "trained_ml_model",
            "data_source": "dataset_profile" if profile else "dil_adapted_profile",
            "llm_status": final_result.get("llm_status", "unknown"),
            "llm_provider_error": final_result.get("llm_provider_error", ""),
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

        # Call the agent
        logger.info(f"[Fraud Agent] Invoking LangGraph for {ctx.application_id}")
        fraud_output = fraud_agent_module.run_fraud_agent(application)

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
        from compliance_agent.agent import run_compliance_agent
        from compliance_agent.schemas import (
            ApplicationFormData, CreditAgentOutput, FraudAgentOutput,
            BankStatementData, MacroConfigData
        )
        from dataset_loader import get_bank_data

        # Build input schemas for compliance agent
        application = ApplicationFormData(
            pan_number=ctx.form.pan_number,
            date_of_birth=ctx.form.date_of_birth,
            employment_type=ctx.form.employment_type.value,
            annual_income=ctx.form.annual_income,
            loan_amount_requested=ctx.form.loan_amount_requested,
            loan_tenure_months=ctx.form.loan_tenure_months,
            loan_purpose=ctx.form.loan_purpose.value,
            existing_emi_monthly=ctx.form.existing_emi_monthly,
            uploaded_docs=["pan_card", "form_16", "salary_slip"],
            employer_name=ctx.form.employer_name,
            gender=ctx.form.gender,
            marital_status="SINGLE",
        )

        risk_score = credit_output.get("model_risk_score")
        if risk_score is None:
            risk_score = _safe_float(credit_output.get("credit_score"), 0.05) * 100

        credit_agent_output = CreditAgentOutput(
            risk_score=_safe_float(risk_score, 5.0),
            risk_band=credit_output.get("risk_band", "MEDIUM"),
            foir=credit_output.get("foir", 0),
            dti_ratio=credit_output.get("dti_ratio", 0),
            macro_adjusted=credit_output.get("macro_adjusted", False),
        )

        fraud_agent_output = FraudAgentOutput(
            fraud_level=fraud_output.get("fraud_level", "CLEAN"),
            fraud_probability=fraud_output.get("fraud_probability", 0.0),
            kyc_verified=fraud_output.get("kyc_verified", True),
            triggered_rules=fraud_output.get("fired_hard_rules", []) + fraud_output.get("fired_soft_signals", []),
        )

        # Get bank statement data from dataset or DIL
        bank_dict = get_bank_data(ctx.form.pan_number) or {}
        bank_statement = BankStatementData(
            avg_monthly_credit=bank_dict.get("avg_monthly_credit", ctx.features.avg_monthly_credit),
            emi_bounce_count=bank_dict.get("emi_bounce_count", ctx.features.emi_bounce_count),
            salary_credit_regularity=bank_dict.get("salary_credit_regularity", ctx.features.salary_regularity),
        )

        macro_data = MacroConfigData(
            stress_scenario=ctx.macro_config.get("stress_scenario", "NORMAL"),
            rbi_repo_rate=ctx.macro_config.get("rbi_repo_rate", 6.5),
            sector_npa_rates=ctx.macro_config.get("sector_npa_rates", {}),
        )

        # Call the agent
        logger.info(f"[Compliance Agent] Invoking LangGraph for {ctx.application_id}")
        compliance_result = run_compliance_agent(
            application, credit_agent_output, fraud_agent_output,
            bank_statement, macro_data
        )

        # Transform output
        status_map = {
            "PASS": "PASS",
            "ESCALATE": "PASS_WITH_WARNINGS",
            "FAIL": "BLOCK_FAIL",
        }

        output = {
            "application_id": ctx.application_id,
            "overall_status": status_map.get(compliance_result.compliance_status, "PASS_WITH_WARNINGS"),
            "rbi_compliant": compliance_result.rbi_compliant,
            "kyc_complete": compliance_result.kyc_complete,
            "foir_check": "PASS" if compliance_result.foir_within_limit else "FAIL",
            "aml_review_required": compliance_result.aml_check_required,
            "block_flags": [
                {"rule_id": "C_FAIL", "description": flag, "severity": "BLOCK"}
                for flag in compliance_result.compliance_flags
                if any(x in flag for x in ['ineligible', 'exceeds', 'block'])
            ],
            "warn_flags": [
                {"rule_id": "C_WARN", "description": flag, "severity": "WARN"}
                for flag in compliance_result.compliance_flags
                if not any(x in flag for x in ['ineligible', 'exceeds', 'block'])
            ],
            "cot_reasoning": compliance_result.audit_narrative[:500],
            "narrative": compliance_result.narrative,
            "agent_execution_mode": "langgraph_agent",
            "prediction_source": "compliance_agent_logic",
            "llm_status": compliance_result.llm_status,
            "llm_provider_error": compliance_result.llm_provider_error,
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
