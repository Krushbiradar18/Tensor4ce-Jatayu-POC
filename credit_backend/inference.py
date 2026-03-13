"""
ML Inference Service - Loads trained model and provides risk scoring with explainability.
Uses permutation-based feature importance as SHAP substitute (no external SHAP lib needed).
"""

import joblib
import json
import numpy as np
import os
from typing import Dict, List, Tuple, Any

MODEL_DIR = os.path.join(os.path.dirname(__file__), 'models_artifacts')


class CreditRiskInferenceService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._load_artifacts()

    def _load_artifacts(self):
        model_path = os.path.join(MODEL_DIR, 'risk_model.pkl')
        scaler_path = os.path.join(MODEL_DIR, 'scaler.pkl')
        metadata_path = os.path.join(MODEL_DIR, 'model_metadata.json')

        try:
            self.model = joblib.load(model_path)
            self.scaler = joblib.load(scaler_path)
            with open(metadata_path) as f:
                self.metadata = json.load(f)
        except Exception as exc:
            raise RuntimeError(
                "Failed to load model artifacts. This usually means your local "
                "numpy/scikit-learn versions do not match the versions used to "
                "train/pickle the model. Reinstall dependencies from requirements.txt "
                "and retrain artifacts with `python train_model.py` if needed. "
                f"Original error: {exc}"
            ) from exc

        self.features = self.metadata['features']
        self.num_features = self.metadata['num_features']
        self.cat_features = self.metadata['cat_features']
        self.le_dict = self.metadata['label_encoders']
        self.risk_map = self.metadata['risk_map']          # "0" -> "P4", etc.
        self.label_map = self.metadata['label_map']        # "P1" -> "High Risk"
        self.feature_importance = self.metadata['feature_importance']
        self.accuracy = self.metadata['accuracy']

    @property
    def model_accuracy(self) -> float:
        return self.accuracy

    def _encode_features(self, user_data: Dict[str, Any]) -> "pd.DataFrame":
        """Build feature DataFrame from user data dict (preserves feature names)."""
        import pandas as pd
        row = {}
        for feat in self.num_features:
            row[feat] = float(user_data.get(feat, 0) or 0)
        for cat in self.cat_features:
            val = str(user_data.get(cat, ''))
            enc_map = self.le_dict.get(cat, {})
            row[cat + '_enc'] = float(enc_map.get(val, 0))
        return pd.DataFrame([row])

    def _compute_shap_approximation(
        self, feature_df: "pd.DataFrame", baseline_proba: np.ndarray
    ) -> Dict[str, float]:
        """
        Approximate SHAP values using leave-one-out feature importance.
        For each feature, zero it out and measure change in predicted risk class probability.
        """
        import pandas as pd
        contributions = {}
        scaled_base = pd.DataFrame(
            self.scaler.transform(feature_df), columns=self.features
        )
        base_pred = self.model.predict_proba(scaled_base)[0]
        pred_class = int(self.model.predict(scaled_base)[0])

        for feat in self.features:
            perturbed = feature_df.copy()
            perturbed[feat] = 0.0
            perturbed_scaled = pd.DataFrame(
                self.scaler.transform(perturbed), columns=self.features
            )
            perturbed_proba = self.model.predict_proba(perturbed_scaled)[0]
            delta = float(base_pred[pred_class] - perturbed_proba[pred_class])
            contributions[feat] = delta

        return contributions

    def predict(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run full inference pipeline: encode → scale → predict → explain.
        Returns dict with score, category, probabilities, and feature contributions.
        """
        import pandas as pd
        fv = self._encode_features(user_data)
        scaled = pd.DataFrame(self.scaler.transform(fv), columns=self.features)

        pred_class = int(self.model.predict(scaled)[0])
        probas = self.model.predict_proba(scaled)[0]

        approved_flag = self.risk_map[str(pred_class)]
        risk_category = self.label_map[approved_flag]

        # Convert class probabilities to named dict
        class_names = ['Low Risk', 'Medium-Low Risk', 'Medium-High Risk', 'High Risk']
        proba_dict = {class_names[i]: round(float(probas[i]) * 100, 2) for i in range(4)}

        # Risk score: weighted combination → 0 (safe) to 100 (very risky)
        weights = [0, 33, 66, 100]
        risk_score = round(float(sum(probas[i] * weights[i] for i in range(4))), 2)
        confidence = round(float(max(probas)) * 100, 2)

        # Feature contributions via SHAP approximation
        contributions = self._compute_shap_approximation(fv, probas)

        return {
            'pred_class': pred_class,
            'approved_flag': approved_flag,
            'risk_category': risk_category,
            'risk_score': risk_score,
            'confidence': confidence,
            'class_probabilities': proba_dict,
            'feature_contributions': contributions,
            'raw_probas': probas.tolist(),
        }

    def get_top_factors(
        self, contributions: Dict[str, float], n: int = 5
    ) -> Tuple[List[Dict], List[Dict]]:
        """Split contributions into top risk-increasing and risk-decreasing factors."""
        sorted_contribs = sorted(contributions.items(), key=lambda x: x[1], reverse=True)

        FEATURE_DESCRIPTIONS = {
            'Credit_Score': 'Credit bureau score',
            'num_times_delinquent': 'Total delinquency count',
            'recent_level_of_deliq': 'Recent delinquency severity',
            'num_deliq_6mts': 'Delinquencies in last 6 months',
            'num_deliq_12mts': 'Delinquencies in last 12 months',
            'num_times_30p_dpd': 'Days past due (30+ days)',
            'num_times_60p_dpd': 'Days past due (60+ days)',
            'num_std': 'Standard (on-time) trade lines',
            'num_sub': 'Sub-standard accounts',
            'num_dbt': 'Doubtful accounts',
            'num_lss': 'Loss accounts',
            'tot_enq': 'Total credit enquiries',
            'enq_L12m': 'Enquiries in last 12 months',
            'enq_L6m': 'Enquiries in last 6 months',
            'time_since_recent_enq': 'Months since last credit enquiry',
            'CC_utilization': 'Credit card utilization %',
            'PL_utilization': 'Personal loan utilization %',
            'max_unsec_exposure_inPct': 'Max unsecured exposure %',
            'pct_of_active_TLs_ever': '% of ever-active trade lines',
            'pct_currentBal_all_TL': '% current balance across all trade lines',
            'AGE': 'Applicant age',
            'NETMONTHLYINCOME': 'Net monthly income',
            'Time_With_Curr_Empr': 'Months with current employer',
            'MARITALSTATUS_enc': 'Marital status',
            'EDUCATION_enc': 'Education level',
            'GENDER_enc': 'Gender',
        }

        risk_factors = []
        positive_factors = []

        for feat, contrib in sorted_contribs:
            desc = FEATURE_DESCRIPTIONS.get(feat, feat.replace('_', ' ').title())
            entry = {
                'feature': feat.replace('_enc', '').replace('_', ' ').title(),
                'contribution': round(abs(contrib) * 100, 3),
                'direction': 'increases_risk' if contrib > 0 else 'decreases_risk',
                'description': desc,
            }
            if contrib > 0:
                risk_factors.append(entry)
            else:
                positive_factors.append(entry)

        return risk_factors[:n], positive_factors[:n]


# Singleton instance
inference_service = CreditRiskInferenceService()
