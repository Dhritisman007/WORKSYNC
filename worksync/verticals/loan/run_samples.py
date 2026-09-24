"""Runs N real Home Credit applications end to end through the shared core
and prints decisions, reason codes and confirms the audit chain. This is the
Phase 3 checkpoint demo.

Run with: python -m worksync.verticals.loan.run_samples [n]
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
from worksync.verticals.loan.adapter import row_to_case
from worksync.verticals.loan.model.risk_model import LoanRiskModel

DATA_PATH = "worksync/data/raw/loan/application_train.csv"
AUDIT_PATH = "worksync/logs/audit/loan.jsonl"
MODEL_VERSION = "loan-lgbm-0.1.0"


def main(n: int = 20, seed: int = 42) -> None:
    df = pd.read_csv(DATA_PATH).sample(n=n, random_state=seed).reset_index(drop=True)

    ruleset = load_ruleset("worksync/verticals/loan/rules.yaml")
    config = load_manager_config("worksync/verticals/loan/manager_config.yaml")
    orchestrator = Orchestrator(
        analyst=AnalystAgent(LoanRiskModel()),
        compliance=ComplianceAgent(ruleset),
        manager=ManagerAgent(config),
        audit=AuditLog(AUDIT_PATH),
        model_version=MODEL_VERSION,
    )

    outcomes = {"approve": 0, "reject": 0, "escalate": 0}
    for _, row in df.iterrows():
        case = row_to_case(row)
        decision = orchestrator.run_case(case)
        outcomes[decision.outcome.value] += 1
        print(
            f"{case.case_id:>14}  actual_target={int(row['TARGET'])}  "
            f"outcome={decision.outcome.value:<9}  prob={decision.risk_probability:.4f}  "
            f"band={decision.confidence_band:<7}  reasons={decision.reason_codes}"
        )

    print(f"\noutcome counts: {outcomes}")

    ok, bad_index = orchestrator.audit.verify_chain()
    all_entries = orchestrator.audit.read_all()
    print(f"audit log: {AUDIT_PATH}  ({len(all_entries)} entries, {len(all_entries) // 3} cases)")
    print(f"verify_chain() -> ok={ok}, first_bad_index={bad_index}")

    sample_case_id = row_to_case(df.iloc[0]).case_id
    replay_ok = orchestrator.audit.replay(
        sample_case_id, orchestrator.analyst, orchestrator.compliance, orchestrator.manager
    )
    print(f"replay({sample_case_id!r}) -> {replay_ok}")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    main(n)
