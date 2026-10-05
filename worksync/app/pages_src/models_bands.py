"""Model & Bands — per-vertical model governance: the real metrics from the
last training run (`model/artifacts/metadata.json`, written by each
vertical's `train.py`) and the Manager agent's decision-threshold bands
from its own `manager_config.yaml`.

If a vertical's artifacts aren't present locally (they're gitignored —
regenerate with `python -m worksync.verticals.<x>.model.train`), this page
says so rather than inventing numbers.
"""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from worksync.app import design
from worksync.app.pipeline import VERTICALS, get_orchestrator


def _load_metadata(vertical_key: str) -> dict | None:
    path = Path(f"worksync/verticals/{vertical_key}/model/artifacts/metadata.json")
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _confusion_metrics(cm: list[list[int]]) -> dict[str, float]:
    (tn, fp), (fn, tp) = cm
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    accuracy = (tp + tn) / (tp + tn + fp + fn) if (tp + tn + fp + fn) else 0.0
    return {"precision": precision, "recall": recall, "accuracy": accuracy}


def render() -> None:
    design.page_header(
        "Governance / Models & Bands",
        "Models & Bands",
        "Real training metrics from each vertical's last model run, and the Manager agent's decision bands.",
    )

    for vertical_key, factory in VERTICALS.items():
        spec = factory()
        orchestrator, _ = get_orchestrator(vertical_key)
        metadata = _load_metadata(vertical_key)

        design.section_title(spec.label)

        if metadata is None:
            st.markdown(
                f'<div class="ws-panel">Model artifacts not present locally for {spec.label}. '
                f"Regenerate with <code>python -m worksync.verticals.{vertical_key}.model.train</code>.</div>",
                unsafe_allow_html=True,
            )
            continue

        primary = next((r for r in metadata["results"] if "primary" in r["model"]), metadata["results"][0])
        cm_metrics = _confusion_metrics(primary["confusion_matrix_at_0.5"])

        design.kpi_row(
            [
                ("Model version", metadata["model_version"], None, None),
                ("AUC-ROC", f"{primary['auc']:.3f}", None, None),
                ("KS statistic", f"{primary['ks']:.3f}", None, None),
                ("Brier score", f"{primary['brier']:.4f}", "lower is better", None),
                ("Precision @0.5", f"{cm_metrics['precision']:.1%}", None, None),
                ("Recall @0.5", f"{cm_metrics['recall']:.1%}", None, None),
            ]
        )
        st.caption(
            f"Trained on {metadata['n_train_rows']:,} rows (test: {metadata['n_test_rows']:,}), "
            f"positive rate {metadata['positive_rate']:.2%}, seed {metadata['seed']}."
        )

        with st.expander(f"All models compared — {spec.label}"):
            for r in metadata["results"]:
                st.markdown(f"**{r['model']}** — AUC {r['auc']:.3f} · KS {r['ks']:.3f} · Brier {r['brier']:.4f}")

        low = orchestrator.manager.config.grey_band_lower
        high = orchestrator.manager.config.grey_band_upper
        st.markdown(
            f"""
            <div style="display:flex; gap:.5rem; margin: .5rem 0 1.3rem 0;">
              <div style="flex:{low}; background:rgba(47,158,88,.14); border:1px solid {design.SUCCESS}; border-radius:6px; padding:.5rem .7rem;">
                <div style="font-size:11px; font-weight:700; color:{design.SUCCESS};">LOW RISK → APPROVE</div>
                <div style="font-size:10.5px; color:{design.TEXT_FAINT};">0% – {low:.0%}</div>
              </div>
              <div style="flex:{high-low}; background:rgba(224,166,58,.14); border:1px solid {design.WARNING}; border-radius:6px; padding:.5rem .7rem;">
                <div style="font-size:11px; font-weight:700; color:{design.WARNING};">GREY ZONE → ESCALATE</div>
                <div style="font-size:10.5px; color:{design.TEXT_FAINT};">{low:.0%} – {high:.0%}</div>
              </div>
              <div style="flex:{1-high}; background:rgba(224,86,75,.14); border:1px solid {design.CRITICAL}; border-radius:6px; padding:.5rem .7rem;">
                <div style="font-size:11px; font-weight:700; color:{design.CRITICAL};">HIGH RISK → REJECT</div>
                <div style="font-size:10.5px; color:{design.TEXT_FAINT};">{high:.0%} – 100%</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.caption(
            "A triggered CRITICAL compliance rule is a hard override on top of these bands — it forces "
            "reject/escalate regardless of where the score falls, and can never be auto-approved through."
        )
