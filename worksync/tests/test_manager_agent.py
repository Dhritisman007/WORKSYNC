from worksync.core.agents.manager import ManagerConfig, ManagerAgent
from worksync.core.schemas.models import (
    AgentName,
    ComplianceFlag,
    ComplianceFlags,
    DecisionOutcome,
    Envelope,
    RiskOutput,
    Severity,
    Vertical,
)

CONFIG = ManagerConfig(
    grey_band_lower=0.4,
    grey_band_upper=0.6,
    high_confidence_bands=["high"],
    escalate_on_soft_flag=False,
)


def _envelope(risk: RiskOutput, flags: ComplianceFlags) -> Envelope:
    return Envelope(
        case_id=risk.case_id,
        vertical=Vertical.DUMMY,
        agent=AgentName.MANAGER,
        payload={"risk": risk.model_dump(mode="json"), "compliance": flags.model_dump(mode="json")},
    )


def _risk(prob: float, band: str = "high") -> RiskOutput:
    return RiskOutput(
        case_id="c1", model_name="dummy", model_version="0.1.0",
        risk_probability=prob, confidence_band=band,
    )


def _flags(*fs: ComplianceFlag) -> ComplianceFlags:
    return ComplianceFlags(case_id="c1", ruleset_version="0.1.0", flags=list(fs))


def test_auto_approve_clearly_good_high_confidence():
    manager = ManagerAgent(CONFIG)
    out = manager.handle(_envelope(_risk(0.1, "high"), _flags()))
    assert out.payload["outcome"] == DecisionOutcome.APPROVE.value


def test_auto_reject_clearly_bad_high_confidence():
    manager = ManagerAgent(CONFIG)
    out = manager.handle(_envelope(_risk(0.9, "high"), _flags()))
    assert out.payload["outcome"] == DecisionOutcome.REJECT.value


def test_grey_band_escalates_even_at_high_confidence():
    manager = ManagerAgent(CONFIG)
    out = manager.handle(_envelope(_risk(0.5, "high"), _flags()))
    assert out.payload["outcome"] == DecisionOutcome.ESCALATE.value
    assert "GREY_BAND_SCORE" in out.payload["reason_codes"]


def test_low_confidence_escalates_regardless_of_score():
    manager = ManagerAgent(CONFIG)
    out = manager.handle(_envelope(_risk(0.05, "low"), _flags()))
    assert out.payload["outcome"] == DecisionOutcome.ESCALATE.value
    assert "LOW_CONFIDENCE" in out.payload["reason_codes"]


def test_hard_flag_forces_reject_even_with_clearly_good_score():
    manager = ManagerAgent(CONFIG)
    hard = ComplianceFlag(
        rule_id="R-1", description="d", source_regulation="s",
        severity=Severity.HARD, action="reject", verified=False,
    )
    out = manager.handle(_envelope(_risk(0.05, "high"), _flags(hard)))
    assert out.payload["outcome"] == DecisionOutcome.REJECT.value
    assert out.payload["hard_flags"] == ["R-1"]


def test_hard_flag_with_escalate_action_never_auto_approves():
    manager = ManagerAgent(CONFIG)
    hard = ComplianceFlag(
        rule_id="R-2", description="d", source_regulation="s",
        severity=Severity.HARD, action="escalate", verified=False,
    )
    out = manager.handle(_envelope(_risk(0.05, "high"), _flags(hard)))
    assert out.payload["outcome"] == DecisionOutcome.ESCALATE.value


def test_soft_flag_recorded_but_does_not_block_auto_decision_by_default():
    manager = ManagerAgent(CONFIG)
    soft = ComplianceFlag(
        rule_id="R-3", description="d", source_regulation="s",
        severity=Severity.SOFT, action="annotate", verified=False,
    )
    out = manager.handle(_envelope(_risk(0.05, "high"), _flags(soft)))
    assert out.payload["outcome"] == DecisionOutcome.APPROVE.value
    assert "SOFT_FLAG:R-3" in out.payload["reason_codes"]


def test_soft_flag_escalates_when_config_says_so():
    config = ManagerConfig(**{**CONFIG.model_dump(), "escalate_on_soft_flag": True})
    manager = ManagerAgent(config)
    soft = ComplianceFlag(
        rule_id="R-4", description="d", source_regulation="s",
        severity=Severity.SOFT, action="annotate", verified=False,
    )
    out = manager.handle(_envelope(_risk(0.05, "high"), _flags(soft)))
    assert out.payload["outcome"] == DecisionOutcome.ESCALATE.value
