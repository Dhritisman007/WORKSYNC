"""Shared, UI-agnostic logic for the demo app: the vertical registry, data
loading, upload parsing/detection, and the plain-English decision narrative.

Nothing in this module is Streamlit-specific except `st.cache_resource` /
`st.cache_data` decorators (caching is a cross-cutting concern, not a UI
one). Every page in `pages_src/` imports from here rather than duplicating
this logic, so there is exactly one place that knows how to build an
Orchestrator for a vertical.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import streamlit as st

from worksync.core.agents.analyst import AnalystAgent
from worksync.core.agents.audit import AuditLog
from worksync.core.agents.compliance import ComplianceAgent
from worksync.core.agents.manager import ManagerAgent, load_manager_config
from worksync.core.orchestrator import CaseResult, Orchestrator
from worksync.core.rule_engine.engine import load_ruleset
from worksync.core.schemas.models import CaseRecord, ComplianceFlags, Decision, RiskOutput, Severity

OUTCOME_STYLE = {
    "approve": {"accent": "#2f9e58", "bg": "#0f2419", "label": "Approved"},
    "reject": {"accent": "#e0564b", "bg": "#2a1513", "label": "Rejected"},
    "escalate": {"accent": "#e0a63a", "bg": "#2a2010", "label": "Escalated for review"},
}

PIPELINE_STEPS = [
    ("ingest", "Ingesting case record into the shared contract"),
    ("analyst", "Analyst agent — risk model + SHAP attribution"),
    ("compliance", "Compliance agent — evaluating ruleset"),
    ("manager", "Manager agent — applying decision policy"),
]


@dataclass
class VerticalSpec:
    label: str
    short_label: str
    icon: str
    data_desc: str
    model_desc: str
    rules_desc: str
    data_path: Path
    rules_path: str
    config_path: str
    audit_path: Path
    model_version: str
    load_risk_model: Callable[[], object]
    row_to_case: Callable[[pd.Series, int], CaseRecord]
    label_col: str | None  # ground-truth column, if any, for display only
    id_col: str | None = None  # raw column row_to_case reads as entity id, if any
    raw_columns: tuple[str, ...] = ()  # this vertical's expected raw source columns


def _loan_spec() -> VerticalSpec:
    from worksync.verticals.loan import adapter as loan_adapter
    from worksync.verticals.loan.model.risk_model import LoanRiskModel

    return VerticalSpec(
        label="Loan Approval",
        short_label="Loan",
        icon="◆",
        data_desc="Tabular application data (Home Credit)",
        model_desc="LightGBM + XGBoost, calibrated",
        rules_desc="RBI-style compliance rules",
        data_path=Path("worksync/data/raw/loan/application_train.csv"),
        rules_path="worksync/verticals/loan/rules.yaml",
        config_path="worksync/verticals/loan/manager_config.yaml",
        audit_path=Path("worksync/logs/audit/loan.jsonl"),
        model_version="loan-lgbm-0.1.0",
        load_risk_model=LoanRiskModel,
        row_to_case=lambda row, idx: loan_adapter.row_to_case(row),
        label_col="TARGET",
        id_col="SK_ID_CURR",
        raw_columns=tuple(loan_adapter.RAW_COLUMNS),
    )


def _kyc_aml_spec() -> VerticalSpec:
    from worksync.verticals.kyc_aml import adapter as kyc_adapter
    from worksync.verticals.kyc_aml.model.risk_model import KycAmlRiskModel

    return VerticalSpec(
        label="KYC / AML Onboarding",
        short_label="KYC/AML",
        icon="◆",
        data_desc="Identity + screening data (synthetic, seeded)",
        model_desc="LightGBM + XGBoost, calibrated",
        rules_desc="PEP / sanctions screening, AML rules",
        data_path=Path("worksync/data/raw/kyc_aml/applicants.csv"),
        rules_path="worksync/verticals/kyc_aml/rules.yaml",
        config_path="worksync/verticals/kyc_aml/manager_config.yaml",
        audit_path=Path("worksync/logs/audit/kyc_aml.jsonl"),
        model_version="kyc-aml-lgbm-0.1.0",
        load_risk_model=KycAmlRiskModel,
        row_to_case=lambda row, idx: kyc_adapter.row_to_case(row),
        label_col="high_risk_label",
        id_col="applicant_id",
        raw_columns=tuple(kyc_adapter.RAW_COLUMNS),
    )


def _bnpl_spec() -> VerticalSpec:
    from worksync.verticals.bnpl import adapter as bnpl_adapter
    from worksync.verticals.bnpl.model.risk_model import BnplRiskModel

    return VerticalSpec(
        label="Credit Card / BNPL",
        short_label="BNPL",
        icon="◆",
        data_desc="Transaction behaviour (Kaggle fraud data)",
        model_desc="LightGBM + XGBoost, calibrated",
        rules_desc="Amount-threshold rules",
        data_path=Path("worksync/data/raw/bnpl/creditcard.csv"),
        rules_path="worksync/verticals/bnpl/rules.yaml",
        config_path="worksync/verticals/bnpl/manager_config.yaml",
        audit_path=Path("worksync/logs/audit/bnpl.jsonl"),
        model_version="bnpl-lgbm-0.1.0",
        load_risk_model=BnplRiskModel,
        row_to_case=bnpl_adapter.row_to_case,
        label_col="Class",
        raw_columns=tuple(bnpl_adapter.RAW_COLUMNS),
    )


def _insurance_spec() -> VerticalSpec:
    from worksync.verticals.insurance import adapter as insurance_adapter
    from worksync.verticals.insurance.model.risk_model import InsuranceRiskModel

    return VerticalSpec(
        label="Insurance Claims",
        short_label="Insurance",
        icon="◆",
        data_desc="Claims data (Kaggle fraud data)",
        model_desc="LightGBM + XGBoost, calibrated",
        rules_desc="IRDAI-style rules",
        data_path=Path("worksync/data/raw/insurance/fraud_oracle.csv"),
        rules_path="worksync/verticals/insurance/rules.yaml",
        config_path="worksync/verticals/insurance/manager_config.yaml",
        audit_path=Path("worksync/logs/audit/insurance.jsonl"),
        model_version="insurance-lgbm-0.1.0",
        load_risk_model=InsuranceRiskModel,
        row_to_case=insurance_adapter.row_to_case,
        label_col="FraudFound_P",
        id_col="PolicyNumber",
        raw_columns=tuple(insurance_adapter.RAW_COLUMNS),
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


def artifacts_present(vertical_key: str) -> bool:
    artifact_dir = Path(f"worksync/verticals/{vertical_key}/model/artifacts")
    return (artifact_dir / "lgbm_calibrated.joblib").exists()


def _ensure_id(row: Any, id_col: str | None, idx: int) -> Any:
    """If the vertical reads a specific raw id column and the uploaded row
    doesn't have one, fill in a synthetic id so row_to_case doesn't produce
    a case_id like "loan-None". Works for both a pandas Series (sample
    dataset) and a plain dict (parsed JSON upload) — both support
    `.get`/`.copy()`/item assignment."""
    if id_col is None:
        return row
    value = row.get(id_col)
    if value is None or (isinstance(value, float) and pd.isna(value)) or value == "":
        row = row.copy()
        row[id_col] = f"upload-{idx}"
    return row


def parse_uploaded_file(uploaded) -> pd.DataFrame:
    """Accepts a raw CSV (one or more rows) or JSON (one record, or a list
    of records) in the vertical's own raw column format — the same format
    its Kaggle/synthetic source file uses, not the engineered CaseRecord
    feature names. Returns a DataFrame so the rest of the app can treat an
    uploaded row exactly like a sample-dataset row."""
    name = uploaded.name.lower()
    if name.endswith(".json"):
        data = json.load(uploaded)
        records = data if isinstance(data, list) else [data]
        return pd.DataFrame(records)
    return pd.read_csv(uploaded)


@dataclass
class VerticalMatch:
    key: str
    label: str
    coverage: float  # fraction of that vertical's expected raw columns present in the upload
    overlap: int


def detect_vertical(columns: list[str]) -> list[VerticalMatch]:
    """Scores every vertical by how much of ITS expected raw-column schema
    is present in the uploaded file's headers, sorted best match first.

    This is a column-signature match, not a model: no training, no
    ambiguity resolution beyond "which schema does this look like" — exact
    header names are what every adapter already keys off (`row.get("AMT_
    INCOME_TOTAL")` etc.), so a header match is a faithful proxy for "will
    this adapter actually populate its features from this file."
    """
    upload_cols = set(columns)
    matches = []
    for key, factory in VERTICALS.items():
        spec = factory()
        if not spec.raw_columns:
            continue
        overlap = upload_cols & set(spec.raw_columns)
        coverage = len(overlap) / len(spec.raw_columns)
        matches.append(VerticalMatch(key=key, label=spec.label, coverage=coverage, overlap=len(overlap)))
    matches.sort(key=lambda m: (m.coverage, m.overlap), reverse=True)
    return matches


def _clean(text: str) -> str:
    return " ".join(text.split())


def build_narrative(result: CaseResult, grey_low: float, grey_high: float) -> str:
    outcome = result.decision.outcome.value
    prob = result.decision.risk_probability or 0.0
    band = result.decision.confidence_band or "unknown"
    reasons = result.decision.reason_codes
    flags_by_id = {f.rule_id: f for f in result.compliance.flags}
    hard = [flags_by_id[r] for r in result.decision.hard_flags if r in flags_by_id]

    sentences: list[str] = []

    if hard:
        cited = "; ".join(f"{f.rule_id} ({_clean(f.description)})" for f in hard)
        verb = "rejected" if outcome == "reject" else "escalated to a human reviewer"
        sentences.append(f"This case was {verb} because it triggered a hard compliance rule: {cited}.")
    elif outcome == "approve":
        sentences.append(
            f"This case was auto-approved: the model's risk score ({prob:.1%}) was clearly on the "
            f"low side with {band} confidence, and no compliance rule blocked it."
        )
    elif outcome == "reject":
        sentences.append(
            f"This case was auto-rejected: the model's risk score ({prob:.1%}) was clearly on the "
            f"high side with {band} confidence."
        )
    elif "GREY_BAND_SCORE" in reasons:
        sentences.append(
            f"This case was escalated because the risk score ({prob:.1%}) fell inside the "
            f"configured grey band ({grey_low:.0%}–{grey_high:.0%}), where the Manager agent is "
            "not authorized to decide automatically."
        )
    elif "LOW_CONFIDENCE" in reasons:
        sentences.append(
            f"This case was escalated because the model's confidence in this score ({band}) "
            "wasn't high enough to decide automatically."
        )
    else:
        sentences.append("This case was escalated for human review.")

    if result.risk.top_attributions:
        top = result.risk.top_attributions[0]
        direction = "pushed the risk score up" if top.contribution > 0 else "pulled the risk score down"
        sentences.append(f"The strongest signal behind the model's score was `{top.feature}`, which {direction}.")

    soft = [
        f for f in result.compliance.flags
        if f.severity == Severity.SOFT and f.rule_id not in result.decision.hard_flags
    ]
    if soft:
        ids = ", ".join(f.rule_id for f in soft)
        noun, verb = ("notes", "were") if len(soft) > 1 else ("note", "was")
        sentences.append(f"{len(soft)} additional {noun} {verb} recorded for reviewers: {ids}.")

    return " ".join(sentences)


def reconstruct_case_result(orchestrator: Orchestrator, case_id: str) -> CaseResult | None:
    """Rebuilds a full CaseResult (risk + compliance + decision) for ANY
    case previously logged — even from a past app run, since it reads only
    the persisted, hash-chained audit log, not in-memory session state.
    This is what makes the Audit Explorer able to show full case detail for
    historical cases, not just the one most recently run in this session.
    Returns None if the case's trace is incomplete (missing an agent step).
    """
    entries = {e.agent.value: e for e in orchestrator.audit.entries_for_case(case_id)}
    if not {"analyst", "compliance", "manager"} <= entries.keys():
        return None
    try:
        risk = RiskOutput.model_validate(entries["analyst"].payload["output"])
        compliance = ComplianceFlags.model_validate(entries["compliance"].payload["output"])
        decision = Decision.model_validate(entries["manager"].payload["output"])
    except Exception:
        return None
    return CaseResult(risk=risk, compliance=compliance, decision=decision)


@dataclass
class VerticalAuditSummary:
    """Real, computed-from-disk summary of one vertical's audit log. Used by
    the Overview and System Health pages. `None` fields mean "no data yet" —
    never filled in with placeholders."""

    key: str
    label: str
    total_cases: int
    outcome_counts: dict[str, int]
    avg_risk_probability: float | None
    avg_processing_seconds: float | None
    chain_ok: bool | None
    last_entry_at: str | None


def summarize_audit_log(vertical_key: str) -> VerticalAuditSummary:
    orchestrator, spec = get_orchestrator(vertical_key)
    entries = orchestrator.audit.read_all()
    if not entries:
        return VerticalAuditSummary(
            key=vertical_key,
            label=spec.label,
            total_cases=0,
            outcome_counts={},
            avg_risk_probability=None,
            avg_processing_seconds=None,
            chain_ok=None,
            last_entry_at=None,
        )

    by_case: dict[str, list] = {}
    for e in entries:
        by_case.setdefault(e.case_id, []).append(e)

    outcome_counts: dict[str, int] = {}
    risk_values: list[float] = []
    durations: list[float] = []
    for case_id, case_entries in by_case.items():
        manager_entry = next((e for e in case_entries if e.agent.value == "manager"), None)
        analyst_entry = next((e for e in case_entries if e.agent.value == "analyst"), None)
        if manager_entry is None:
            continue
        outcome = manager_entry.payload.get("output", {}).get("outcome")
        if outcome:
            outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1
        prob = manager_entry.payload.get("output", {}).get("risk_probability")
        if prob is not None:
            risk_values.append(prob)
        if analyst_entry is not None:
            durations.append((manager_entry.timestamp - analyst_entry.timestamp).total_seconds())

    ok, _ = orchestrator.audit.verify_chain()

    return VerticalAuditSummary(
        key=vertical_key,
        label=spec.label,
        total_cases=len(by_case),
        outcome_counts=outcome_counts,
        avg_risk_probability=(sum(risk_values) / len(risk_values)) if risk_values else None,
        avg_processing_seconds=(sum(durations) / len(durations)) if durations else None,
        chain_ok=ok,
        last_entry_at=entries[-1].timestamp.isoformat() if entries else None,
    )
