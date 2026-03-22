"""
tools.py — MCP Tools Layer
===========================
Two categories:

  DATA TOOLS  — plain Python functions called inside LangGraph nodes.
                Also wrapped as @tool so CrewAI agents can call them too.

  AGENT RUNNER TOOLS  — @tool functions that the CrewAI manager agent calls
                        to invoke each specialist LangGraph graph.
                        These are what make the system genuinely agentic:
                        the manager LLM autonomously decides when and how
                        to call each specialist.
"""
from __future__ import annotations
import os, json, hashlib, logging, re, urllib.request, urllib.error
from pathlib import Path
from typing import Optional
from crewai.tools import tool

logger = logging.getLogger(__name__)

_DANGLING_END_RE = re.compile(r"\b(with|as|and|or|to|for|of|in|on|at|from|by|that|which|because|while|if)$", re.IGNORECASE)


def _looks_incomplete_llm_text(text: str) -> bool:
    """Heuristic check for visibly truncated model output."""
    clean = (text or "").strip()
    if not clean:
        return True
    # Most portfolio/compliance narratives should end like complete sentences.
    if clean.endswith(":"):
        return True
    if _DANGLING_END_RE.search(clean):
        return True
    return False

# ─── Shared output store (A2A) ────────────────────────────────────────────────
# Each LangGraph graph writes its typed output here.
# Other agents and the orchestrator read from it.
AGENT_OUTPUTS: dict[str, dict] = {}   # { app_id: { "credit": {...}, "fraud": {...}, ... } }

def _init_outputs(app_id: str):
    if app_id not in AGENT_OUTPUTS:
        AGENT_OUTPUTS[app_id] = {}

def set_agent_output(app_id: str, agent: str, output: dict):
    _init_outputs(app_id)
    AGENT_OUTPUTS[app_id][agent] = output

def get_agent_output(app_id: str, agent: str) -> Optional[dict]:
    return AGENT_OUTPUTS.get(app_id, {}).get(agent)


# ═══════════════════════════════════════════════════════════════════════════════
# DATA TOOLS — plain Python (called from LangGraph nodes)
# ═══════════════════════════════════════════════════════════════════════════════

def _get_features(app_id: str, group: str = "all") -> dict:
    """Read from DIL FeatureStore."""
    from dil import get_features, get_context
    result = get_features(app_id, group)
    if result is None:
        raise ValueError(f"No features found for {app_id}. DIL may not have run.")
    return result

def _get_context_dict(app_id: str) -> dict:
    """Read the full ApplicationContext as a dict."""
    from dil import get_context
    ctx = get_context(app_id)
    if ctx is None:
        raise ValueError(f"ApplicationContext not found for {app_id}")
    return ctx.model_dump(mode="json")

def _get_bureau_data(pan: str) -> dict:
    """Mock CIBIL bureau response — deterministic from PAN."""
    from dil import get_bureau_data
    return get_bureau_data(pan)

def _get_macro_config() -> dict:
    """Read macro config — always fresh from disk (so demo toggle works)."""
    from dil import _MACRO, load_static_data
    # Re-load to pick up any manual changes to macro_config.json
    data_dir = os.environ.get("DATA_DIR", "data")
    mc_path = Path(data_dir) / "macro_config.json"
    if mc_path.exists():
        return json.loads(mc_path.read_text())
    return _MACRO

def _get_portfolio_data(product: str, state: str, amount: float) -> dict:
    """Compute portfolio concentration impact for a new loan."""
    from agents_base import _PORTFOLIO, LGD_MAP
    active = [r for r in _PORTFOLIO if r.get("status") in ("ACTIVE", "NPA")]
    if not active:
        return {
            "sector_current": 0.25, "sector_new": 0.27,
            "geo_current": 0.15, "geo_new": 0.16,
            "total_outstanding": 50000000,
            "risk_band_dist": {"LOW":0.45,"MEDIUM":0.35,"HIGH":0.15,"VERY_HIGH":0.05},
            "portfolio_npa_rate": 0.03, "flags": [],
            "recommendation": "ACCEPT", "lgd": LGD_MAP.get(product, 0.5),
        }
    total = sum(float(r.get("outstanding", 0)) for r in active)
    new_total = total + amount
    sector_os = sum(float(r.get("outstanding", 0)) for r in active if r.get("loan_product") == product)
    geo_os = sum(float(r.get("outstanding", 0)) for r in active if r.get("state_code", "").lower() == state.lower())
    sector_cur = sector_os / max(total, 1)
    sector_new = (sector_os + amount) / max(new_total, 1)
    geo_cur = geo_os / max(total, 1)
    geo_new = (geo_os + amount) / max(new_total, 1)
    rb_dist = {}
    for rb in ("LOW", "MEDIUM", "HIGH", "VERY_HIGH"):
        rb_os = sum(float(r.get("outstanding", 0)) for r in active if r.get("risk_band") == rb)
        rb_dist[rb] = round(rb_os / max(total, 1), 4)
    npa_rate = sum(1 for r in active if r.get("status") == "NPA") / max(len(active), 1)
    flags = []
    if sector_new > 0.40: flags.append(f"SECTOR_BREACH: {product} at {sector_new:.0%} > 40% limit")
    elif sector_new > 0.35: flags.append(f"SECTOR_WARNING: {product} at {sector_new:.0%} nearing 35%")
    if geo_new > 0.25: flags.append(f"GEO_WARNING: {state} at {geo_new:.0%} nearing 25%")
    rec = "REJECT_FOR_PORTFOLIO" if sector_new > 0.40 else ("CAUTION" if flags else "ACCEPT")
    return {
        "sector_current": round(sector_cur, 4), "sector_new": round(sector_new, 4),
        "geo_current": round(geo_cur, 4), "geo_new": round(geo_new, 4),
        "total_outstanding": round(total), "risk_band_dist": rb_dist,
        "portfolio_npa_rate": round(npa_rate, 4), "flags": flags,
        "recommendation": rec, "lgd": LGD_MAP.get(product, 0.5),
        "active_loan_count": len(active),
    }

def _compute_pd(features: dict, macro: dict) -> dict:
    """Rule-based PD estimation. Returns {pd, risk_band, shap_factors}."""
    f = features
    pd_val = 0.05
    factors = []

    def factor(name, contribution, value, label):
        factors.append({"feature": name, "value": value, "shap_value": round(contribution, 5),
                         "human_label": label, "direction": "POSITIVE" if contribution < 0 else "NEGATIVE"})

    cibil = f.get("cibil_score", 0)
    if cibil > 0:
        c = (750 - cibil) / 750 * 0.35; pd_val += c; factor("cibil_score", -c, cibil, "CIBIL Score")
    else:
        pd_val += 0.15; factor("cibil_score", 0.15, 0, "CIBIL Score (unavailable)")

    foir = f.get("foir", 0)
    fc = max(0, (foir - 0.40) * 0.25); pd_val += fc; factor("foir", fc, foir, "Fixed Obligation-to-Income Ratio")

    dpd90 = f.get("dpd_90_count", 0); dc = dpd90 * 0.08; pd_val += dc
    factor("dpd_90_count", dc, dpd90, "90-Day Payment Defaults")

    dpd30 = f.get("dpd_30_count", 0); dc30 = dpd30 * 0.03; pd_val += dc30
    factor("dpd_30_count", dc30, dpd30, "30-Day Payment Delays")

    if f.get("is_salaried"): pd_val -= 0.03; factor("is_salaried", -0.03, 1, "Salaried Employment")

    ltv = f.get("ltv_ratio", 0); lc = max(0, (ltv - 0.75) * 0.10); pd_val += lc
    factor("ltv_ratio", lc, ltv, "Loan-to-Value Ratio")

    bounces = f.get("emi_bounce_count", 0); bc = bounces * 0.05; pd_val += bc
    factor("emi_bounce_count", bc, bounces, "EMI Bounce Count")

    sal_reg = f.get("salary_regularity", 1.0); pd_val -= sal_reg * 0.02
    factor("salary_regularity", -sal_reg * 0.02, sal_reg, "Salary Credit Regularity")

    pd_val = max(0.005, min(0.95, pd_val))

    # Macro stress overlay
    macro_adjusted = False
    stress = macro.get("stress_scenario", "NORMAL")
    product = f.get("loan_product_code", 0)
    product_name = {0:"HOME",1:"AUTO",2:"PERSONAL",3:"EDUCATION"}.get(product, "PERSONAL")
    if stress != "NORMAL":
        mult = macro.get("stress_multipliers", {}).get(stress, 0.0)
        npa = macro.get("sector_npa_rates", {}).get(product_name, 0.05)
        pd_val = min(0.95, pd_val + npa * mult)
        macro_adjusted = True

    if pd_val < 0.02: rb = "LOW"
    elif pd_val < 0.08: rb = "MEDIUM"
    elif pd_val < 0.18: rb = "HIGH"
    else: rb = "VERY_HIGH"

    return {"pd": round(pd_val, 6), "risk_band": rb, "shap_factors": factors,
            "macro_adjusted": macro_adjusted, "stress_scenario": stress}

def _run_fraud_checks(features: dict) -> dict:
    """Evaluate fraud signals. Returns {fraud_level, probability, hard_rules, soft_signals}."""
    f = features
    hard, soft = [], []

    if f.get("pan_blacklisted"): hard.append("PAN_ON_FRAUD_BLACKLIST")
    enquiries = f.get("num_hard_enquiries_6m", 0)
    if enquiries > 4: hard.append(f"ENQUIRY_SPIKE: {enquiries} hard enquiries in 6m")
    dpd90 = f.get("dpd_90_count", 0)
    if dpd90 >= 2: hard.append(f"DPD_90_MULTIPLE: {dpd90} instances")
    bounces = f.get("emi_bounce_count", 0)
    if bounces >= 3: hard.append(f"EMI_BOUNCE_HIGH: {bounces} bounces")
    if f.get("ip_risk_score", 0) >= 1.0: hard.append("IP_VPN_OR_PROXY: Application from VPN/datacenter IP")
    if f.get("ip_country_mismatch"): hard.append("IP_COUNTRY_MISMATCH: IP country ≠ Aadhaar country")

    fill_time = f.get("form_fill_time_seconds", 300)
    if fill_time < 45: soft.append(f"FAST_FORM_FILL: {fill_time:.0f}s (threshold 45s)")
    velocity = f.get("application_velocity", 1)
    if velocity > 1: soft.append(f"HIGH_VELOCITY: {velocity} applications from this PAN")
    outlier_z = f.get("income_loan_ratio_outlier", 0)
    if outlier_z > 2.5: soft.append(f"INCOME_LOAN_OUTLIER: z-score {outlier_z:.1f}")
    if f.get("device_fingerprint_new"): soft.append("NEW_DEVICE: Unrecognised device fingerprint")
    if enquiries > 2: soft.append(f"MODERATE_ENQUIRIES: {enquiries} enquiries in 6m")

    prob = 0.05
    prob += f.get("ip_risk_score", 0) * 0.30
    prob += enquiries * 0.04
    prob += dpd90 * 0.08
    prob += bounces * 0.05
    if fill_time < 45: prob += 0.12
    if hard: prob = max(prob, 0.55 + min(len(hard), 3) * 0.10)
    prob = round(min(0.95, prob), 4)

    if prob < 0.15: level = "CLEAN"
    elif prob < 0.35: level = "LOW_RISK"
    elif prob < 0.60: level = "SUSPICIOUS"
    else: level = "HIGH_RISK"

    return {"fraud_level": level, "fraud_probability": prob,
            "fired_hard_rules": hard, "fired_soft_signals": soft,
            "ip_risk_score": f.get("ip_risk_score", 0),
            "recommend_kyc_recheck": level in ("SUSPICIOUS", "HIGH_RISK")}

def _run_compliance_rules(features: dict, form_data: dict) -> dict:
    """Run RBI compliance rule engine. Returns {status, blocks, warns}."""
    from agents_base import _RULES
    ns = {
        "applicant_age": features.get("applicant_age", 30),
        "foir": features.get("foir", 0),
        "ltv_ratio": features.get("ltv_ratio", 0),
        "annual_income_verified": features.get("annual_income_verified", 0),
        "loan_amount": form_data.get("loan_amount_requested", 0),
        "loan_product": form_data.get("loan_purpose", "PERSONAL"),
        "income_proof_age_months": features.get("income_proof_age_months", 12),
        "kyc_pan_present": features.get("kyc_pan_present", True),
        "kyc_aadhaar_present": features.get("kyc_aadhaar_present", True),
        "bureau_check_done": features.get("bureau_check_done", True),
        "pan_blacklisted": features.get("pan_blacklisted", False),
        "name_match_score": features.get("name_match_score", 1.0),
        "aml_declaration_present": features.get("aml_declaration_present", False),
        "bank_statement_months": features.get("bank_statement_months", 6),
        "cibil_score": features.get("cibil_score", 0),
        "pan_number": form_data.get("pan_number", ""),
        "dti_ratio": features.get("dti_ratio", 0),
    }
    blocks, warns = [], []
    for rule in _RULES:
        try:
            passed = bool(eval(rule["expression"], {"__builtins__": {}}, ns))
        except Exception:
            passed = True
        if not passed:
            try:
                msg = (rule.get("error_message") or rule.get("warning_message", "")).format(**{k: ns.get(k, "") for k in ns})
            except Exception:
                msg = rule.get("error_message") or rule.get("warning_message", "Flag raised")
            flag = {"rule_id": rule["id"], "severity": rule["severity"],
                    "description": rule["description"], "regulation": rule.get("regulation", ""), "message": msg}
            if rule["severity"] == "BLOCK":
                blocks.append(flag)
            else:
                warns.append(flag)
    all_passed = len(blocks) == 0
    status = "PASS" if all_passed and not warns else ("PASS_WITH_WARNINGS" if all_passed else "BLOCK_FAIL")
    audit_hash = hashlib.sha256(json.dumps({"app": ns.get("pan_number",""), "b": len(blocks), "w": len(warns)}, sort_keys=True).encode()).hexdigest()[:16]
    aml_required = (not features.get("aml_declaration_present") and
                    form_data.get("loan_amount_requested", 0) > 1_000_000 and
                    form_data.get("loan_purpose") == "PERSONAL")
    return {"all_blocks_passed": all_passed, "block_flags": blocks, "warn_flags": warns,
            "overall_status": status, "kyc_complete": features.get("kyc_pan_present") and features.get("kyc_aadhaar_present"),
            "aml_review_required": aml_required, "audit_hash": audit_hash}

def _vertex_stream_url(model_name: str, api_key: str) -> str:
    return (
        "https://aiplatform.googleapis.com/v1/"
        f"publishers/google/models/{model_name}:streamGenerateContent?key={api_key}"
    )


def _extract_text_from_vertex_stream(raw_text: str) -> str:
    text = (raw_text or "").strip()
    if not text:
        return ""

    def _collect(obj: dict) -> list[str]:
        out: list[str] = []
        for candidate in obj.get("candidates") or []:
            parts = ((candidate.get("content") or {}).get("parts") or [])
            for part in parts:
                piece = part.get("text")
                if piece:
                    out.append(piece)
        return out

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return "\n".join(_collect(parsed)).strip()
        if isinstance(parsed, list):
            chunks: list[str] = []
            for item in parsed:
                if isinstance(item, dict):
                    chunks.extend(_collect(item))
            return "\n".join(chunks).strip()
    except json.JSONDecodeError:
        pass

    chunks = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            continue
        try:
            obj = json.loads(payload)
            if isinstance(obj, dict):
                chunks.extend(_collect(obj))
        except json.JSONDecodeError:
            continue
    return "\n".join(chunks).strip()


def _call_gemini(prompt: str, fallback: str) -> str:
    """Call Vertex AI Gemini endpoint. Returns fallback string if unavailable."""
    if os.environ.get("LLM_USAGE_MODE", "FULL").upper() == "FALLBACK":
        return fallback

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""
    if not api_key:
        return fallback

    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash-exp")
    payload = json.dumps(
        {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 300},
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        _vertex_stream_url(model, api_key),
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
        text = _extract_text_from_vertex_stream(raw)
        if not text or _looks_incomplete_llm_text(text):
            return fallback
        return text
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="ignore")
        logger.warning(f"Vertex AI call failed (HTTP {e.code}): {error_body[:200]}")
        return fallback
    except Exception as e:
        logger.warning(f"Vertex AI call failed: {e}")
        return fallback

def _log_event(app_id: str, agent: str, event_type: str, payload: dict):
    """Write to audit log."""
    try:
        import db
        db.log_event(app_id, agent, event_type, payload)
    except Exception as e:
        logger.warning(f"Audit log skipped for {app_id}/{agent}/{event_type}: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# @tool WRAPPERS — CrewAI-registered tools (thin wrappers around data tools)
# ═══════════════════════════════════════════════════════════════════════════════

@tool("Get Application Features")
def get_features_tool(application_id: str, group: str = "all") -> str:
    """
    Fetch the engineered feature vector for an application from the DIL feature store.
    group can be: all, credit_risk, fraud, compliance, portfolio
    Returns JSON of feature name → value pairs.
    """
    try:
        return json.dumps(_get_features(application_id, group))
    except Exception as e:
        return json.dumps({"error": str(e)})

@tool("Get Bureau Score")
def get_bureau_score_tool(pan_number: str) -> str:
    """
    Fetch CIBIL bureau score and credit history for a PAN number.
    Returns JSON with cibil_score, enquiries, DPD counts, credit utilization.
    """
    return json.dumps(_get_bureau_data(pan_number))

@tool("Get Macro Economic Config")
def get_macro_config_tool() -> str:
    """
    Get current macroeconomic configuration including RBI repo rate,
    sector NPA rates, stress scenario, and effective lending rates.
    Important: stress_scenario can be NORMAL, MILD_STRESS, or HIGH_STRESS.
    """
    return json.dumps(_get_macro_config())

@tool("Get Portfolio Exposure")
def get_portfolio_exposure_tool(loan_product: str, state: str, loan_amount: float) -> str:
    """
    Get current portfolio concentration and compute impact of a new loan.
    Returns sector/geo concentration percentages, expected loss data, and recommendation.
    """
    return json.dumps(_get_portfolio_data(loan_product, state, loan_amount))

@tool("Log Audit Event")
def log_audit_tool(application_id: str, agent_name: str, event_type: str, message: str) -> str:
    """Log an audit event for an application. Always call at start and end of each agent task."""
    _log_event(application_id, agent_name, event_type, {"message": message})
    return f"Logged: {event_type} for {application_id}"


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT RUNNER TOOLS — The CrewAI manager calls these to invoke LangGraph graphs
# These are the true A2A interface: manager → specialist graph → typed output
# ═══════════════════════════════════════════════════════════════════════════════

@tool("Run Credit Risk Assessment Agent")
def run_credit_risk_assessment(application_id: str) -> str:
    """
    Invoke the Real Credit Risk LangGraph agent (credit_backend).
    Uses RandomForest ML model + SHAP explanations + Gemini LLM.
    Loads real CIBIL data from dataset if available.

    Returns JSON with: credit_score (PD), risk_band, foir, ltv_ratio,
    net_monthly_surplus, top_factors (SHAP), officer_narrative, customer_narrative,
    macro_adjusted, stress_scenario.
    """
    try:
        from agent_adapters import call_credit_agent
        from dil import get_context

        # Get application context from DIL
        ctx = get_context(application_id)
        if ctx is None:
            raise ValueError(f"ApplicationContext not found for {application_id}")

        # Call the real credit agent
        logger.info(f"[CrewAI Tool] Invoking real Credit Risk Agent for {application_id}")
        result = call_credit_agent(ctx)
        set_agent_output(application_id, "credit", result)
        return json.dumps(result)
    except Exception as e:
        logger.exception(f"Credit Risk Agent failed: {e}")
        return json.dumps({"error": str(e), "risk_band": "HIGH", "credit_score": 0.5})

@tool("Run Fraud Detection Agent")
def run_fraud_detection(application_id: str) -> str:
    """
    Invoke the Real Fraud Detection LangGraph agent (Fraud-Agent).
    Uses IsolationForest ML model + Hard/Soft rules + SHAP explanations.

    Returns JSON with: fraud_level, fraud_probability, fired_hard_rules,
    fired_soft_signals, ip_risk_score, recommend_kyc_recheck, shap_top_features,
    llm_explanation.
    """
    try:
        from agent_adapters import call_fraud_agent
        from dil import get_context

        # Get application context from DIL
        ctx = get_context(application_id)
        if ctx is None:
            raise ValueError(f"ApplicationContext not found for {application_id}")

        # Call the real fraud agent
        logger.info(f"[CrewAI Tool] Invoking real Fraud Detection Agent for {application_id}")
        result = call_fraud_agent(ctx)
        set_agent_output(application_id, "fraud", result)
        return json.dumps(result)
    except Exception as e:
        logger.exception(f"Fraud Agent failed: {e}")
        return json.dumps({"error": str(e), "fraud_level": "SUSPICIOUS", "fraud_probability": 0.5})

@tool("Run Compliance Verification Agent")
def run_compliance_check(application_id: str) -> str:
    """
    Invoke the Real Compliance LangGraph agent (compliance_agent).
    Runs RBI eligibility checks, FOIR validation, AML checks, fairness audit,
    and generates compliance narratives via Gemini LLM.

    Returns JSON with: overall_status, rbi_compliant, kyc_complete, foir_check,
    aml_review_required, block_flags, warn_flags, narrative, cot_reasoning.
    """
    try:
        from agent_adapters import call_compliance_agent
        from dil import get_context

        # Get application context from DIL
        ctx = get_context(application_id)
        if ctx is None:
            raise ValueError(f"ApplicationContext not found for {application_id}")

        # Get credit and fraud outputs (compliance agent depends on these)
        credit_out = get_agent_output(application_id, "credit") or {}
        fraud_out = get_agent_output(application_id, "fraud") or {}

        # Call the real compliance agent
        logger.info(f"[CrewAI Tool] Invoking real Compliance Agent for {application_id}")
        result = call_compliance_agent(ctx, credit_out, fraud_out)
        set_agent_output(application_id, "compliance", result)
        return json.dumps(result)
    except Exception as e:
        logger.exception(f"Compliance Agent failed: {e}")
        return json.dumps({"error": str(e), "overall_status": "BLOCK_FAIL"})

@tool("Run Portfolio Analysis Agent")
def run_portfolio_analysis(application_id: str) -> str:
    """
    Invoke the Portfolio Intelligence LangGraph agent for a loan application.
    The agent queries the live loan portfolio, computes sector and geographic
    concentration impact, calculates Expected Loss using the credit agent's PD,
    finds similar past loans, and generates a portfolio strategy recommendation.

    IMPORTANT: Call run_credit_risk_assessment first — this agent uses the PD
    from the credit agent for accurate Expected Loss calculation (A2A dependency).

    Returns JSON with: portfolio_recommendation, sector concentrations,
    geo concentrations, el_impact_inr, concentration_flags, cot_reasoning.
    """
    try:
        from graphs import run_portfolio_graph
        # A2A: read credit output for actual PD
        credit_out = get_agent_output(application_id, "credit") or {}
        result = run_portfolio_graph(application_id, credit_out)
        set_agent_output(application_id, "portfolio", result)
        return json.dumps(result)
    except Exception as e:
        logger.exception(f"Portfolio Agent failed: {e}")
        return json.dumps({"error": str(e), "portfolio_recommendation": "ACCEPT"})

@tool("Apply Decision Matrix and Produce Final Decision")
def apply_decision_matrix_tool(application_id: str) -> str:
    """
    Apply the RBI-compliant decision matrix using all four agent outputs.
    Reads credit, fraud, compliance, and portfolio results from the A2A output store.

    Decision rules:
    - Compliance BLOCK or Fraud HIGH_RISK or Credit VERY_HIGH → REJECT
    - Credit HIGH risk → ESCALATE to human officer
    - Fraud SUSPICIOUS → ESCALATE
    - Minor issues (warnings, caution) → CONDITIONAL with specific conditions
    - All clear → APPROVE

    Returns JSON FinalDecision with ai_recommendation, conditions, decision_matrix_row,
    officer_summary, and all four agent outputs embedded.
    """
    try:
        from crew_runner import build_final_decision
        result = build_final_decision(application_id)
        return json.dumps(result)
    except Exception as e:
        logger.exception(f"Decision matrix failed: {e}")
        return json.dumps({"error": str(e), "ai_recommendation": "ESCALATE"})


# ── Tool registries ───────────────────────────────────────────────────────────

# All @tool objects available to CrewAI manager
MANAGER_TOOLS = [
    run_credit_risk_assessment,
    run_fraud_detection,
    run_compliance_check,
    run_portfolio_analysis,
    apply_decision_matrix_tool,
    log_audit_tool,
]

# Data tools available to specialist agents (optional — for direct data access)
DATA_TOOLS = [
    get_features_tool,
    get_bureau_score_tool,
    get_macro_config_tool,
    get_portfolio_exposure_tool,
    log_audit_tool,
]
