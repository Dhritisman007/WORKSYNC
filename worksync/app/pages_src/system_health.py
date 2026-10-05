"""System Health — real status of each vertical's pipeline components:
sample data present, model artifacts present, ruleset/config loadable, and
audit log reachability + chain integrity.

This project has no separate API Gateway / Orchestrator service / database
— the "backend" is the Python agent code running in this same process, and
the "database" is the hash-chained JSONL audit log. This page reports on
what actually exists rather than simulating infrastructure that isn't
there.
"""

from __future__ import annotations

import streamlit as st

from worksync.app import design
from worksync.app.pipeline import VERTICALS, artifacts_present, get_orchestrator, load_data


def _status_row(label: str, ok: bool, detail: str) -> None:
    badge = design.badge("● ONLINE", "success") if ok else design.badge("● UNAVAILABLE", "critical")
    st.markdown(
        f'<div class="ws-panel" style="display:flex; justify-content:space-between; align-items:center;">'
        f'<div><div style="font-weight:600; font-size:13.5px;">{label}</div>'
        f'<div style="font-size:11.5px; color:{design.TEXT_FAINT};">{detail}</div></div>'
        f"<div>{badge}</div></div>",
        unsafe_allow_html=True,
    )


def render() -> None:
    design.page_header(
        "System / Agent Health",
        "Agent Health",
        "Real status of each vertical's pipeline components — data, model, rules, and the audit log.",
    )
    st.caption(
        "This project runs as a single Python process (no separate API gateway, orchestrator service, "
        "or database) — the Orchestrator and agents run in-process, and the audit log is the JSONL file "
        "on disk shown below. This page reports what's actually loaded, not simulated infrastructure."
    )

    for vertical_key, factory in VERTICALS.items():
        spec = factory()
        design.section_title(spec.label)

        df = load_data(vertical_key, str(spec.data_path))
        _status_row("Sample data", df is not None, str(spec.data_path) + (f" ({len(df):,} rows)" if df is not None else " — not found"))

        has_artifacts = artifacts_present(vertical_key)
        _status_row(
            "Analyst agent — model artifacts",
            has_artifacts,
            f"worksync/verticals/{vertical_key}/model/artifacts/" + ("" if has_artifacts else " — not found, regenerate via train.py"),
        )

        try:
            orchestrator, _ = get_orchestrator(vertical_key)
            rule_count = len(orchestrator.compliance.ruleset.rules)
            _status_row(
                "Compliance agent — ruleset",
                True,
                f"{rule_count} rule(s), version {orchestrator.compliance.ruleset.version}",
            )
            _status_row(
                "Manager agent — config",
                True,
                f"grey band {orchestrator.manager.config.grey_band_lower:.0%}–{orchestrator.manager.config.grey_band_upper:.0%}",
            )

            entries = orchestrator.audit.read_all()
            if entries:
                ok, bad_index = orchestrator.audit.verify_chain()
                _status_row(
                    "Audit agent — log",
                    ok,
                    f"{len(entries)} entries, last at {entries[-1].timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
                    + ("" if ok else f" — tampering at entry {bad_index}"),
                )
            else:
                _status_row("Audit agent — log", True, "0 entries — no cases run yet")
        except Exception as exc:
            _status_row("Compliance / Manager / Audit", False, f"Failed to initialize: {exc}")
