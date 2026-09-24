# Structural parity report

This is the project's central claim, checked mechanically rather than just
asserted: **the same Compliance, Manager and Audit agents — and the
orchestrator that routes between them — run all four BFSI verticals
unchanged.** `tests/test_parity.py` enforces this automatically:

1. `test_core_has_no_vertical_specific_branching` — scans every `.py` file
   under `core/` for `vertical ==` / `vertical in (...)` and fails the
   build if any exists. Zero occurrences today.
2. `test_vertical_wires_up_the_unchanged_core_classes` — for each vertical,
   constructs its `ComplianceAgent`/`ManagerAgent`/`AnalystAgent`/`AuditLog`/
   `Orchestrator` exactly as that vertical's own `run_samples.py` does, and
   asserts `type(x) is <core class>` (not `isinstance`, specifically to
   catch a future per-vertical subclass masquerading as the shared type).
3. `test_vertical_case_record_fits_the_one_shared_schema` — builds a
   `CaseRecord` for each vertical and runs it through that vertical's
   pipeline end to end, confirming the one shared `CaseRecord`/`Envelope`
   schema needs no per-vertical variant.

Run it yourself: `pytest worksync/tests/test_parity.py -v`.

## What changed vs. what stayed the same, per vertical

| | Loan | KYC/AML | Credit card/BNPL | Insurance claims |
|---|---|---|---|---|
| **Data source** | Kaggle Home Credit Default Risk (real, 307,511 rows) | Synthetic, seeded (`data_gen.py`, 5,000 rows) | Kaggle Credit Card Fraud Detection (real, 284,807 rows) | Kaggle Vehicle Insurance Claim Fraud Detection (real, 15,420 rows) |
| **Adapter** (`verticals/<x>/adapter.py`) | Curated Home Credit columns + ratio features | Synthetic identity/device/screening fields | `Amount`/`Time`-derived + 28 anonymized PCA components, no categoricals | Interpretable columns + bucket→midpoint mapping for pre-binned strings |
| **Model** (`verticals/<x>/model/`) | LightGBM (calibrated) + XGBoost baseline | same shape, smaller data | same shape, no categorical preprocessing branch | same shape |
| **Rules** (`verticals/<x>/rules.yaml`) | 5 rules: KYC gap, DTI, age, leverage, missing doc | 5 rules: sanctions (hard reject), PEP (hard escalate), doc quality, adverse media, velocity | 2 rules: amount thresholds only (no invented meaning for opaque PCA features) | 5 rules incl. the project's first compound (`all`) condition |
| **Config** (`verticals/<x>/manager_config.yaml`) | grey band 0.35–0.65 | grey band 0.35–0.65 | grey band 0.35–0.65 | grey band 0.35–0.65 |
| **What did NOT change** | `core/agents/{analyst,compliance,manager,audit}.py`, `core/orchestrator.py`, `core/rule_engine/*`, `core/schemas/models.py` — identical across all four |

## Model metrics (real, from each vertical's own report — see `docs/<x>_model_report.md`)

| Vertical | AUC (calibrated LightGBM) | KS | Brier |
|---|---|---|---|
| Loan | 0.7562 | 0.3885 | 0.0678 |
| KYC/AML | 0.6584 | 0.2470 | 0.1148 |
| Credit card/BNPL | 0.9357 | 0.8433 | 0.0009 |
| Insurance claims | 0.7909 | 0.4979 | 0.0527 |

Spread is expected and not a red flag: BNPL has by far the largest, cleanest,
most unambiguously labeled dataset; KYC/AML's label is synthetic and noisy
by construction; loan and insurance sit in between with real but inherently
harder credit-risk/fraud tasks.

## Findings logged during the build (see `CHANGELOG.md` for full reasoning)

None of these required a `core/` change — each was resolved inside a
vertical's own `adapter.py`/`rules.yaml`/`model/`, which is itself evidence
for the parity claim (if the frozen core had been too rigid, one of these
would have forced an exception):

- **Audit entry granularity** (Phase 2): one hash-chained entry per agent
  observation rather than one entry per case, given the brief's two
  requirements ("one entry per case" and "observes every agent's input/
  output") were in tension. Flagged as an interpretation, not resolved by
  guessing silently.
- **No compliance rules against opaque features** (BNPL's PCA components,
  Phase 4b): writing a rule against `V14` would mean inventing a business
  justification for a number with no recoverable meaning — treated as the
  same category of problem as inventing a citation, so left to the model
  instead.
- **No fabricated identifiers** (BNPL has no customer/session ID, Phase
  4b): no velocity-style feature was added for that vertical, unlike
  KYC/AML, because the data doesn't support it.
- **A real false negative, reported honestly** (insurance, Phase 4c): one
  of two forced known-fraud sample cases was auto-approved in the
  checkpoint run. Left in the report rather than filtered out — this
  system is decision support with human escalation, not a guarantee.
- **A `numpy` type leak, found via the Streamlit app, not the test suite**
  (Phase 5): `pandas.DataFrame.iloc[i]` can return `numpy.bool`/`numpy.int64`
  scalars for some columns where `.iterrows()` (used in every prior test)
  happens to box them to native Python types. `CaseRecord.model_dump(mode=
  "json")` can't serialize a raw numpy scalar. Fixed in `verticals/loan/
  adapter.py` (`bool(...)` casts) and covered by a new regression test
  (`test_case_from_iloc_row_access_has_no_numpy_leaks_and_serializes`) —
  the other three adapters were checked and were already safe.

## Regenerating this report's data

Every real dataset is gitignored; regenerate the underlying model reports
with each vertical's own `model/train.py` (see each `verticals/<x>/README.md`).
This report itself is hand-written, not auto-generated — the numbers above
are transcribed from the actual `docs/<x>_model_report.md` files.
