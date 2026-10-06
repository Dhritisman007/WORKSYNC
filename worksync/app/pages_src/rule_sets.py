"""Rule Sets — a governance view of each vertical's compliance ruleset
(`verticals/<x>/rules.yaml`), loaded directly from disk via the same
`load_ruleset()` the Compliance Agent itself uses at runtime.

Read-only by design: there is no rule-editing/versioning/publish backend in
this project (rules are edited in the YAML file and the app restarted), so
this page doesn't pretend otherwise with buttons that don't do anything.
"""

from __future__ import annotations

import html

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

    reg_rules = [r for r in ruleset.rules if r.basis == "regulation"]
    checked = sum(1 for r in reg_rules if r.verified)
    policy_count = len(ruleset.rules) - len(reg_rules)
    hard_count = sum(1 for r in ruleset.rules if r.severity.value == "hard")

    design.kpi_row(
        [
            ("Ruleset version", ruleset.version, None, None),
            ("Total rules", str(len(ruleset.rules)), None, None),
            ("Hard / critical", str(hard_count), None, design.CRITICAL),
            ("Citations checked", f"{checked}/{len(reg_rules)}", None, design.WARNING if checked < len(reg_rules) else design.SUCCESS),
            ("Internal policy", str(policy_count), None, None),
        ]
    )

    if checked < len(reg_rules):
        st.markdown(
            design.badge(f"⚠ {len(reg_rules) - checked} regulation citation(s) not yet checked against the source", "warning"),
            unsafe_allow_html=True,
        )
    st.caption(
        "**Regulation** rules cite a section copied from the regulator's official text — the date shows when it was "
        "last checked; re-check at the source link before relying on it. **Internal policy** rules are thresholds "
        "no regulation prescribes, so there is nothing to verify — the team owns those numbers."
    )

    design.section_title("Rules")
    severity_order = {"hard": 0, "soft": 1, "info": 2}
    for rule in sorted(ruleset.rules, key=lambda r: severity_order.get(r.severity.value, 9)):
        sev = rule.severity.value
        color = design.SEVERITY_HEX.get(sev, design.TEXT_FAINT)
        kind = design.SEVERITY_KIND.get(sev, "neutral")
        sev_label = {"hard": "CRITICAL", "soft": "WARN", "info": "INFO"}.get(sev, sev.upper())
        if rule.basis == "internal_policy":
            status_badge = design.badge("internal policy", "accent")
        elif rule.verified:
            status_badge = design.badge("✓ citation checked", "success")
        else:
            status_badge = design.badge("not verified", "warning")

        meta = html.escape(" ".join(rule.source_regulation.split()))
        if rule.reference_url:
            label = "official source ↗" if rule.basis == "regulation" else "related regulation ↗"
            meta += f' · <a href="{html.escape(rule.reference_url)}" target="_blank" rel="noopener">{label}</a>'
        if rule.verified_on:
            meta += f" · checked {html.escape(rule.verified_on)}"

        st.markdown(
            f'<div class="ws-flag" style="--sev:{color};">'
            f'<div class="ws-flag-title">{rule.id} '
            + design.badge(sev_label, kind)
            + " "
            + design.badge(rule.action, "neutral")
            + " "
            + status_badge
            + "</div>"
            f'<div class="ws-flag-desc">{html.escape(" ".join(rule.description.split()))}</div>'
            f'<div class="ws-flag-meta">{meta}</div>'
            f'<details><summary>Condition</summary><div class="ws-cond">{_describe(rule.condition)}</div></details>'
            f"</div>",
            unsafe_allow_html=True,
        )


_OP_TEXT = {
    "eq": "=", "ne": "≠", "lt": "<", "lte": "≤", "gt": ">", "gte": "≥",
    "in": "in", "not_in": "not in", "contains": "contains",
}


def _kw(word: str) -> str:
    return f'<span class="ws-cond-kw">{word}</span>'


def _describe(cond: dict) -> str:
    """Render a rule condition as readable HTML, one clause per line (joined
    with <br>, never blank lines — Streamlit's markdown ends an HTML block
    at a blank line)."""
    return "<br>".join("&nbsp;" * (4 * indent) + text for indent, text in _lines(cond, 0, top=True))


def _lines(cond: dict, indent: int, top: bool = False) -> list[tuple[int, str]]:
    if "all" in cond or "any" in cond:
        key = "all" if "all" in cond else "any"
        joiner = _kw("AND" if key == "all" else "OR")
        out: list[tuple[int, str]] = []
        for i, child in enumerate(cond[key]):
            child_lines = _lines(child, indent if top else indent + 1)
            if i:
                lvl, text = child_lines[0]
                child_lines[0] = (lvl, f"{joiner} {text}")
            out.extend(child_lines)
        return out if top else [(indent, "(")] + out + [(indent, ")")]
    if "not" in cond:
        inner = cond["not"]
        if isinstance(inner, dict) and inner.get("op") == "exists":
            return [(indent, f"{html.escape(str(inner['field']))} {_kw('is missing')}")]
        sub = _lines(inner, indent + 1)
        return [(indent, _kw("NOT") + " (")] + sub + [(indent, ")")]
    field = html.escape(str(cond.get("field")))
    op = cond.get("op")
    if op == "exists":
        return [(indent, f"{field} {_kw('is present')}")]
    value = cond.get("value")
    value_text = str(value).lower() if isinstance(value, bool) else html.escape(str(value))
    return [(indent, f"{field} {_kw(html.escape(_OP_TEXT.get(op, str(op))))} {value_text}")]
