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

A multi-page BFSI decisioning console:

- **Overview** — real KPIs (total cases, outcome mix, avg. risk, avg.
  decision time) computed from the actual audit logs, plus the four-agent
  pipeline diagram.
- **Cases → Case Submission** — pick a vertical, provide case data (sample
  dataset or upload your own raw CSV/JSON — the vertical is auto-detected
  from the column headers), validate, and run it through the live pipeline.
  Results show a decision verdict, a plain-English "why this decision"
  explanation, risk/SHAP, compliance flags, a timeline, and the audit trail.
- **Governance → Audit Explorer** — search the persisted, hash-chained
  audit log for any vertical, reopen any past case's full detail (even
  across app restarts), verify the chain, and replay a case.
- **Governance → Rule Sets** — each vertical's real compliance rules, with
  severity and verification status.
- **Governance → Models & Bands** — real training metrics (AUC, KS, Brier,
  precision/recall) from each vertical's last model run, and the Manager
  agent's decision-threshold bands.
- **System → Agent Health** — real status of each vertical's pipeline
  components (data, model, rules, audit log) — this project has no
  separate API/database to monitor, so this reports what's actually
  loaded, not simulated infrastructure.

Needs each vertical's data + trained model artifacts in place first (see
`worksync/verticals/<x>/README.md`).

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
  LightGBM (+ XGBoost baseline) with SHAP, RBI/KYC rules (citations
  checked against the official text, or marked internal policy), decision bands, and 20 real sample cases run end to end. See
  `worksync/verticals/loan/README.md` and `worksync/docs/loan_model_report.md`.
- Phase 4a (KYC/AML vertical): seeded synthetic identity + PEP/sanctions
  data, calibrated LightGBM (+ XGBoost baseline) with SHAP, AML/KYC rules
  citing the RBI KYC Master Direction (sanctions/PEP hard flags), and 20 sample cases
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
  SHAP, 5 claims rules (4 Red Flag Indicators under
  IRDAI's 2025 Fraud Monitoring Guidelines, 1 internal policy) (early-claim timing,
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
