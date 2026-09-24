"""Runs N synthetic applicants end to end through the shared core and
prints decisions, reason codes and confirms the audit chain. KYC/AML
equivalent of verticals/loan/run_samples.py.

Run with: python -m worksync.verticals.kyc_aml.run_samples [n]
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
from worksync.verticals.kyc_aml.adapter import row_to_case
from worksync.verticals.kyc_aml.model.risk_model import KycAmlRiskModel

DATA_PATH = "worksync/data/raw/kyc_aml/applicants.csv"
AUDIT_PATH = "worksync/logs/audit/kyc_aml.jsonl"
MODEL_VERSION = "kyc-aml-lgbm-0.1.0"


def main(n: int = 20, seed: int = 42) -> None:
    df = pd.read_csv(DATA_PATH)
    # Force at least one PEP and one sanctions hit into the sample so the
    # checkpoint demo actually exercises the hard-flag rules.
    forced = pd.concat(
        [df[df["sanctions_match"]].head(1), df[df["pep_match"]].head(1)]
    )
    rest = df.drop(forced.index).sample(n=max(n - len(forced), 0), random_state=seed)
    sample = pd.concat([forced, rest]).reset_index(drop=True)

    ruleset = load_ruleset("worksync/verticals/kyc_aml/rules.yaml")
    config = load_manager_config("worksync/verticals/kyc_aml/manager_config.yaml")
    orchestrator = Orchestrator(
        analyst=AnalystAgent(KycAmlRiskModel()),
        compliance=ComplianceAgent(ruleset),
        manager=ManagerAgent(config),
        audit=AuditLog(AUDIT_PATH),
        model_version=MODEL_VERSION,
    )

    outcomes = {"approve": 0, "reject": 0, "escalate": 0}
    for _, row in sample.iterrows():
        case = row_to_case(row)
        decision = orchestrator.run_case(case)
        outcomes[decision.outcome.value] += 1
        print(
            f"{case.case_id:>14}  actual_label={int(row['high_risk_label'])}  "
            f"outcome={decision.outcome.value:<9}  prob={decision.risk_probability:.4f}  "
            f"band={decision.confidence_band:<7}  reasons={decision.reason_codes}"
        )

    print(f"\noutcome counts: {outcomes}")

    ok, bad_index = orchestrator.audit.verify_chain()
    all_entries = orchestrator.audit.read_all()
    print(f"audit log: {AUDIT_PATH}  ({len(all_entries)} entries, {len(all_entries) // 3} cases)")
    print(f"verify_chain() -> ok={ok}, first_bad_index={bad_index}")

    sample_case_id = row_to_case(sample.iloc[0]).case_id
    replay_ok = orchestrator.audit.replay(
        sample_case_id, orchestrator.analyst, orchestrator.compliance, orchestrator.manager
    )
    print(f"replay({sample_case_id!r}) -> {replay_ok}")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    main(n)
