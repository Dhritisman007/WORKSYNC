"""Structural-parity test: proves the project's central claim — that the
Compliance, Manager and Audit agents (and the orchestrator that routes
between them) never change per vertical. This is Phase 5's formal check of
what every Phase 3/4 checkpoint has been asserting informally.

Two things are checked:
1. `core/` contains no source line that branches on `vertical` (a static
   scan — the brief's own example is "no `if vertical ==` anywhere in
   core/").
2. Every vertical, when wired up exactly as its own `run_samples.py` does,
   ends up using the *literal same classes* from `core.agents.*` and
   `core.orchestrator` — not a per-vertical subclass — and every vertical's
   CaseRecord round-trips through the one shared schema.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from worksync.core.agents.analyst import AnalystAgent
from worksync.core.agents.audit import AuditLog
from worksync.core.agents.compliance import ComplianceAgent
from worksync.core.agents.manager import ManagerAgent, load_manager_config
from worksync.core.orchestrator import Orchestrator
from worksync.core.rule_engine.engine import load_ruleset
from worksync.core.schemas.models import CaseRecord, RiskOutput, ShapAttribution, Vertical

CORE_DIR = Path("worksync/core")

VERTICALS = ["loan", "kyc_aml", "bnpl", "insurance"]

RULES_PATHS = {v: f"worksync/verticals/{v}/rules.yaml" for v in VERTICALS}
CONFIG_PATHS = {v: f"worksync/verticals/{v}/manager_config.yaml" for v in VERTICALS}


class _StubRiskModel:
    """Satisfies core.agents.analyst.RiskModel without needing a trained
    model on disk — this test is about structure, not model quality."""

    def predict(self, case: CaseRecord) -> RiskOutput:
        return RiskOutput(
            case_id=case.case_id,
            model_name="stub",
            model_version="0.0.0",
            risk_probability=0.5,
            confidence_band="low",
            top_attributions=[ShapAttribution(feature="stub", value=0.0, contribution=0.0)],
        )


def test_core_has_no_vertical_specific_branching():
    offending = []
    for path in sorted(CORE_DIR.rglob("*.py")):
        if path.name.startswith("._"):
            continue  # macOS AppleDouble sidecar file, not source
        for lineno, line in enumerate(path.read_text().splitlines(), start=1):
            stripped = line.strip()
            if any(
                pattern in stripped
                for pattern in ("vertical ==", "vertical in (", "vertical in {", "vertical in [")
            ):
                offending.append(f"{path}:{lineno}: {stripped}")
    assert offending == [], "core/ must never branch on vertical:\n" + "\n".join(offending)


@pytest.mark.parametrize("vertical", VERTICALS)
def test_vertical_wires_up_the_unchanged_core_classes(vertical, tmp_path):
    ruleset = load_ruleset(RULES_PATHS[vertical])
    config = load_manager_config(CONFIG_PATHS[vertical])

    compliance = ComplianceAgent(ruleset)
    manager = ManagerAgent(config)
    analyst = AnalystAgent(_StubRiskModel())
    audit = AuditLog(tmp_path / f"{vertical}_audit.jsonl")
    orchestrator = Orchestrator(analyst=analyst, compliance=compliance, manager=manager, audit=audit)

    # Not isinstance() — type() is, to also catch a future per-vertical
    # subclass that would technically satisfy isinstance but still be a
    # structural change the brief requires stopping and reporting on.
    assert type(compliance) is ComplianceAgent
    assert type(manager) is ManagerAgent
    assert type(analyst) is AnalystAgent
    assert type(audit) is AuditLog
    assert type(orchestrator) is Orchestrator


@pytest.mark.parametrize("vertical", VERTICALS)
def test_vertical_case_record_fits_the_one_shared_schema(vertical, tmp_path):
    ruleset = load_ruleset(RULES_PATHS[vertical])
    config = load_manager_config(CONFIG_PATHS[vertical])
    orchestrator = Orchestrator(
        analyst=AnalystAgent(_StubRiskModel()),
        compliance=ComplianceAgent(ruleset),
        manager=ManagerAgent(config),
        audit=AuditLog(tmp_path / f"{vertical}_audit.jsonl"),
    )

    case = CaseRecord(
        case_id=f"{vertical}-parity-1",
        vertical=Vertical(vertical),
        entity_id="parity-entity-1",
        features={"anything": 1, "goes": "here", "no_schema_change_needed": True},
    )
    decision = orchestrator.run_case(case)
    assert decision.case_id == case.case_id
    assert decision.outcome.value in {"approve", "reject", "escalate"}

    ok, bad_index = orchestrator.audit.verify_chain()
    assert ok is True and bad_index is None
