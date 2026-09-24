"""The Manager Agent: implements bounded authority (docs/manager_authority.md).

Precedence, fixed here and not configurable per vertical:
  1. A triggered hard compliance flag always wins (reject or escalate, per
     that rule's own `action` — never auto-approved through).
  2. Otherwise, low/medium confidence always escalates.
  3. Otherwise, a score inside the grey band escalates.
  4. Otherwise (high confidence, outside grey band, no hard flag), the score
     side of the grey band decides approve vs reject.
  A triggered soft flag never blocks an auto-decision by itself unless the
  vertical config says so (`escalate_on_soft_flag`); either way it is always
  recorded in `reason_codes`.

Only the thresholds below are per-vertical config; the precedence order is
fixed in code so it is provably identical across verticals.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from worksync.core.agents.base_agent import BaseAgent
from worksync.core.schemas.models import (
    AgentName,
    ComplianceFlags,
    Decision,
    DecisionOutcome,
    Envelope,
    RiskOutput,
    Severity,
)


class ManagerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grey_band_lower: float = Field(ge=0.0, le=1.0)
    grey_band_upper: float = Field(ge=0.0, le=1.0)
    high_confidence_bands: list[str]
    escalate_on_soft_flag: bool = False


def load_manager_config(path: str | Path) -> ManagerConfig:
    data = yaml.safe_load(Path(path).read_text())
    return ManagerConfig.model_validate(data)


class ManagerAgent(BaseAgent):
    name = AgentName.MANAGER

    def __init__(self, config: ManagerConfig):
        self.config = config

    def handle(self, envelope: Envelope) -> Envelope:
        risk = RiskOutput.model_validate(envelope.payload["risk"])
        compliance = ComplianceFlags.model_validate(envelope.payload["compliance"])
        decision = self._decide(risk, compliance)
        return Envelope(
            case_id=risk.case_id,
            vertical=envelope.vertical,
            agent=self.name,
            payload=decision.model_dump(mode="json"),
        )

    def _decide(self, risk: RiskOutput, compliance: ComplianceFlags) -> Decision:
        hard_flags = [
            f for f in compliance.flags if f.severity == Severity.HARD and f.triggered
        ]
        soft_flags = [
            f for f in compliance.flags if f.severity == Severity.SOFT and f.triggered
        ]
        soft_reason_codes = [f"SOFT_FLAG:{f.rule_id}" for f in soft_flags]

        if hard_flags:
            actions = {f.action for f in hard_flags}
            outcome = (
                DecisionOutcome.REJECT if "reject" in actions else DecisionOutcome.ESCALATE
            )
            reason_codes = [f"HARD_FLAG:{f.rule_id}" for f in hard_flags] + soft_reason_codes
            return Decision(
                case_id=risk.case_id,
                outcome=outcome,
                reason_codes=reason_codes,
                risk_probability=risk.risk_probability,
                confidence_band=risk.confidence_band,
                hard_flags=[f.rule_id for f in hard_flags],
            )

        if soft_flags and self.config.escalate_on_soft_flag:
            return Decision(
                case_id=risk.case_id,
                outcome=DecisionOutcome.ESCALATE,
                reason_codes=soft_reason_codes,
                risk_probability=risk.risk_probability,
                confidence_band=risk.confidence_band,
            )

        high_confidence = risk.confidence_band in self.config.high_confidence_bands
        in_grey_band = (
            self.config.grey_band_lower <= risk.risk_probability <= self.config.grey_band_upper
        )

        if not high_confidence:
            return Decision(
                case_id=risk.case_id,
                outcome=DecisionOutcome.ESCALATE,
                reason_codes=["LOW_CONFIDENCE"] + soft_reason_codes,
                risk_probability=risk.risk_probability,
                confidence_band=risk.confidence_band,
            )

        if in_grey_band:
            return Decision(
                case_id=risk.case_id,
                outcome=DecisionOutcome.ESCALATE,
                reason_codes=["GREY_BAND_SCORE"] + soft_reason_codes,
                risk_probability=risk.risk_probability,
                confidence_band=risk.confidence_band,
            )

        outcome = (
            DecisionOutcome.APPROVE
            if risk.risk_probability < self.config.grey_band_lower
            else DecisionOutcome.REJECT
        )
        return Decision(
            case_id=risk.case_id,
            outcome=outcome,
            reason_codes=[f"AUTO_{outcome.value.upper()}"] + soft_reason_codes,
            risk_probability=risk.risk_probability,
            confidence_band=risk.confidence_band,
        )
