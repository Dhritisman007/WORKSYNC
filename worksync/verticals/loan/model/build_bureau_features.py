"""Aggregates Home Credit's `bureau.csv` (each applicant's credit history at
other institutions, 1.7M rows / ~306k applicants) into one row per
SK_ID_CURR, written to `worksync/data/processed/loan_bureau_features.csv`.

This is the single highest-value known feature addition for this dataset:
an applicant's existing credit bureau history (how many prior loans, how
many are overdue, total outstanding debt) is strongly predictive of default
risk and isn't contained anywhere in `application_train.csv` itself. Kept
as a separate precomputed table (not joined live) because `bureau.csv` is
170MB / 1.7M rows — expensive to scan per-request, cheap to aggregate once.

This table only covers applicants present in Home Credit's own bureau.csv —
a genuinely new/uploaded application has no real bureau history to join
against (no live credit bureau API here), so `adapter.py` looks up by
SK_ID_CURR and falls back to None/missing for anyone not found, same as any
other missing feature. That's not a bug: it's the honest behavior for data
we don't have.

Run with: python -m worksync.verticals.loan.model.build_bureau_features
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

BUREAU_PATH = Path("worksync/data/raw/loan/bureau.csv")
OUTPUT_PATH = Path("worksync/data/processed/loan_bureau_features.csv")


def build() -> pd.DataFrame:
    bureau = pd.read_csv(BUREAU_PATH)

    bureau["is_active"] = (bureau["CREDIT_ACTIVE"] == "Active").astype(int)
    bureau["is_overdue"] = (bureau["CREDIT_DAY_OVERDUE"] > 0).astype(int)

    agg = bureau.groupby("SK_ID_CURR").agg(
        bureau_count=("SK_ID_BUREAU", "count"),
        bureau_active_count=("is_active", "sum"),
        bureau_overdue_count=("is_overdue", "sum"),
        bureau_days_credit_mean=("DAYS_CREDIT", "mean"),
        bureau_credit_sum=("AMT_CREDIT_SUM", "sum"),
        bureau_credit_sum_debt=("AMT_CREDIT_SUM_DEBT", "sum"),
        bureau_credit_sum_overdue=("AMT_CREDIT_SUM_OVERDUE", "sum"),
        bureau_max_overdue=("AMT_CREDIT_MAX_OVERDUE", "max"),
    )
    agg = agg.round(2).reset_index()
    return agg


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(f"loading {BUREAU_PATH} ...")
    agg = build()
    agg.to_csv(OUTPUT_PATH, index=False)
    print(f"wrote {OUTPUT_PATH} ({len(agg)} applicants)")


if __name__ == "__main__":
    main()
