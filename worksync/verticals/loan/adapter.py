"""Maps a Home Credit Default Risk application row to the shared CaseRecord.

`engineer_features` is the single source of truth for feature engineering.
It is used both here (for live/inference CaseRecords) and by
`model/train.py` (to build the training matrix), so there is no train/serve
skew between what the model was fit on and what it sees at inference time.

Feature engineering: a curated subset of the raw Home Credit columns, a
handful of standard ratio/derived features (credit-to-income, annuity-to-
income, age, years employed, mean of the three EXT_SOURCE_* external
credit-bureau-style scores), plus aggregated features from `bureau.csv`
(each applicant's credit history at other institutions — see
`model/build_bureau_features.py`). The bureau lookup only covers applicants
present in Home Credit's own bureau.csv; any case without a matching
SK_ID_CURR (including every uploaded/new case — there's no live credit
bureau API here) simply gets `None` for those fields, same as any other
missing feature.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from worksync.core.schemas.models import CaseRecord, Vertical

BUREAU_FEATURES_PATH = Path("worksync/data/processed/loan_bureau_features.csv")

# DAYS_EMPLOYED uses a sentinel (365243) for "not currently employed"
# (e.g. pensioners) instead of a null — Home Credit's own known data quirk.
_DAYS_EMPLOYED_ANOMALY = 365243

# Raw columns this adapter reads from application_{train,test}.csv.
RAW_COLUMNS = [
    "SK_ID_CURR",
    "NAME_CONTRACT_TYPE",
    "CODE_GENDER",
    "FLAG_OWN_CAR",
    "FLAG_OWN_REALTY",
    "CNT_CHILDREN",
    "AMT_INCOME_TOTAL",
    "AMT_CREDIT",
    "AMT_ANNUITY",
    "AMT_GOODS_PRICE",
    "NAME_INCOME_TYPE",
    "NAME_EDUCATION_TYPE",
    "NAME_FAMILY_STATUS",
    "NAME_HOUSING_TYPE",
    "OCCUPATION_TYPE",
    "CNT_FAM_MEMBERS",
    "REGION_RATING_CLIENT",
    "DAYS_BIRTH",
    "DAYS_EMPLOYED",
    "DAYS_LAST_PHONE_CHANGE",
    "EXT_SOURCE_1",
    "EXT_SOURCE_2",
    "EXT_SOURCE_3",
    "FLAG_DOCUMENT_3",
    "AMT_REQ_CREDIT_BUREAU_YEAR",
]

# The engineered feature names, in the order a model pipeline should expect
# them. Kept explicit (rather than "whatever engineer_features returns") so
# training and inference can both assert on it.
NUMERIC_FEATURES = [
    "num_children",
    "income_total",
    "credit_amount",
    "annuity_amount",
    "goods_price",
    "family_members",
    "region_rating",
    "age_years",
    "years_employed",
    "days_since_phone_change",
    "ext_source_1",
    "ext_source_2",
    "ext_source_3",
    "ext_source_mean",
    "credit_income_ratio",
    "annuity_income_ratio",
    "goods_credit_ratio",
    "bureau_inquiries_last_year",
    "bureau_count",
    "bureau_active_count",
    "bureau_overdue_count",
    "bureau_days_credit_mean",
    "bureau_credit_sum",
    "bureau_credit_sum_debt",
    "bureau_credit_sum_overdue",
    "bureau_max_overdue",
]
CATEGORICAL_FEATURES = [
    "contract_type",
    "gender",
    "income_type",
    "education_type",
    "family_status",
    "housing_type",
    "occupation_type",
]
BOOLEAN_FEATURES = ["own_car", "own_realty", "doc3_provided"]
ALL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES + BOOLEAN_FEATURES


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


def _days_to_years(days: float | None) -> float | None:
    if days is None:
        return None
    return round(-days / 365.25, 2)


_BUREAU_NUMERIC_COLS = [
    "bureau_count",
    "bureau_active_count",
    "bureau_overdue_count",
    "bureau_days_credit_mean",
    "bureau_credit_sum",
    "bureau_credit_sum_debt",
    "bureau_credit_sum_overdue",
    "bureau_max_overdue",
]


@lru_cache(maxsize=1)
def _load_bureau_lookup() -> dict[str, dict[str, float]]:
    """Loaded once per process and cached — `bureau.csv`'s aggregate is
    ~306k rows, cheap to hold in memory but not cheap to reload per case.
    Returns {} if the precomputed table hasn't been built yet
    (`python -m worksync.verticals.loan.model.build_bureau_features`), so
    callers degrade to "no bureau history available" rather than erroring."""
    if not BUREAU_FEATURES_PATH.exists():
        return {}
    df = pd.read_csv(BUREAU_FEATURES_PATH, dtype={"SK_ID_CURR": str})
    return df.set_index("SK_ID_CURR")[_BUREAU_NUMERIC_COLS].to_dict(orient="index")


def _normalize_id(value: Any) -> str | None:
    """"100002", 100002, 100002.0 and numpy.int64(100002) must all resolve
    to the same lookup key — a CSV round-trip can produce any of these."""
    if value is None:
        return None
    try:
        return str(int(float(value)))
    except (TypeError, ValueError):
        return str(value)


def _bureau_features(row: Mapping[str, Any]) -> dict[str, float | None]:
    sk_id = _normalize_id(row.get("SK_ID_CURR"))
    if sk_id is None:
        return dict.fromkeys(_BUREAU_NUMERIC_COLS, None)
    record = _load_bureau_lookup().get(sk_id)
    if record is None:
        return dict.fromkeys(_BUREAU_NUMERIC_COLS, None)
    return record


def engineer_features(row: Mapping[str, Any]) -> dict[str, Any]:
    """`row` is one Home Credit application record (a dict or a pandas
    Series both satisfy Mapping's `.get`)."""

    income_total = _num(row, "AMT_INCOME_TOTAL")
    credit_amount = _num(row, "AMT_CREDIT")
    annuity_amount = _num(row, "AMT_ANNUITY")
    goods_price = _num(row, "AMT_GOODS_PRICE")

    days_employed = _num(row, "DAYS_EMPLOYED")
    if days_employed == _DAYS_EMPLOYED_ANOMALY:
        days_employed = None
    years_employed = _days_to_years(days_employed)

    ext_1 = _num(row, "EXT_SOURCE_1")
    ext_2 = _num(row, "EXT_SOURCE_2")
    ext_3 = _num(row, "EXT_SOURCE_3")
    ext_scores = [e for e in (ext_1, ext_2, ext_3) if e is not None]
    ext_mean = round(sum(ext_scores) / len(ext_scores), 4) if ext_scores else None

    credit_income_ratio = (
        round(credit_amount / income_total, 4) if credit_amount and income_total else None
    )
    annuity_income_ratio = (
        round(annuity_amount / income_total, 4) if annuity_amount and income_total else None
    )
    goods_credit_ratio = (
        round(goods_price / credit_amount, 4) if goods_price and credit_amount else None
    )

    features = {
        "contract_type": row.get("NAME_CONTRACT_TYPE"),
        "gender": row.get("CODE_GENDER"),
        "own_car": bool(row.get("FLAG_OWN_CAR") == "Y"),
        "own_realty": bool(row.get("FLAG_OWN_REALTY") == "Y"),
        "num_children": _num(row, "CNT_CHILDREN"),
        "income_total": income_total,
        "credit_amount": credit_amount,
        "annuity_amount": annuity_amount,
        "goods_price": goods_price,
        "income_type": row.get("NAME_INCOME_TYPE"),
        "education_type": row.get("NAME_EDUCATION_TYPE"),
        "family_status": row.get("NAME_FAMILY_STATUS"),
        "housing_type": row.get("NAME_HOUSING_TYPE"),
        "occupation_type": row.get("OCCUPATION_TYPE"),
        "family_members": _num(row, "CNT_FAM_MEMBERS"),
        "region_rating": _num(row, "REGION_RATING_CLIENT"),
        "age_years": _days_to_years(_num(row, "DAYS_BIRTH")),
        "years_employed": years_employed,
        "days_since_phone_change": abs(_num(row, "DAYS_LAST_PHONE_CHANGE") or 0),
        "ext_source_1": ext_1,
        "ext_source_2": ext_2,
        "ext_source_3": ext_3,
        "ext_source_mean": ext_mean,
        "credit_income_ratio": credit_income_ratio,
        "annuity_income_ratio": annuity_income_ratio,
        "goods_credit_ratio": goods_credit_ratio,
        "bureau_inquiries_last_year": _num(row, "AMT_REQ_CREDIT_BUREAU_YEAR"),
        "doc3_provided": bool(row.get("FLAG_DOCUMENT_3") == 1),
    }
    features.update(_bureau_features(row))
    return features


def row_to_case(row: Mapping[str, Any]) -> CaseRecord:
    entity_id = str(row.get("SK_ID_CURR"))
    return CaseRecord(
        case_id=f"loan-{entity_id}",
        vertical=Vertical.LOAN,
        entity_id=entity_id,
        features=engineer_features(row),
    )
