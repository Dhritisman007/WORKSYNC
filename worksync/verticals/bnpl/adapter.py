"""Maps a row from the Kaggle Credit Card Fraud Detection dataset
(mlg-ulb/creditcardfraud) to the shared CaseRecord.

The dataset's V1-V28 columns are PCA components of the original transaction
features (anonymized for privacy by the dataset's publisher) — there is no
way to recover human-readable names for them, so they pass through as-is.
`amount` and `hour_of_day` (derived from `Time`, seconds-since-first-
transaction modulo a day) are the only two features with real business
meaning available in this data, which is also why `rules.yaml` for this
vertical only has rules about those two.

There is no customer/session identifier in this dataset, so unlike the loan
and KYC/AML verticals, no cross-transaction feature (e.g. velocity) is
possible here without fabricating an identifier the data doesn't support —
left out rather than invented.
"""

from __future__ import annotations

from typing import Any, Mapping

from worksync.core.schemas.models import CaseRecord, Vertical

V_COLUMNS = [f"V{i}" for i in range(1, 29)]
NUMERIC_FEATURES = ["amount", "hour_of_day"] + [f"v{i}" for i in range(1, 29)]
CATEGORICAL_FEATURES: list[str] = []
BOOLEAN_FEATURES: list[str] = []
ALL_FEATURES = NUMERIC_FEATURES


def _num(row: Mapping[str, Any], col: str) -> float | None:
    value = row.get(col)
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


def engineer_features(row: Mapping[str, Any]) -> dict[str, Any]:
    time_seconds = _num(row, "Time") or 0.0
    hour_of_day = int((time_seconds % 86400) // 3600)

    features: dict[str, Any] = {
        "amount": _num(row, "Amount"),
        "hour_of_day": hour_of_day,
    }
    for col in V_COLUMNS:
        features[col.lower()] = _num(row, col)
    return features


def row_to_case(row: Mapping[str, Any], index: int) -> CaseRecord:
    """`index` is the row's position in the source CSV — this dataset has no
    real transaction or customer identifier, so the index is the entity id."""
    entity_id = f"txn-{index}"
    return CaseRecord(
        case_id=f"bnpl-{entity_id}",
        vertical=Vertical.BNPL,
        entity_id=entity_id,
        features=engineer_features(row),
    )
