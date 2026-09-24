"""KYC/AML vertical tests. Skipped automatically if the synthetic data or
trained model artifacts aren't present locally (both are gitignored —
regenerate with:
  python -m worksync.verticals.kyc_aml.data_gen
  python -m worksync.verticals.kyc_aml.model.train
)."""

from pathlib import Path

import pytest

from worksync.core.rule_engine.engine import evaluate_ruleset, load_ruleset
from worksync.verticals.kyc_aml.adapter import engineer_features, row_to_case

RULES_PATH = "worksync/verticals/kyc_aml/rules.yaml"
ARTIFACT_DIR = Path("worksync/verticals/kyc_aml/model/artifacts")
DATA_PATH = Path("worksync/data/raw/kyc_aml/applicants.csv")

requires_artifacts = pytest.mark.skipif(
    not (ARTIFACT_DIR / "lgbm_calibrated.joblib").exists(),
    reason="model artifacts not present; run `python -m worksync.verticals.kyc_aml.model.train`",
)
requires_data = pytest.mark.skipif(
    not DATA_PATH.exists(),
    reason="applicants.csv not present; run `python -m worksync.verticals.kyc_aml.data_gen`",
)


def test_data_generator_is_deterministic():
    from worksync.verticals.kyc_aml.data_gen import generate

    run1 = generate()
    run2 = generate()
    assert run1["applicants"]["full_name"].tolist() == run2["applicants"]["full_name"].tolist()
    assert run1["applicants"]["high_risk_label"].tolist() == run2["applicants"]["high_risk_label"].tolist()


def test_engineer_features_bool_coercion():
    row = {
        "age_years": 30,
        "document_quality_score": 0.9,
        "address_match_score": 0.8,
        "selfie_liveness_score": 0.95,
        "device_risk_score": 0.1,
        "application_velocity_24h": 1,
        "country_of_residence": "IN",
        "id_type": "passport",
        "pep_match": "True",
        "sanctions_match": False,
        "adverse_media_hit": "false",
    }
    features = engineer_features(row)
    assert features["pep_match"] is True
    assert features["sanctions_match"] is False
    assert features["adverse_media_hit"] is False


def test_row_to_case_produces_valid_case_record():
    row = {"applicant_id": "A000123", "age_years": 30}
    case = row_to_case(row)
    assert case.case_id == "kyc-A000123"
    assert case.entity_id == "A000123"


def test_sanctions_match_triggers_hard_reject_rule():
    ruleset = load_ruleset(RULES_PATH)
    flags = evaluate_ruleset(ruleset, {"sanctions_match": True})
    fired = {f.rule_id: f for f in flags}
    assert "KYC-SANCTIONS-001" in fired
    assert fired["KYC-SANCTIONS-001"].action == "reject"


def test_pep_match_triggers_hard_escalate_rule():
    ruleset = load_ruleset(RULES_PATH)
    flags = evaluate_ruleset(ruleset, {"pep_match": True})
    fired = {f.rule_id: f for f in flags}
    assert "KYC-PEP-001" in fired
    assert fired["KYC-PEP-001"].action == "escalate"


def test_all_rules_are_unverified_pending_team_review():
    ruleset = load_ruleset(RULES_PATH)
    assert all(rule.verified is False for rule in ruleset.rules)


@requires_artifacts
@requires_data
def test_risk_model_predicts_a_valid_output_for_a_real_row():
    import pandas as pd

    from worksync.verticals.kyc_aml.model.risk_model import KycAmlRiskModel

    df = pd.read_csv(DATA_PATH, nrows=1)
    case = row_to_case(df.iloc[0])
    risk = KycAmlRiskModel().predict(case)
    assert 0.0 <= risk.risk_probability <= 1.0
    assert risk.confidence_band in {"low", "medium", "high"}
    assert 1 <= len(risk.top_attributions) <= 5


@requires_artifacts
@requires_data
def test_kyc_aml_pipeline_end_to_end_including_sanctions_and_pep_hits(tmp_path):
    import pandas as pd

    from worksync.core.agents.analyst import AnalystAgent
    from worksync.core.agents.audit import AuditLog
    from worksync.core.agents.compliance import ComplianceAgent
    from worksync.core.agents.manager import ManagerAgent, load_manager_config
    from worksync.core.orchestrator import Orchestrator
    from worksync.core.schemas.models import DecisionOutcome
    from worksync.verticals.kyc_aml.model.risk_model import KycAmlRiskModel

    ruleset = load_ruleset(RULES_PATH)
    config = load_manager_config("worksync/verticals/kyc_aml/manager_config.yaml")
    orchestrator = Orchestrator(
        analyst=AnalystAgent(KycAmlRiskModel()),
        compliance=ComplianceAgent(ruleset),
        manager=ManagerAgent(config),
        audit=AuditLog(tmp_path / "kyc_audit.jsonl"),
        model_version="kyc-aml-lgbm-0.1.0",
    )

    df = pd.read_csv(DATA_PATH)
    sanctions_row = df[df["sanctions_match"]].iloc[0]
    pep_row = df[df["pep_match"] & ~df["sanctions_match"]].iloc[0]
    clean_row = df[~df["sanctions_match"] & ~df["pep_match"]].iloc[0]

    sanctions_decision = orchestrator.run_case(row_to_case(sanctions_row))
    assert sanctions_decision.outcome == DecisionOutcome.REJECT
    assert "KYC-SANCTIONS-001" in sanctions_decision.hard_flags

    pep_decision = orchestrator.run_case(row_to_case(pep_row))
    assert pep_decision.outcome == DecisionOutcome.ESCALATE
    assert "KYC-PEP-001" in pep_decision.hard_flags

    clean_decision = orchestrator.run_case(row_to_case(clean_row))
    assert clean_decision.outcome.value in {"approve", "reject", "escalate"}

    ok, bad_index = orchestrator.audit.verify_chain()
    assert ok is True and bad_index is None
    assert orchestrator.audit.replay(
        row_to_case(sanctions_row).case_id, orchestrator.analyst, orchestrator.compliance, orchestrator.manager
    ) is True
