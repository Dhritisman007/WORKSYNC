"""Loan vertical tests. Skipped automatically if the Kaggle CSV or trained
model artifacts aren't present locally (both are gitignored — regenerate
with `python -m worksync.verticals.loan.model.train`)."""

from pathlib import Path

import pytest

from worksync.core.rule_engine.engine import evaluate_ruleset, load_ruleset
from worksync.verticals.loan.adapter import engineer_features, row_to_case

RULES_PATH = "worksync/verticals/loan/rules.yaml"
ARTIFACT_DIR = Path("worksync/verticals/loan/model/artifacts")
DATA_PATH = Path("worksync/data/raw/loan/application_train.csv")

requires_artifacts = pytest.mark.skipif(
    not (ARTIFACT_DIR / "lgbm_calibrated.joblib").exists(),
    reason="model artifacts not present; run `python -m worksync.verticals.loan.model.train`",
)
requires_data = pytest.mark.skipif(
    not DATA_PATH.exists(), reason="application_train.csv not present in data/raw/loan/"
)


def test_engineer_features_ratios_and_anomaly_handling():
    row = {
        "SK_ID_CURR": 1,
        "AMT_INCOME_TOTAL": 100000,
        "AMT_CREDIT": 500000,
        "AMT_ANNUITY": 20000,
        "AMT_GOODS_PRICE": 450000,
        "DAYS_BIRTH": -365 * 30,
        "DAYS_EMPLOYED": 365243,  # anomaly sentinel -> should become None
        "EXT_SOURCE_1": 0.5,
        "EXT_SOURCE_2": None,
        "EXT_SOURCE_3": 0.7,
        "FLAG_DOCUMENT_3": 1,
        "FLAG_OWN_CAR": "Y",
        "FLAG_OWN_REALTY": "N",
    }
    features = engineer_features(row)
    assert features["credit_income_ratio"] == 5.0
    assert features["annuity_income_ratio"] == 0.2
    assert features["years_employed"] is None
    assert features["ext_source_mean"] == 0.6
    assert features["own_car"] is True
    assert features["own_realty"] is False
    assert features["doc3_provided"] is True


def test_row_to_case_produces_valid_case_record():
    row = {"SK_ID_CURR": 42, "AMT_INCOME_TOTAL": 50000, "AMT_CREDIT": 100000}
    case = row_to_case(row)
    assert case.case_id == "loan-42"
    assert case.entity_id == "42"


def test_missing_kyc_fields_trigger_escalate_rule():
    ruleset = load_ruleset(RULES_PATH)
    flags = evaluate_ruleset(ruleset, {"ext_source_mean": None, "occupation_type": None})
    fired = {f.rule_id for f in flags}
    assert "LOAN-KYC-001" in fired


def test_high_dti_triggers_hard_reject_rule():
    ruleset = load_ruleset(RULES_PATH)
    flags = evaluate_ruleset(ruleset, {"annuity_income_ratio": 0.9})
    fired = {f.rule_id for f in flags}
    assert "LOAN-DTI-001" in fired


def test_every_regulation_rule_has_a_checked_citation():
    """Regulation-based rules must cite a source that was checked against
    the regulator's text; internal-policy thresholds claim no regulation."""
    ruleset = load_ruleset(RULES_PATH)
    for rule in ruleset.rules:
        if rule.basis == "regulation":
            assert rule.verified and rule.reference_url and rule.verified_on, rule.id
        else:
            assert rule.verified is False, rule.id


@requires_data
def test_case_from_iloc_row_access_has_no_numpy_leaks_and_serializes():
    """Regression test: `.iloc[i]` (unlike `.iterrows()`, used elsewhere in
    this test file) keeps numpy scalar types in the resulting Series for
    some columns (e.g. an int64 column compared to a literal produces
    numpy.bool, not bool). pydantic's `model_dump(mode="json")` can't
    serialize that. The Streamlit demo app uses `.iloc[]` directly, so this
    must hold for any row, not just ones reached via `.iterrows()`."""
    import pandas as pd

    df = pd.read_csv(DATA_PATH)
    case = row_to_case(df.iloc[0])
    for key, value in case.features.items():
        assert type(value).__module__ != "numpy", f"{key} leaked a numpy type: {type(value)}"
    case.model_dump(mode="json")  # must not raise


@requires_artifacts
@requires_data
def test_risk_model_predicts_a_valid_output_for_a_real_row():
    import pandas as pd

    from worksync.verticals.loan.model.risk_model import LoanRiskModel

    df = pd.read_csv(DATA_PATH, nrows=1)
    case = row_to_case(df.iloc[0])
    risk = LoanRiskModel().predict(case)
    assert 0.0 <= risk.risk_probability <= 1.0
    assert risk.confidence_band in {"low", "medium", "high"}
    assert 1 <= len(risk.top_attributions) <= 5


@requires_artifacts
@requires_data
def test_loan_pipeline_end_to_end_for_sample_cases(tmp_path):
    import pandas as pd

    from worksync.core.agents.analyst import AnalystAgent
    from worksync.core.agents.audit import AuditLog
    from worksync.core.agents.compliance import ComplianceAgent
    from worksync.core.agents.manager import ManagerAgent, load_manager_config
    from worksync.core.orchestrator import Orchestrator
    from worksync.verticals.loan.model.risk_model import LoanRiskModel

    ruleset = load_ruleset(RULES_PATH)
    config = load_manager_config("worksync/verticals/loan/manager_config.yaml")
    orchestrator = Orchestrator(
        analyst=AnalystAgent(LoanRiskModel()),
        compliance=ComplianceAgent(ruleset),
        manager=ManagerAgent(config),
        audit=AuditLog(tmp_path / "loan_audit.jsonl"),
        model_version="loan-lgbm-0.1.0",
    )

    df = pd.read_csv(DATA_PATH, nrows=5)
    for _, row in df.iterrows():
        case = row_to_case(row)
        decision = orchestrator.run_case(case)
        assert decision.outcome.value in {"approve", "reject", "escalate"}
        assert decision.case_id == case.case_id

    ok, bad_index = orchestrator.audit.verify_chain()
    assert ok is True and bad_index is None

    first_case = row_to_case(df.iloc[0])
    assert orchestrator.audit.replay(
        first_case.case_id, orchestrator.analyst, orchestrator.compliance, orchestrator.manager
    ) is True
