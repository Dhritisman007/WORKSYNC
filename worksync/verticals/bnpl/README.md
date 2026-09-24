# Credit card / BNPL vertical

Data: [Credit Card Fraud Detection](https://www.kaggle.com/mlg-ulb/creditcardfraud)
(`creditcard.csv`, not committed — see `worksync/data/raw/bnpl/`). 284,807
real anonymized European transactions, 492 frauds (~0.17% positive rate).

## Pipeline

1. `adapter.py` — `Time`, `Amount` and the 28 PCA-anonymized `V1..V28`
   columns pass through mostly unchanged; `hour_of_day` is derived from
   `Time` (seconds since the first transaction, modulo a day). There's no
   customer/session identifier in this dataset, so — unlike KYC/AML — no
   velocity-style feature was added; it isn't supportable by the data.
2. `model/train.py` / `model/risk_model.py` — same LightGBM (primary,
   calibrated) + XGBoost (baseline) + SHAP shape as the other two
   verticals. No categorical preprocessing branch — everything here is
   numeric.
3. `rules.yaml` — only `amount` is used. The `V1..V28` columns are PCA
   components with no recoverable business meaning, so writing a rule
   against them would mean inventing a justification for an opaque number;
   the model (which is allowed to be opaque) is what handles those
   signals, not the rules engine. `verified: false`, no invented clause
   numbers, same as every other vertical.
4. `manager_config.yaml` — same grey-band shape as the others.
5. `run_samples.py` — forces in 2 known-fraud rows so the demo shows the
   model actually catching something.

## Regenerating

```bash
# 1. put creditcard.csv in worksync/data/raw/bnpl/
python -m worksync.verticals.bnpl.model.train
python -m worksync.verticals.bnpl.run_samples 20
```

## Metrics (real, not estimated — see `docs/bnpl_model_report.md`)

Calibrated LightGBM: AUC 0.9357, KS 0.8433, Brier 0.0009 on the test split —
noticeably stronger than loan or KYC/AML, expected given this is a much
larger, cleaner, real dataset with an unambiguous fraud label.
