# Loan vertical (reference implementation)

Data: [Home Credit Default Risk](https://www.kaggle.com/c/home-credit-default-risk)
(`application_train.csv`, not committed — see `worksync/data/raw/loan/`).

## Pipeline

1. `adapter.py` — `row_to_case()` maps one raw application row to a
   `CaseRecord`. Feature engineering (`engineer_features()`) is the single
   source of truth used by both the adapter and `model/train.py`, so
   training and inference can never drift apart.
2. `model/train.py` — trains LightGBM (primary, isotonic-calibrated) and
   XGBoost (comparison baseline only). Writes artifacts to
   `model/artifacts/` (gitignored — regenerate with
   `python -m worksync.verticals.loan.model.train`) and
   `worksync/docs/loan_model_report.md`.
3. `model/risk_model.py` — `LoanRiskModel`, the `RiskModel` the Analyst
   Agent uses at inference time. Produces a calibrated risk probability, a
   confidence band, and the top-5 SHAP attributions (one-hot-encoded
   categorical contributions are summed back to their original human-
   readable feature name).
4. `rules.yaml` — illustrative RBI digital-lending / KYC-style checks.
   **Every rule is `verified: false`** and cites only general guidance, no
   invented clause numbers — verify against the current RBI Master
   Directions before trusting any of these in a real decision.
5. `manager_config.yaml` — this vertical's grey-band thresholds and
   confidence definition for the (vertical-agnostic) Manager Agent.
6. `run_samples.py` — runs N real applications end to end and prints
   decisions/reason codes, and confirms the audit chain + replay. Used for
   the Phase 3 checkpoint.

## Regenerating

```bash
# 1. put application_train.csv and bureau.csv (and optionally the other
#    Home Credit files) in worksync/data/raw/loan/
python -m worksync.verticals.loan.model.build_bureau_features  # once, or whenever bureau.csv changes
python -m worksync.verticals.loan.model.train
python -m worksync.verticals.loan.run_samples 20
```

## Known simplifications (see CHANGELOG.md for the full reasoning)

- **`bureau.csv` is joined** (aggregated per applicant — see
  `model/build_bureau_features.py`), but `previous_application.csv`,
  `POS_CASH_balance.csv`, `credit_card_balance.csv`, and
  `installments_payments.csv` are not — a further, not-yet-taken extension.
  The bureau join only covers applicants present in Home Credit's own
  `bureau.csv`; any new/uploaded case has no real bureau history to join
  against (no live credit bureau API here), so those features come back
  `None` for it, same as any other missing field.
- `rules.yaml`'s conditions reference engineered features, not raw document
  scans — document/image inputs are metadata-only for now per the brief
  (OCR is a stretch goal).
- SHAP explains the *base* (uncalibrated) LightGBM model; calibration only
  rescales the probability, so this still faithfully explains what drove
  the model's score.
