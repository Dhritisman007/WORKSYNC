# Insurance claims vertical

Data: [Vehicle Insurance Claim Fraud Detection](https://www.kaggle.com/datasets/shivamb/vehicle-claim-fraud-detection)
(`fraud_oracle.csv`, not committed — see `worksync/data/raw/insurance/`).
15,420 claims, `FraudFound_P` target, ~6% positive rate.

## Pipeline

1. `adapter.py` — maps interpretable columns (age, driver rating,
   deductible, fault, policy type, etc.) plus several pre-binned string
   columns (e.g. `PastNumberOfClaims`: "none"/"1"/"2 to 4"/"more than 4").
   Each bucket is also mapped to a numeric midpoint (`_*_MIDPOINT` dicts in
   `adapter.py`) so `rules.yaml` can threshold on them the same way the
   other verticals threshold on raw numbers — the model still sees the raw
   bucket too, as a category.
2. `model/train.py` / `model/risk_model.py` — same LightGBM (primary,
   calibrated) + XGBoost (baseline) + SHAP shape as loan/KYC-AML.
3. `rules.yaml` — 5 illustrative IRDAI-style checks: early claim (< 8 days
   after policy start — hard escalate), highest vehicle-price bracket (hard
   escalate), recent address change (soft), frequent past claims (soft), no
   police report + no witness (soft, compound `all` condition). All
   `verified: false`, no invented clause numbers.
4. `manager_config.yaml` — same grey-band shape as the other three.
5. `run_samples.py` — forces in 2 known-fraud rows.

## Regenerating

```bash
# 1. put fraud_oracle.csv in worksync/data/raw/insurance/
python -m worksync.verticals.insurance.model.train
python -m worksync.verticals.insurance.run_samples 20
```

## Metrics (real, not estimated — see `docs/insurance_model_report.md`)

Calibrated LightGBM: AUC 0.7909, KS 0.4979, Brier 0.0527 on the test split.

## Known limitation

In the 20-case checkpoint run, one of the two forced fraud cases was
auto-approved (low model score, no hard flag triggered) — a real false
negative, not filtered out of this README. Illustrates why this is framed
throughout as a decision-support system with human escalation, not a fraud
oracle: neither the model nor this rule set claims to catch everything.
