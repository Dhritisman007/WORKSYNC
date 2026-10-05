"""Maps a synthetic KYC/AML applicant row to the shared CaseRecord.

Mirrors verticals/loan/adapter.py's shape: `engineer_features` is the single
source of truth used by both the adapter (inference) and `model/train.py`
(training matrix), so there's no train/serve skew.
"""

from __future__ import annotations

from typing import Any, Mapping

from worksync.core.schemas.models import CaseRecord, Vertical

NUMERIC_FEATURES = [
    "age_years",
    "document_quality_score",
    "address_match_score",
    "selfie_liveness_score",
    "device_risk_score",
    "application_velocity_24h",
]
CATEGORICAL_FEATURES = ["country_of_residence", "id_type"]
BOOLEAN_FEATURES = ["pep_match", "sanctions_match", "adverse_media_hit"]
ALL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES + BOOLEAN_FEATURES

# This vertical's raw source columns are identical to its engineered
# feature names (no Kaggle-style renaming happens here) plus the id column.
# Used by the demo app's upload-vertical detector to recognize this file
# shape without needing a separate schema.
RAW_COLUMNS = ["applicant_id"] + ALL_FEATURES


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


def _bool(row: Mapping[str, Any], col: str) -> bool:
    value = row.get(col)
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return bool(value)


def engineer_features(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "age_years": _num(row, "age_years"),
        "document_quality_score": _num(row, "document_quality_score"),
        "address_match_score": _num(row, "address_match_score"),
        "selfie_liveness_score": _num(row, "selfie_liveness_score"),
        "device_risk_score": _num(row, "device_risk_score"),
        "application_velocity_24h": _num(row, "application_velocity_24h"),
        "country_of_residence": row.get("country_of_residence"),
        "id_type": row.get("id_type"),
        "pep_match": _bool(row, "pep_match"),
        "sanctions_match": _bool(row, "sanctions_match"),
        "adverse_media_hit": _bool(row, "adverse_media_hit"),
    }


def row_to_case(row: Mapping[str, Any]) -> CaseRecord:
    entity_id = str(row.get("applicant_id"))
    return CaseRecord(
        case_id=f"kyc-{entity_id}",
        vertical=Vertical.KYC_AML,
        entity_id=entity_id,
        features=engineer_features(row),
    )
