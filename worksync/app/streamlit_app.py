"""WorkSync.AI — BFSI decisioning console entry point.

Defines the application shell (navigation, header) and routes to each page.
All pages share the exact same underlying pipeline (`worksync/app/pipeline.py`)
and agents (`worksync/core/`) — nothing about the four-agent architecture,
decision logic, compliance rules, or model code changes between pages; this
file and `pages_src/` are presentation and navigation only.

Run with: streamlit run worksync/app/streamlit_app.py
"""

from __future__ import annotations

import streamlit as st

from worksync.app import design
from worksync.app.pages_src import audit_explorer, case_submission, models_bands, overview, rule_sets, system_health

st.set_page_config(page_title="WorkSync.AI", page_icon="◆", layout="wide")
design.inject_css()

with st.sidebar:
    st.markdown(
        '<div style="font-weight:700; font-size:16px; letter-spacing:-.01em;">WORKSYNC.AI</div>'
        f'<div style="font-size:10.5px; color:{design.TEXT_FAINT}; letter-spacing:.06em; margin-bottom:.8rem;">'
        "BFSI DECISIONING PLATFORM</div>",
        unsafe_allow_html=True,
    )

pages = {
    "": [st.Page(overview.render, title="Overview", icon=":material/space_dashboard:", url_path="overview", default=True)],
    "Cases": [st.Page(case_submission.render, title="Case Submission", icon=":material/fact_check:", url_path="case-submission")],
    "Governance": [
        st.Page(audit_explorer.render, title="Audit Explorer", icon=":material/history:", url_path="audit-explorer"),
        st.Page(rule_sets.render, title="Rule Sets", icon=":material/gavel:", url_path="rule-sets"),
        st.Page(models_bands.render, title="Models & Bands", icon=":material/insights:", url_path="models-bands"),
    ],
    "System": [st.Page(system_health.render, title="Agent Health", icon=":material/monitor_heart:", url_path="agent-health")],
}

current_page = st.navigation(pages, expanded=True)

with st.sidebar:
    st.divider()
    st.markdown(
        f'<div style="font-size:11px; color:{design.TEXT_FAINT};">'
        f'{design.badge("● SYSTEM OPERATIONAL", "success")}'
        f'<div style="margin-top:.4rem;">Environment: Prototype</div>'
        f"</div>",
        unsafe_allow_html=True,
    )

current_page.run()
