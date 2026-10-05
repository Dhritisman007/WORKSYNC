"""Case Submission — select a vertical, provide case data (sample dataset
or upload), validate, and run it through the real four-agent pipeline.
Results render below: decision, risk analysis, compliance, a "why this
decision" explanation, a timeline, and the audit trail.

Everything here calls the exact same Orchestrator/agents as every other
entry point in the project (run_samples.py, the test suite) — this page
adds presentation and workflow structure around that pipeline, not a
different code path into it.
"""

from __future__ import annotations

import time
from typing import Any

import pandas as pd
import streamlit as st

from worksync.app import components, design
from worksync.app.pipeline import (
    PIPELINE_STEPS,
    VERTICALS,
    _ensure_id,
    build_narrative,
    detect_vertical,
    get_orchestrator,
    load_data,
    parse_uploaded_file,
)
from worksync.core.orchestrator import CaseResult, Orchestrator
from worksync.core.schemas.models import CaseRecord


def _row_fingerprint(vertical_key: str, idx: int, row: Any) -> tuple:
    items = tuple(sorted((str(k), str(v)) for k, v in dict(row).items()))
    return (vertical_key, idx, items)


def _step_select_vertical() -> str:
    design.section_title("Step 1 — Select vertical")
    st.session_state.setdefault("cs_vertical", "loan")

    cols = st.columns(4)
    for col, key in zip(cols, VERTICALS.keys()):
        spec = VERTICALS[key]()
        selected = st.session_state["cs_vertical"] == key
        border = design.ACCENT if selected else design.BORDER
        with col:
            st.markdown(
                f'<div class="ws-panel ws-panel-lift" style="border-color:{border}; border-width:1.5px; min-height:132px;">'
                f'<div style="font-weight:600; font-size:13.5px;">{spec.label}</div>'
                f'<div style="font-size:11.5px; color:{design.TEXT_MUTED}; margin-top:.4rem;">{spec.data_desc}</div>'
                f'<div style="font-size:11.5px; color:{design.TEXT_FAINT}; margin-top:.25rem;">{spec.model_desc}</div>'
                f'<div style="font-size:11.5px; color:{design.TEXT_FAINT};">{spec.rules_desc}</div>'
                f"</div>",
                unsafe_allow_html=True,
            )
            if st.button(
                "Selected" if selected else "Select",
                key=f"pick-{key}",
                width="stretch",
                type="primary" if selected else "secondary",
            ):
                st.session_state["cs_vertical"] = key
                st.rerun()

    return st.session_state["cs_vertical"]


def _step_case_data(vertical_key: str) -> tuple[Any, int, str]:
    """Returns (row, idx, resolved_vertical_key) — resolved may differ from
    `vertical_key` if the user uploads a file that clearly belongs to a
    different vertical and chooses to switch."""
    design.section_title("Step 2 — Case data")
    orchestrator, spec = get_orchestrator(vertical_key)
    df = load_data(vertical_key, str(spec.data_path))

    source = st.radio("Source", ["Sample dataset", "Upload a file"], horizontal=True, key="cs_source")

    if source == "Sample dataset":
        if df is None:
            st.warning(
                f"Sample data not found at `{spec.data_path}`. "
                f"See `worksync/verticals/{vertical_key}/README.md`, or switch to 'Upload a file'."
            )
            st.stop()
        max_index = len(df) - 1
        col1, col2 = st.columns([3, 1])
        with col1:
            row_index = st.number_input("Row index", min_value=0, max_value=max_index, value=0, step=1)
        with col2:
            st.write("")
            st.write("")
            if st.button("Random", width="stretch"):
                row_index = int(df.sample(1).index[0])
        row = df.iloc[row_index]
        idx = int(row.name)
        if spec.label_col and spec.label_col in df.columns:
            st.caption(f"Ground-truth `{spec.label_col}`: {row[spec.label_col]}")
        return row, idx, vertical_key

    # Upload a file
    st.caption(
        "Upload a raw case file: CSV (one or more rows) or JSON (one record, or a list). "
        "Same raw column names as the vertical's own source data."
    )
    with st.expander("Need a template?"):
        for vkey, factory in VERTICALS.items():
            vspec = factory()
            vdf = load_data(vkey, str(vspec.data_path))
            if vdf is None or len(vdf) == 0:
                st.caption(f"{vspec.label}: sample data not available locally.")
                continue
            cols = [c for c in vdf.columns if vspec.label_col is None or c != vspec.label_col]
            st.download_button(
                f"{vspec.label} template (CSV)",
                data=vdf.iloc[[0]][cols].to_csv(index=False),
                file_name=f"{vkey}_template.csv",
                mime="text/csv",
                key=f"template-{vkey}",
            )

    uploaded = st.file_uploader("Raw case file", type=["csv", "json"], key="cs-upload")
    if uploaded is None:
        st.info("Upload a CSV or JSON file to continue.")
        st.stop()

    try:
        upload_df = parse_uploaded_file(uploaded)
    except Exception as exc:
        st.error(f"Couldn't parse `{uploaded.name}`: {exc}")
        st.stop()
    if upload_df.empty:
        st.error("The uploaded file has no rows.")
        st.stop()

    matches = detect_vertical(list(upload_df.columns))
    best = matches[0] if matches else None
    resolved_key = vertical_key

    if best and best.coverage >= 0.4 and best.key != vertical_key:
        st.warning(
            f"This file's columns match **{best.label}** ({best.coverage:.0%}), not the "
            f"**{VERTICALS[vertical_key]().label}** selected in Step 1."
        )
        if st.button(f"Use detected vertical ({best.label}) instead"):
            st.session_state["cs_vertical"] = best.key
            st.rerun()
    elif best is None or best.coverage == 0:
        st.warning("Couldn't match these columns to any known vertical schema.")

    with st.expander("Column match scores"):
        st.dataframe(
            pd.DataFrame(
                [{"vertical": m.label, "columns matched": m.overlap, "coverage": f"{m.coverage:.0%}"} for m in matches]
            ),
            width="stretch",
            hide_index=True,
        )

    idx = 0
    if len(upload_df) > 1:
        idx = st.number_input("Row in uploaded file", min_value=0, max_value=len(upload_df) - 1, value=0, step=1)
    row = upload_df.iloc[idx]
    with st.expander("Preview uploaded row"):
        st.dataframe(pd.DataFrame(sorted(row.items()), columns=["column", "value"]), width="stretch", hide_index=True)

    return row, idx, resolved_key


def _step_validate(vertical_key: str, row: Any) -> None:
    design.section_title("Step 3 — Validation")
    spec = VERTICALS[vertical_key]()
    if not spec.raw_columns:
        st.markdown(
            design.badge("✓ Valid", "success") + " — no schema check configured for this vertical.",
            unsafe_allow_html=True,
        )
        return

    row_cols = set(dict(row).keys())
    expected = set(spec.raw_columns)
    coverage = len(row_cols & expected) / len(expected)

    if coverage >= 0.7:
        kind, label = "success", f"✓ Valid — {coverage:.0%} schema match"
    elif coverage >= 0.4:
        kind, label = "warning", f"⚠ Partial — {coverage:.0%} schema match"
    else:
        kind, label = "critical", f"✕ Low match — {coverage:.0%} schema match"

    st.markdown(design.badge(label, kind), unsafe_allow_html=True)
    missing = expected - row_cols
    if missing:
        st.caption(f"Missing columns will be treated as unknown by the model/rules: {', '.join(sorted(missing))}")


def _run_case_with_progress(orchestrator: Orchestrator, case: CaseRecord) -> CaseResult:
    with st.status("Running case through the pipeline…", expanded=True) as status:
        placeholders = {key: st.empty() for key, _ in PIPELINE_STEPS}
        for key, label in PIPELINE_STEPS:
            placeholders[key].markdown(
                f'<div class="ws-step ws-step-pending"><span class="ws-step-dot"></span>{label}</div>',
                unsafe_allow_html=True,
            )

        def on_step(stage: str) -> None:
            label = dict(PIPELINE_STEPS)[stage]
            placeholders[stage].markdown(
                f'<div class="ws-step ws-step-done"><span class="ws-step-dot"></span>{label}</div>',
                unsafe_allow_html=True,
            )
            time.sleep(0.15)

        result = orchestrator.run_case_with_detail(case, on_step=on_step)
        status.update(label="Pipeline complete — 4/4 steps", state="complete", expanded=False)
    return result


def render() -> None:
    design.page_header(
        "Cases / Case Submission",
        "Case Submission",
        "Select a vertical, provide case data, and run it through the live four-agent pipeline.",
    )

    vertical_key = _step_select_vertical()
    row, idx, resolved_key = _step_case_data(vertical_key)
    row = _ensure_id(row, VERTICALS[resolved_key]().id_col, idx)
    _step_validate(resolved_key, row)

    design.section_title("Step 4 — Run")
    run_clicked = st.button("Run decision", type="primary", width="stretch")
    if run_clicked:
        st.session_state["active_case"] = {"vertical_key": resolved_key, "row": row, "idx": idx}

    active = st.session_state.get("active_case")
    if active is None:
        st.markdown(
            '<div class="ws-panel">No case has been run yet — nothing below reflects real data '
            "until you click <strong>Run decision</strong>.</div>",
            unsafe_allow_html=True,
        )
        return

    orchestrator, spec = get_orchestrator(active["vertical_key"])
    try:
        case = spec.row_to_case(active["row"], active["idx"])
    except Exception as exc:
        st.error(f"Couldn't build a case record: {exc}")
        return

    fingerprint = _row_fingerprint(active["vertical_key"], active["idx"], active["row"])
    cache = st.session_state.setdefault("case_result_cache", {})
    if fingerprint in cache:
        result = cache[fingerprint]
    else:
        try:
            result = _run_case_with_progress(orchestrator, case)
        except Exception as exc:
            st.error(f"Couldn't run this case through the pipeline: {exc}")
            return
        cache[fingerprint] = result

    grey_low = orchestrator.manager.config.grey_band_lower
    grey_high = orchestrator.manager.config.grey_band_upper

    st.markdown(f"**Case:** `{case.case_id}` · vertical: `{case.vertical.value}` · entity: `{case.entity_id}`")
    components.render_decision_banner(result, build_narrative(result, grey_low, grey_high))

    prob_display = f"{result.decision.risk_probability:.1%}" if result.decision.risk_probability is not None else "—"
    design.kpi_row(
        [
            ("Risk score", prob_display, None, None),
            ("Confidence", result.decision.confidence_band or "—", None, None),
            ("Compliance flags", str(len(result.compliance.flags)), None, None),
            ("Model version", result.risk.model_version, None, None),
        ]
    )
    st.markdown(
        components.risk_gauge_html(result.decision.risk_probability or 0.0, grey_low, grey_high, design.ACCENT),
        unsafe_allow_html=True,
    )

    tab_why, tab_risk, tab_compliance, tab_case, tab_timeline, tab_audit = st.tabs(
        ["Why this decision", "Risk analysis", "Compliance", "Case record", "Timeline", "Audit trail"]
    )
    with tab_why:
        components.render_why_block(result, grey_low, grey_high)
    with tab_risk:
        components.render_risk_block(result)
    with tab_compliance:
        components.render_compliance_block(result)
    with tab_case:
        rows = [(k, str(v)) for k, v in sorted(case.features.items())]
        st.dataframe(pd.DataFrame(rows, columns=["feature", "value"]), width="stretch", hide_index=True)
    with tab_timeline:
        components.render_timeline_block(orchestrator, case.case_id)
    with tab_audit:
        components.render_audit_block(orchestrator, case.case_id)
