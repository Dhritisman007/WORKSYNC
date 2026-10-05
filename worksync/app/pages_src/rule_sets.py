"""Rule Sets — a governance view of each vertical's compliance ruleset
(`verticals/<x>/rules.yaml`), loaded directly from disk via the same
`load_ruleset()` the Compliance Agent itself uses at runtime.

Read-only by design: there is no rule-editing/versioning/publish backend in
this project (rules are edited in the YAML file and the app restarted), so
this page doesn't pretend otherwise with buttons that don't do anything.
"""

from __future__ import annotations

import streamlit as st

from worksync.app import design
from worksync.app.pipeline import VERTICALS
from worksync.core.rule_engine.engine import load_ruleset


def render() -> None:
    design.page_header(
        "Governance / Rule Sets",
        "Rule Sets",
        "The declarative compliance rules each vertical's Compliance agent evaluates — loaded live from rules.yaml.",
    )

    vertical_key = st.selectbox(
        "Vertical", options=list(VERTICALS.keys()), format_func=lambda k: VERTICALS[k]().label
    )
    spec = VERTICALS[vertical_key]()
    ruleset = load_ruleset(spec.rules_path)

    verified_count = sum(1 for r in ruleset.rules if r.verified)
    hard_count = sum(1 for r in ruleset.rules if r.severity.value == "hard")

    design.kpi_row(
        [
            ("Ruleset version", ruleset.version, None, None),
            ("Total rules", str(len(ruleset.rules)), None, None),
            ("Hard / critical", str(hard_count), None, design.CRITICAL),
            ("Verified", f"{verified_count}/{len(ruleset.rules)}", None, design.WARNING if verified_count < len(ruleset.rules) else design.SUCCESS),
        ]
    )

    if verified_count < len(ruleset.rules):
        st.markdown(
            design.badge(
                f"⚠ {len(ruleset.rules) - verified_count} rule(s) not yet verified against the current regulations",
                "warning",
            ),
            unsafe_allow_html=True,
        )

    design.section_title("Rules")
    severity_order = {"hard": 0, "soft": 1, "info": 2}
    for rule in sorted(ruleset.rules, key=lambda r: severity_order.get(r.severity.value, 9)):
        sev = rule.severity.value
        color = design.SEVERITY_HEX.get(sev, design.TEXT_FAINT)
        kind = design.SEVERITY_KIND.get(sev, "neutral")
        sev_label = {"hard": "CRITICAL", "soft": "WARN", "info": "INFO"}.get(sev, sev.upper())
        verified_badge = design.badge("verified", "success") if rule.verified else design.badge("not verified", "warning")
        st.markdown(
            f'<div class="ws-flag" style="--sev:{color};">'
            f'<div class="ws-flag-title">{rule.id} '
            + design.badge(sev_label, kind)
            + " "
            + design.badge(rule.action, "neutral")
            + " "
            + verified_badge
            + "</div>"
            f'<div class="ws-flag-desc">{" ".join(rule.description.split())}</div>'
            f'<div class="ws-flag-meta">{" ".join(rule.source_regulation.split())}</div>'
            f"</div>",
            unsafe_allow_html=True,
        )
        with st.expander(f"Condition — {rule.id}"):
            st.json(rule.condition)
