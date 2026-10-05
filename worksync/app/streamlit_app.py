"""WorkSync.AI demo: pick a vertical and a case, watch it move through the
shared pipeline step by step, and see a clear verdict — the decision,
confidence, a plain-English explanation of why, then the supporting detail
(case record, risk model, compliance flags, audit trail) in tabs below.

This file is the one place the project deliberately imports every
vertical's specifics by name (the `VERTICALS` registry below) — that's
expected and fine: something has to know all four verticals exist in order
to offer a picker. What matters structurally is that everything below the
registry — `Orchestrator`, `ComplianceAgent`, `ManagerAgent`, `AuditLog` —
is the exact same shared code for every one of them.

Run with: streamlit run worksync/app/streamlit_app.py
"""

from __future__ import annotations

import json
import time
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
from worksync.core.schemas.models import CaseRecord, Severity

st.set_page_config(page_title="WorkSync.AI", layout="wide")

OUTCOME_STYLE = {
    "approve": {"accent": "#1b7a3d", "bg": "#e8f5ee", "label": "Approved"},
    "reject": {"accent": "#b3261e", "bg": "#fdecea", "label": "Rejected"},
    "escalate": {"accent": "#946200", "bg": "#fff4e0", "label": "Escalated for review"},
}

PIPELINE_STEPS = [
    ("ingest", "Ingesting case record into the shared contract"),
    ("analyst", "Analyst agent — risk model + SHAP attribution"),
    ("compliance", "Compliance agent — evaluating ruleset"),
    ("manager", "Manager agent — applying decision policy"),
]


def inject_css() -> None:
    st.markdown(
        """
        <style>
        .wsync-topbar { height: 4px; background: linear-gradient(90deg, #1b3a6b, #2d6cdf 45%, #1b7a3d); border-radius: 2px; margin-bottom: 1.1rem; }
        .wsync-eyebrow { font-size: 12px; letter-spacing: .08em; text-transform: uppercase; color: #8a93a6; font-weight: 600; margin-bottom: .15rem; }
        .wsync-card { border: 1px solid rgba(140,150,170,0.25); border-radius: 10px; padding: 1rem 1.2rem; margin-bottom: .9rem; background: rgba(140,150,170,0.05); }
        .wsync-step-done { color: #1b7a3d; font-size: 14px; margin: .15rem 0; }
        .wsync-step-pending { color: #8a93a6; font-size: 14px; margin: .15rem 0; }
        .wsync-chip { display:inline-block; padding:2px 9px; border-radius:999px; font-size:12px; font-weight:600; margin-right:6px; }
        .wsync-flag-card { border-left: 4px solid; border-radius: 6px; padding: .6rem .9rem; margin-bottom: .55rem; background: rgba(140,150,170,0.06); }
        .wsync-flag-title { font-weight: 600; font-size: 14px; }
        .wsync-flag-desc { font-size: 13px; color: #a9b0bd; margin-top: 2px; }
        .wsync-flag-meta { font-size: 11.5px; color: #8a93a6; margin-top: 4px; }
        </style>
        """,
        unsafe_allow_html=True,
    )


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
    id_col: str | None = None  # raw column row_to_case reads as entity id, if any


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
        id_col="SK_ID_CURR",
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
        id_col="applicant_id",
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
        id_col="PolicyNumber",
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


# --------------------------------------------------------------------------
# Conclusion: a plain-English narrative built from the decision + flags.
# --------------------------------------------------------------------------


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


def risk_gauge_html(prob: float, low: float, high: float, accent: str) -> str:
    pct = max(0.0, min(1.0, prob)) * 100
    low_pct = max(0.0, min(100.0, low * 100))
    high_pct = max(0.0, min(100.0, high * 100))
    return f"""
    <div style="margin: .3rem 0 .2rem 0;">
      <div style="position:relative; height:10px; border-radius:6px; overflow:hidden;
                  background: linear-gradient(to right,
                    rgba(27,122,61,0.35) 0%, rgba(27,122,61,0.35) {low_pct}%,
                    rgba(148,98,0,0.35) {low_pct}%, rgba(148,98,0,0.35) {high_pct}%,
                    rgba(179,38,30,0.35) {high_pct}%, rgba(179,38,30,0.35) 100%);">
        <div style="position:absolute; top:-3px; left:calc({pct}% - 2px); width:4px; height:16px;
                    background:{accent}; border-radius:2px;"></div>
      </div>
      <div style="display:flex; justify-content:space-between; font-size:11px; color:#8a93a6; margin-top:3px;">
        <span>0%</span><span>grey band {low:.0%}–{high:.0%}</span><span>100%</span>
      </div>
    </div>
    """


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def render_header() -> None:
    st.markdown('<div class="wsync-topbar"></div>', unsafe_allow_html=True)
    st.markdown('<div class="wsync-eyebrow">BFSI decisioning framework</div>', unsafe_allow_html=True)
    st.title("WorkSync.AI")
    st.caption(
        "One four-agent pipeline — Analyst, Compliance, Manager, observed by Audit — "
        "reused unchanged across four BFSI verticals."
    )


def run_case_with_progress(orchestrator: Orchestrator, case: CaseRecord) -> CaseResult:
    with st.status("Running case through the pipeline…", expanded=True) as status:
        placeholders = {key: st.empty() for key, _ in PIPELINE_STEPS}
        for key, label in PIPELINE_STEPS:
            placeholders[key].markdown(f'<div class="wsync-step-pending">○ &nbsp;{label}</div>', unsafe_allow_html=True)

        def on_step(stage: str) -> None:
            label = dict(PIPELINE_STEPS)[stage]
            placeholders[stage].markdown(f'<div class="wsync-step-done">✓ &nbsp;{label}</div>', unsafe_allow_html=True)
            time.sleep(0.2)

        result = orchestrator.run_case_with_detail(case, on_step=on_step)
        status.update(label="Pipeline complete — 4/4 steps", state="complete", expanded=False)
    return result


def render_conclusion(result: CaseResult, orchestrator: Orchestrator) -> None:
    outcome = result.decision.outcome.value
    style = OUTCOME_STYLE[outcome]
    grey_low = orchestrator.manager.config.grey_band_lower
    grey_high = orchestrator.manager.config.grey_band_upper
    narrative = build_narrative(result, grey_low, grey_high)

    st.markdown(
        f"""
        <div style="border-left: 6px solid {style['accent']}; background:{style['bg']};
                    color:#1a1a1a; padding:1.1rem 1.4rem; border-radius:10px; margin: .4rem 0 1rem 0;">
          <div style="font-size:12px; text-transform:uppercase; letter-spacing:.07em;
                      color:{style['accent']}; font-weight:700;">Decision</div>
          <div style="font-size:26px; font-weight:700; color:{style['accent']}; margin:.1rem 0 .55rem 0;">
            {style['label']}
          </div>
          <div style="font-size:14.5px; line-height:1.55;">{narrative}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns(3)
    col1.metric("Risk probability", f"{result.decision.risk_probability:.1%}" if result.decision.risk_probability is not None else "—")
    col2.metric("Model confidence", result.decision.confidence_band or "—")
    col3.metric("Compliance flags", len(result.compliance.flags))

    st.markdown(
        risk_gauge_html(result.decision.risk_probability or 0.0, grey_low, grey_high, style["accent"]),
        unsafe_allow_html=True,
    )


def render_risk_tab(result: CaseResult) -> None:
    c1, c2, c3 = st.columns(3)
    c1.metric("Risk probability", f"{result.risk.risk_probability:.4f}")
    c2.metric("Confidence band", result.risk.confidence_band)
    c3.metric("Model", f"{result.risk.model_name} · {result.risk.model_version}")

    st.markdown("**Top SHAP attributions**")
    st.caption("Positive bars pushed the risk score up; negative bars pulled it down.")
    attr_df = pd.DataFrame(
        [(a.feature, a.contribution) for a in result.risk.top_attributions],
        columns=["feature", "contribution"],
    ).set_index("feature")
    st.bar_chart(attr_df)


def render_case_record_tab(case: CaseRecord) -> None:
    st.caption(f"`{case.case_id}` · vertical: `{case.vertical.value}` · entity: `{case.entity_id}`")
    rows = [(k, str(v)) for k, v in sorted(case.features.items())]
    st.dataframe(pd.DataFrame(rows, columns=["feature", "value"]), width="stretch", hide_index=True)


def render_compliance_tab(result: CaseResult) -> None:
    st.caption(f"Ruleset version: `{result.compliance.ruleset_version}`")
    if not result.compliance.flags:
        st.markdown(
            '<div class="wsync-card">No rules triggered for this case.</div>', unsafe_allow_html=True
        )
        return

    severity_color = {"hard": "#b3261e", "soft": "#946200", "info": "#2d6cdf"}
    for f in result.compliance.flags:
        color = severity_color.get(f.severity.value, "#8a93a6")
        verified = "verified" if f.verified else "not yet verified"
        st.markdown(
            f"""
            <div class="wsync-flag-card" style="border-color:{color};">
              <div class="wsync-flag-title">{f.rule_id}
                <span class="wsync-chip" style="background:{color}22; color:{color};">{f.severity.value}</span>
                <span class="wsync-chip" style="background:#8a93a622; color:#8a93a6;">{f.action}</span>
              </div>
              <div class="wsync-flag-desc">{_clean(f.description)}</div>
              <div class="wsync-flag-meta">{f.source_regulation} · {verified}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_audit_tab(orchestrator: Orchestrator, case_id: str) -> None:
    entries = orchestrator.audit.entries_for_case(case_id)
    st.caption(f"{len(entries)} recorded step(s) for this case, hash-chained into the full audit log.")
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
    inject_css()
    render_header()

    with st.sidebar:
        st.header("Pick a case")
        vertical_key = st.selectbox(
            "Vertical",
            options=list(VERTICALS.keys()),
            format_func=lambda k: VERTICALS[k]().label,
        )
        orchestrator, spec = get_orchestrator(vertical_key)
        df = load_data(vertical_key, str(spec.data_path))

        source = st.radio("Case source", ["Sample dataset", "Upload a file"], horizontal=True)

        row: Any = None
        idx = 0

        if source == "Sample dataset":
            if df is None:
                st.warning(
                    f"Data file not found at `{spec.data_path}`. "
                    f"See `worksync/verticals/{vertical_key}/README.md` for how to get/generate it, "
                    f"or switch to 'Upload a file' above."
                )
                st.stop()

            max_index = len(df) - 1
            row_index = st.number_input("Row index", min_value=0, max_value=max_index, value=0, step=1)
            if st.button("New random case"):
                row_index = int(df.sample(1).index[0])
            row = df.iloc[row_index]
            idx = int(row.name)
            if spec.label_col and spec.label_col in df.columns:
                st.caption(f"Ground-truth `{spec.label_col}`: {row[spec.label_col]}")

        else:  # Upload a file
            st.caption(
                f"Upload a raw {spec.label} case: CSV (one or more rows) or JSON "
                "(one record, or a list of records) — the same raw column "
                "names as the vertical's own source data, not the engineered "
                "feature names."
            )
            if df is not None and len(df) > 0:
                template_cols = [c for c in df.columns if spec.label_col is None or c != spec.label_col]
                template_csv = df.iloc[[0]][template_cols].to_csv(index=False)
                st.download_button(
                    "Download a template row (CSV)",
                    data=template_csv,
                    file_name=f"{vertical_key}_template.csv",
                    mime="text/csv",
                )

            uploaded = st.file_uploader("Raw case file", type=["csv", "json"], key=f"upload-{vertical_key}")
            if uploaded is None:
                st.info("Upload a CSV or JSON file to run it through the pipeline.")
                st.stop()

            try:
                upload_df = parse_uploaded_file(uploaded)
            except Exception as exc:
                st.error(f"Couldn't parse `{uploaded.name}`: {exc}")
                st.stop()

            if upload_df.empty:
                st.error("The uploaded file has no rows.")
                st.stop()

            st.success(f"Loaded {len(upload_df)} row(s) from `{uploaded.name}`.")
            if len(upload_df) > 1:
                idx = st.number_input(
                    "Row in uploaded file", min_value=0, max_value=len(upload_df) - 1, value=0, step=1
                )
            row = upload_df.iloc[idx]
            with st.expander("Preview uploaded row"):
                st.dataframe(
                    pd.DataFrame(sorted(row.items()), columns=["column", "value"]),
                    width="stretch",
                    hide_index=True,
                )

        row = _ensure_id(row, spec.id_col, idx)

    try:
        case = spec.row_to_case(row, idx)
        result = run_case_with_progress(orchestrator, case)
    except Exception as exc:
        st.error(f"Couldn't run this case through the pipeline: {exc}")
        st.stop()

    render_conclusion(result, orchestrator)

    tab_risk, tab_case, tab_compliance, tab_audit = st.tabs(
        ["Risk analysis", "Case record", "Compliance", "Audit trail"]
    )
    with tab_risk:
        render_risk_tab(result)
    with tab_case:
        render_case_record_tab(case)
    with tab_compliance:
        render_compliance_tab(result)
    with tab_audit:
        render_audit_tab(orchestrator, case.case_id)


if __name__ == "__main__":
    main()
