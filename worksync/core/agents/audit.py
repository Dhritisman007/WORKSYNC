"""Append-only, hash-chained audit log.

The Audit Agent is log-only: it observes each agent's input, output and
timestamp but never changes the pipeline's flow or its decision. Each entry
stores sha256(this entry's own fields + the previous entry's hash), so
tampering with or deleting any past entry breaks every hash after it —
`verify_chain()` detects that. `replay()` proves a logged case is
reproducible by re-running it through the same agent instances and checking
the decision matches.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worksync.core.schemas.models import (
    SCHEMA_VERSION,
    AgentName,
    AuditEntry,
    CaseRecord,
    Envelope,
    Vertical,
)

GENESIS_HASH = "0" * 64


def _hash_entry(entry_without_hash: AuditEntry, prev_hash: str) -> str:
    canonical = entry_without_hash.model_dump_json(exclude={"entry_hash"})
    return hashlib.sha256((canonical + prev_hash).encode("utf-8")).hexdigest()


class AuditLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    def _last_hash(self) -> str:
        last_line: str | None = None
        with self.path.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    last_line = line
        if last_line is None:
            return GENESIS_HASH
        return AuditEntry.model_validate_json(last_line).entry_hash

    def log(
        self,
        case_id: str,
        vertical: Vertical,
        agent: AgentName,
        payload: dict[str, Any],
        model_version: str | None = None,
        ruleset_version: str | None = None,
        timestamp: datetime | None = None,
    ) -> AuditEntry:
        prev_hash = self._last_hash()
        entry = AuditEntry.model_construct(
            schema_version=SCHEMA_VERSION,
            case_id=case_id,
            vertical=vertical,
            agent=agent,
            timestamp=timestamp or datetime.now(timezone.utc),
            model_version=model_version,
            ruleset_version=ruleset_version,
            payload=payload,
            prev_hash=prev_hash,
            entry_hash="",
        )
        entry_hash = _hash_entry(entry, prev_hash)
        entry = entry.model_copy(update={"entry_hash": entry_hash})
        with self.path.open("a") as f:
            f.write(entry.model_dump_json() + "\n")
        return entry

    def read_all(self) -> list[AuditEntry]:
        entries = []
        with self.path.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(AuditEntry.model_validate_json(line))
        return entries

    def entries_for_case(self, case_id: str) -> list[AuditEntry]:
        return [e for e in self.read_all() if e.case_id == case_id]

    def verify_chain(self) -> tuple[bool, int | None]:
        """Returns (True, None) if every entry's hash and link check out, or
        (False, index) for the first entry that fails."""
        prev = GENESIS_HASH
        for i, entry in enumerate(self.read_all()):
            if entry.prev_hash != prev:
                return False, i
            recomputed = _hash_entry(entry.model_copy(update={"entry_hash": ""}), entry.prev_hash)
            if recomputed != entry.entry_hash:
                return False, i
            prev = entry.entry_hash
        return True, None

    def replay(self, case_id: str, analyst, compliance, manager) -> bool:
        """Re-run a logged case through the given Analyst/Compliance/Manager
        agent instances and confirm it reaches the same decision that was
        logged. Returns False if the case has no complete logged trace."""
        entries = {e.agent: e for e in self.entries_for_case(case_id)}
        if not {AgentName.ANALYST, AgentName.COMPLIANCE, AgentName.MANAGER} <= entries.keys():
            return False

        analyst_entry = entries[AgentName.ANALYST]
        case = CaseRecord.model_validate(analyst_entry.payload["input"])

        risk_env = analyst.handle(
            Envelope(case_id=case.case_id, vertical=case.vertical, agent=AgentName.ANALYST, payload=case.model_dump(mode="json"))
        )
        compliance_env = compliance.handle(
            Envelope(case_id=case.case_id, vertical=case.vertical, agent=AgentName.COMPLIANCE, payload=case.model_dump(mode="json"))
        )
        manager_env = manager.handle(
            Envelope(
                case_id=case.case_id,
                vertical=case.vertical,
                agent=AgentName.MANAGER,
                payload={"risk": risk_env.payload, "compliance": compliance_env.payload},
            )
        )

        logged_decision = entries[AgentName.MANAGER].payload["output"]
        return (
            manager_env.payload["outcome"] == logged_decision["outcome"]
            and manager_env.payload["reason_codes"] == logged_decision["reason_codes"]
        )
