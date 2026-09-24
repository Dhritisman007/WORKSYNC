"""Credit card/BNPL vertical tests. Skipped automatically if the Kaggle CSV
or trained model artifacts aren't present locally (both are gitignored —
regenerate with `python -m worksync.verticals.bnpl.model.train`)."""

from pathlib import Path

import pytest

from worksync.core.rule_engine.engine import evaluate_ruleset, load_ruleset
from worksync.verticals.bnpl.adapter import engineer_features, row_to_case

RULES_PATH = "worksync/verticals/bnpl/rules.yaml"
ARTIFACT_DIR = Path("worksync/verticals/bnpl/model/artifacts")
DATA_PATH = Path("worksync/data/raw/bnpl/creditcard.csv")

requires_artifacts = pytest.mark.skipif(
    not (ARTIFACT_DIR / "lgbm_calibrated.joblib").exists(),
    reason="model artifacts not present; run `python -m worksync.verticals.bnpl.model.train`",
)
requires_data = pytest.mark.skipif(
    not DATA_PATH.exists(), reason="creditcard.csv not present in data/raw/bnpl/"
)


def test_engineer_features_derives_hour_of_day():
    row = {"Time": 3 * 3600 + 100, "Amount": 250.0, "V1": 0.5, "V28": -0.2}
    features = engineer_features(row)
    assert features["hour_of_day"] == 3
    assert features["amount"] == 250.0
    assert features["v1"] == 0.5
    assert features["v28"] == -0.2


def test_row_to_case_uses_row_index_as_entity_id():
    row = {"Time": 0, "Amount": 100.0}
    case = row_to_case(row, index=42)
    assert case.case_id == "bnpl-txn-42"
    assert case.entity_id == "txn-42"


def test_large_amount_triggers_hard_escalate_rule():
    ruleset = load_ruleset(RULES_PATH)
    flags = evaluate_ruleset(ruleset, {"amount": 15000})
    fired = {f.rule_id: f for f in flags}
    assert "BNPL-AMOUNT-001" in fired
    assert fired["BNPL-AMOUNT-001"].action == "escalate"


def test_moderate_amount_triggers_soft_flag_only():
    ruleset = load_ruleset(RULES_PATH)
    flags = evaluate_ruleset(ruleset, {"amount": 3000})
    fired = {f.rule_id for f in flags}
    assert fired == {"BNPL-AMOUNT-002"}


def test_small_amount_triggers_no_flags():
    ruleset = load_ruleset(RULES_PATH)
    flags = evaluate_ruleset(ruleset, {"amount": 50})
    assert flags == []


def test_all_rules_are_unverified_pending_team_review():
    ruleset = load_ruleset(RULES_PATH)
    assert all(rule.verified is False for rule in ruleset.rules)


@requires_artifacts
@requires_data
def test_risk_model_predicts_a_valid_output_for_a_real_row():
    import pandas as pd

    from worksync.verticals.bnpl.model.risk_model import BnplRiskModel

    df = pd.read_csv(DATA_PATH, nrows=1)
    case = row_to_case(df.iloc[0], index=0)
    risk = BnplRiskModel().predict(case)
    assert 0.0 <= risk.risk_probability <= 1.0
    assert risk.confidence_band in {"low", "medium", "high"}
    assert 1 <= len(risk.top_attributions) <= 5


@requires_artifacts
@requires_data
def test_bnpl_pipeline_end_to_end_including_a_known_fraud_case(tmp_path):
    import pandas as pd

    from worksync.core.agents.analyst import AnalystAgent
    from worksync.core.agents.audit import AuditLog
    from worksync.core.agents.compliance import ComplianceAgent
    from worksync.core.agents.manager import ManagerAgent, load_manager_config
    from worksync.core.orchestrator import Orchestrator
    from worksync.verticals.bnpl.model.risk_model import BnplRiskModel

    ruleset = load_ruleset(RULES_PATH)
    config = load_manager_config("worksync/verticals/bnpl/manager_config.yaml")
    orchestrator = Orchestrator(
        analyst=AnalystAgent(BnplRiskModel()),
        compliance=ComplianceAgent(ruleset),
        manager=ManagerAgent(config),
        audit=AuditLog(tmp_path / "bnpl_audit.jsonl"),
        model_version="bnpl-lgbm-0.1.0",
    )

    df = pd.read_csv(DATA_PATH)
    fraud_row = df[df["Class"] == 1].iloc[0]
    fraud_idx = df[df["Class"] == 1].index[0]
    legit_row = df[df["Class"] == 0].iloc[0]
    legit_idx = df[df["Class"] == 0].index[0]

    fraud_decision = orchestrator.run_case(row_to_case(fraud_row, fraud_idx))
    assert fraud_decision.outcome.value in {"reject", "escalate"}

    legit_decision = orchestrator.run_case(row_to_case(legit_row, legit_idx))
    assert legit_decision.outcome.value in {"approve", "reject", "escalate"}

    ok, bad_index = orchestrator.audit.verify_chain()
    assert ok is True and bad_index is None

    fraud_case_id = row_to_case(fraud_row, fraud_idx).case_id
    assert orchestrator.audit.replay(
        fraud_case_id, orchestrator.analyst, orchestrator.compliance, orchestrator.manager
    ) is True
