from __future__ import annotations

from typing import Protocol

from worksync.core.agents.base_agent import BaseAgent
from worksync.core.schemas.models import AgentName, CaseRecord, Envelope, RiskOutput


class RiskModel(Protocol):
    """What the Analyst Agent needs from a model. Phase 3+ implementations
    (LightGBM/XGBoost + SHAP) and the Phase 2 dummy stub both satisfy this,
    so `AnalystAgent` itself never changes between verticals."""

    def predict(self, case: CaseRecord) -> RiskOutput: ...


class AnalystAgent(BaseAgent):
    """Vertical-agnostic: delegates scoring to whatever RiskModel it was
    configured with. Never branches on `vertical`."""

    name = AgentName.ANALYST

    def __init__(self, model: RiskModel):
        self.model = model

    def handle(self, envelope: Envelope) -> Envelope:
        case = CaseRecord.model_validate(envelope.payload)
        risk = self.model.predict(case)
        return Envelope(
            case_id=case.case_id,
            vertical=case.vertical,
            agent=self.name,
            payload=risk.model_dump(mode="json"),
        )
