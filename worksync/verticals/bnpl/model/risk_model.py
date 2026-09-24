"""The RiskModel used by the Analyst Agent at inference time for the credit
card/BNPL vertical. Same shape as the loan/KYC-AML risk models, minus the
categorical-column aggregation step (this vertical has no categoricals)."""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import shap

from worksync.core.schemas.models import CaseRecord, RiskOutput, ShapAttribution
from worksync.verticals.bnpl.adapter import NUMERIC_FEATURES
from worksync.verticals.bnpl.model.train import ARTIFACT_DIR, MODEL_VERSION, confidence_band


class BnplRiskModel:
    def __init__(self, artifact_dir: Path = ARTIFACT_DIR):
        self.preprocessor = joblib.load(artifact_dir / "preprocessor.joblib")
        self.base_model = joblib.load(artifact_dir / "lgbm_base.joblib")
        self.calibrated_model = joblib.load(artifact_dir / "lgbm_calibrated.joblib")
        self._explainer = shap.TreeExplainer(self.base_model)

    def predict(self, case: CaseRecord) -> RiskOutput:
        row = {k: case.features.get(k) for k in NUMERIC_FEATURES}
        X = pd.DataFrame([row])

        Xt = self.preprocessor.transform(X)
        Xt_dense = Xt.toarray() if hasattr(Xt, "toarray") else np.asarray(Xt)

        probability = float(self.calibrated_model.predict_proba(Xt_dense)[0, 1])
        band = confidence_band(probability)

        shap_values = self._explainer.shap_values(Xt_dense)
        if isinstance(shap_values, list):
            shap_values = shap_values[1]
        contributions = np.asarray(shap_values).reshape(-1)

        pairs = list(zip(NUMERIC_FEATURES, contributions))
        top = sorted(pairs, key=lambda kv: abs(kv[1]), reverse=True)[:5]
        attributions = [
            ShapAttribution(
                feature=name,
                value=float(case.features.get(name)) if case.features.get(name) is not None else 0.0,
                contribution=round(float(contribution), 5),
            )
            for name, contribution in top
        ]

        return RiskOutput(
            case_id=case.case_id,
            model_name="lightgbm_calibrated",
            model_version=MODEL_VERSION,
            risk_probability=round(probability, 6),
            confidence_band=band,
            top_attributions=attributions,
        )
