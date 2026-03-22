"""agent.py — Portfolio Intelligence Agent (LangGraph, 6 nodes).

Graph architecture (sequential):
  START
    └─ node_sector_concentration
          └─ node_geographic_concentration
                └─ node_risk_band_distribution
                      └─ node_expected_loss
                            └─ node_recommendation_synthesis
                                  └─ node_llm_narrative
                                        └─ END

Public entry:
  run_portfolio_agent(application, credit_output, fraud_output,
                      compliance_output, bank_data, macro_data, portfolio_stats)
  -> dict  (field names compatible with backend/schemas.py PortfolioOutput)
"""
from __future__ import annotations

import logging
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv optional
logger = logging.getLogger(__name__)

from portfolio_agent.schemas import (
    ApplicationFormData, CreditAgentOutput, FraudAgentOutput,
    ComplianceAgentOutput, BankStatementData, MacroConfigData,
    PortfolioStats, PortfolioState,
)

# ─── Helpers ─────────────────────────────────────────────────────────────────

def _stress_multiplier(stress_scenario: str) -> float:
    return {"NORMAL": 1.0, "MILD_STRESS": 0.8, "HIGH_STRESS": 0.6}.get(stress_scenario, 1.0)


def _degrade_recommendation(current: str, new: str) -> str:
    """Only allow downgrade: ACCEPT → CAUTION → REJECT_FOR_PORTFOLIO."""
    rank = {"ACCEPT": 0, "CAUTION": 1, "REJECT_FOR_PORTFOLIO": 2}
    return new if rank.get(new, 0) > rank.get(current, 0) else current


# ─── Node 1: Sector Concentration ────────────────────────────────────────────

def node_sector_concentration(state: PortfolioState) -> dict:
    """
    Checks:
      1. Personal sector concentration (current and post-approval)
      2. SELF_EMPLOYED segment (> 30% × stress_mult)
      3. Employer concentration (single employer > 5% × stress_mult)
    """
    app = state["application"]
    ps = state["portfolio_stats"]
    macro = state["macro_data"]
    flags: list[str] = list(state.get("concentration_flags") or [])

    stress_mult = _stress_multiplier(macro.stress_scenario)
    sector_threshold = 0.35 * stress_mult

    current_personal_pct = ps.sector_distribution.get("PERSONAL", 0.0)
    total_exposure = ps.total_exposure_inr
    new_exposure = app.loan_amount_requested

    if total_exposure > 0:
        post_approval_sector_pct = (
            current_personal_pct * total_exposure + new_exposure
        ) / (total_exposure + new_exposure)
    else:
        post_approval_sector_pct = 1.0  # all PERSONAL if portfolio is empty

    concentration_flag = post_approval_sector_pct >= sector_threshold
    if concentration_flag:
        flags.append("sector_concentration_breach")

    # SELF_EMPLOYED segment check
    total_loans = max(ps.total_loans, 1)
    current_se_count = round(ps.self_employed_pct * total_loans)
    if app.employment_type == "SELF_EMPLOYED":
        se_pct_post = (current_se_count + 1) / (total_loans + 1)
    else:
        se_pct_post = current_se_count / (total_loans + 1)

    segment_concentration_flag = se_pct_post >= 0.30 * stress_mult
    if segment_concentration_flag:
        flags.append("self_employed_segment_concentration")

    # Employer concentration check
    employer_matches = [
        e for e in ps.employer_top_10
        if str(e.get("employer", "")).lower() == app.employer_name.lower()
    ]
    employer_pct = employer_matches[0]["pct"] if employer_matches else 0.0
    employer_concentration_flag = employer_pct >= 0.05 * stress_mult
    if employer_concentration_flag:
        flags.append("employer_concentration_breach")

    return {
        "sector_concentration_pct": current_personal_pct,
        "post_approval_sector_pct": post_approval_sector_pct,
        "concentration_flag": concentration_flag,
        "sector_threshold_used": sector_threshold,
        "segment_concentration_flag": segment_concentration_flag,
        "employer_concentration_flag": employer_concentration_flag,
        "employer_pct": employer_pct,
        "concentration_flags": flags,
    }


# ─── Node 2: Geographic Concentration ────────────────────────────────────────

def node_geographic_concentration(state: PortfolioState) -> dict:
    """Checks top-state geographic concentration post-approval."""
    app = state["application"]
    ps = state["portfolio_stats"]
    macro = state["macro_data"]
    flags: list[str] = list(state.get("concentration_flags") or [])

    stress_mult = _stress_multiplier(macro.stress_scenario)
    geo_threshold = 0.25 * stress_mult

    geo = ps.geographic_distribution
    if not geo:
        geo = {"Maharashtra": 0.22}

    top_state = max(geo, key=lambda k: geo[k])
    top_state_pct = geo[top_state]

    total_loans = max(ps.total_loans, 1)

    # Recompute top-state pct after adding this application
    if app.applicant_state == top_state:
        adjusted_pct = (top_state_pct * total_loans + 1) / (total_loans + 1)
    else:
        adjusted_pct = top_state_pct  # top state doesn't change

    geographic_concentration_flag = adjusted_pct > geo_threshold
    if geographic_concentration_flag:
        flags.append("geographic_concentration_breach")

    return {
        "geographic_concentration_flag": geographic_concentration_flag,
        "city_concentration_flag": False,  # PoC: city data limited
        "top_state": top_state,
        "top_state_pct": top_state_pct,
        "concentration_flags": flags,
    }


# ─── Node 3: Risk Band Distribution ──────────────────────────────────────────

def node_risk_band_distribution(state: PortfolioState) -> dict:
    """Checks HIGH+VERY_HIGH concentration post-approval and may set REJECT."""
    ps = state["portfolio_stats"]
    credit = state["credit_output"]
    macro = state["macro_data"]
    flags: list[str] = list(state.get("concentration_flags") or [])
    current_rec = state.get("portfolio_recommendation", "ACCEPT")

    stress_mult = _stress_multiplier(macro.stress_scenario)
    high_risk_threshold = 0.15 * stress_mult

    dist = ps.risk_band_distribution
    high_risk_pct_current = dist.get("HIGH", 0.0) + dist.get("VERY_HIGH", 0.0)
    very_high_pct_current = dist.get("VERY_HIGH", 0.0)

    total = max(ps.total_loans, 1)
    new_risk_band = credit.risk_band

    current_high_count = high_risk_pct_current * total
    if new_risk_band in ("HIGH", "VERY_HIGH"):
        high_risk_pct_post = (current_high_count + 1) / (total + 1)
    else:
        high_risk_pct_post = current_high_count / (total + 1)

    # VERY_HIGH band post-approval
    current_vh_count = very_high_pct_current * total
    if new_risk_band == "VERY_HIGH":
        very_high_post = (current_vh_count + 1) / (total + 1)
    else:
        very_high_post = current_vh_count / (total + 1)

    risk_band_flag = False
    if high_risk_pct_post >= high_risk_threshold:
        risk_band_flag = True
        flags.append("high_risk_band_concentration")
        if 0.15 <= high_risk_pct_post < 0.20:
            current_rec = _degrade_recommendation(current_rec, "CAUTION")
        elif high_risk_pct_post >= 0.20:
            current_rec = _degrade_recommendation(current_rec, "REJECT_FOR_PORTFOLIO")

    if very_high_post >= 0.05 * stress_mult:
        flags.append("very_high_band_cap_breached")
        current_rec = _degrade_recommendation(current_rec, "REJECT_FOR_PORTFOLIO")

    # Compute post-approval distribution (for output)
    post_dist = {band: round(dist.get(band, 0.0) * total / (total + 1), 6) for band in ["LOW", "MEDIUM", "HIGH", "VERY_HIGH"]}
    post_dist[new_risk_band] = round(
        (dist.get(new_risk_band, 0.0) * total + 1) / (total + 1), 6
    )

    return {
        "high_risk_pct_current": high_risk_pct_current,
        "high_risk_pct_post_approval": high_risk_pct_post,
        "risk_band_flag": risk_band_flag,
        "post_approval_risk_distribution": post_dist,
        "portfolio_recommendation": current_rec,
        "concentration_flags": flags,
    }


# ─── Node 4: Expected Loss ────────────────────────────────────────────────────

def node_expected_loss(state: PortfolioState) -> dict:
    """
    EL = PD × LGD × EAD
    PD adjusted for fraud signal and EMI bounces.
    LGD adjusted for stress, inflation, and GDP.
    """
    app = state["application"]
    credit = state["credit_output"]
    fraud = state["fraud_output"]
    bank = state["bank_data"]
    macro = state["macro_data"]
    ps = state["portfolio_stats"]
    flags: list[str] = list(state.get("concentration_flags") or [])
    current_rec = state.get("portfolio_recommendation", "ACCEPT")

    # 1. PD Adjustment
    pd_base = credit.predicted_pd
    pd_adjusted = (
        pd_base * (1 + fraud.fraud_probability * 0.5)
        + bank.emi_bounce_count * 0.02
    )
    pd_adjusted = min(pd_adjusted, 0.95)

    # 2. LGD
    base_lgd = 0.45  # RBI CIRR standard for unsecured personal loans
    stress_lgd_adj = {"NORMAL": 0.0, "MILD_STRESS": 0.05, "HIGH_STRESS": 0.10}.get(
        macro.stress_scenario, 0.0
    )
    if macro.inflation_rate > 6.0:
        stress_lgd_adj += 0.05
    npa_multiplier = 1.5 if macro.gdp_growth_rate < 5.0 else 1.0
    sector_npa = macro.sector_npa_rates.get("PERSONAL", 0.038)
    lgd = base_lgd + stress_lgd_adj + (sector_npa * npa_multiplier * 0.1)
    lgd = min(lgd, 0.80)

    # 3. EAD — full unsecured loan amount
    ead = app.loan_amount_requested

    # 4. Expected Loss impact
    expected_loss_impact = pd_adjusted * lgd * ead

    # 5. Portfolio EL before/after
    portfolio_el_before = ps.portfolio_el_total
    portfolio_el_after = portfolio_el_before + expected_loss_impact

    if portfolio_el_before > 0:
        el_increase_pct = (
            (portfolio_el_after - portfolio_el_before) / portfolio_el_before * 100
        )
    else:
        el_increase_pct = 0.0

    # 6. EL-based recommendation
    if el_increase_pct > 5.0:
        current_rec = _degrade_recommendation(current_rec, "REJECT_FOR_PORTFOLIO")
        flags.append("el_impact_exceeds_5pct")
    elif el_increase_pct > 2.0:
        current_rec = _degrade_recommendation(current_rec, "CAUTION")
        flags.append("el_impact_caution_2_to_5pct")

    return {
        "pd_adjusted": round(pd_adjusted, 6),
        "lgd": round(lgd, 4),
        "ead": ead,
        "expected_loss_impact": round(expected_loss_impact, 2),
        "portfolio_el_before": round(portfolio_el_before, 2),
        "portfolio_el_after": round(portfolio_el_after, 2),
        "el_increase_pct": round(el_increase_pct, 4),
        "portfolio_recommendation": current_rec,
        "concentration_flags": flags,
    }


# ─── Node 5: Recommendation Synthesis ────────────────────────────────────────

def node_recommendation_synthesis(state: PortfolioState) -> dict:
    """
    Final consolidation of recommendation from all flags.
    After this node, portfolio_recommendation is frozen.
    """
    current_rec = state.get("portfolio_recommendation", "ACCEPT")
    flags = state.get("concentration_flags") or []

    conc_flag = state.get("concentration_flag", False)
    seg_flag = state.get("segment_concentration_flag", False)
    geo_flag = state.get("geographic_concentration_flag", False)
    emp_flag = state.get("employer_concentration_flag", False)
    el_pct = state.get("el_increase_pct", 0.0)
    high_risk_post = state.get("high_risk_pct_post_approval", 0.0)

    # Hard REJECT conditions
    if conc_flag and el_pct > 5.0:
        current_rec = "REJECT_FOR_PORTFOLIO"
    elif high_risk_post >= 0.20:
        current_rec = "REJECT_FOR_PORTFOLIO"
    elif el_pct > 5.0:
        current_rec = "REJECT_FOR_PORTFOLIO"

    # CAUTION conditions (upgrade from ACCEPT only)
    if current_rec == "ACCEPT":
        if conc_flag or seg_flag or geo_flag or emp_flag:
            current_rec = "CAUTION"
        elif 2.0 < el_pct <= 5.0:
            current_rec = "CAUTION"
        elif 0.15 <= high_risk_post < 0.20:
            current_rec = "CAUTION"

    # Never downgrade from REJECT
    if state.get("portfolio_recommendation") == "REJECT_FOR_PORTFOLIO":
        current_rec = "REJECT_FOR_PORTFOLIO"

    return {"portfolio_recommendation": current_rec}


# ─── Node 6: LLM Narrative ───────────────────────────────────────────────────

def node_llm_narrative(state: PortfolioState) -> dict:
    """Generate a professional portfolio manager narrative using Gemini."""
    macro = state["macro_data"]
    rec = state.get("portfolio_recommendation", "ACCEPT")
    flags = state.get("concentration_flags") or []

    fallback = (
        f"Portfolio analysis complete. Recommendation: {rec}. "
        f"Sector concentration at {state.get('post_approval_sector_pct', 0):.1%} post-approval "
        f"(threshold {state.get('sector_threshold_used', 0.35):.1%}), "
        f"EL impact ₹{state.get('expected_loss_impact', 0):,.0f} "
        f"({state.get('el_increase_pct', 0):.1f}% portfolio EL increase). "
        f"Flags: {', '.join(flags) if flags else 'None'}. "
        f"Macro stress: {macro.stress_scenario}."
    )

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        logger.info("No GEMINI_API_KEY — using deterministic narrative fallback")
        return {"narrative": fallback}

    prompt = f"""You are a portfolio risk manager at an Indian bank. Review the following portfolio impact analysis for a new personal loan application and write a concise professional narrative.

--- PORTFOLIO ANALYSIS RESULTS ---
Recommendation: {rec}
Sector Concentration (current): {state.get('sector_concentration_pct', 0):.1%}
Sector Concentration (post-approval): {state.get('post_approval_sector_pct', 0):.1%}
Sector Threshold Used: {state.get('sector_threshold_used', 0.35):.1%}
Geographic Concentration Flag: {state.get('geographic_concentration_flag', False)}
Employer Concentration Flag: {state.get('employer_concentration_flag', False)}
Segment Concentration Flag (Self-Employed): {state.get('segment_concentration_flag', False)}
High-Risk Band (current): {state.get('high_risk_pct_current', 0):.1%}
High-Risk Band (post-approval): {state.get('high_risk_pct_post_approval', 0):.1%}
Expected Loss Impact: INR {state.get('expected_loss_impact', 0):,.0f}
EL Increase: {state.get('el_increase_pct', 0):.2f}%
Portfolio EL Before: INR {state.get('portfolio_el_before', 0):,.0f}
Portfolio EL After: INR {state.get('portfolio_el_after', 0):,.0f}
Macro Stress Scenario: {macro.stress_scenario}
Flags Fired: {flags}

--- INSTRUCTIONS ---
Write a 3-sentence portfolio manager narrative for the Senior Credit Officer. Be data-driven, cite the specific percentages, and state clearly whether this loan improves, maintains, or deteriorates portfolio health. End with the portfolio recommendation and why.
Respond ONLY with the narrative text — no JSON, no headers."""

    try:
        # Try new google.genai SDK first (google-genai package)
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
            )
            narrative = response.text.strip()
        except ImportError:
            # Fall back to legacy google.generativeai (still functional)
            import google.generativeai as genai_legacy
            genai_legacy.configure(api_key=api_key)
            model = genai_legacy.GenerativeModel("gemini-2.5-flash")
            response = model.generate_content(
                prompt,
                generation_config={"max_output_tokens": 400},
            )
            narrative = response.text.strip()

        if narrative:
            return {"narrative": narrative}
    except Exception as exc:
        logger.warning(f"Gemini narrative generation failed: {exc} — using fallback")

    return {"narrative": fallback}


# ─── Graph Assembly ───────────────────────────────────────────────────────────

def _build_portfolio_graph():
    from langgraph.graph import StateGraph, END

    g = StateGraph(PortfolioState)

    g.add_node("sector_concentration",     node_sector_concentration)
    g.add_node("geographic_concentration", node_geographic_concentration)
    g.add_node("risk_band_distribution",   node_risk_band_distribution)
    g.add_node("expected_loss",            node_expected_loss)
    g.add_node("recommendation_synthesis", node_recommendation_synthesis)
    g.add_node("llm_narrative",            node_llm_narrative)

    g.set_entry_point("sector_concentration")
    g.add_edge("sector_concentration",     "geographic_concentration")
    g.add_edge("geographic_concentration", "risk_band_distribution")
    g.add_edge("risk_band_distribution",   "expected_loss")
    g.add_edge("expected_loss",            "recommendation_synthesis")
    g.add_edge("recommendation_synthesis", "llm_narrative")
    g.add_edge("llm_narrative",            END)

    return g.compile()


_GRAPH = None

def _get_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = _build_portfolio_graph()
    return _GRAPH


# ─── Public Entry Function ────────────────────────────────────────────────────

def run_portfolio_agent(
    application: ApplicationFormData,
    credit_output: CreditAgentOutput,
    fraud_output: FraudAgentOutput,
    compliance_output: ComplianceAgentOutput,
    bank_data: BankStatementData,
    macro_data: MacroConfigData,
    portfolio_stats: PortfolioStats,
) -> dict:
    """
    Run the Portfolio Intelligence Agent.

    Returns a dict with field names matching backend/schemas.py PortfolioOutput:
      - portfolio_recommendation
      - sector_concentration_current  (= sector_concentration_pct)
      - sector_concentration_new      (= post_approval_sector_pct)
      - geo_concentration_current     (derived from top_state_pct)
      - geo_concentration_new         (adjusted top_state_pct)
      - risk_band_distribution
      - el_impact_inr                 (= expected_loss_impact)
      - concentration_flags
      - similar_cases_npa_rate        (from macro sector_npa_rates)
      - cot_reasoning                 (= narrative — used by crew_runner)
    """
    # If compliance is BLOCK_FAIL, skip deep analysis and reject immediately
    if compliance_output.overall_status == "BLOCK_FAIL":
        fallback_narrative = (
            "Portfolio analysis skipped: compliance block detected. "
            "Application automatically receives REJECT_FOR_PORTFOLIO due to compliance failure."
        )
        return {
            "portfolio_recommendation": "REJECT_FOR_PORTFOLIO",
            "sector_concentration_current": portfolio_stats.sector_distribution.get("PERSONAL", 0.0),
            "sector_concentration_new": portfolio_stats.sector_distribution.get("PERSONAL", 0.0),
            "geo_concentration_current": 0.0,
            "geo_concentration_new": 0.0,
            "risk_band_distribution": portfolio_stats.risk_band_distribution,
            "el_impact_inr": 0.0,
            "concentration_flags": ["compliance_block_fail"],
            "similar_cases_npa_rate": macro_data.sector_npa_rates.get("PERSONAL", 0.038),
            "cot_reasoning": fallback_narrative,
            # Extended fields (for test runner)
            "post_approval_sector_pct": portfolio_stats.sector_distribution.get("PERSONAL", 0.0),
            "concentration_flag": False,
            "geographic_concentration_flag": False,
            "employer_concentration_flag": False,
            "segment_concentration_flag": False,
            "expected_loss_impact": 0.0,
            "el_increase_pct": 0.0,
            "portfolio_el_before": portfolio_stats.portfolio_el_total,
            "portfolio_el_after": portfolio_stats.portfolio_el_total,
            "post_approval_risk_distribution": portfolio_stats.risk_band_distribution,
            "total_portfolio_loans": portfolio_stats.total_loans,
            "total_portfolio_exposure": portfolio_stats.total_exposure_inr,
            "narrative": fallback_narrative,
        }

    initial_state: PortfolioState = {
        "application": application,
        "credit_output": credit_output,
        "fraud_output": fraud_output,
        "compliance_output": compliance_output,
        "bank_data": bank_data,
        "macro_data": macro_data,
        "portfolio_stats": portfolio_stats,
        # Computed fields — defaults
        "sector_concentration_pct": 0.0,
        "post_approval_sector_pct": 0.0,
        "concentration_flag": False,
        "sector_threshold_used": 0.35,
        "geographic_concentration_flag": False,
        "city_concentration_flag": False,
        "top_state": "",
        "top_state_pct": 0.0,
        "employer_concentration_flag": False,
        "employer_pct": 0.0,
        "segment_concentration_flag": False,
        "high_risk_pct_current": 0.0,
        "high_risk_pct_post_approval": 0.0,
        "risk_band_flag": False,
        "post_approval_risk_distribution": {},
        "pd_adjusted": 0.0,
        "lgd": 0.45,
        "ead": 0.0,
        "expected_loss_impact": 0.0,
        "portfolio_el_before": 0.0,
        "portfolio_el_after": 0.0,
        "el_increase_pct": 0.0,
        "portfolio_recommendation": "ACCEPT",
        "concentration_flags": [],
        "narrative": "",
    }

    final_state = _get_graph().invoke(initial_state)

    sector_npa = macro_data.sector_npa_rates.get("PERSONAL", 0.038)

    # Map to backend/schemas.py PortfolioOutput field names
    return {
        "portfolio_recommendation":    final_state["portfolio_recommendation"],

        # Fields used by crew_runner.py and backend PortfolioOutput
        "sector_concentration_current": final_state["sector_concentration_pct"],
        "sector_concentration_new":    final_state["post_approval_sector_pct"],
        "geo_concentration_current":   final_state["top_state_pct"],
        "geo_concentration_new":       (
            (final_state["top_state_pct"] * portfolio_stats.total_loans + (
                1 if final_state.get("geographic_concentration_flag") else 0
            )) / max(portfolio_stats.total_loans + 1, 1)
        ),
        "risk_band_distribution":      portfolio_stats.risk_band_distribution,
        "el_impact_inr":               final_state["expected_loss_impact"],
        "concentration_flags":         final_state["concentration_flags"],
        "similar_cases_npa_rate":      sector_npa,
        "cot_reasoning":               final_state["narrative"],

        # Extended fields (used by test runner and frontend)
        "post_approval_sector_pct":    final_state["post_approval_sector_pct"],
        "concentration_flag":          final_state["concentration_flag"],
        "geographic_concentration_flag": final_state["geographic_concentration_flag"],
        "employer_concentration_flag": final_state["employer_concentration_flag"],
        "segment_concentration_flag":  final_state["segment_concentration_flag"],
        "expected_loss_impact":        final_state["expected_loss_impact"],
        "el_increase_pct":             final_state["el_increase_pct"],
        "portfolio_el_before":         final_state["portfolio_el_before"],
        "portfolio_el_after":          final_state["portfolio_el_after"],
        "post_approval_risk_distribution": final_state.get("post_approval_risk_distribution", {}),
        "total_portfolio_loans":       portfolio_stats.total_loans,
        "total_portfolio_exposure":    portfolio_stats.total_exposure_inr,
        "narrative":                   final_state["narrative"],
    }
