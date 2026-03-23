"""
crew_runner.py — Decision Matrix & Final Decision Builder
Called by the apply_decision_matrix_tool in tools.py.
"""
from __future__ import annotations
import uuid, json, logging
from datetime import datetime
from typing import Optional
from tools import AGENT_OUTPUTS

logger = logging.getLogger(__name__)


def _normalize_credit_band(credit: dict) -> str:
    band = str(credit.get("risk_band", "") or "").upper()
    if band in {"LOW", "MEDIUM", "HIGH", "VERY_HIGH"}:
        return band

    category = str(credit.get("model_risk_category", "") or "").strip().lower()
    category_map = {
        "low risk": "LOW",
        "medium-low risk": "MEDIUM",
        "medium-high risk": "HIGH",
        "high risk": "VERY_HIGH",
        "p1": "LOW",
        "p2": "MEDIUM",
        "p3": "HIGH",
        "p4": "VERY_HIGH",
    }
    if category in category_map:
        return category_map[category]

    numeric_score = credit.get("model_risk_score")
    if numeric_score is not None:
        score = float(numeric_score)
        if score >= 75:
            return "VERY_HIGH"
        if score >= 45:
            return "HIGH"
        if score >= 20:
            return "MEDIUM"
        return "LOW"

    pd_proxy = float(credit.get("credit_score", 0.0) or 0.0)
    if pd_proxy >= 0.75:
        return "VERY_HIGH"
    if pd_proxy >= 0.45:
        return "HIGH"
    if pd_proxy >= 0.20:
        return "MEDIUM"
    return "LOW"


def _normalize_fraud_level(fraud: dict) -> str:
    level = str(fraud.get("fraud_level", "") or "").upper()
    probability = float(fraud.get("fraud_probability", 0.0) or 0.0)

    if level == "HIGH_RISK" or probability >= 0.75:
        return "HIGH_RISK"
    if level == "SUSPICIOUS" or probability >= 0.45:
        return "SUSPICIOUS"
    if level in {"LOW_RISK", "CLEAN"}:
        return "CLEAN"
    return "CLEAN"


def _normalize_compliance_status(comp: dict) -> str:
    status = str(comp.get("overall_status", "") or "").upper()
    if status in {"BLOCK_FAIL", "PASS_WITH_WARNINGS", "PASS"}:
        return status

    if comp.get("block_flags"):
        return "BLOCK_FAIL"
    if comp.get("warn_flags") or comp.get("aml_review_required"):
        return "PASS_WITH_WARNINGS"
    return "PASS"


def _apply_matrix(credit: dict, fraud: dict, comp: dict, port: dict, ctx: dict) -> tuple[str, str, list, Optional[float]]:
    """Pure Python decision matrix. Returns (decision, matrix_row, conditions, max_amount)."""
    rb = _normalize_credit_band(credit)
    fl = _normalize_fraud_level(fraud)
    cs = _normalize_compliance_status(comp)
    pr = port.get("portfolio_recommendation", "ACCEPT")
    conditions = []
    fv = ctx.get("features", {})
    form = ctx.get("form", {})

    if cs == "BLOCK_FAIL":
        rules = ", ".join(b.get("rule_id","?") for b in comp.get("block_flags", []))
        return "REJECT", f"R1_COMPLIANCE_BLOCK({rules})", [], None

    if fl == "HIGH_RISK":
        return "REJECT", "R2_FRAUD_HIGH_RISK", [], None

    if rb == "VERY_HIGH":
        return "REJECT", "R3_CREDIT_VERY_HIGH", [], None

    if pr == "REJECT_FOR_PORTFOLIO":
        return "REJECT", "R4_PORTFOLIO_BREACH", [], None

    if rb == "HIGH":
        return "ESCALATE", "R5_HIGH_RISK_ESCALATE", [], None

    if fl == "SUSPICIOUS":
        return "ESCALATE", "R6_SUSPICIOUS_FRAUD", [], None

    # LOW or MEDIUM credit, CLEAN/LOW_RISK fraud from here
    if cs == "PASS_WITH_WARNINGS":
        conditions.append({"condition_type": "DOCUMENTATION",
                           "description": "Please provide updated documents to resolve flagged compliance items. Our team will contact you.",
                           "required_by_days": 7})
        return "CONDITIONAL", "R7a_COMPLIANCE_WARNINGS", conditions, None

    if pr == "CAUTION" and fv.get("foir", 0) > 0.48:
        macro = ctx.get("macro_config", {})
        rate  = macro.get("effective_rates", {}).get(form.get("loan_purpose", "PERSONAL"), 10.0)
        r     = (rate / 100) / 12
        n     = form.get("loan_tenure_months", 60)
        max_emi    = fv.get("annual_income_verified", 0) / 12 * 0.45 - form.get("existing_emi_monthly", 0)
        max_emi    = max(0, max_emi)
        max_amount = (max_emi * (((1+r)**n - 1) / (r*(1+r)**n)) if r > 0 else max_emi * n)
        max_amount = round(max(0, max_amount) / 50000) * 50000
        conditions.append({"condition_type": "REDUCED_AMOUNT",
                           "description": f"Based on your income and obligations, we can approve ₹{max_amount:,.0f} instead of ₹{form.get('loan_amount_requested',0):,.0f} requested.",
                           "required_by_days": 3})
        return "CONDITIONAL", "R7b_REDUCED_AMOUNT", conditions, max_amount

    if fraud.get("recommend_kyc_recheck") and fl == "CLEAN":
        conditions.append({"condition_type": "VERIFY_IDENTITY",
                           "description": "Please resubmit clear copies of your PAN and Aadhaar for re-verification.",
                           "required_by_days": 7})
        return "CONDITIONAL", "R7c_KYC_VERIFY", conditions, None

    if comp.get("aml_review_required"):
        conditions.append({"condition_type": "DOCUMENTATION",
                           "description": "A source-of-funds declaration is required for personal loans above ₹10 lakhs (RBI/PMLA).",
                           "required_by_days": 5})
        return "CONDITIONAL", "R7d_AML_DECLARATION", conditions, None

    return "APPROVE", "R7e_CLEAN_APPROVE", [], None


def build_final_decision(app_id: str) -> dict:
    """Assemble FinalDecision from A2A outputs and apply decision matrix."""
    from dil import get_context
    ctx_obj = get_context(app_id)
    ctx = ctx_obj.model_dump(mode="json") if ctx_obj else {}

    outputs = AGENT_OUTPUTS.get(app_id, {})
    credit  = outputs.get("credit", {})
    fraud   = outputs.get("fraud", {})
    comp    = outputs.get("compliance", {})
    port    = outputs.get("portfolio", {})

    decision, row, conditions, max_amount = _apply_matrix(credit, fraud, comp, port, ctx)

    # Officer summary
    lines = [
        f"AI RECOMMENDATION: {decision}",
        f"Matrix rule matched: {row}",
        "",
        f"CREDIT RISK:  {credit.get('risk_band','—')} | PD={credit.get('credit_score',0):.2%} | FOIR={credit.get('foir',0):.1%} | Surplus ₹{credit.get('net_monthly_surplus',0):,.0f}/mo",
        f"FRAUD:        {fraud.get('fraud_level','—')} | Prob={fraud.get('fraud_probability',0):.2%} | Hard rules: {len(fraud.get('fired_hard_rules',[]))} | Soft: {len(fraud.get('fired_soft_signals',[]))}",
        f"COMPLIANCE:   {comp.get('overall_status','—')} | Blocks: {len(comp.get('block_flags',[]))} | Warns: {len(comp.get('warn_flags',[]))}",
        f"PORTFOLIO:    {port.get('portfolio_recommendation','—')} | Sector {port.get('sector_concentration_new',0):.1%} | EL ₹{port.get('el_impact_inr',0):,.0f}",
    ]
    lines += [
        f"CREDIT PATH: {credit.get('prediction_source', 'unknown')} | LLM={credit.get('llm_status', 'unknown')}",
        f"COMPLIANCE PATH: {comp.get('prediction_source', 'unknown')} | LLM={comp.get('llm_status', 'unknown')}",
    ]
    if credit.get("officer_narrative"): lines += ["", f"Credit: {credit['officer_narrative']}"]
    if fraud.get("explanation"):        lines += [f"Fraud:  {fraud['explanation']}"]
    if comp.get("cot_reasoning"):       lines += [f"Compliance: {comp['cot_reasoning'][:200]}"]
    if port.get("cot_reasoning"):       lines += [f"Portfolio: {port['cot_reasoning'][:200]}"]
    if conditions:
        lines += ["", "CONDITIONS:"]
        for c in conditions:
            lines.append(f"  [{c['condition_type']}] {c['description'][:80]}")

    result = {
        "decision_id":           f"DEC-{uuid.uuid4().hex[:10].upper()}",
        "application_id":        app_id,
        "ai_recommendation":     decision,
        "decision_matrix_row":   row,
        "conditions":            conditions,
        "max_approvable_amount": max_amount,
        "credit_risk":           credit,
        "fraud":                 fraud,
        "compliance":            comp,
        "portfolio":             port,
        "officer_summary":       "\n".join(lines),
        "context":               ctx,
        "decided_at":            datetime.utcnow().isoformat(),
    }
    return result
