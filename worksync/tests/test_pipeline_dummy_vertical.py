"""Proves the shared core runs a full case end to end (Phase 2 checkpoint):
Ingestion -> CaseRecord -> Analyst + Compliance -> Manager -> Decision,
observed by the Audit Agent, with a replayable, tamper-evident log."""

import pytest

from worksync.core.agents.analyst import AnalystAgent
from worksync.core.agents.audit import AuditLog
from worksync.core.agents.compliance import ComplianceAgent
from worksync.core.agents.manager import ManagerAgent, load_manager_config
from worksync.core.orchestrator import Orchestrator
from worksync.core.rule_engine.engine import load_ruleset
from worksync.core.schemas.models import CaseRecord, DecisionOutcome, Vertical
from worksync.tests.fixtures.dummy_vertical.model import DummyRiskModel

FIXTURES = "worksync/tests/fixtures/dummy_vertical"


@pytest.fixture
def orchestrator(tmp_path):
    ruleset = load_ruleset(f"{FIXTURES}/rules.yaml")
    config = load_manager_config(f"{FIXTURES}/manager_config.yaml")
    return Orchestrator(
        analyst=AnalystAgent(DummyRiskModel()),
        compliance=ComplianceAgent(ruleset),
        manager=ManagerAgent(config),
        audit=AuditLog(tmp_path / "audit.jsonl"),
        model_version="dummy-0.1.0",
    )


def _case(case_id: str, **features) -> CaseRecord:
    return CaseRecord(case_id=case_id, vertical=Vertical.DUMMY, entity_id="e1", features=features)


def test_clean_case_runs_end_to_end_and_auto_approves(orchestrator):
    decision = orchestrator.run_case(_case("case-approve", raw_score=0.1, on_watchlist=False, amount=500))
    assert decision.outcome == DecisionOutcome.APPROVE

    entries = orchestrator.audit.entries_for_case("case-approve")
    assert [e.agent.value for e in entries] == ["analyst", "compliance", "manager"]

    ok, bad_index = orchestrator.audit.verify_chain()
    assert ok is True and bad_index is None


def test_watchlisted_case_is_rejected_by_hard_flag(orchestrator):
    decision = orchestrator.run_case(_case("case-reject", raw_score=0.05, on_watchlist=True, amount=500))
    assert decision.outcome == DecisionOutcome.REJECT
    assert decision.hard_flags == ["DUMMY-HARD-001"]


def test_grey_band_case_escalates(orchestrator):
    decision = orchestrator.run_case(_case("case-escalate", raw_score=0.5, on_watchlist=False, amount=500))
    assert decision.outcome == DecisionOutcome.ESCALATE


def test_replay_reproduces_the_logged_decision(orchestrator):
    orchestrator.run_case(_case("case-replay", raw_score=0.1, on_watchlist=False, amount=500))
    assert orchestrator.audit.replay("case-replay", orchestrator.analyst, orchestrator.compliance, orchestrator.manager) is True


def test_replay_fails_after_the_log_is_tampered_with(orchestrator, tmp_path):
    orchestrator.run_case(_case("case-tamper", raw_score=0.1, on_watchlist=False, amount=500))

    import json

    lines = orchestrator.audit.path.read_text().splitlines()
    manager_line = json.loads(lines[-1])
    manager_line["payload"]["output"]["outcome"] = "reject"  # tamper with the recorded decision
    lines[-1] = json.dumps(manager_line)
    orchestrator.audit.path.write_text("\n".join(lines) + "\n")

    assert orchestrator.audit.replay("case-tamper", orchestrator.analyst, orchestrator.compliance, orchestrator.manager) is False


def test_multiple_cases_share_one_hash_chain_without_interference(orchestrator):
    d1 = orchestrator.run_case(_case("multi-1", raw_score=0.1, on_watchlist=False, amount=500))
    d2 = orchestrator.run_case(_case("multi-2", raw_score=0.9, on_watchlist=False, amount=500))
    assert d1.outcome == DecisionOutcome.APPROVE
    assert d2.outcome == DecisionOutcome.REJECT

    ok, bad_index = orchestrator.audit.verify_chain()
    assert ok is True and bad_index is None
    assert orchestrator.audit.replay("multi-1", orchestrator.analyst, orchestrator.compliance, orchestrator.manager) is True
    assert orchestrator.audit.replay("multi-2", orchestrator.analyst, orchestrator.compliance, orchestrator.manager) is True
