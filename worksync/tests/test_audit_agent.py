import json

import pytest

from worksync.core.agents.audit import AuditLog
from worksync.core.schemas.models import AgentName, Vertical


@pytest.fixture
def audit_log(tmp_path):
    return AuditLog(tmp_path / "audit.jsonl")


def test_empty_log_verifies(audit_log):
    ok, bad_index = audit_log.verify_chain()
    assert ok is True
    assert bad_index is None


def test_chain_links_sequential_entries(audit_log):
    e1 = audit_log.log("c1", Vertical.DUMMY, AgentName.ANALYST, {"input": {}, "output": {}})
    e2 = audit_log.log("c1", Vertical.DUMMY, AgentName.COMPLIANCE, {"input": {}, "output": {}})
    assert e2.prev_hash == e1.entry_hash
    ok, bad_index = audit_log.verify_chain()
    assert ok is True
    assert bad_index is None


def test_tampering_with_a_past_entry_is_detected(audit_log):
    audit_log.log("c1", Vertical.DUMMY, AgentName.ANALYST, {"input": {}, "output": {"risk_probability": 0.1}})
    audit_log.log("c1", Vertical.DUMMY, AgentName.COMPLIANCE, {"input": {}, "output": {}})
    audit_log.log("c1", Vertical.DUMMY, AgentName.MANAGER, {"input": {}, "output": {"outcome": "approve"}})

    ok_before, _ = audit_log.verify_chain()
    assert ok_before is True

    lines = audit_log.path.read_text().splitlines()
    first_entry = json.loads(lines[0])
    first_entry["payload"]["output"]["risk_probability"] = 0.99  # tamper
    lines[0] = json.dumps(first_entry)
    audit_log.path.write_text("\n".join(lines) + "\n")

    ok_after, bad_index = audit_log.verify_chain()
    assert ok_after is False
    assert bad_index == 0


def test_deleting_an_entry_breaks_the_chain(audit_log):
    audit_log.log("c1", Vertical.DUMMY, AgentName.ANALYST, {"input": {}, "output": {}})
    audit_log.log("c1", Vertical.DUMMY, AgentName.COMPLIANCE, {"input": {}, "output": {}})
    audit_log.log("c1", Vertical.DUMMY, AgentName.MANAGER, {"input": {}, "output": {}})

    lines = audit_log.path.read_text().splitlines()
    del lines[1]
    audit_log.path.write_text("\n".join(lines) + "\n")

    ok, bad_index = audit_log.verify_chain()
    assert ok is False
    assert bad_index == 1


def test_entries_for_case_filters_and_preserves_order(audit_log):
    audit_log.log("c1", Vertical.DUMMY, AgentName.ANALYST, {"input": {}, "output": {"n": 1}})
    audit_log.log("c2", Vertical.DUMMY, AgentName.ANALYST, {"input": {}, "output": {"n": 99}})
    audit_log.log("c1", Vertical.DUMMY, AgentName.COMPLIANCE, {"input": {}, "output": {"n": 2}})

    c1_entries = audit_log.entries_for_case("c1")
    assert [e.payload["output"]["n"] for e in c1_entries] == [1, 2]
