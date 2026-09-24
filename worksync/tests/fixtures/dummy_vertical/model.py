"""A stub RiskModel used only to prove the shared core works end to end in
Phase 2. Real models (LightGBM + XGBoost + SHAP) arrive in Phase 3."""

from __future__ import annotations

from worksync.core.schemas.models import CaseRecord, RiskOutput, ShapAttribution

MODEL_VERSION = "dummy-0.1.0"


class DummyRiskModel:
    def predict(self, case: CaseRecord) -> RiskOutput:
        raw_score = float(case.features.get("raw_score", 0.5))
        confidence_band = "high" if abs(raw_score - 0.5) >= 0.2 else "low"
        return RiskOutput(
            case_id=case.case_id,
            model_name="dummy",
            model_version=MODEL_VERSION,
            risk_probability=raw_score,
            confidence_band=confidence_band,
            top_attributions=[
                ShapAttribution(feature="raw_score", value=raw_score, contribution=raw_score - 0.5)
            ],
        )
