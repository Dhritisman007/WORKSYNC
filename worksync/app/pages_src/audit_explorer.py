"""Audit Explorer — search the real, persisted, hash-chained audit log for
any vertical, inspect any past case's full agent trace, verify the chain,
and replay a case to confirm its decision is still reproducible.

Reads directly from each vertical's `logs/audit/<vertical>.jsonl` file —
this works across app restarts, not just within the current session, since
the audit log itself (not session state) is the source of truth.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from worksync.app import components, design
from worksync.app.pipeline import VERTICALS, build_narrative, get_orchestrator, reconstruct_case_result


def render() -> None:
    design.page_header(
        "Governance / Audit Explorer",
        "Audit Explorer",
        "Search the hash-chained audit log, inspect any case's full agent trace, verify integrity, and replay.",
    )

    vertical_key = st.selectbox(
        "Vertical", options=list(VERTICALS.keys()), format_func=lambda k: VERTICALS[k]().label
    )
    orchestrator, spec = get_orchestrator(vertical_key)
    entries = orchestrator.audit.read_all()

    if not entries:
        st.markdown(
            f'<div class="ws-panel">No audit entries yet for {spec.label}. Run a case from '
            "<strong>Cases → Case Submission</strong> first.</div>",
            unsafe_allow_html=True,
        )
        return

    ok, bad_index = orchestrator.audit.verify_chain()
    design.kpi_row(
        [
            ("Total entries", f"{len(entries):,}", None, None),
            ("Cases logged", f"{len({e.case_id for e in entries}):,}", None, None),
            ("Chain status", "VERIFIED" if ok else "TAMPERED", None, design.SUCCESS if ok else design.CRITICAL),
            ("Last entry", entries[-1].timestamp.strftime("%Y-%m-%d %H:%M:%S"), None, None),
        ]
    )
    if not ok:
        st.markdown(design.badge(f"✕ TAMPERING DETECTED at entry {bad_index}", "critical"), unsafe_allow_html=True)
    else:
        st.markdown(design.badge("✓ HASH CHAIN VERIFIED", "success"), unsafe_allow_html=True)

    design.section_title("Search")
    by_case: dict[str, list] = {}
    for e in entries:
        by_case.setdefault(e.case_id, []).append(e)

    case_rows = []
    for case_id, case_entries in by_case.items():
        manager_entry = next((e for e in case_entries if e.agent.value == "manager"), None)
        outcome = manager_entry.payload.get("output", {}).get("outcome") if manager_entry else None
        case_rows.append(
            {
                "case_id": case_id,
                "outcome": outcome or "incomplete",
                "steps": len(case_entries),
                "last_seen": max(e.timestamp for e in case_entries),
            }
        )
    case_rows.sort(key=lambda r: r["last_seen"], reverse=True)

    col1, col2 = st.columns([2, 1])
    with col1:
        search = st.text_input("Filter by case ID", placeholder="e.g. loan-100002")
    with col2:
        outcome_filter = st.selectbox("Outcome", ["All", "approve", "reject", "escalate", "incomplete"])

    filtered = [
        r for r in case_rows
        if (not search or search.lower() in r["case_id"].lower())
        and (outcome_filter == "All" or r["outcome"] == outcome_filter)
    ]

    st.dataframe(
        pd.DataFrame(
            [
                {
                    "case_id": r["case_id"],
                    "outcome": r["outcome"],
                    "steps": r["steps"],
                    "last_seen": r["last_seen"].strftime("%Y-%m-%d %H:%M:%S"),
                }
                for r in filtered
            ]
        ),
        width="stretch",
        hide_index=True,
    )

    if not filtered:
        st.caption("No cases match this filter.")
        return

    design.section_title("Case detail")
    selected_case_id = st.selectbox("Open case", options=[r["case_id"] for r in filtered])

    result = reconstruct_case_result(orchestrator, selected_case_id)
    if result is None:
        st.warning("This case's audit trace is incomplete (missing an agent step) — cannot reconstruct full detail.")
        components.render_audit_block(orchestrator, selected_case_id, allow_replay=False)
        return

    grey_low = orchestrator.manager.config.grey_band_lower
    grey_high = orchestrator.manager.config.grey_band_upper
    components.render_decision_banner(result, build_narrative(result, grey_low, grey_high))

    tab_why, tab_risk, tab_compliance, tab_timeline, tab_audit = st.tabs(
        ["Why this decision", "Risk analysis", "Compliance", "Timeline", "Audit trail"]
    )
    with tab_why:
        components.render_why_block(result, grey_low, grey_high)
    with tab_risk:
        components.render_risk_block(result)
    with tab_compliance:
        components.render_compliance_block(result)
    with tab_timeline:
        components.render_timeline_block(orchestrator, selected_case_id)
    with tab_audit:
        components.render_audit_block(orchestrator, selected_case_id)
