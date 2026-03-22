"""
agents_base.py — Shared data loaded once at startup.
Imported by tools.py and graphs.py.
"""
from __future__ import annotations
import json, logging
from pathlib import Path

logger = logging.getLogger(__name__)

_RULES: list[dict] = []
_PORTFOLIO: list[dict] = []

LGD_MAP = {"HOME": 0.25, "AUTO": 0.40, "PERSONAL": 0.65, "EDUCATION": 0.55}

def load_compliance_rules(yaml_path: str = "data/compliance_rules.yaml"):
    global _RULES
    path = Path(yaml_path)
    if path.exists():
        import yaml
        data = yaml.safe_load(path.read_text())
        _RULES = data.get("rules", [])
    else:
        _RULES = [
            {"id":"C001","description":"Age 21-65","expression":"21 <= applicant_age <= 65",
             "severity":"BLOCK","regulation":"RBI Retail Lending 2023","error_message":"Age {applicant_age} outside 21-65"},
            {"id":"C002","description":"FOIR <= 55%","expression":"foir <= 0.55",
             "severity":"BLOCK","regulation":"RBI Guidelines 2023","error_message":"FOIR {foir:.1%} exceeds 55% limit"},
            {"id":"C003","description":"LTV home <= 80%","expression":"ltv_ratio <= (0.80 if loan_amount < 3000000 else 0.75) if loan_product == 'HOME' else True",
             "severity":"BLOCK","regulation":"RBI Housing Finance Circular","error_message":"LTV {ltv_ratio:.1%} exceeds limit"},
            {"id":"C005","description":"Bureau check done","expression":"bureau_check_done == True",
             "severity":"BLOCK","regulation":"RBI Credit Info Act 2005","error_message":"Bureau check not completed"},
            {"id":"C006","description":"KYC complete","expression":"kyc_pan_present and kyc_aadhaar_present",
             "severity":"BLOCK","regulation":"RBI KYC Master Direction 2016","error_message":"Incomplete KYC"},
            {"id":"C010","description":"PAN not blacklisted","expression":"pan_blacklisted == False",
             "severity":"BLOCK","regulation":"RBI Fraud Registry","error_message":"PAN on fraud registry"},
            {"id":"C007","description":"Income proof < 24m","expression":"income_proof_age_months <= 24",
             "severity":"WARN","regulation":"Internal Policy","warning_message":"Income proof {income_proof_age_months}m old"},
            {"id":"C012","description":"AML for large personal loans",
             "expression":"not (loan_product == 'PERSONAL' and loan_amount > 1000000) or aml_declaration_present",
             "severity":"WARN","regulation":"PMLA/RBI AML","warning_message":"Personal loan >10L needs AML declaration"},
        ]
    logger.info(f"Loaded {len(_RULES)} compliance rules")

def load_portfolio(csv_path: str = "data/portfolio_loans.csv"):
    global _PORTFOLIO
    path = Path(csv_path)
    if path.exists():
        import csv
        with open(path) as f:
            _PORTFOLIO = list(csv.DictReader(f))
        logger.info(f"Loaded {len(_PORTFOLIO)} portfolio loans")
    else:
        logger.warning(f"Portfolio CSV not found at {csv_path} — portfolio checks use defaults")
        _PORTFOLIO = []
