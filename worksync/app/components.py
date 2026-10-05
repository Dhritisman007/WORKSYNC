"""Shared render components for displaying a CaseResult — used by both
Case Submission (a case just run) and the Audit Explorer (a case
reconstructed from the persisted audit log). Keeping one copy means the
two pages can never drift in what they show for the same data.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from worksync.app import design
from worksync.core.orchestrator import CaseResult, Orchestrator
from worksync.core.schemas.models import Severity


def risk_gauge_html(prob: float, low: float, high: float, accent: str) -> str:
    pct = max(0.0, min(1.0, prob)) * 100
    low_pct = max(0.0, min(100.0, low * 100))
    high_pct = max(0.0, min(100.0, high * 100))
    return f"""
    <div style="margin: .3rem 0 .2rem 0;">
      <div style="position:relative; height:8px; border-radius:4px; overflow:visible;
                  background: linear-gradient(to right,
                    rgba(47,158,88,.3) 0%, rgba(47,158,88,.3) {low_pct}%,
                    rgba(224,166,58,.3) {low_pct}%, rgba(224,166,58,.3) {high_pct}%,
                    rgba(224,86,75,.3) {high_pct}%, rgba(224,86,75,.3) 100%);">
        <div class="ws-gauge-marker" title="{pct:.1f}%"
             style="position:absolute; top:-3px; left:calc({pct}% - 2px); width:4px; height:14px;
                    background:{accent}; border-radius:2px;"></div>
      </div>
      <div style="display:flex; justify-content:space-between; font-size:10.5px; color:{design.TEXT_FAINT}; margin-top:3px;">
        <span>0%</span><span>grey band {low:.0%}–{high:.0%}</span><span>100%</span>
      </div>
    </div>
    """


def render_decision_banner(result: CaseResult, narrative: str) -> None:
    from worksync.app.pipeline import OUTCOME_STYLE

    outcome = result.decision.outcome.value
    style = OUTCOME_STYLE[outcome]
    st.markdown(
        f"""
        <div class="ws-decision" style="--accent:{style['accent']}; --bg:{style['bg']};">
          <div style="font-size:11px; text-transform:uppercase; letter-spacing:.07em; color:{style['accent']}; font-weight:700;">Final decision</div>
          <div style="font-size:26px; font-weight:700; color:{style['accent']}; margin:.1rem 0 .55rem 0;">{style['label']}</div>
          <div style="font-size:14px; line-height:1.55; color:{design.TEXT_MUTED};">{narrative}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if outcome == "escalate":
        st.markdown(design.badge("HUMAN REVIEW REQUIRED", "warning"), unsafe_allow_html=True)


def render_risk_block(result: CaseResult) -> None:
    design.kpi_row(
        [
            ("Risk probability", f"{result.risk.risk_probability:.4f}", None, None),
            ("Confidence band", result.risk.confidence_band, None, None),
            ("Model", result.risk.model_name, result.risk.model_version, None),
        ]
    )
    st.markdown("**Top SHAP attributions**")
    st.caption("Positive bars pushed the risk score up; negative bars pulled it down.")
    attr_df = pd.DataFrame(
        [(a.feature, a.contribution) for a in result.risk.top_attributions],
        columns=["feature", "contribution"],
    ).set_index("feature")
    st.bar_chart(attr_df)


def render_compliance_block(result: CaseResult) -> None:
    st.caption(f"Ruleset version: `{result.compliance.ruleset_version}`")
    if not result.compliance.flags:
        st.markdown(design.badge("✓ PASS — no rules triggered", "success"), unsafe_allow_html=True)
        return

    for f in result.compliance.flags:
        sev = f.severity.value
        color = design.SEVERITY_HEX.get(sev, design.TEXT_FAINT)
        kind = design.SEVERITY_KIND.get(sev, "neutral")
        sev_label = {"hard": "CRITICAL", "soft": "WARN", "info": "INFO"}.get(sev, sev.upper())
        verified = "verified" if f.verified else "not yet verified"
        st.markdown(
            f'<div class="ws-flag" style="--sev:{color};">'
            f'<div class="ws-flag-title">{f.rule_id} '
            + design.badge(sev_label, kind)
            + " "
            + design.badge(f.action, "neutral")
            + "</div>"
            f'<div class="ws-flag-desc">{" ".join(f.description.split())}</div>'
            f'<div class="ws-flag-meta">{f.source_regulation} · {verified}</div>'
            f"</div>",
            unsafe_allow_html=True,
        )

    if any(f.severity == Severity.HARD for f in result.compliance.flags):
        st.caption(
            "A triggered CRITICAL/hard rule always overrides the risk score — the Manager agent "
            "cannot auto-approve past it regardless of how low the score is."
        )


def render_why_block(result: CaseResult, grey_low: float, grey_high: float) -> None:
    st.markdown(f"**DECISION: {result.decision.outcome.value.upper()}**")

    hard_flags = [f for f in result.compliance.flags if f.severity == Severity.HARD]
    soft_flags = [f for f in result.compliance.flags if f.severity == Severity.SOFT]

    st.markdown("**Risk factors**")
    if result.risk.top_attributions:
        for a in result.risk.top_attributions[:5]:
            direction = "increases risk" if a.contribution > 0 else "decreases risk"
            st.markdown(f"- `{a.feature}` → {direction} (contribution {a.contribution:+.3f})")
    else:
        st.caption("No SHAP attributions available for this case.")

    st.markdown("**Compliance findings**")
    if hard_flags:
        for f in hard_flags:
            st.markdown(
                f"- {design.badge('CRITICAL', 'critical')} `{f.rule_id}` — {' '.join(f.description.split())}",
                unsafe_allow_html=True,
            )
    if soft_flags:
        for f in soft_flags:
            st.markdown(
                f"- {design.badge('WARN', 'warning')} `{f.rule_id}` — {' '.join(f.description.split())}",
                unsafe_allow_html=True,
            )
    if not hard_flags and not soft_flags:
        st.markdown(f"- {design.badge('PASS', 'success')} no rules triggered", unsafe_allow_html=True)

    st.markdown("**Manager decision logic**")
    reason_labels = {
        "AUTO_APPROVE": "Score clearly below the grey band, with high confidence — auto-approved.",
        "AUTO_REJECT": "Score clearly above the grey band, with high confidence — auto-rejected.",
        "GREY_BAND_SCORE": f"Score fell inside the grey band ({grey_low:.0%}–{grey_high:.0%}) — not authorized to auto-decide.",
        "LOW_CONFIDENCE": "Model confidence too low to auto-decide.",
    }
    for code in result.decision.reason_codes:
        base = code.split(":")[0]
        st.markdown(f"- `{code}`" if base in ("HARD_FLAG", "SOFT_FLAG") else f"- {reason_labels.get(code, code)}")

    with st.expander("View technical details"):
        st.json(
            {
                "decision": result.decision.model_dump(mode="json"),
                "risk": result.risk.model_dump(mode="json"),
                "compliance": result.compliance.model_dump(mode="json"),
            }
        )


def render_timeline_block(orchestrator: Orchestrator, case_id: str) -> None:
    entries = orchestrator.audit.entries_for_case(case_id)
    if not entries:
        st.caption("No audit entries found for this case.")
        return
    items_html = []
    for e in entries:
        meta_bits = [b for b in [e.model_version, e.ruleset_version] if b]
        meta = " · ".join(meta_bits) if meta_bits else ""
        items_html.append(
            f'<div class="ws-timeline-item">'
            f'<div class="ws-timeline-time">{e.timestamp.strftime("%Y-%m-%d %H:%M:%S")}</div>'
            f'<div class="ws-timeline-label">{e.agent.value.capitalize()} agent completed</div>'
            + (f'<div class="ws-timeline-meta">{meta}</div>' if meta else "")
            + "</div>"
        )
    st.markdown(f'<div class="ws-timeline">{"".join(items_html)}</div>', unsafe_allow_html=True)


def render_audit_block(orchestrator: Orchestrator, case_id: str, allow_replay: bool = True) -> None:
    entries = orchestrator.audit.entries_for_case(case_id)
    st.caption(f"{len(entries)} recorded step(s) for this case, hash-chained into the full audit log.")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "agent": e.agent.value,
                    "timestamp": e.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
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
        st.markdown(design.badge("✓ HASH CHAIN VERIFIED", "success"), unsafe_allow_html=True)
    else:
        st.markdown(design.badge(f"✕ TAMPERING DETECTED at entry {bad_index}", "critical"), unsafe_allow_html=True)

    if allow_replay and st.button("Replay this case", key=f"replay-{case_id}"):
        replay_ok = orchestrator.audit.replay(case_id, orchestrator.analyst, orchestrator.compliance, orchestrator.manager)
        if replay_ok:
            st.success("replay(): re-running this case reproduces the logged decision.")
        else:
            st.error("replay(): re-running this case did NOT reproduce the logged decision.")
