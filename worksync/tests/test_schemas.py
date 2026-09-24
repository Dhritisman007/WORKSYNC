from worksync.core.schemas.models import (
    CaseRecord,
    ComplianceFlag,
    ComplianceFlags,
    Decision,
    DecisionOutcome,
    Envelope,
    RiskOutput,
    Severity,
    Vertical,
)


def make_case(vertical: Vertical, features: dict) -> CaseRecord:
    return CaseRecord(
        case_id=f"{vertical.value}-0001",
        vertical=vertical,
        entity_id="entity-0001",
        features=features,
    )


def test_case_record_fits_every_vertical_without_schema_changes():
    loan = make_case(Vertical.LOAN, {"loan_amount": 50000, "income": 120000})
    kyc = make_case(Vertical.KYC_AML, {"pep_match": False, "sanctions_hit": False})
    bnpl = make_case(Vertical.BNPL, {"txn_count_30d": 12, "avg_txn_amount": 340.5})
    insurance = make_case(Vertical.INSURANCE, {"claim_amount": 2200, "claim_type": "auto"})

    for case in (loan, kyc, bnpl, insurance):
        assert case.schema_version == "1.0.0"
        round_tripped = CaseRecord.model_validate_json(case.model_dump_json())
        assert round_tripped == case


def test_compliance_flags_hard_flag_detection():
    flags = ComplianceFlags(
        case_id="loan-0001",
        ruleset_version="0.1.0",
        flags=[
            ComplianceFlag(
                rule_id="R-001",
                description="test rule",
                source_regulation="N/A",
                severity=Severity.SOFT,
                action="annotate",
                verified=False,
            )
        ],
    )
    assert flags.has_hard_flag is False

    flags.flags.append(
        ComplianceFlag(
            rule_id="R-002",
            description="hard test rule",
            source_regulation="N/A",
            severity=Severity.HARD,
            action="reject",
            verified=False,
        )
    )
    assert flags.has_hard_flag is True


def test_decision_and_envelope_round_trip():
    decision = Decision(
        case_id="loan-0001",
        outcome=DecisionOutcome.ESCALATE,
        reason_codes=["GREY_BAND_SCORE"],
        risk_probability=0.5,
        confidence_band="medium",
    )
    envelope = Envelope(
        case_id="loan-0001",
        vertical=Vertical.LOAN,
        agent="manager",
        payload=decision.model_dump(mode="json"),
    )
    assert envelope.payload["outcome"] == "escalate"


def test_risk_output_probability_bounds():
    risk = RiskOutput(
        case_id="loan-0001",
        model_name="lightgbm",
        model_version="0.1.0",
        risk_probability=0.42,
        confidence_band="high",
    )
    assert 0.0 <= risk.risk_probability <= 1.0
