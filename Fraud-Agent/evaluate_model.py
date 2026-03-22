"""Evaluation metrics for the Isolation Forest fraud model."""
import numpy as np
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    confusion_matrix, classification_report, roc_auc_score,
)
from fraud_model import load_model, _generate_training_data, FRAUD_FEATURES
import math


def sigmoid_prob(model, X):
    """Convert decision_function scores to fraud probabilities."""
    raw_scores = model.decision_function(X)
    return np.array([1 / (1 + math.exp(8 * r)) for r in raw_scores])


def evaluate():
    model = load_model()

    # ── Generate labeled test data (separate seed from training) ──────────
    rng = np.random.RandomState(99)  # different seed = unseen data

    n_clean, n_fraud, n_border = 2000, 300, 100

    clean = np.column_stack([
        rng.normal(750, 35, n_clean).clip(680, 900),
        rng.choice([0, 1], n_clean, p=[0.7, 0.3]),
        np.zeros(n_clean), np.zeros(n_clean), np.zeros(n_clean),
        rng.uniform(0.80, 1.0, n_clean),
        rng.uniform(0.75, 1.0, n_clean),
        np.zeros(n_clean), np.zeros(n_clean), np.zeros(n_clean),
        rng.binomial(1, 0.03, n_clean).astype(float),
        rng.uniform(150, 600, n_clean),
        rng.binomial(1, 0.02, n_clean).astype(float),
        np.zeros(n_clean), np.zeros(n_clean),
    ])

    fraud = np.column_stack([
        rng.normal(450, 60, n_fraud).clip(300, 580),
        rng.choice([5, 6, 7, 8, 9], n_fraud),
        rng.choice([3, 4, 5, 6], n_fraud),
        rng.choice([2, 3, 4], n_fraud),
        rng.choice([2, 3, 4, 5], n_fraud),
        rng.uniform(0.10, 0.40, n_fraud),
        rng.uniform(0.05, 0.35, n_fraud),
        rng.choice([0.8, 1.0], n_fraud, p=[0.2, 0.8]),
        rng.binomial(1, 0.6, n_fraud).astype(float),
        rng.choice([1, 2], n_fraud).astype(float),
        rng.binomial(1, 0.75, n_fraud).astype(float),
        rng.uniform(5, 35, n_fraud),
        rng.binomial(1, 0.7, n_fraud).astype(float),
        rng.binomial(1, 0.8, n_fraud).astype(float),
        rng.binomial(1, 0.85, n_fraud).astype(float),
    ])

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

    X_test = np.vstack([clean, fraud, borderline])
    # Labels: 0 = clean, 1 = fraud, borderline treated as fraud (suspicious)
    y_true = np.array([0]*n_clean + [1]*n_fraud + [1]*n_border)

    # ── Model predictions ─────────────────────────────────────────────────
    probs = sigmoid_prob(model, X_test)

    # Isolation Forest native: -1 = anomaly, 1 = normal
    y_raw = model.predict(X_test)
    y_pred_native = np.where(y_raw == -1, 1, 0)

    # Threshold-based: prob >= 0.45 = fraud
    y_pred_045 = (probs >= 0.45).astype(int)
    # Threshold-based: prob >= 0.50 = fraud
    y_pred_050 = (probs >= 0.50).astype(int)

    total = len(y_true)
    n_pos = y_true.sum()
    n_neg = total - n_pos

    print("=" * 65)
    print("  FRAUD ISOLATION FOREST — EVALUATION REPORT")
    print("=" * 65)
    print(f"\nTest set: {total} samples ({n_neg} clean, {n_pos} fraud/borderline)")
    print(f"Features: {len(FRAUD_FEATURES)}")
    print(f"Model: StandardScaler + IsolationForest(n_estimators=500, contamination=0.10)")
    print(f"\nFraud probability distribution:")
    print(f"  Clean    — mean: {probs[:n_clean].mean():.4f}, median: {np.median(probs[:n_clean]):.4f}, "
          f"min: {probs[:n_clean].min():.4f}, max: {probs[:n_clean].max():.4f}")
    print(f"  Fraud    — mean: {probs[n_clean:n_clean+n_fraud].mean():.4f}, median: {np.median(probs[n_clean:n_clean+n_fraud]):.4f}, "
          f"min: {probs[n_clean:n_clean+n_fraud].min():.4f}, max: {probs[n_clean:n_clean+n_fraud].max():.4f}")
    print(f"  Border   — mean: {probs[n_clean+n_fraud:].mean():.4f}, median: {np.median(probs[n_clean+n_fraud:]):.4f}, "
          f"min: {probs[n_clean+n_fraud:].min():.4f}, max: {probs[n_clean+n_fraud:].max():.4f}")

    for name, y_pred in [
        ("Native IForest (anomaly=-1)", y_pred_native),
        ("Threshold ≥ 0.45", y_pred_045),
        ("Threshold ≥ 0.50", y_pred_050),
    ]:
        print(f"\n{'─'*65}")
        print(f"  {name}")
        print(f"{'─'*65}")
        acc = accuracy_score(y_true, y_pred)
        prec = precision_score(y_true, y_pred, zero_division=0)
        rec = recall_score(y_true, y_pred, zero_division=0)
        f1 = f1_score(y_true, y_pred, zero_division=0)
        cm = confusion_matrix(y_true, y_pred)
        tn, fp, fn, tp = cm.ravel()

        print(f"  Accuracy  : {acc:.4f}  ({int(acc*total)}/{total})")
        print(f"  Precision : {prec:.4f}  (of predicted fraud, how many are actually fraud)")
        print(f"  Recall    : {rec:.4f}  (of actual fraud, how many did we catch)")
        print(f"  F1 Score  : {f1:.4f}")
        print(f"\n  Confusion Matrix:")
        print(f"                  Predicted Clean  Predicted Fraud")
        print(f"  Actual Clean       {tn:>5}            {fp:>5}")
        print(f"  Actual Fraud       {fn:>5}            {tp:>5}")
        print(f"\n  False Positive Rate: {fp/(fp+tn):.4f}  (clean flagged as fraud)")
        print(f"  False Negative Rate: {fn/(fn+tp):.4f}  (fraud missed as clean)")

    # ── ROC AUC (probability-based) ───────────────────────────────────────
    auc = roc_auc_score(y_true, probs)
    print(f"\n{'─'*65}")
    print(f"  ROC AUC Score: {auc:.4f}")
    print(f"{'─'*65}")
    print(f"\n  AUC Interpretation:")
    if auc >= 0.95:
        print(f"  → Excellent: model separates clean vs fraud very well")
    elif auc >= 0.85:
        print(f"  → Good: strong separation with some overlap on borderline cases")
    elif auc >= 0.75:
        print(f"  → Fair: moderate separation, rules engine needed to compensate")
    else:
        print(f"  → Poor: model needs retraining")

    print(f"\n{'='*65}")
    print(f"  Full Classification Report (threshold ≥ 0.45)")
    print(f"{'='*65}")
    print(classification_report(y_true, y_pred_045, target_names=["Clean", "Fraud"]))


if __name__ == "__main__":
    evaluate()
