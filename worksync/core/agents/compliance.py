from __future__ import annotations

from worksync.core.agents.base_agent import BaseAgent
from worksync.core.rule_engine.engine import RuleSet, evaluate_ruleset
from worksync.core.schemas.models import AgentName, CaseRecord, ComplianceFlags, Envelope


class ComplianceAgent(BaseAgent):
    """Vertical-agnostic: evaluates whatever RuleSet it was configured with.

    Never branches on `vertical` — the rules themselves are the only
    vertical-specific input.
    """

    name = AgentName.COMPLIANCE

    def __init__(self, ruleset: RuleSet):
        self.ruleset = ruleset

    def handle(self, envelope: Envelope) -> Envelope:
        case = CaseRecord.model_validate(envelope.payload)
        flags = evaluate_ruleset(self.ruleset, case.features)
        result = ComplianceFlags(
            case_id=case.case_id,
            ruleset_version=self.ruleset.version,
            flags=flags,
        )
        return Envelope(
            case_id=case.case_id,
            vertical=case.vertical,
            agent=self.name,
            payload=result.model_dump(mode="json"),
        )
