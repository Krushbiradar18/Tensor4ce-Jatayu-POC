# XGBoost Credit Risk Model - Evaluation Report

**Dataset:** External_Cibil_Dataset.xlsx (Kaggle Real CIBIL Dataset)
**Model:** XGBoostClassifier
**Total Samples:** 51,336
**Train / Test Split:** 80% / 20% (stratified)
**Training Samples:** 41,068
**Test Samples:** 10,268
**Features Used:** 26 (23 numeric + 3 categorical)

---

## Target Class Distribution

| Class | Label | Count | % of Dataset |
|---|---|---|---|
| P1 | Low Risk | 5,803 | 11.3% |
| P2 | Medium-Low Risk | 32,199 | 62.7% |
| P3 | Medium-High Risk | 7,452 | 14.5% |
| P4 | High Risk | 5,882 | 11.5% |

> Dataset is imbalanced: P2 represents 62.7% of all samples.

---

## Overall Metrics

| Metric | Value |
|---|---|
| **Accuracy** | **0.9127 (91.27%)** |
| Macro Precision | 0.9164 |
| Macro Recall | 0.8672 |
| **Macro F1 Score** | **0.8901** |
| Weighted Precision | 0.9131 |
| Weighted Recall | 0.9127 |
| Weighted F1 Score | 0.9118 |

> **Macro** = unweighted average across all 4 classes (treats each class equally).
> **Weighted** = average weighted by class sample count (reflects real distribution).

---

## Per-Class Metrics

| Class | Precision | Recall | F1 Score | Support (test set) |
|---|---|---|---|---|
| P1 (Low Risk) | 0.9716 | 0.8553 | 0.9098 | 1,161 |
| P2 (Med-Low) | 0.9183 | 0.9640 | 0.9406 | 6,440 |
| P3 (Med-High) | 0.7783 | 0.7344 | 0.7557 | 1,491 |
| P4 (High Risk) | 0.9972 | 0.9150 | 0.9543 | 1,176 |

### What Precision / Recall / F1 Mean

| Metric | Simple Meaning | Why It Matters for Credit |
|---|---|---|
| **Precision** | Of all predicted as this class, how many actually were? | High precision on P4 = fewer good applicants wrongly rejected |
| **Recall** | Of all actual in this class, how many did we catch? | High recall on P4 = fewer actual defaulters slipping through |
| **F1 Score** | Harmonic mean of Precision and Recall | Balanced class-level performance |

---

## Confusion Matrix

> Rows = **Actual** class | Columns = **Predicted** class

| Actual \ Predicted | P1 (Low) | P2 (Med-Low) | P3 (Med-High) | P4 (High) |
|---|---|---|---|---|
| P1 (Low Risk) | 993 | 165 | 3 | 0 |
| P2 (Med-Low) | 23 | 6208 | 209 | 0 |
| P3 (Med-High) | 6 | 387 | 1095 | 3 |
| P4 (High Risk) | 0 | 0 | 100 | 1076 |

### How to Read This
- **Diagonal** = correct predictions
- **Off-diagonal** = misclassifications
- A large value in (Row P4, Col P3) = high-risk applicants wrongly predicted as medium-high risk (most dangerous miss)

---

## True Positive / True Negative / False Positive / False Negative

> Computed using **One-vs-Rest** per class.

| Class | TP | TN | FP | FN |
|---|---|---|---|---|
| P1 (Low Risk) | 993 | 9,078 | 29 | 168 |
| P2 (Med-Low) | 6,208 | 3,276 | 552 | 232 |
| P3 (Med-High) | 1,095 | 8,465 | 312 | 396 |
| P4 (High Risk) | 1,076 | 9,089 | 3 | 100 |

### What Each Term Means

| Term | Definition | Credit Risk Implication |
|---|---|---|
| **TP (True Positive)** | Correctly predicted as this risk class | Model correctly identified the risk level |
| **TN (True Negative)** | Correctly predicted as NOT this class | Model correctly excluded wrong risk |
| **FP (False Positive)** | Predicted as this class but actually different | For P4: good applicant wrongly rejected (business loss) |
| **FN (False Negative)** | Actually this class but predicted as different | For P4: actual defaulter not caught (credit loss) |

> **FN on P4 (High Risk) is the most costly error** - it means a likely defaulter was approved.

---

## Top 10 Most Important Features

| Rank | Feature | Importance Score | What It Represents |
|---|---|---|---|
| 1 | `Credit_Score` | 0.807094 | CIBIL bureau score (300-900) |
| 2 | `enq_L6m` | 0.036761 | Enquiries in last 6 months |
| 3 | `num_times_delinquent` | 0.019708 | Total missed payments ever |
| 4 | `enq_L12m` | 0.015153 | Enquiries in last 12 months |
| 5 | `num_std` | 0.014298 | Accounts in good standing |
| 6 | `time_since_recent_enq` | 0.008419 | Months since last credit enquiry |
| 7 | `num_deliq_12mts` | 0.007761 | Delinquencies in last 12 months |
| 8 | `num_deliq_6mts` | 0.006888 | Delinquencies in last 6 months |
| 9 | `recent_level_of_deliq` | 0.006675 | Severity of most recent delinquency |
| 10 | `pct_of_active_TLs_ever` | 0.005856 | % of trade lines ever active |

---

## Model Configuration

| Parameter | Value |
|---|---|
| Algorithm | XGBoostClassifier |
| Objective | multi:softprob (4-class probability output) |
| Number of Classes | 4 (P1 / P2 / P3 / P4) |
| Estimators | 300 |
| Max Depth | 6 |
| Learning Rate | 0.1 |
| Subsample | 0.8 |
| Column Sample by Tree | 0.8 |
| Eval Metric | mlogloss (multi-class log loss) |
| Train/Test Split | 80% / 20% stratified |
| Total Features | 26 |
| Training Dataset | Real Kaggle CIBIL Dataset (51,336 rows) |

---

## Why XGBoost Over Random Forest

| Factor | Random Forest (Previous) | XGBoost (Current) |
|---|---|---|
| Training data | 4,000 synthetic rows | 51,336 real CIBIL rows |
| Accuracy | ~80.6% (on synthetic test) | See above (on real data) |
| SHAP explainability | Approximate | Exact via TreeExplainer |
| Probability calibration | Moderate | Well-calibrated softprob |
| Overfitting control | Max depth only | Regularization + subsampling |
| Industry standard for credit scoring | No | Yes |
| Regulatory acceptance | Less common | Widely accepted |
