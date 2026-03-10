"""
Train and save the credit risk model artifacts.
Run once: python train_model.py
Saves to: models_artifacts/risk_model.pkl, scaler.pkl, model_metadata.json
"""

import os
import json
import numpy as np
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "models_artifacts")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Feature spec ─────────────────────────────────────────────────────────────
NUM_FEATURES = [
    "Credit_Score", "num_times_delinquent", "recent_level_of_deliq",
    "num_deliq_6mts", "num_deliq_12mts", "num_times_30p_dpd", "num_times_60p_dpd",
    "num_std", "num_sub", "num_dbt", "num_lss",
    "tot_enq", "enq_L12m", "enq_L6m", "time_since_recent_enq",
    "CC_utilization", "PL_utilization", "max_unsec_exposure_inPct",
    "pct_of_active_TLs_ever", "pct_currentBal_all_TL",
    "AGE", "NETMONTHLYINCOME", "Time_With_Curr_Empr",
]
CAT_FEATURES = ["MARITALSTATUS", "EDUCATION", "GENDER"]
FEATURES = NUM_FEATURES + [c + "_enc" for c in CAT_FEATURES]

LABEL_ENCODERS = {
    "MARITALSTATUS": {"Single": 0, "Married": 1, "Divorced": 2, "Widowed": 3},
    "EDUCATION":     {"10TH": 0, "12TH": 1, "GRADUATE": 2, "POST-GRADUATE": 3, "PROFESSIONAL": 4},
    "GENDER":        {"M": 0, "F": 1, "OTHER": 2},
}

# Risk classes: 0=Low, 1=Med-Low, 2=Med-High, 3=High
RISK_MAP   = {"0": "P1", "1": "P2", "2": "P3", "3": "P4"}
LABEL_MAP  = {"P1": "Low Risk", "P2": "Medium-Low Risk", "P3": "Medium-High Risk", "P4": "High Risk"}

# ── Synthetic training data ───────────────────────────────────────────────────
np.random.seed(42)
N = 4000

def generate_samples(n_per_class):
    rows, labels = [], []
    profiles = [
        # (credit_score_mean, delinq_mean, class_label)
        (750, 0.1, 0),   # Low Risk
        (660, 0.8, 1),   # Med-Low
        (590, 2.5, 2),   # Med-High
        (490, 5.0, 3),   # High Risk
    ]
    for cs_mean, dq_mean, label in profiles:
        for _ in range(n_per_class):
            cs   = int(np.clip(np.random.normal(cs_mean, 40), 300, 900))
            dq   = max(0, int(np.random.poisson(dq_mean)))
            row = [
                cs,                                                   # Credit_Score
                dq,                                                   # num_times_delinquent
                min(dq, np.random.randint(0, 3)),                     # recent_level_of_deliq
                min(dq, np.random.randint(0, 2)),                     # num_deliq_6mts
                dq,                                                   # num_deliq_12mts
                max(0, dq - 1),                                       # num_times_30p_dpd
                max(0, dq - 2),                                       # num_times_60p_dpd
                max(1, 8 - dq),                                       # num_std
                min(dq, 3),                                           # num_sub
                max(0, dq - 3),                                       # num_dbt
                max(0, dq - 4),                                       # num_lss
                abs(int(np.random.normal(3 + dq, 1))),               # tot_enq
                abs(int(np.random.normal(2 + dq * 0.5, 1))),         # enq_L12m
                abs(int(np.random.normal(1 + dq * 0.3, 1))),         # enq_L6m
                max(1, int(np.random.normal(12 - dq, 3))),           # time_since_recent_enq
                float(np.clip(np.random.normal(20 + dq * 8, 10), 0, 100)),   # CC_utilization
                float(np.clip(np.random.normal(10 + dq * 5, 8), 0, 100)),    # PL_utilization
                float(np.clip(np.random.normal(25 + dq * 5, 10), 0, 100)),   # max_unsec_exposure_inPct
                float(np.clip(np.random.normal(80 - dq * 8, 10), 0, 100)),   # pct_of_active_TLs_ever
                float(np.clip(np.random.normal(40 + dq * 5, 10), 0, 100)),   # pct_currentBal_all_TL
                int(np.clip(np.random.normal(35, 8), 22, 70)),        # AGE
                float(np.clip(np.random.normal(40000 - label * 8000, 12000), 8000, 200000)),  # NETMONTHLYINCOME
                max(1, int(np.random.normal(30 - dq * 3, 10))),       # Time_With_Curr_Empr
                # categorical encodings
                np.random.choice([0, 1, 2, 3]),                       # MARITALSTATUS_enc
                np.random.choice([0, 1, 2, 3, 4]),                    # EDUCATION_enc
                np.random.choice([0, 1]),                              # GENDER_enc
            ]
            rows.append(row)
            labels.append(label)
    return np.array(rows, dtype=float), np.array(labels)

X, y = generate_samples(N // 4)

# ── Train ─────────────────────────────────────────────────────────────────────
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

scaler = StandardScaler()
X_train_s = scaler.fit_transform(X_train)
X_test_s  = scaler.transform(X_test)

clf = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42, n_jobs=-1)
clf.fit(X_train_s, y_train)
accuracy = float(clf.score(X_test_s, y_test))
print(f"Model accuracy: {accuracy:.4f}")

feature_importance = {feat: round(float(imp), 6)
                      for feat, imp in zip(FEATURES, clf.feature_importances_)}

# ── Save artifacts ────────────────────────────────────────────────────────────
joblib.dump(clf,    os.path.join(OUTPUT_DIR, "risk_model.pkl"))
joblib.dump(scaler, os.path.join(OUTPUT_DIR, "scaler.pkl"))

metadata = {
    "features":           FEATURES,
    "num_features":       NUM_FEATURES,
    "cat_features":       CAT_FEATURES,
    "label_encoders":     LABEL_ENCODERS,
    "risk_map":           RISK_MAP,
    "label_map":          LABEL_MAP,
    "feature_importance": feature_importance,
    "accuracy":           accuracy,
}
with open(os.path.join(OUTPUT_DIR, "model_metadata.json"), "w") as f:
    json.dump(metadata, f, indent=2)

print(f"Artifacts saved to {OUTPUT_DIR}/")
