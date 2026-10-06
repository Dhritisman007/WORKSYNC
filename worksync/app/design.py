"""Shared design system: color tokens, global CSS, and reusable render
helpers used by every page. Kept deliberately restrained — a regulated
BFSI console should read as calm and precise, not as a flashy AI product.
"""

from __future__ import annotations

import streamlit as st

# Palette: near-black navy background, two panel shades, cool-gray borders,
# a single restrained accent blue, and semantic colors used ONLY to
# communicate system state (never decorative).
BG = "#080B12"
PANEL = "#10151F"
PANEL_ALT = "#141A24"
BORDER = "#232A38"
BORDER_STRONG = "#333c4e"
TEXT_PRIMARY = "#E7EAF0"
TEXT_MUTED = "#9AA3B5"
TEXT_FAINT = "#6B7386"
ACCENT = "#3B82F6"
ACCENT_DIM = "#1E3A66"
SUCCESS = "#2F9E58"
WARNING = "#E0A63A"
CRITICAL = "#E0564B"


def inject_css() -> None:
    st.markdown(
        f"""
        <style>
        :root {{
          --ws-bg: {BG}; --ws-panel: {PANEL}; --ws-panel-alt: {PANEL_ALT};
          --ws-border: {BORDER}; --ws-border-strong: {BORDER_STRONG};
          --ws-text: {TEXT_PRIMARY}; --ws-text-muted: {TEXT_MUTED}; --ws-text-faint: {TEXT_FAINT};
          --ws-accent: {ACCENT}; --ws-accent-dim: {ACCENT_DIM};
          --ws-success: {SUCCESS}; --ws-warning: {WARNING}; --ws-critical: {CRITICAL};
        }}

        @keyframes wsFadeUp {{ from {{ opacity: 0; transform: translateY(5px); }} to {{ opacity: 1; transform: translateY(0); }} }}

        [data-testid="stAppViewContainer"], [data-testid="stHeader"] {{ background: var(--ws-bg); }}
        section[data-testid="stSidebar"] {{ background: var(--ws-panel); border-right: 1px solid var(--ws-border); }}
        html, body, [class*="css"] {{ color: var(--ws-text); }}

        .ws-eyebrow {{ font-size: 11px; letter-spacing: .09em; text-transform: uppercase; color: var(--ws-text-faint); font-weight: 600; }}
        .ws-page-title {{ font-size: 26px; font-weight: 600; margin: .1rem 0 .15rem 0; letter-spacing: -.01em; }}
        .ws-page-sub {{ font-size: 13.5px; color: var(--ws-text-muted); margin-bottom: 1.1rem; }}
        .ws-section-title {{ font-size: 15px; font-weight: 600; margin: 1.3rem 0 .5rem 0; color: var(--ws-text); }}

        .ws-panel {{
          border: 1px solid var(--ws-border); border-radius: 10px; padding: 1rem 1.2rem;
          margin-bottom: .8rem; background: var(--ws-panel);
          transition: border-color .15s ease, transform .15s ease, box-shadow .15s ease;
          animation: wsFadeUp .2s ease;
        }}
        .ws-panel:hover {{ border-color: var(--ws-border-strong); }}
        .ws-panel-lift:hover {{ transform: translateY(-2px); box-shadow: 0 8px 20px rgba(0,0,0,.35); }}

        .ws-kpi-row {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: .65rem; margin: .4rem 0 1rem 0; }}
        .ws-kpi {{
          border: 1px solid var(--ws-border); border-top: 2px solid var(--kpi-accent, var(--ws-accent));
          border-radius: 8px; padding: .65rem .85rem; background: var(--ws-panel);
          transition: transform .15s ease, border-color .15s ease; animation: wsFadeUp .25s ease;
        }}
        .ws-kpi:hover {{ transform: translateY(-2px); border-color: var(--ws-border-strong); }}
        .ws-kpi-label {{ font-size: 10.5px; text-transform: uppercase; letter-spacing: .06em; color: var(--ws-text-faint); font-weight: 600; }}
        .ws-kpi-value {{ font-size: 22px; font-weight: 700; margin-top: .15rem; line-height: 1.15; }}
        .ws-kpi-sub {{ font-size: 11px; color: var(--ws-text-faint); margin-top: .15rem; }}

        .ws-badge {{ display:inline-block; padding: 1px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; letter-spacing: .02em; }}
        .ws-badge-success {{ background: rgba(47,158,88,.14); color: var(--ws-success); border: 1px solid rgba(47,158,88,.35); }}
        .ws-badge-warning {{ background: rgba(224,166,58,.14); color: var(--ws-warning); border: 1px solid rgba(224,166,58,.35); }}
        .ws-badge-critical {{ background: rgba(224,86,75,.14); color: var(--ws-critical); border: 1px solid rgba(224,86,75,.35); }}
        .ws-badge-neutral {{ background: rgba(154,163,181,.12); color: var(--ws-text-muted); border: 1px solid var(--ws-border); }}
        .ws-badge-accent {{ background: rgba(59,130,246,.14); color: var(--ws-accent); border: 1px solid rgba(59,130,246,.35); }}

        .ws-decision {{
          border-left: 4px solid var(--accent); border-radius: 10px; padding: 1.1rem 1.4rem;
          margin: .3rem 0 1rem 0; background: var(--bg); animation: wsFadeUp .25s ease;
        }}

        .ws-flag {{
          border-left: 3px solid var(--sev); border-radius: 6px; padding: .6rem .9rem; margin-bottom: .5rem;
          background: var(--ws-panel-alt); transition: transform .12s ease; animation: wsFadeUp .2s ease;
        }}
        .ws-flag:hover {{ transform: translateX(2px); }}
        .ws-flag-title {{ font-weight: 600; font-size: 13.5px; }}
        .ws-flag-desc {{ font-size: 12.5px; color: var(--ws-text-muted); margin-top: 2px; }}
        .ws-flag-meta {{ font-size: 11px; color: var(--ws-text-faint); margin-top: 4px; }}
        .ws-flag-meta a {{ color: var(--ws-accent); text-decoration: none; }}
        .ws-flag-meta a:hover {{ text-decoration: underline; }}
        .ws-flag details {{ margin-top: .55rem; border-top: 1px solid var(--ws-border); padding-top: .45rem; }}
        .ws-flag summary {{ cursor: pointer; font-size: 11.5px; color: var(--ws-text-muted); list-style: none; user-select: none; }}
        .ws-flag summary::-webkit-details-marker {{ display: none; }}
        .ws-flag summary::before {{ content: "▸"; display: inline-block; width: 1em; transition: transform .12s ease; }}
        .ws-flag details[open] summary::before {{ transform: rotate(90deg); }}
        .ws-flag summary:hover {{ color: var(--ws-text); }}
        .ws-cond {{ margin: .4rem 0 0 0; padding: .5rem .7rem; border-radius: 5px; background: var(--ws-bg);
          font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; color: var(--ws-text); line-height: 1.6; }}
        .ws-cond-kw {{ color: var(--ws-accent); font-weight: 600; }}

        .ws-step {{ display:flex; align-items:center; gap:.5rem; font-size: 13px; padding: .25rem 0; }}
        .ws-step-dot {{ width:7px; height:7px; border-radius:50%; flex-shrink:0; }}
        .ws-step-done {{ color: var(--ws-text); }}
        .ws-step-done .ws-step-dot {{ background: var(--ws-success); }}
        .ws-step-pending {{ color: var(--ws-text-faint); }}
        .ws-step-pending .ws-step-dot {{ background: var(--ws-border-strong); }}

        .ws-timeline {{ border-left: 2px solid var(--ws-border); margin-left: 6px; padding-left: 1.1rem; }}
        .ws-timeline-item {{ position: relative; padding-bottom: 1rem; }}
        .ws-timeline-item::before {{
          content: ""; position: absolute; left: -1.46rem; top: 3px; width: 9px; height: 9px;
          border-radius: 50%; background: var(--ws-accent); border: 2px solid var(--ws-bg);
        }}
        .ws-timeline-time {{ font-size: 11px; color: var(--ws-text-faint); font-family: var(--font-mono, monospace); }}
        .ws-timeline-label {{ font-size: 13.5px; font-weight: 600; margin-top: 1px; }}
        .ws-timeline-meta {{ font-size: 11.5px; color: var(--ws-text-muted); margin-top: 1px; }}

        /* Buttons */
        div[data-testid="stButton"] button, div[data-testid="stDownloadButton"] button {{
          border-radius: 6px !important; font-weight: 600 !important; font-size: 13.5px !important;
          transition: transform .08s ease, box-shadow .15s ease, filter .15s ease !important;
        }}
        div[data-testid="stButton"] button:hover, div[data-testid="stDownloadButton"] button:hover {{
          transform: translateY(-1px); filter: brightness(1.08);
        }}
        div[data-testid="stButton"] button:active, div[data-testid="stDownloadButton"] button:active {{
          transform: translateY(0) scale(.98); filter: brightness(.95);
        }}

        [data-baseweb="tab-list"] {{ gap: 2px; border-bottom: 1px solid var(--ws-border); }}
        [data-baseweb="tab"] {{ transition: color .15s ease, background-color .15s ease; border-radius: 6px 6px 0 0 !important; }}
        [data-baseweb="tab"]:hover {{ background: rgba(154,163,181,.06); }}
        [data-baseweb="tab-highlight"] {{ transition: left .2s ease, width .2s ease !important; background: var(--ws-accent) !important; }}

        [data-testid="stFileUploaderDropzone"] {{ border-radius: 8px !important; transition: border-color .15s ease, background-color .15s ease !important; }}
        [data-testid="stFileUploaderDropzone"]:hover {{ border-color: var(--ws-accent) !important; background: rgba(59,130,246,.05) !important; }}

        .ws-gauge-marker {{ transition: left .25s ease; }}

        [data-testid="stMetric"] {{ background: var(--ws-panel); border: 1px solid var(--ws-border); border-radius: 8px; padding: .6rem .8rem; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_header(eyebrow: str, title: str, subtitle: str) -> None:
    st.markdown(f'<div class="ws-eyebrow">{eyebrow}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="ws-page-title">{title}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="ws-page-sub">{subtitle}</div>', unsafe_allow_html=True)


def section_title(text: str) -> None:
    st.markdown(f'<div class="ws-section-title">{text}</div>', unsafe_allow_html=True)


def kpi_row(items: list[tuple[str, str, str | None, str | None]]) -> None:
    """Each item: (label, value, sub_text_or_None, accent_hex_or_None)."""
    style_attr = lambda accent: f' style="--kpi-accent:{accent};"' if accent else ""
    cards = "".join(
        f'<div class="ws-kpi"{style_attr(accent)}>'
        f'<div class="ws-kpi-label">{label}</div>'
        f'<div class="ws-kpi-value">{value}</div>'
        + (f'<div class="ws-kpi-sub">{sub}</div>' if sub else "")
        + "</div>"
        for label, value, sub, accent in items
    )
    st.markdown(f'<div class="ws-kpi-row">{cards}</div>', unsafe_allow_html=True)


def badge(text: str, kind: str = "neutral") -> str:
    """Returns inline badge HTML (does not call st.markdown itself, so
    callers can compose it inside a larger block)."""
    return f'<span class="ws-badge ws-badge-{kind}">{text}</span>'


OUTCOME_KIND = {"approve": "success", "reject": "critical", "escalate": "warning"}
SEVERITY_KIND = {"hard": "critical", "soft": "warning", "info": "accent"}
SEVERITY_HEX = {"hard": CRITICAL, "soft": WARNING, "info": ACCENT}


def render_pipeline_diagram() -> None:
    """The signature architecture visual: case input flows through
    ingestion, Analyst and Compliance agents run independently in parallel
    on the same case record, Manager combines both into a decision, and
    Audit observes every step (dashed lines — it never alters the flow).
    One single st.markdown call, no concatenation — see stat_card_row's
    docstring in pipeline.py-era code for why that matters with Streamlit's
    markdown renderer.
    """
    svg = (
        f'<svg viewBox="0 0 760 400" width="100%" role="img" aria-label="Four-agent pipeline architecture">'
        f'<defs><marker id="wsArrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
        f'<path d="M2 1L8 5L2 9" fill="none" stroke="{TEXT_FAINT}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>'
        f"</marker></defs>"
        f'<rect x="310" y="10" width="140" height="34" rx="6" fill="{PANEL_ALT}" stroke="{BORDER_STRONG}"/>'
        f'<text x="380" y="27" text-anchor="middle" dominant-baseline="central" fill="{TEXT_PRIMARY}" font-size="12.5" font-weight="600">CASE INPUT</text>'
        f'<line x1="380" y1="44" x2="380" y2="60" stroke="{TEXT_FAINT}" stroke-width="1.3" marker-end="url(#wsArrow)"/>'
        f'<rect x="310" y="60" width="140" height="34" rx="6" fill="{PANEL_ALT}" stroke="{BORDER_STRONG}"/>'
        f'<text x="380" y="77" text-anchor="middle" dominant-baseline="central" fill="{TEXT_PRIMARY}" font-size="12.5" font-weight="600">INGESTION</text>'
        f'<path d="M380 94 L380 108 L215 108 L215 122" fill="none" stroke="{TEXT_FAINT}" stroke-width="1.3" marker-end="url(#wsArrow)"/>'
        f'<path d="M380 94 L380 108 L545 108 L545 122" fill="none" stroke="{TEXT_FAINT}" stroke-width="1.3" marker-end="url(#wsArrow)"/>'
        f'<rect x="110" y="122" width="210" height="68" rx="8" fill="{PANEL}" stroke="{ACCENT}" stroke-width="1.2"/>'
        f'<text x="215" y="144" text-anchor="middle" dominant-baseline="central" fill="{ACCENT}" font-size="12.5" font-weight="700">ANALYST AGENT</text>'
        f'<text x="215" y="162" text-anchor="middle" dominant-baseline="central" fill="{TEXT_MUTED}" font-size="11">Risk score · confidence</text>'
        f'<text x="215" y="177" text-anchor="middle" dominant-baseline="central" fill="{TEXT_MUTED}" font-size="11">SHAP explanation</text>'
        f'<rect x="440" y="122" width="210" height="68" rx="8" fill="{PANEL}" stroke="{ACCENT}" stroke-width="1.2"/>'
        f'<text x="545" y="144" text-anchor="middle" dominant-baseline="central" fill="{ACCENT}" font-size="12.5" font-weight="700">COMPLIANCE AGENT</text>'
        f'<text x="545" y="162" text-anchor="middle" dominant-baseline="central" fill="{TEXT_MUTED}" font-size="11">Rule evaluation</text>'
        f'<text x="545" y="177" text-anchor="middle" dominant-baseline="central" fill="{TEXT_MUTED}" font-size="11">PASS · WARN · HARD</text>'
        f'<text x="380" y="153" text-anchor="middle" dominant-baseline="central" fill="{TEXT_FAINT}" font-size="12" font-weight="600">+</text>'
        f'<path d="M215 190 L215 204 L380 204 L380 218" fill="none" stroke="{TEXT_FAINT}" stroke-width="1.3" marker-end="url(#wsArrow)"/>'
        f'<path d="M545 190 L545 204 L380 204 L380 218" fill="none" stroke="{TEXT_FAINT}" stroke-width="1.3"/>'
        f'<rect x="300" y="218" width="160" height="50" rx="8" fill="{PANEL}" stroke="{ACCENT}" stroke-width="1.2"/>'
        f'<text x="380" y="236" text-anchor="middle" dominant-baseline="central" fill="{ACCENT}" font-size="12.5" font-weight="700">MANAGER AGENT</text>'
        f'<text x="380" y="252" text-anchor="middle" dominant-baseline="central" fill="{TEXT_MUTED}" font-size="11">Decision policy · bands</text>'
        f'<line x1="380" y1="268" x2="380" y2="284" stroke="{TEXT_FAINT}" stroke-width="1.3" marker-end="url(#wsArrow)"/>'
        f'<rect x="199" y="284" width="110" height="30" rx="15" fill="rgba(47,158,88,.12)" stroke="{SUCCESS}"/>'
        f'<text x="254" y="299" text-anchor="middle" dominant-baseline="central" fill="{SUCCESS}" font-size="11.5" font-weight="700">APPROVE</text>'
        f'<rect x="325" y="284" width="110" height="30" rx="15" fill="rgba(224,166,58,.12)" stroke="{WARNING}"/>'
        f'<text x="380" y="299" text-anchor="middle" dominant-baseline="central" fill="{WARNING}" font-size="11.5" font-weight="700">ESCALATE</text>'
        f'<rect x="451" y="284" width="110" height="30" rx="15" fill="rgba(224,86,75,.12)" stroke="{CRITICAL}"/>'
        f'<text x="506" y="299" text-anchor="middle" dominant-baseline="central" fill="{CRITICAL}" font-size="11.5" font-weight="700">REJECT</text>'
        f'<rect x="270" y="345" width="220" height="46" rx="8" fill="{PANEL}" stroke="{BORDER_STRONG}" stroke-dasharray="3,3"/>'
        f'<text x="380" y="362" text-anchor="middle" dominant-baseline="central" fill="{TEXT_PRIMARY}" font-size="12" font-weight="700">AUDIT AGENT</text>'
        f'<text x="380" y="378" text-anchor="middle" dominant-baseline="central" fill="{TEXT_MUTED}" font-size="10.5">Hash-chained · replayable log</text>'
        f'<path d="M215 190 L215 320 L340 320 L340 345" fill="none" stroke="{TEXT_FAINT}" stroke-width="1" stroke-dasharray="3,3"/>'
        f'<path d="M545 190 L545 320 L420 320 L420 345" fill="none" stroke="{TEXT_FAINT}" stroke-width="1" stroke-dasharray="3,3"/>'
        f'<path d="M380 268 L380 330 L380 345" fill="none" stroke="{TEXT_FAINT}" stroke-width="1" stroke-dasharray="3,3"/>'
        f"</svg>"
    )
    st.markdown(svg, unsafe_allow_html=True)
    st.markdown(
        f'<div style="font-size:11px; color:{TEXT_FAINT}; margin-top:-.4rem;">'
        f'Solid arrows: data flow &nbsp;·&nbsp; Dashed lines: observed by the Audit agent (log-only, never alters the decision)'
        f"</div>",
        unsafe_allow_html=True,
    )
