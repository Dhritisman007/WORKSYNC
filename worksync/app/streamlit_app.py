"""WorkSync.AI demo: pick a vertical and a case, run it through the shared
pipeline, and see every step — the case record, the risk score with its
confidence band, the SHAP attributions, the compliance flags, the decision
with reason codes, and the audit trail with its chain-verification status.

This file is the one place the project deliberately imports every
vertical's specifics by name (the `VERTICALS` registry below) — that's
expected and fine: something has to know all four verticals exist in order
to offer a picker. What matters structurally is that everything below the
registry — `Orchestrator`, `ComplianceAgent`, `ManagerAgent`, `AuditLog` —
is the exact same shared code for every one of them.

Run with: streamlit run worksync/app/streamlit_app.py
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pandas as pd
import streamlit as st

from worksync.core.agents.analyst import AnalystAgent
from worksync.core.agents.audit import AuditLog
from worksync.core.agents.compliance import ComplianceAgent
from worksync.core.agents.manager import ManagerAgent, load_manager_config
from worksync.core.orchestrator import CaseResult, Orchestrator
from worksync.core.rule_engine.engine import load_ruleset
from worksync.core.schemas.models import CaseRecord

st.set_page_config(page_title="WorkSync.AI", layout="wide")


@dataclass
class VerticalSpec:
    label: str
    data_path: Path
    rules_path: str
    config_path: str
    audit_path: Path
    model_version: str
    load_risk_model: Callable[[], object]
    row_to_case: Callable[[pd.Series, int], CaseRecord]
    label_col: str | None  # ground-truth column, if any, for display only


def _loan_spec() -> VerticalSpec:
    from worksync.verticals.loan.adapter import row_to_case as loan_row_to_case
    from worksync.verticals.loan.model.risk_model import LoanRiskModel

    return VerticalSpec(
        label="Loan",
        data_path=Path("worksync/data/raw/loan/application_train.csv"),
        rules_path="worksync/verticals/loan/rules.yaml",
        config_path="worksync/verticals/loan/manager_config.yaml",
        audit_path=Path("worksync/logs/audit/loan.jsonl"),
        model_version="loan-lgbm-0.1.0",
        load_risk_model=LoanRiskModel,
        row_to_case=lambda row, idx: loan_row_to_case(row),
        label_col="TARGET",
    )


def _kyc_aml_spec() -> VerticalSpec:
    from worksync.verticals.kyc_aml.adapter import row_to_case as kyc_row_to_case
    from worksync.verticals.kyc_aml.model.risk_model import KycAmlRiskModel

    return VerticalSpec(
        label="KYC/AML",
        data_path=Path("worksync/data/raw/kyc_aml/applicants.csv"),
        rules_path="worksync/verticals/kyc_aml/rules.yaml",
        config_path="worksync/verticals/kyc_aml/manager_config.yaml",
        audit_path=Path("worksync/logs/audit/kyc_aml.jsonl"),
        model_version="kyc-aml-lgbm-0.1.0",
        load_risk_model=KycAmlRiskModel,
        row_to_case=lambda row, idx: kyc_row_to_case(row),
        label_col="high_risk_label",
    )


def _bnpl_spec() -> VerticalSpec:
    from worksync.verticals.bnpl.adapter import row_to_case as bnpl_row_to_case
    from worksync.verticals.bnpl.model.risk_model import BnplRiskModel

    return VerticalSpec(
        label="Credit card / BNPL",
        data_path=Path("worksync/data/raw/bnpl/creditcard.csv"),
        rules_path="worksync/verticals/bnpl/rules.yaml",
        config_path="worksync/verticals/bnpl/manager_config.yaml",
        audit_path=Path("worksync/logs/audit/bnpl.jsonl"),
        model_version="bnpl-lgbm-0.1.0",
        load_risk_model=BnplRiskModel,
        row_to_case=bnpl_row_to_case,
        label_col="Class",
    )


def _insurance_spec() -> VerticalSpec:
    from worksync.verticals.insurance.adapter import row_to_case as insurance_row_to_case
    from worksync.verticals.insurance.model.risk_model import InsuranceRiskModel

    return VerticalSpec(
        label="Insurance claims",
        data_path=Path("worksync/data/raw/insurance/fraud_oracle.csv"),
        rules_path="worksync/verticals/insurance/rules.yaml",
        config_path="worksync/verticals/insurance/manager_config.yaml",
        audit_path=Path("worksync/logs/audit/insurance.jsonl"),
        model_version="insurance-lgbm-0.1.0",
        load_risk_model=InsuranceRiskModel,
        row_to_case=insurance_row_to_case,
        label_col="FraudFound_P",
    )


VERTICALS: dict[str, Callable[[], VerticalSpec]] = {
    "loan": _loan_spec,
    "kyc_aml": _kyc_aml_spec,
    "bnpl": _bnpl_spec,
    "insurance": _insurance_spec,
}


@st.cache_resource(show_spinner=False)
def get_orchestrator(vertical_key: str) -> tuple[Orchestrator, VerticalSpec]:
    spec = VERTICALS[vertical_key]()
    ruleset = load_ruleset(spec.rules_path)
    config = load_manager_config(spec.config_path)
    orchestrator = Orchestrator(
        analyst=AnalystAgent(spec.load_risk_model()),
        compliance=ComplianceAgent(ruleset),
        manager=ManagerAgent(config),
        audit=AuditLog(spec.audit_path),
        model_version=spec.model_version,
    )
    return orchestrator, spec


@st.cache_data(show_spinner=False)
def load_data(vertical_key: str, data_path_str: str) -> pd.DataFrame | None:
    path = Path(data_path_str)
    if not path.exists():
        return None
    return pd.read_csv(path)


def render_case_record(case: CaseRecord) -> None:
    st.subheader("Case record")
    st.caption(f"`{case.case_id}` · vertical: `{case.vertical.value}` · entity: `{case.entity_id}`")
    rows = [(k, str(v)) for k, v in sorted(case.features.items())]
    st.dataframe(
        pd.DataFrame(rows, columns=["feature", "value"]),
        width="stretch",
        hide_index=True,
    )


def render_risk(result: CaseResult) -> None:
    st.subheader("Risk score")
    col1, col2, col3 = st.columns(3)
    col1.metric("Risk probability", f"{result.risk.risk_probability:.4f}")
    col2.metric("Confidence band", result.risk.confidence_band)
    col3.metric("Model", f"{result.risk.model_name} · {result.risk.model_version}")

    st.caption("Top SHAP attributions")
    attr_df = pd.DataFrame(
        [(a.feature, a.contribution) for a in result.risk.top_attributions],
        columns=["feature", "contribution"],
    ).set_index("feature")
    st.bar_chart(attr_df)


def render_compliance(result: CaseResult) -> None:
    st.subheader("Compliance flags")
    st.caption(f"Ruleset version: `{result.compliance.ruleset_version}`")
    if not result.compliance.flags:
        st.write("No rules triggered.")
        return
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "rule_id": f.rule_id,
                    "severity": f.severity.value,
                    "action": f.action,
                    "verified": f.verified,
                    "description": f.description,
                }
                for f in result.compliance.flags
            ]
        ),
        width="stretch",
        hide_index=True,
    )


def render_decision(result: CaseResult) -> None:
    st.subheader("Decision")
    outcome_color = {"approve": "green", "reject": "red", "escalate": "orange"}[
        result.decision.outcome.value
    ]
    st.markdown(f"### :{outcome_color}[{result.decision.outcome.value.upper()}]")
    st.write("Reason codes:", result.decision.reason_codes or "(none)")
    if result.decision.hard_flags:
        st.write("Hard flags:", result.decision.hard_flags)


def render_audit_trail(orchestrator: Orchestrator, case_id: str) -> None:
    st.subheader("Audit trail")
    entries = orchestrator.audit.entries_for_case(case_id)
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "agent": e.agent.value,
                    "timestamp": e.timestamp,
                    "model_version": e.model_version,
                    "ruleset_version": e.ruleset_version,
                    "entry_hash": e.entry_hash[:12] + "…",
                    "prev_hash": e.prev_hash[:12] + "…",
                }
                for e in entries
            ]
        ),
        width="stretch",
        hide_index=True,
    )

    ok, bad_index = orchestrator.audit.verify_chain()
    if ok:
        st.success("verify_chain(): OK — the full audit log's hash chain is intact.")
    else:
        st.error(f"verify_chain(): TAMPERING DETECTED at entry {bad_index}.")

    if st.button("Replay this case", key=f"replay-{case_id}"):
        replay_ok = orchestrator.audit.replay(
            case_id, orchestrator.analyst, orchestrator.compliance, orchestrator.manager
        )
        if replay_ok:
            st.success("replay(): re-running this case reproduces the logged decision.")
        else:
            st.error("replay(): re-running this case did NOT reproduce the logged decision.")


def main() -> None:
    st.title("WorkSync.AI")
    st.caption(
        "One four-agent pipeline (Analyst → Compliance → Manager, observed by Audit), "
        "reused unchanged across four BFSI verticals."
    )

    with st.sidebar:
        st.header("Pick a case")
        vertical_key = st.selectbox(
            "Vertical",
            options=list(VERTICALS.keys()),
            format_func=lambda k: VERTICALS[k]().label,
        )
        orchestrator, spec = get_orchestrator(vertical_key)
        df = load_data(vertical_key, str(spec.data_path))

        if df is None:
            st.warning(
                f"Data file not found at `{spec.data_path}`. "
                f"See `worksync/verticals/{vertical_key}/README.md` for how to get/generate it."
            )
            st.stop()

        max_index = len(df) - 1
        row_index = st.number_input("Row index", min_value=0, max_value=max_index, value=0, step=1)
        if st.button("🎲 Random case"):
            row_index = int(df.sample(1).index[0])
        row = df.iloc[row_index]
        if spec.label_col and spec.label_col in df.columns:
            st.caption(f"Ground-truth `{spec.label_col}`: {row[spec.label_col]}")

    case = spec.row_to_case(row, int(row.name))
    result = orchestrator.run_case_with_detail(case)

    left, right = st.columns(2)
    with left:
        render_case_record(case)
        render_compliance(result)
    with right:
        render_risk(result)
        render_decision(result)

    render_audit_trail(orchestrator, case.case_id)


if __name__ == "__main__":
    main()
