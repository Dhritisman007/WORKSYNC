"""Overview — the landing dashboard. Real KPIs computed from each
vertical's actual hash-chained audit log; if no cases have been run yet in
any vertical, it says so rather than showing placeholder numbers.
"""

from __future__ import annotations

import streamlit as st

from worksync.app import design
from worksync.app.pipeline import VERTICALS, summarize_audit_log

OUTCOME_LABELS = {"approve": "Approved", "reject": "Rejected", "escalate": "Escalated"}


def render() -> None:
    design.page_header(
        "BFSI decisioning framework",
        "Decision Intelligence Console",
        "Automated risk scoring, regulatory compliance, decisioning and auditability across BFSI workflows.",
    )

    summaries = [summarize_audit_log(key) for key in VERTICALS]
    total_cases = sum(s.total_cases for s in summaries)

    design.section_title("System status")

    if total_cases == 0:
        st.markdown(
            '<div class="ws-panel">No cases have been run yet in this environment — the KPIs below '
            "will populate from the real, hash-chained audit log as soon as a case is submitted from "
            '<strong>Cases → Case Submission</strong>.</div>',
            unsafe_allow_html=True,
        )
    else:
        outcome_totals: dict[str, int] = {}
        for s in summaries:
            for outcome, count in s.outcome_counts.items():
                outcome_totals[outcome] = outcome_totals.get(outcome, 0) + count

        risk_values = [s.avg_risk_probability for s in summaries if s.avg_risk_probability is not None]
        avg_risk = sum(risk_values) / len(risk_values) if risk_values else None
        duration_values = [s.avg_processing_seconds for s in summaries if s.avg_processing_seconds is not None]
        avg_duration = sum(duration_values) / len(duration_values) if duration_values else None

        design.kpi_row(
            [
                ("Total cases", f"{total_cases:,}", "across all verticals", None),
                ("Approved", f"{outcome_totals.get('approve', 0):,}", None, design.SUCCESS),
                ("Rejected", f"{outcome_totals.get('reject', 0):,}", None, design.CRITICAL),
                ("Escalated", f"{outcome_totals.get('escalate', 0):,}", None, design.WARNING),
                ("Avg. risk score", f"{avg_risk:.1%}" if avg_risk is not None else "—", None, None),
                (
                    "Avg. decision time",
                    f"{avg_duration:.2f}s" if avg_duration is not None else "—",
                    "analyst → manager",
                    None,
                ),
            ]
        )

        chain_bad = [s for s in summaries if s.chain_ok is False]
        if chain_bad:
            st.error(
                "Hash chain tampering detected in: " + ", ".join(s.label for s in chain_bad) + ". "
                "See Governance → Audit Explorer."
            )
        else:
            st.markdown(design.badge("ALL AUDIT CHAINS VERIFIED", "success"), unsafe_allow_html=True)

        design.section_title("By vertical")
        cols = st.columns(4)
        for col, s in zip(cols, summaries):
            with col:
                counts_line = " · ".join(
                    f"{OUTCOME_LABELS.get(o, o)} {c}" for o, c in sorted(s.outcome_counts.items())
                ) or "No decisions yet"
                st.markdown(
                    f'<div class="ws-panel ws-panel-lift">'
                    f'<div style="font-weight:600; font-size:13.5px;">{s.label}</div>'
                    f'<div style="font-size:20px; font-weight:700; margin-top:.25rem;">{s.total_cases:,}</div>'
                    f'<div style="font-size:11px; color:{design.TEXT_FAINT};">cases processed</div>'
                    f'<div style="font-size:11.5px; color:{design.TEXT_MUTED}; margin-top:.4rem;">{counts_line}</div>'
                    f"</div>",
                    unsafe_allow_html=True,
                )

    design.section_title("Four-agent architecture")
    st.caption(
        "The same Analyst, Compliance, Manager and Audit agents run unchanged across all four verticals "
        "— only the data adapter, model, rule set and config file differ per vertical."
    )
    design.render_pipeline_diagram()

    with st.expander("How WorkSync works"):
        st.markdown(
            """
Each case moves through a fixed pipeline, identical for every vertical:

1. **Ingestion** normalizes raw vertical input (a loan application, a KYC
   record, a transaction, a claim) into one shared, versioned case-record
   contract.
2. **Analyst agent** and **Compliance agent** run independently on that
   same case record — one scores risk with a calibrated model and explains
   it with SHAP, the other evaluates a declarative YAML ruleset and
   produces structured compliance flags.
3. **Manager agent** combines both outputs under a fixed precedence: a
   triggered hard compliance rule always wins (never overridden by a good
   risk score); otherwise, a high-confidence score outside the configured
   grey band auto-decides; everything else escalates to a human reviewer.
4. **Audit agent** observes every agent's input, output and timestamp
   without altering the flow, writing an append-only, hash-chained,
   replayable log entry.

Go to **Cases → Case Submission** to run a real case through this pipeline,
or **Governance → Audit Explorer** to inspect the hash chain.
            """
        )
