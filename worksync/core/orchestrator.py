"""Runs the fixed pipeline for any vertical: it is handed agent instances and
a CaseRecord, and knows nothing else about the vertical. This is what lets
the same orchestrator run all four BFSI verticals — and the dummy one.
"""

from __future__ import annotations

from worksync.core.agents.audit import AuditLog
from worksync.core.agents.analyst import AnalystAgent
from worksync.core.agents.compliance import ComplianceAgent
from worksync.core.agents.manager import ManagerAgent
from worksync.core.schemas.models import AgentName, CaseRecord, Decision, Envelope


class Orchestrator:
    def __init__(
        self,
        analyst: AnalystAgent,
        compliance: ComplianceAgent,
        manager: ManagerAgent,
        audit: AuditLog,
        model_version: str | None = None,
    ):
        self.analyst = analyst
        self.compliance = compliance
        self.manager = manager
        self.audit = audit
        self.model_version = model_version

    def run_case(self, case: CaseRecord) -> Decision:
        case_payload = case.model_dump(mode="json")

        risk_env = self.analyst.handle(
            Envelope(case_id=case.case_id, vertical=case.vertical, agent=AgentName.ANALYST, payload=case_payload)
        )
        self.audit.log(
            case.case_id,
            case.vertical,
            AgentName.ANALYST,
            {"input": case_payload, "output": risk_env.payload},
            model_version=self.model_version,
        )

        compliance_env = self.compliance.handle(
            Envelope(case_id=case.case_id, vertical=case.vertical, agent=AgentName.COMPLIANCE, payload=case_payload)
        )
        self.audit.log(
            case.case_id,
            case.vertical,
            AgentName.COMPLIANCE,
            {"input": case_payload, "output": compliance_env.payload},
            ruleset_version=self.compliance.ruleset.version,
        )

        manager_input = {"risk": risk_env.payload, "compliance": compliance_env.payload}
        manager_env = self.manager.handle(
            Envelope(case_id=case.case_id, vertical=case.vertical, agent=AgentName.MANAGER, payload=manager_input)
        )
        self.audit.log(
            case.case_id,
            case.vertical,
            AgentName.MANAGER,
            {"input": manager_input, "output": manager_env.payload},
        )

        return Decision.model_validate(manager_env.payload)
