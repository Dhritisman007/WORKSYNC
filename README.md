# WorkSync.AI

A reusable four-agent framework for automated risk scoring, regulatory
compliance checking, decisioning and audit logging, reused across four BFSI
verticals: loan approval, KYC/AML onboarding, credit card/BNPL decisioning,
and insurance claims.

**Core claim:** the same Compliance, Manager and Audit agents run every
vertical unchanged. Adding a vertical needs only a new data adapter, model,
rule set and config file under `worksync/verticals/<name>/`.

See `worksync/docs/manager_authority.md` for the Manager Agent's decision
authority, and `CHANGELOG.md` for the log of design decisions.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Tests

```bash
pytest worksync/tests -q
```

## Demo

```bash
streamlit run worksync/app/streamlit_app.py
```

Pick a vertical and a case in the sidebar; needs that vertical's data +
trained model artifacts in place first (see each `worksync/verticals/<x>/README.md`).

Two case sources: browse the sample dataset, or upload your own raw CSV/JSON
case (same raw column names as that vertical's own source data — use the
"Download a template row" button to see the expected columns). Either way
the case runs through the identical four-agent pipeline.

## Project report

See `worksync/docs/project_writeup.md` for the full write-up and
`worksync/docs/parity_report.md` for the structural-parity evidence.

## Status

- Phase 1 (lock the contract): schemas, JSON Schema exports, the Manager
  authority doc (default proposal, pending mentor sign-off), and the
  `BaseAgent` interface.
- Phase 2 (shared core): YAML rule engine, hash-chained Audit Agent (with
  `verify_chain()` and `replay()`), config-driven Manager Agent, the
  orchestrator, and a dummy-vertical pipeline test proving the pipeline runs
  end to end and that audit-log tampering is detected.
- Phase 3 (loan reference vertical): Home Credit adapter, calibrated
  LightGBM (+ XGBoost baseline) with SHAP, illustrative unverified RBI/KYC
  rules, decision bands, and 20 real sample cases run end to end. See
  `worksync/verticals/loan/README.md` and `worksync/docs/loan_model_report.md`.
- Phase 4a (KYC/AML vertical): seeded synthetic identity + PEP/sanctions
  data, calibrated LightGBM (+ XGBoost baseline) with SHAP, illustrative
  unverified AML/KYC rules (sanctions/PEP hard flags), and 20 sample cases
  (including forced sanctions/PEP hits) run end to end through the
  unchanged core agents. See `worksync/verticals/kyc_aml/README.md` and
  `worksync/docs/kyc_aml_model_report.md`.
- Phase 4b (credit card/BNPL vertical): Kaggle Credit Card Fraud Detection
  dataset, calibrated LightGBM (+ XGBoost baseline) with SHAP, an
  amount-only ruleset (no invented meaning for anonymized PCA features),
  and 20 sample cases (including 2 forced known-fraud rows) run end to end.
  See `worksync/verticals/bnpl/README.md` and `worksync/docs/bnpl_model_report.md`.
- Phase 4c (insurance claims vertical): Kaggle Vehicle Insurance Claim
  Fraud Detection dataset, calibrated LightGBM (+ XGBoost baseline) with
  SHAP, 5 illustrative unverified IRDAI-style rules (early-claim timing,
  high value, address change, past claims, missing evidence), and 20
  sample cases (including 2 forced known-fraud rows) run end to end. All
  four BFSI verticals are now built on the same unchanged core agents. See
  `worksync/verticals/insurance/README.md` and
  `worksync/docs/insurance_model_report.md`.
- Phase 5 (parity + demo): automated structural-parity test
  (`tests/test_parity.py`, 9 tests) proving `core/` never branches per
  vertical, `docs/parity_report.md`, a Streamlit demo app
  (`app/streamlit_app.py`), and the project write-up
  (`docs/project_writeup.md`). **Project complete — all 5 phases built.**

See `CHANGELOG.md` for the reasoning behind each decision.

Model artifacts and raw data are gitignored (see `worksync/verticals/loan/README.md`
for how to regenerate them).
