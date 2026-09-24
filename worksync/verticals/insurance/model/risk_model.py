"""The RiskModel used by the Analyst Agent at inference time for the
insurance claims vertical. Same shape as the loan/KYC-AML risk models."""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import shap

from worksync.core.schemas.models import CaseRecord, RiskOutput, ShapAttribution
from worksync.verticals.insurance.adapter import (
    BOOLEAN_FEATURES,
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
)
from worksync.verticals.insurance.model.train import ARTIFACT_DIR, MODEL_VERSION, confidence_band

_ALL_INPUT_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES + BOOLEAN_FEATURES


class InsuranceRiskModel:
    def __init__(self, artifact_dir: Path = ARTIFACT_DIR):
        self.preprocessor = joblib.load(artifact_dir / "preprocessor.joblib")
        self.base_model = joblib.load(artifact_dir / "lgbm_base.joblib")
        self.calibrated_model = joblib.load(artifact_dir / "lgbm_calibrated.joblib")
        self._explainer = shap.TreeExplainer(self.base_model)
        self._transformed_feature_names = self._build_feature_name_map()

    def _build_feature_name_map(self) -> list[str]:
        names = list(NUMERIC_FEATURES) + list(BOOLEAN_FEATURES)
        onehot = self.preprocessor.named_transformers_["categorical"].named_steps["onehot"]
        for col, categories in zip(CATEGORICAL_FEATURES, onehot.categories_):
            names.extend([col] * len(categories))
        return names

    def predict(self, case: CaseRecord) -> RiskOutput:
        row = {k: case.features.get(k) for k in _ALL_INPUT_FEATURES}
        X = pd.DataFrame([row])
        for col in BOOLEAN_FEATURES:
            X[col] = X[col].astype(float)

        Xt = self.preprocessor.transform(X)
        Xt_dense = Xt.toarray() if hasattr(Xt, "toarray") else np.asarray(Xt)

        probability = float(self.calibrated_model.predict_proba(Xt_dense)[0, 1])
        band = confidence_band(probability)

        shap_values = self._explainer.shap_values(Xt_dense)
        if isinstance(shap_values, list):
            shap_values = shap_values[1]
        contributions = np.asarray(shap_values).reshape(-1)

        aggregated: dict[str, float] = {}
        for name, contribution in zip(self._transformed_feature_names, contributions):
            aggregated[name] = aggregated.get(name, 0.0) + float(contribution)

        top = sorted(aggregated.items(), key=lambda kv: abs(kv[1]), reverse=True)[:5]
        attributions = [
            ShapAttribution(
                feature=name,
                value=self._reportable_value(name, case),
                contribution=round(contribution, 5),
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

    @staticmethod
    def _reportable_value(feature_name: str, case: CaseRecord) -> float:
        raw = case.features.get(feature_name)
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            return float(raw)
        if isinstance(raw, bool):
            return 1.0 if raw else 0.0
        return 1.0 if raw is not None else 0.0
