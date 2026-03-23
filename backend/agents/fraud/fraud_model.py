"""Fraud Isolation Forest model — training, feature extraction, and inference."""

import json, hashlib, math, pickle
import numpy as np
from pathlib import Path
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

ROOT = Path(__file__).resolve().parent.parent.parent


def _resolve_data_file(*parts: str) -> Path:
    candidates = [
        ROOT.joinpath(*parts),
        ROOT / "data" / Path(*parts),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[-1]

# ── load static configs once ──────────────────────────────────────────────
with open(_resolve_data_file("ip_mock_map.json")) as f:
    IP_PATTERNS = json.load(f)["patterns"]
with open(_resolve_data_file("fraud_blacklist.json")) as f:
    BLACKLIST = {e["pan"] for e in json.load(f)["blacklisted_pans"]}
with open(_resolve_data_file("bureau_mock_rules.json")) as f:
    BUREAU = json.load(f)

FRAUD_FEATURES = [
    "cibil_score", "num_hard_enquiries_6m", "dpd_30_count", "dpd_90_count",
    "emi_bounce_count", "salary_regularity", "income_stability_score",
    "ip_risk_score", "ip_country_mismatch", "application_velocity",
    "device_fingerprint_new", "form_fill_time_seconds",
    "address_pincode_mismatch", "income_loan_ratio_outlier", "enquiry_spike_flag",
]
REQUIRED_APP_FIELDS = ["pan_number", "annual_income", "loan_amount_requested", "ip_metadata"]
MODEL_PATH = Path(__file__).resolve().parent / "isolation_forest.pkl"


# ── helpers ───────────────────────────────────────────────────────────────
def _hash_int(s: str, mod: int = 1000) -> int:
    return int(hashlib.sha256(s.encode()).hexdigest(), 16) % mod


def validate_application(app: dict) -> None:
    """Raise ValueError if required fields are missing or empty."""
    for f in REQUIRED_APP_FIELDS:
        if f not in app or app[f] is None:
            raise ValueError(f"Missing required field: '{f}'")
    pan = app["pan_number"]
    if not isinstance(pan, str) or len(pan.strip()) < 5:
        raise ValueError(f"Invalid pan_number: '{pan}' — must be a valid PAN string")
    ip_meta = app["ip_metadata"]
    for k in ("ip_address", "form_fill_seconds", "device_fingerprint"):
        if k not in ip_meta or not ip_meta[k]:
            raise ValueError(f"Missing required ip_metadata field: '{k}'")
    if float(app["annual_income"]) <= 0:
        raise ValueError("annual_income must be > 0")
    if float(app["loan_amount_requested"]) <= 0:
        raise ValueError("loan_amount_requested must be > 0")


def ip_lookup(ip: str) -> dict:
    """Mock IP geolocation from ip_mock_map.json prefix matching."""
    for p in IP_PATTERNS:
        if ip.startswith(p["prefix"]):
            return p
    return IP_PATTERNS[-1]  # fallback


def bureau_lookup(pan: str) -> dict:
    """Return bureau record from overrides or deterministic hash."""
    overrides = BUREAU.get("pan_overrides", {})
    if pan in overrides:
        return overrides[pan]
    cibil = (_hash_int(pan, 600)) + 300
    return {
        "cibil_score": cibil,
        "num_hard_enquiries_6m": max(0, int(4 - cibil / 200)),
        "dpd_30_count": max(0, int((650 - cibil) / 80)) if cibil < 650 else 0,
        "dpd_90_count": max(0, int((550 - cibil) / 80)) if cibil < 550 else 0,
        "payment_history_score": int(80 * (cibil - 300) / 600 + 20),
        "credit_utilization_pct": round(max(0, min(1, 1 - cibil / 900)), 2),
        "total_outstanding_debt": 0,
    }


def extract_features(app: dict) -> dict:
    """Build the 15-feature fraud vector from a test-case JSON dict."""
    validate_application(app)

    pan = app["pan_number"]
    bur = bureau_lookup(pan)
    ip_info = ip_lookup(app["ip_metadata"]["ip_address"])
    form_fill = float(app["ip_metadata"]["form_fill_seconds"])
    income = float(app["annual_income"])
    loan = float(app["loan_amount_requested"])

    # derived signals
    emi_bounce = max(0, int((650 - bur["cibil_score"]) / 120)) if bur["cibil_score"] < 650 else 0
    salary_reg = round(min(1.0, 0.5 + bur.get("payment_history_score", 50) / 200), 2)
    income_stab = round(min(1.0, salary_reg * 0.8 + 0.2 * (1 - bur.get("credit_utilization_pct", 0.3))), 2)
    app_velocity = 2 if bur["num_hard_enquiries_6m"] >= 5 else (1 if bur["num_hard_enquiries_6m"] >= 3 else 0)
    dev_fp_new = 1 if app["ip_metadata"]["device_fingerprint"].endswith(("004", "005", "010")) else 0
    addr_state = app.get("address", {}).get("state", "")
    ip_state = ip_info.get("region", "")
    pincode_mismatch = 1 if addr_state and ip_state and addr_state.lower() != ip_state.lower() and ip_info["country"] == "IN" else 0
    ratio = loan / income if income > 0 else 99
    outlier = 1 if ratio > 5.0 else 0
    enquiry_spike = 1 if bur["num_hard_enquiries_6m"] >= 5 else 0

    return {
        "cibil_score": bur["cibil_score"],
        "num_hard_enquiries_6m": bur["num_hard_enquiries_6m"],
        "dpd_30_count": bur["dpd_30_count"],
        "dpd_90_count": bur["dpd_90_count"],
        "emi_bounce_count": emi_bounce,
        "salary_regularity": salary_reg,
        "income_stability_score": income_stab,
        "ip_risk_score": ip_info["ip_risk_score"],
        "ip_country_mismatch": 1 if ip_info["country"] != "IN" else 0,
        "application_velocity": app_velocity,
        "device_fingerprint_new": dev_fp_new,
        "form_fill_time_seconds": form_fill,
        "address_pincode_mismatch": pincode_mismatch,
        "income_loan_ratio_outlier": outlier,
        "enquiry_spike_flag": enquiry_spike,
    }


def _to_vector(feat: dict) -> list[float]:
    return [float(feat[k]) for k in FRAUD_FEATURES]


# ── synthetic training data ───────────────────────────────────────────────
def _generate_training_data(n: int = 10000, contamination: float = 0.10) -> np.ndarray:
    """Create synthetic feature matrix — 10k samples, 10% fraud, clear separation."""
    rng = np.random.RandomState(42)
    n_clean = int(n * (1 - contamination))
    n_fraud = n - n_clean

    # ── CLEAN profiles: high cibil, zero risk flags, normal form fill ──
    clean = np.column_stack([
        rng.normal(750, 35, n_clean).clip(680, 900),     # cibil_score — healthy
        rng.choice([0, 1], n_clean, p=[0.7, 0.3]),       # enquiries — 0 or 1
        np.zeros(n_clean),                                 # dpd_30 — none
        np.zeros(n_clean),                                 # dpd_90 — none
        np.zeros(n_clean),                                 # emi_bounce — none
        rng.uniform(0.80, 1.0, n_clean),                  # salary_reg — high
        rng.uniform(0.75, 1.0, n_clean),                  # income_stab — high
        np.zeros(n_clean),                                 # ip_risk — clean
        np.zeros(n_clean),                                 # ip_country_mismatch — no
        np.zeros(n_clean),                                 # app_velocity — 0
        rng.binomial(1, 0.03, n_clean).astype(float),    # dev_fp_new — very rare
        rng.uniform(150, 600, n_clean),                    # form_fill — normal pace
        rng.binomial(1, 0.02, n_clean).astype(float),    # pincode_mismatch — very rare
        np.zeros(n_clean),                                 # income_loan_outlier — no
        np.zeros(n_clean),                                 # enquiry_spike — no
    ])

    # ── FRAUD profiles: low cibil, stacked risk indicators, bot-speed fill ──
    fraud = np.column_stack([
        rng.normal(450, 60, n_fraud).clip(300, 580),      # cibil — clearly bad
        rng.choice([5, 6, 7, 8, 9], n_fraud),             # enquiries — spiking hard
        rng.choice([3, 4, 5, 6], n_fraud),                 # dpd_30 — chronic
        rng.choice([2, 3, 4], n_fraud),                    # dpd_90 — severe
        rng.choice([2, 3, 4, 5], n_fraud),                 # emi_bounce — high
        rng.uniform(0.10, 0.40, n_fraud),                  # salary_reg — very low
        rng.uniform(0.05, 0.35, n_fraud),                  # income_stab — very low
        rng.choice([0.8, 1.0], n_fraud, p=[0.2, 0.8]),   # ip_risk — mostly VPN
        rng.binomial(1, 0.6, n_fraud).astype(float),      # ip_country — often foreign
        rng.choice([1, 2], n_fraud).astype(float),         # velocity — elevated
        rng.binomial(1, 0.75, n_fraud).astype(float),     # dev_fp_new — usually new
        rng.uniform(5, 35, n_fraud),                       # form_fill — bot speed
        rng.binomial(1, 0.7, n_fraud).astype(float),      # pincode_mismatch — common
        rng.binomial(1, 0.8, n_fraud).astype(float),      # income_loan_outlier
        rng.binomial(1, 0.85, n_fraud).astype(float),     # enquiry_spike
    ])

    # ── BORDERLINE: mix of clean + a few bad signals ──
    n_border = int(n * 0.05)
    borderline = np.column_stack([
        rng.normal(640, 30, n_border).clip(580, 700),
        rng.choice([2, 3, 4], n_border),
        rng.choice([0, 1, 2], n_border),
        rng.choice([0, 1], n_border, p=[0.6, 0.4]),
        rng.choice([0, 1], n_border, p=[0.5, 0.5]),
        rng.uniform(0.45, 0.65, n_border),
        rng.uniform(0.40, 0.60, n_border),
        rng.choice([0.0, 0.5, 1.0], n_border, p=[0.4, 0.3, 0.3]),
        rng.binomial(1, 0.2, n_border).astype(float),
        rng.choice([0, 1], n_border).astype(float),
        rng.binomial(1, 0.4, n_border).astype(float),
        rng.uniform(35, 90, n_border),
        rng.binomial(1, 0.3, n_border).astype(float),
        rng.binomial(1, 0.3, n_border).astype(float),
        rng.binomial(1, 0.4, n_border).astype(float),
    ])

    return np.vstack([clean, fraud, borderline])


def train_model() -> Pipeline:
    """Train StandardScaler + IsolationForest pipeline, save to pkl."""
    X = _generate_training_data()
    pipe = Pipeline([
        ("scaler", StandardScaler()),
        ("iforest", IsolationForest(
            contamination=0.10,
            n_estimators=500,
            max_samples=0.7,
            max_features=1.0,
            random_state=42,
        )),
    ])
    pipe.fit(X)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(pipe, f)
    print(f"[fraud_model] Trained on {X.shape[0]} samples, saved to {MODEL_PATH}")
    return pipe


def load_model() -> Pipeline:
    if not MODEL_PATH.exists():
        return train_model()
    with open(MODEL_PATH, "rb") as f:
        return pickle.load(f)


def predict(model: Pipeline, features: dict) -> float:
    """Return fraud_probability ∈ [0,1]. More negative decision_score = more anomalous."""
    vec = np.array([_to_vector(features)])
    raw = model.decision_function(vec)[0]
    # raw typically in [-0.5, 0.15]. Use steep sigmoid for sharp separation.
    # Negative raw = anomaly → high prob. Positive raw = normal → low prob.
    prob = 1 / (1 + math.exp(8 * raw))
    return round(max(0.0, min(1.0, prob)), 4)


def shap_explain(model: Pipeline, features: dict, top_k: int = 5) -> list[dict]:
    """
    Return top-k SHAP feature contributions for this prediction.
    Each entry: {"feature": name, "shap_value": float, "feature_value": value, "direction": "fraud"/"clean"}
    """
    import shap

    vec = np.array([_to_vector(features)])
    scaler = model.named_steps["scaler"]
    iforest = model.named_steps["iforest"]

    vec_scaled = scaler.transform(vec)

    explainer = shap.TreeExplainer(iforest)
    shap_values = explainer.shap_values(vec_scaled)

    contributions = []
    for i, fname in enumerate(FRAUD_FEATURES):
        sv = float(shap_values[0][i])
        contributions.append({
            "feature": fname,
            "shap_value": round(sv, 6),
            "feature_value": features[fname],
            # IsolationForest: negative SHAP = pushes toward anomaly (fraud)
            "direction": "fraud" if sv < 0 else "clean",
        })

    contributions.sort(key=lambda x: abs(x["shap_value"]), reverse=True)
    return contributions[:top_k]
