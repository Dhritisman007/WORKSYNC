# Changelog

Design decisions and their reasons, logged as we go, for the project report.

## Post-Phase-5 — file upload in the demo app (2026-10-05)

- **`app/streamlit_app.py` gained a "Case source" toggle: sample dataset
  (existing) vs. upload a file.** Upload accepts CSV (one or more raw rows)
  or JSON (one record, or a list of records), in the vertical's own raw
  column format — the same columns its Kaggle/synthetic source file uses,
  not the engineered `CaseRecord` feature names. A per-vertical template
  download button (generated from the sample dataset's first row, ground-
  truth column stripped) tells the user exactly which columns to fill in.
- **`_ensure_id()` fills in a synthetic entity id** (`upload-{n}`) when an
  uploaded row is missing the raw id column that vertical's `row_to_case`
  reads (`SK_ID_CURR` for loan, `applicant_id` for KYC/AML) — an uploaded
  case won't have Kaggle's internal id, and without this it would read as
  `loan-None`. Works identically for a pandas row or a parsed JSON dict,
  since both support `.get`/`.copy()`/item assignment.
- **No `core/` or adapter changes were needed** — an uploaded row runs
  through `spec.row_to_case()` and `orchestrator.run_case_with_detail()`
  exactly like a sample-dataset row, because the adapters already treat
  missing/null raw fields gracefully (built in Phase 3, not new). This is
  more evidence for the parity claim: the demo's input path changed, the
  four-agent pipeline underneath did not.
- **`worksync/tests/test_streamlit_app.py`**: parsing/id-filling unit
  tests (always run) plus one full-pipeline test per vertical that has
  artifacts present — including a sanctions-match KYC/AML upload that must
  hard-reject, proving the uploaded path enforces compliance rules exactly
  like the sample-dataset path does.

## Phase 1 — Lock the contract (2026-09-24)

- **Repo layout** follows the brief exactly: `core/` is vertical-agnostic,
  `verticals/<name>/` holds everything vertical-specific. Enforced later by
  `tests/test_parity.py` in Phase 5 (no `if vertical ==` in `core/`).
- **Schemas are pydantic v2 models, JSON Schema is exported from them**
  (`core/schemas/export_json_schema.py`), not hand-written — keeps the two
  representations from drifting apart. `schema_version` is a plain string
  (`"1.0.0"`) on every contract object so future breaking changes are
  detectable at replay time.
- **`CaseRecord.features` is an untyped `dict[str, Any]`.** This is the one
  place vertical-specific data lives inside an otherwise-fixed schema. The
  alternative (a typed field per vertical) would have forced schema changes
  per vertical, which breaks the project's core claim. Tradeoff: no
  pydantic-level validation of feature contents — validation for
  vertical-specific features happens in that vertical's adapter, not in
  `core/`.
- **`ComplianceFlags` carries a `ruleset_version` and each `ComplianceFlag`
  carries `verified: bool`, defaulting to `False`.** Per the brief, every
  AI-authored regulatory rule starts unverified until a team member checks
  it against the current Master Directions — this is enforced at the schema
  level so an unverified rule can't silently look authoritative in a report.
- **`BaseAgent.handle(Envelope) -> Envelope`** is the only interface. Agents
  never call each other directly — the orchestrator (Phase 2) is the sole
  router. This is what makes the Phase 5 structural-parity test meaningful:
  if agents called each other directly, "the same agents ran every
  vertical" would be harder to prove mechanically.
- **Manager authority model: bounded authority, per `docs/manager_authority.md`.**
  Chosen as the default (not yet confirmed with mentor) because it is the
  easiest position to defend in a regulated setting and keeps all
  vertical-specific tuning in config rather than in `Manager` code.
  **Open item:** needs mentor (Dr. Azra Nazir) sign-off before Phase 2.

## Phase 2 — Shared core (2026-09-24)

- **Rule conditions are a small closed YAML DSL, not `eval()`.** Leaf
  comparisons (`field`/`op`/`value`) plus `all`/`any`/`not` combinators cover
  every rule shape we need for RBI/IRDAI-style checks without letting a rule
  file execute arbitrary Python. Rejected: `eval()`/`simpleeval` on a string
  expression — faster to write but an unnecessary injection surface for a
  file that (per the brief) starts as AI-authored and `verified: false`.
- **Manager Agent precedence is fixed in code; only thresholds are config.**
  `manager.py` hard-codes the four-step order from
  `docs/manager_authority.md` (hard flag > confidence gate > grey band >
  default escalate). `ManagerConfig` (loaded from each vertical's
  `manager_config.yaml`) only supplies the grey-band bounds, which
  confidence labels count as "high," and whether a soft flag alone forces
  escalation. This is what makes "the Manager needs no structural changes
  across verticals" checkable, not just claimed.
- **Audit Agent logs one entry per agent observation (Analyst, Compliance,
  Manager), not one entry per case**, despite the brief's "one immutable,
  replayable log entry per case" phrasing. Reasoning: the same brief also
  says the Audit Agent "observes every agent's input, output and timestamp"
  for all three of D/E/F in the flowchart, and a single entry can't be
  hash-chained against a single well-defined predecessor if it's written
  before all three agents have run. Chaining per-observation still yields
  one append-only, tamper-evident, replayable *trace* per case (see
  `AuditLog.entries_for_case` / `.replay()`), which is what the checkpoint
  ("audit-log tampering is detected") actually tests. Flagging this as an
  interpretation, not a silent one — happy to switch to a single
  end-of-case entry if that's what was meant.
- **`AuditLog.replay(case_id, analyst, compliance, manager)` takes live agent
  instances rather than being a free function in `core/`.** Replay has to
  actually re-run a vertical's real model and rules to prove reproducibility,
  and `core/` cannot import anything vertical-specific — so the caller
  (tests here, the CLI/app later) supplies the already-configured agents for
  that vertical's replay.
- **The Phase 2 "dummy vertical" fixture lives under
  `tests/fixtures/dummy_vertical/`, not `verticals/dummy/`.** `verticals/`
  is reserved for the four real BFSI verticals per the repo layout in the
  brief; a fifth non-BFSI directory there would need its own explaining in
  the Phase 5 parity report for no reason. The dummy stub model, rules and
  manager config exist solely to exercise the pipeline in tests.
- **Hash chain: `entry_hash = sha256(entry_json_without_entry_hash +
  prev_hash)`**, genesis `prev_hash` is 64 zero characters. Verified in
  `test_audit_agent.py` that both tampering with an old entry's payload and
  deleting an entry are detected (chain breaks at the first bad index).

## Phase 3 — Loan reference vertical (2026-09-24)

- **`adapter.engineer_features()` is the single source of truth for feature
  engineering**, called by both `adapter.row_to_case()` (inference) and
  `model/train.py` (training matrix), to rule out train/serve skew by
  construction rather than by convention.
- **Feature set is a curated ~25-feature subset of the raw 122 Home Credit
  columns** plus standard ratios (credit-to-income, annuity-to-income,
  goods-to-credit, mean of the three `EXT_SOURCE_*` bureau-style scores) and
  age/tenure in years. No joins against `bureau.csv`,
  `previous_application.csv`, etc. — per the brief's "keep feature
  engineering simple" instruction. `DAYS_EMPLOYED`'s known 365243 sentinel
  (Home Credit's own placeholder for "not currently employed") is mapped to
  `None`, not treated as a real value.
- **Calibration: `CalibratedClassifierCV(FrozenEstimator(lgbm), method=
  "isotonic")` fit on a held-out slice of the training split (not the test
  split).** The brief's originally-planned `cv="prefit"` API was removed in
  scikit-learn ≥1.6 (installed: 1.9.1) — `FrozenEstimator` is its
  replacement. Bumped `requirements.txt` to `scikit-learn>=1.6` accordingly.
  This is a dependency-API accommodation, not a scope change.
- **XGBoost is trained and reported on, never used for scoring** — matches
  the brief's "LightGBM as primary, XGBoost as comparison baseline."
- **SHAP explains the base (uncalibrated) LightGBM model**, not the
  calibrated wrapper — `shap.TreeExplainer` needs a tree model directly, and
  calibration only rescales the probability, so the base model's feature
  attributions are still a faithful explanation of the score. One-hot
  columns from a single categorical feature (e.g. `income_type`) are summed
  back into one attribution under the original column name before taking
  the top 5, so the report shows human-readable feature names, not encoded
  dummy-column names.
- **`rules.yaml`: every rule is `verified: false`, and `source_regulation`
  cites only general guidance documents, never a specific clause/circular
  number** — per the brief's explicit "never invent circular or clause
  numbers" instruction. These 5 rules are illustrative starting points, not
  a compliance-verified ruleset; a team member must check each against the
  current RBI Master Directions before this vertical is trusted for
  anything beyond the class demo.
- **`manager_config.yaml`'s grey band (0.35–0.65) is deliberately wider than
  the 0.5 reporting threshold** used for the model report's confusion
  matrix — auto-deciding a loan should require a clearly one-sided score,
  not a bare majority; most borderline cases are meant to escalate.
- **Trained model artifacts (`model/artifacts/*.joblib`) are gitignored**,
  not committed — they're fully reproducible from `train.py` given the
  (also gitignored, must be downloaded from Kaggle) CSV and the fixed seed
  (42). Keeps the repo free of binary blobs and avoids the artifacts
  silently going stale relative to the training code.
- **20 real sample cases ran end to end** via
  `verticals/loan/run_samples.py`: decisions, reason codes and confidence
  bands all populated correctly, `verify_chain()` passed, and `replay()`
  reproduced the logged decision. See `docs/loan_model_report.md` for the
  actual AUC/KS/Brier numbers from this run (not estimated).
- **No `core/` changes were needed** to add this vertical — confirms the
  Phase 2 contracts hold for a real model + real rules, not just the dummy
  fixture.

## Phase 4a — KYC/AML vertical (2026-09-24)

- **Data is entirely synthetic** (`data_gen.py`, seed `4242`): fabricated
  applicant names, PEP list, sanctions list, and a `high_risk_label` target
  that's a documented function of the same risk signals plus noise — not a
  real fraud outcome. This vertical has no public reference dataset (unlike
  loan), so per the brief this had to be generated, not downloaded; kept
  deterministic and tested for it (`test_data_generator_is_deterministic`)
  so replay/audit stay meaningful across runs.
- **A small fraction of synthetic applicants are deliberately given a name
  that matches the PEP/sanctions lists** (2% / 1%), rather than relying on
  pure chance, so the hard-flag rules have real hits to exercise in tests
  and the sample run — `run_samples.py` forces at least one of each into
  its sample for the same reason.
- **Same LightGBM+XGBoost+SHAP model shape as the loan vertical**, reusing
  the identical calibration approach (`FrozenEstimator` + isotonic,
  prefit on a held-out training slice) — deliberately not inventing a new
  modeling pattern per vertical, since the whole point is that only the
  adapter/model/rules/config differ, not the approach.
- **`rules.yaml`: sanctions match is `hard`+`reject`, PEP match is
  `hard`+`escalate`** (enhanced due diligence, not automatic rejection —
  a PEP isn't necessarily disqualifying, just requires a human look). Both
  still `verified: false` with only general-guidance citations, same as
  loan's rules.
- **The model is intentionally somewhat redundant with the hard rules** —
  sanctions/PEP hits always override the score via the Manager's fixed
  precedence. The model's actual job is catching residual risk in cases
  that pass screening but still look weak (poor document quality, high
  device risk, velocity spikes). Documented in
  `verticals/kyc_aml/README.md` so this isn't mistaken for a design flaw.
- **AUC ~0.66–0.68 on the synthetic test split** — lower than loan's 0.756,
  expected given a smaller synthetic dataset (5,000 rows vs. 307,511) with
  a noisier, non-empirical label. Documented in
  `docs/kyc_aml_model_report.md` as a pipeline-correctness check, not a
  real-world performance claim.
- **20 sample cases (including forced sanctions/PEP hits) ran end to end**:
  correct reject/escalate outcomes for the forced hits, `verify_chain()`
  passed, `replay()` reproduced the logged decision.
- **No `core/` changes were needed.**

## Phase 4b — Credit card/BNPL vertical (2026-09-24)

- **Dataset: Kaggle `mlg-ulb/creditcardfraud`** (chosen with the user rather
  than assumed) — 284,807 real anonymized European transactions, 492 frauds.
  Unlike loan and KYC/AML, this dataset's 28 features (`V1..V28`) are PCA
  components with no recoverable human-readable meaning (anonymized by the
  dataset's publisher, not by us).
- **`rules.yaml` for this vertical only covers `amount`.** Writing a rule
  against `V14` or any other PCA component would mean fabricating a
  business justification for an opaque number — that's exactly the kind of
  invented-authority problem the brief's "never invent clause numbers"
  instruction is guarding against, just one level removed (inventing rule
  *meaning* rather than a citation). The model is allowed to use those
  columns opaquely; the compliance rules engine is not.
- **No velocity-style feature, unlike KYC/AML** — this dataset has no
  customer/session identifier, so a cross-transaction feature isn't
  supportable by the data. Left out rather than fabricated an identifier.
- **Preprocessor for this vertical is numeric-only** (no categorical
  `ColumnTransformer` branch) — first vertical without any categorical
  features, confirms the shared model-plumbing pattern degrades gracefully
  rather than assuming every vertical has categoricals.
- **Metrics are meaningfully stronger than loan/KYC-AML**: calibrated
  LightGBM AUC 0.9357, KS 0.8433, Brier 0.0009. Expected — this is a real,
  cleanly-labeled fraud dataset with an unambiguous outcome, unlike
  KYC/AML's synthetic label or loan's inherently noisier credit-risk task.
- **20 sample cases (2 forced known-fraud rows) ran end to end**: one fraud
  case auto-rejected (prob 0.90, high confidence), the other escalated
  (prob 0.64, low confidence — correctly not auto-decided at that
  confidence level). `verify_chain()` passed, `replay()` reproduced the
  logged decision.
- **No `core/` changes were needed** — fourth vertical, same unchanged
  Analyst/Compliance/Manager/Audit agents, now proven across a real
  imbalanced-classification dataset with zero categorical features and no
  entity identifier, the most structurally different of the three real/
  synthetic datasets used so far.

## Phase 4c — Insurance claims vertical (2026-09-24)

- **Dataset: Kaggle `shivamb/vehicle-claim-fraud-detection`** (chosen with
  the user) — 15,420 claims, `FraudFound_P` target, ~6% positive rate.
  Interpretable columns, unlike BNPL's anonymized PCA features.
- **Several source columns are pre-binned strings, not raw numbers** (e.g.
  `PastNumberOfClaims`: "none"/"1"/"2 to 4"/"more than 4"). Each bucket is
  mapped to a documented numeric midpoint (`adapter.py`'s `_*_MIDPOINT`
  dicts) purely so `rules.yaml` can threshold on them the same way the
  other verticals threshold on raw numbers. This is a lossy simplification
  (a bucket loses its internal spread) — acceptable per "keep feature
  engineering simple," and the model still also sees the raw bucket as a
  category, so it isn't solely reliant on the midpoint.
- **`rules.yaml`: early claim (< 8 days after policy start) is `hard`+
  `escalate`** — this is one of the most well-established real insurance-
  fraud heuristics (a claim filed almost immediately after coverage starts
  is inherently suspicious), used here structurally the same way loan's
  DTI rule or BNPL's amount rule are: a threshold on an interpretable
  field, cited only generally, `verified: false`.
- **`INS-NOEVIDENCE-001` is this project's first compound rule condition
  in production use** (`all: [police_report_filed == false, witness_present
  == false]`) — exercises the `all`/`any`/`not` combinators from Phase 2's
  rule engine beyond the single-leaf conditions used so far.
- **20 sample cases (2 forced known-fraud rows) ran end to end. One forced
  fraud case was auto-approved** (low score, no hard flag triggered) — a
  genuine false negative, left in the checkpoint report rather than
  filtered out, since the point of this project is an honest decision-
  support pipeline, not a claim that either the model or the rules catch
  everything. `verify_chain()` passed, `replay()` reproduced the logged
  decision for the last case run.
- **No `core/` changes were needed** — all four verticals now built, same
  unchanged Analyst/Compliance/Manager/Audit agents throughout. This is the
  claim Phase 5's structural-parity test formalizes next.

## Phase 5 — Structural parity and demo (2026-09-24)

- **`Orchestrator` gained `run_case_with_detail()` returning a `CaseResult`
  (risk + compliance + decision), alongside the existing `run_case()`
  (decision only).** This is a `core/` change, but an additive,
  vertical-agnostic one — needed so the Streamlit demo can show the
  intermediate risk score and compliance flags, not just the final
  decision. `run_case()` is now a one-line wrapper around it, so no
  existing caller (tests, `run_samples.py`) needed to change.
- **`tests/test_parity.py` checks `type(x) is <core class>`, not
  `isinstance`** — deliberately stricter, to catch a hypothetical future
  per-vertical subclass that would technically satisfy `isinstance` while
  still being the kind of structural change the brief says must be a
  stop-and-report moment.
- **Found via the Streamlit app, not the test suite: `pandas.DataFrame
  .iloc[i]` can return raw `numpy.bool`/`numpy.int64` scalars for some
  columns, where `.iterrows()` (used everywhere in the existing test
  suite) happens to box them to native Python types first.**
  `CaseRecord.model_dump(mode="json")` can't serialize a bare numpy scalar,
  so this crashed the demo app on the loan vertical's `doc3_provided`
  field (`FLAG_DOCUMENT_3 == 1`) the moment a case was built via `.iloc[]`
  instead of `.iterrows()`. Fixed with explicit `bool(...)` casts in
  `verticals/loan/adapter.py`; the other three verticals' adapters were
  checked directly and were already safe. Added a regression test
  (`test_case_from_iloc_row_access_has_no_numpy_leaks_and_serializes`) that
  exercises `.iloc[]` specifically, since the existing tests' exclusive use
  of `.iterrows()` is exactly what let this ship unnoticed through 59
  passing tests. This is the kind of bug that only surfaces once something
  actually drives the pipeline from outside the test suite — worth noting
  for the report as a reason the brief asked for a working demo, not just
  tests.
- **`docs/parity_report.md`**: what changed vs. what stayed the same per
  vertical, the real model metrics side by side, and every cross-vertical
  finding from Phases 2–5 in one place.
- **`app/streamlit_app.py`**: vertical + case picker, case record, risk
  score + confidence band, SHAP bar chart, compliance flags, decision with
  reason codes, and an audit trail table with live `verify_chain()` status
  and a `replay()` button. The only file in the project that imports all
  four verticals by name (a `VERTICALS` registry) — expected, since
  something has to know they all exist to offer a picker; everything the
  registry wires up underneath is the same shared `core/` code.
- **`docs/project_writeup.md`**: the project write-up tying architecture,
  phase-by-phase outcomes, results and known limitations together for the
  final report.
