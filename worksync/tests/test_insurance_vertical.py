"""Insurance claims vertical tests. Skipped automatically if the Kaggle CSV
or trained model artifacts aren't present locally (both are gitignored —
regenerate with `python -m worksync.verticals.insurance.model.train`)."""

from pathlib import Path

import pytest

from worksync.core.rule_engine.engine import evaluate_ruleset, load_ruleset
from worksync.verticals.insurance.adapter import engineer_features, row_to_case

RULES_PATH = "worksync/verticals/insurance/rules.yaml"
ARTIFACT_DIR = Path("worksync/verticals/insurance/model/artifacts")
DATA_PATH = Path("worksync/data/raw/insurance/fraud_oracle.csv")

requires_artifacts = pytest.mark.skipif(
    not (ARTIFACT_DIR / "lgbm_calibrated.joblib").exists(),
    reason="model artifacts not present; run `python -m worksync.verticals.insurance.model.train`",
)
requires_data = pytest.mark.skipif(
    not DATA_PATH.exists(), reason="fraud_oracle.csv not present in data/raw/insurance/"
)


def test_engineer_features_maps_binned_strings_to_midpoints():
    row = {
        "Age": 35,
        "DriverRating": 2,
        "Deductible": 400,
        "WeekOfMonth": 2,
        "WeekOfMonthClaimed": 3,
        "PastNumberOfClaims": "2 to 4",
        "Days_Policy_Accident": "1 to 7",
        "Days_Policy_Claim": "more than 30",
        "AddressChange_Claim": "under 6 months",
        "VehiclePrice": "more than 69000",
        "AgeOfVehicle": "new",
        "AgeOfPolicyHolder": "31 to 35",
        "NumberOfSuppliments": "3 to 5",
        "NumberOfCars": "2 vehicles",
        "Make": "Honda",
        "AccidentArea": "Urban",
        "Sex": "Male",
        "MaritalStatus": "Married",
        "Fault": "Third Party",
        "PolicyType": "Sedan - Liability",
        "VehicleCategory": "Sedan",
        "BasePolicy": "Liability",
        "AgentType": "External",
        "PoliceReportFiled": "No",
        "WitnessPresent": "Yes",
    }
    features = engineer_features(row)
    assert features["past_claims_count"] == 3
    assert features["days_policy_to_accident"] == 4
    assert features["address_change_recency_years"] == 0.25
    assert features["vehicle_price_midpoint"] == 80000
    assert features["vehicle_age_years"] == 0
    assert features["police_report_filed"] is False
    assert features["witness_present"] is True


def test_row_to_case_uses_policy_number_as_entity_id():
    row = {"PolicyNumber": 12345}
    case = row_to_case(row, index=0)
    assert case.case_id == "insurance-12345"
    assert case.entity_id == "12345"


def test_early_claim_triggers_hard_escalate_rule():
    ruleset = load_ruleset(RULES_PATH)
    flags = evaluate_ruleset(ruleset, {"days_policy_to_accident": 4})
    fired = {f.rule_id: f for f in flags}
    assert "INS-TIMING-001" in fired
    assert fired["INS-TIMING-001"].action == "escalate"


def test_high_value_claim_triggers_hard_escalate_rule():
    ruleset = load_ruleset(RULES_PATH)
    flags = evaluate_ruleset(ruleset, {"vehicle_price_midpoint": 80000})
    fired = {f.rule_id for f in flags}
    assert "INS-HIGHVALUE-001" in fired


def test_no_evidence_compound_condition_requires_both_missing():
    ruleset = load_ruleset(RULES_PATH)
    flags = evaluate_ruleset(
        ruleset, {"police_report_filed": False, "witness_present": True}
    )
    fired = {f.rule_id for f in flags}
    assert "INS-NOEVIDENCE-001" not in fired

    flags = evaluate_ruleset(
        ruleset, {"police_report_filed": False, "witness_present": False}
    )
    fired = {f.rule_id for f in flags}
    assert "INS-NOEVIDENCE-001" in fired


def test_all_rules_are_unverified_pending_team_review():
    ruleset = load_ruleset(RULES_PATH)
    assert all(rule.verified is False for rule in ruleset.rules)


@requires_artifacts
@requires_data
def test_risk_model_predicts_a_valid_output_for_a_real_row():
    import pandas as pd

    from worksync.verticals.insurance.model.risk_model import InsuranceRiskModel

    df = pd.read_csv(DATA_PATH, nrows=1)
    case = row_to_case(df.iloc[0], index=0)
    risk = InsuranceRiskModel().predict(case)
    assert 0.0 <= risk.risk_probability <= 1.0
    assert risk.confidence_band in {"low", "medium", "high"}
    assert 1 <= len(risk.top_attributions) <= 5


@requires_artifacts
@requires_data
def test_insurance_pipeline_end_to_end_for_sample_cases(tmp_path):
    import pandas as pd

    from worksync.core.agents.analyst import AnalystAgent
    from worksync.core.agents.audit import AuditLog
    from worksync.core.agents.compliance import ComplianceAgent
    from worksync.core.agents.manager import ManagerAgent, load_manager_config
    from worksync.core.orchestrator import Orchestrator
    from worksync.verticals.insurance.model.risk_model import InsuranceRiskModel

    ruleset = load_ruleset(RULES_PATH)
    config = load_manager_config("worksync/verticals/insurance/manager_config.yaml")
    orchestrator = Orchestrator(
        analyst=AnalystAgent(InsuranceRiskModel()),
        compliance=ComplianceAgent(ruleset),
        manager=ManagerAgent(config),
        audit=AuditLog(tmp_path / "insurance_audit.jsonl"),
        model_version="insurance-lgbm-0.1.0",
    )

    df = pd.read_csv(DATA_PATH, nrows=5)
    for idx, row in df.iterrows():
        case = row_to_case(row, idx)
        decision = orchestrator.run_case(case)
        assert decision.outcome.value in {"approve", "reject", "escalate"}
        assert decision.case_id == case.case_id

    ok, bad_index = orchestrator.audit.verify_chain()
    assert ok is True and bad_index is None

    first_case = row_to_case(df.iloc[0], 0)
    assert orchestrator.audit.replay(
        first_case.case_id, orchestrator.analyst, orchestrator.compliance, orchestrator.manager
    ) is True
