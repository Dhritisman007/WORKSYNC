"""Runs N insurance claims end to end through the shared core and prints
decisions, reason codes and confirms the audit chain. Forces in a couple of
known-fraud rows so the demo shows the model catching something.

Run with: python -m worksync.verticals.insurance.run_samples [n]
"""

from __future__ import annotations

import sys

import pandas as pd

from worksync.core.agents.analyst import AnalystAgent
from worksync.core.agents.audit import AuditLog
from worksync.core.agents.compliance import ComplianceAgent
from worksync.core.agents.manager import ManagerAgent, load_manager_config
from worksync.core.orchestrator import Orchestrator
from worksync.core.rule_engine.engine import load_ruleset
from worksync.verticals.insurance.adapter import row_to_case
from worksync.verticals.insurance.model.risk_model import InsuranceRiskModel

DATA_PATH = "worksync/data/raw/insurance/fraud_oracle.csv"
AUDIT_PATH = "worksync/logs/audit/insurance.jsonl"
MODEL_VERSION = "insurance-lgbm-0.1.0"


def main(n: int = 20, seed: int = 42) -> None:
    df = pd.read_csv(DATA_PATH)
    fraud_rows = df[df["FraudFound_P"] == 1].sample(n=2, random_state=seed)
    rest = df.drop(fraud_rows.index).sample(n=max(n - len(fraud_rows), 0), random_state=seed)
    sample = pd.concat([fraud_rows, rest])

    ruleset = load_ruleset("worksync/verticals/insurance/rules.yaml")
    config = load_manager_config("worksync/verticals/insurance/manager_config.yaml")
    orchestrator = Orchestrator(
        analyst=AnalystAgent(InsuranceRiskModel()),
        compliance=ComplianceAgent(ruleset),
        manager=ManagerAgent(config),
        audit=AuditLog(AUDIT_PATH),
        model_version=MODEL_VERSION,
    )

    outcomes = {"approve": 0, "reject": 0, "escalate": 0}
    last_case_id = None
    for idx, row in sample.iterrows():
        case = row_to_case(row, idx)
        decision = orchestrator.run_case(case)
        outcomes[decision.outcome.value] += 1
        last_case_id = case.case_id
        print(
            f"{case.case_id:>20}  actual_fraud={int(row['FraudFound_P'])}  "
            f"outcome={decision.outcome.value:<9}  prob={decision.risk_probability:.4f}  "
            f"band={decision.confidence_band:<7}  reasons={decision.reason_codes}"
        )

    print(f"\noutcome counts: {outcomes}")

    ok, bad_index = orchestrator.audit.verify_chain()
    all_entries = orchestrator.audit.read_all()
    print(f"audit log: {AUDIT_PATH}  ({len(all_entries)} entries, {len(all_entries) // 3} cases)")
    print(f"verify_chain() -> ok={ok}, first_bad_index={bad_index}")

    replay_ok = orchestrator.audit.replay(
        last_case_id, orchestrator.analyst, orchestrator.compliance, orchestrator.manager
    )
    print(f"replay({last_case_id!r}) -> {replay_ok}")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    main(n)
