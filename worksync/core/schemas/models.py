"""Versioned data contracts shared by every vertical and every agent.

Nothing in this module may import from worksync.verticals.*. Any field that
is specific to one vertical belongs in that vertical's adapter output inside
`CaseRecord.features`, not as a new top-level field here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0.0"


class Vertical(str, Enum):
    LOAN = "loan"
    KYC_AML = "kyc_aml"
    BNPL = "bnpl"
    INSURANCE = "insurance"
    DUMMY = "dummy"


class AgentName(str, Enum):
    INGESTION = "ingestion"
    ANALYST = "analyst"
    COMPLIANCE = "compliance"
    MANAGER = "manager"
    AUDIT = "audit"


class Severity(str, Enum):
    HARD = "hard"
    SOFT = "soft"
    INFO = "info"


class DecisionOutcome(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    ESCALATE = "escalate"


class DocumentRef(BaseModel):
    """Metadata placeholder for a document/image input. OCR is a stretch goal;
    for now the document is represented by metadata only."""

    model_config = ConfigDict(extra="forbid")

    doc_type: str
    verified: bool = False
    reference: str | None = None


class CaseRecord(BaseModel):
    """The versioned contract every vertical adapter must produce.

    Every vertical must fit into this without adding top-level fields.
    Vertical-specific data goes inside `features`.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    case_id: str
    vertical: Vertical
    entity_id: str
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    features: dict[str, Any] = Field(default_factory=dict)
    documents: list[DocumentRef] = Field(default_factory=list)


class ShapAttribution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feature: str
    value: float
    contribution: float


class RiskOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    case_id: str
    model_name: str
    model_version: str
    risk_probability: float = Field(ge=0.0, le=1.0)
    confidence_band: str
    top_attributions: list[ShapAttribution] = Field(default_factory=list)


class ComplianceFlag(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    description: str
    source_regulation: str
    severity: Severity
    action: str
    verified: bool = False
    triggered: bool = True
    evidence: dict[str, Any] = Field(default_factory=dict)


class ComplianceFlags(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    case_id: str
    ruleset_version: str
    flags: list[ComplianceFlag] = Field(default_factory=list)

    @property
    def has_hard_flag(self) -> bool:
        return any(f.severity == Severity.HARD and f.triggered for f in self.flags)


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    case_id: str
    outcome: DecisionOutcome
    reason_codes: list[str] = Field(default_factory=list)
    risk_probability: float | None = None
    confidence_band: str | None = None
    hard_flags: list[str] = Field(default_factory=list)


class AuditEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    case_id: str
    vertical: Vertical
    agent: AgentName
    timestamp: datetime
    model_version: str | None = None
    ruleset_version: str | None = None
    payload: dict[str, Any]
    prev_hash: str
    entry_hash: str


class Envelope(BaseModel):
    """The only object agents exchange. Agents never call each other
    directly; only the orchestrator routes envelopes between them."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    case_id: str
    vertical: Vertical
    agent: AgentName
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any]
