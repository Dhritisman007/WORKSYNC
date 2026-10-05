# Changelog

Design decisions and their reasons, logged as we go, for the project report.

## Post-Phase-5 — enterprise BFSI console redesign (2026-10-06)

- **Restructured the single-page Streamlit app into a multi-page console**
  (`st.navigation`, Streamlit 1.65) with the sections a BFSI decisioning
  platform's SRS actually asks for: Overview, Cases → Case Submission,
  Governance → Audit Explorer / Rule Sets / Models & Bands, System → Agent
  Health. The brief for this also described a Reviewer Queue and Human
  Review workspace with persistent assignment, priority and override
  history, and a System Health page for a separate API Gateway/Orchestrator/
  database — **none of those exist in this project** (no REST API, no
  database, no user accounts), so rather than fabricate placeholder data
  for them, they were left out and flagged to the user. Every page that
  *was* built uses only real, already-existing data sources: the persisted
  hash-chained audit log, the actual `rules.yaml` per vertical, and the
  real `model/artifacts/metadata.json` written by each vertical's own
  `train.py`.
- **`worksync/app/pipeline.py`**: all vertical/orchestrator/upload-parsing
  logic, extracted out of the single app file so every page can share it
  without duplication. `worksync/app/design.py`: the enterprise dark theme
  (near-black navy background, two panel shades, a single restrained accent
  blue, semantic colors used only for state) plus reusable components (KPI
  rows, badges, the pipeline diagram). `worksync/app/components.py`: the
  shared result-rendering blocks (decision banner, risk/compliance/why/
  timeline/audit) used identically by Case Submission (a case just run) and
  Audit Explorer (a case reconstructed from the log) — one implementation,
  not two that could drift.
- **New: `reconstruct_case_result()`** rebuilds a full `CaseResult` (risk +
  compliance + decision) for *any* previously logged case by reading only
  the persisted JSONL audit entries and re-validating their payloads back
  into the real pydantic models — this is what lets the Audit Explorer show
  complete historical case detail even after an app restart, not just the
  current session's last-run case. It is a read path only; it does not
  re-run the agents (that's what `replay()` already does).
- **New: `summarize_audit_log()`** computes genuine KPIs (total cases,
  outcome counts, average risk probability, average analyst→manager
  processing time, chain-verification status) directly from each
  vertical's audit log. The Overview page shows these, or an explicit
  "no cases run yet" state — never placeholder numbers.
- **Theme via `.streamlit/config.toml`**, not CSS overrides fighting
  Streamlit's defaults — `primaryColor` etc. set there so native widgets
  (buttons, the active-tab underline, radio selection) pick up the accent
  blue automatically instead of Streamlit's default red.
- **Found and fixed the same HTML-block-termination bug a second time, in
  a new place**: the pipeline diagram's inline SVG (a single `st.markdown`
  call, not a concatenation this time) rendered only its top half — the
  Manager/decision/Audit portion leaked out as literal visible text. Cause:
  Streamlit's CommonMark-based renderer treats `<svg>` as a generic block
  tag (not a `<style>`/`<script>`/`<pre>` "verbatim until closing tag"
  element), so a *single blank line inside the SVG* (used purely for
  visual grouping in the source) terminated the HTML block early. Fixed by
  rewriting the diagram as one unbroken string with zero internal blank
  lines, matching the lesson from the stat-card bug. Audited every other
  multi-line HTML block in the new pages for the same risk — all clear.
  This is the second time this exact class of bug has appeared and the
  second time it was only caught by actually loading the page in a
  browser, not by linting, type-checking, or the test suite.
- `worksync/tests/test_streamlit_app.py` updated to import from
  `worksync.app.pipeline` (where the logic now lives) instead of
  `worksync.app.streamlit_app`. All 83 tests still pass unchanged
  otherwise — this was a presentation-layer restructure, not a change to
  any agent, model, rule, or decision logic.

## Post-Phase-5 — tactile visual pass on the demo app (2026-10-06)

- **Custom stat-card component (`stat_card_row()`) replaces `st.metric`**
  for risk probability / confidence / flag count — bordered tiles with a
  colored top accent, shadow, and hover lift, consistent with the card
  language used everywhere else (compliance flags, landing page).
- **Hover/press states added throughout**: cards lift on hover (translateY
  + shadow), buttons lift on hover and depress on click (scale .98,
  darker shadow), the file-upload dropzone highlights on hover, tabs get
  a background tint on hover and an animated underline transition.
  "Tactile" specifically meant interactive elements should visibly respond
  to being touched, not just exist — this is the direct fix for that.
- **Animated topbar and fade-up entrance** on cards/stats/decision banner
  (`wsyncFadeUp` keyframe) — new content appearing (after clicking Run)
  now visibly settles in instead of popping in static.
- **Found and fixed a real rendering bug while building this**: concatenating
  multiple multi-line, Python-source-indented HTML f-strings for the stat
  cards produced a blank-looking line between cards. Streamlit's markdown
  renderer (CommonMark semantics) treats a recognized `<div>`-starting
  block as raw HTML only until the next blank line — after that, a line
  indented 4+ spaces reverts to being parsed as a Markdown code block.
  The second and third stat cards were rendering as literal `<div...>`
  text in the browser, not broken Python — only visible by actually
  loading the page, not from a lint or test. Fixed by building each card
  as a single line with no internal newlines/indentation; documented in
  `stat_card_row()`'s docstring so the next multi-card HTML helper doesn't
  reintroduce it.
- All colors/spacing centralized into CSS custom properties (`--wsync-*`)
  at the top of `inject_css()` instead of scattered hex literals, so the
  palette can be adjusted in one place.

## Post-Phase-5 — explicit landing page instead of auto-running on load (2026-10-06)

- **The app no longer runs a case the instant it loads.** Previously it
  auto-ran row 0 of the Loan sample dataset on first paint, which read as
  a bug/unfinished state rather than a deliberate default — a fresh visit
  showed "real" results from data nobody asked to see yet. Now the
  pipeline only runs when the user clicks **"Run this case"** in the
  sidebar; before that, a landing screen explains what the app does and
  summarizes the four verticals.
- **Implementation: `st.session_state["active_case"]` holds the last case
  that was explicitly submitted** (vertical key, row, row index) — set
  only inside the `if run_clicked:` branch. The sidebar's vertical/row/
  upload selection is always live, but it doesn't re-run the pipeline on
  every tweak; the displayed result stays pinned to whatever was last
  explicitly run until Run is clicked again. This is a standard "configure
  then submit" pattern, not a core/ or adapter change — nothing about the
  four-agent pipeline changed, only when the demo app chooses to call it.
- `render_landing()` reuses the existing `.wsync-card` styling so it reads
  as part of the same design system, not a bolted-on splash screen.

## Post-Phase-5 — automatic vertical detection on upload (2026-10-06)

- **Upload no longer requires picking the vertical first.** "Case source:
  Upload a file" now shows a single file picker; `detect_vertical()`
  compares the uploaded file's column headers against each vertical's
  `RAW_COLUMNS` (added to the three adapters that didn't already have one —
  `loan/adapter.py` already did) and scores each vertical by what fraction
  of its expected schema is present. The detected vertical pre-selects a
  normal override dropdown — never a silent, unconfirmable auto-route —
  and a "column match scores" expander shows the scoring for all four so
  the choice isn't a black box.
- **This is a column-signature match, not a model.** No training, no
  embeddings — exact header names are what every adapter already keys off
  (`row.get("AMT_INCOME_TOTAL")` etc.), so a header match is a faithful
  proxy for "will this adapter actually populate its features from this
  file," and it's fully explainable (the match-score table *is* the
  reasoning). Verified against all four `worksync/samples/*` files: 100%
  coverage for BNPL/insurance, 92-96% for KYC-AML/loan (a couple of
  optional columns missing from the samples), 0% cross-contamination
  between verticals.
- **Low-confidence matches (<40% coverage) surface a warning instead of
  silently picking the top score** — important because an upload with very
  few matching columns is exactly the case where guessing wrong is most
  likely and most costly (wrong rules, wrong model, wrong decision).
- **No `core/` changes** — detection lives entirely in `app/streamlit_app.py`
  and reads each vertical's own `RAW_COLUMNS`; the four-agent pipeline
  underneath is identical whether the vertical was picked manually or
  detected.
- Template downloads moved into a "Need a template first?" expander
  listing all four verticals, since the vertical isn't known before upload
  anymore.
- `worksync/tests/test_streamlit_app.py`: one detection test per sample
  file (must match its own vertical, zero coverage elsewhere) plus an
  unrelated-columns case that must return zero confidence everywhere.

## Post-Phase-5 — professional redesign of the demo app (2026-10-06)

- **Rebuilt the app around a decision, not a data dump.** Previous layout
  led with raw tables (case record, then risk metrics, then decision
  buried below). Now: a live processing stepper, then a prominent color-
  coded decision card with a plain-English conclusion up front, then
  supporting detail in tabs (Risk analysis / Case record / Compliance /
  Audit trail) — the verdict is the first thing anyone sees.
- **`Orchestrator.run_case_with_detail()` gained an optional `on_step`
  callback** (`core/orchestrator.py`), called after each of the four
  pipeline stages. Additive and backward compatible — every existing
  caller that doesn't pass it behaves identically. This lets the demo show
  genuine per-stage progress (ingest → analyst → compliance → manager)
  instead of faking it with a generic spinner; the UI never pretends a
  step finished before the underlying agent call actually returned.
- **`build_narrative()` composes a 2-4 sentence plain-English explanation**
  of the decision from the actual `Decision`/`ComplianceFlags`/`RiskOutput`
  objects — which hard rule fired (if any) and why, the dominant SHAP
  signal and its direction, and a count of any additional soft-flag notes.
  Not a canned string per outcome type — it reads differently case to case
  based on what actually happened.
- **A risk gauge renders where the score sits relative to the vertical's
  own grey-band config** (`orchestrator.manager.config.grey_band_lower/
  upper`), color-zoned green/amber/red, so "why didn't this auto-decide"
  is visible at a glance instead of requiring someone to read the
  Manager's threshold config.
- **Compliance flags render as individual cards** (severity-colored left
  border, action/severity chips, citation + verified status) instead of a
  raw dataframe — easier to scan when there are several flags on one case.
- Fixed a singular/plural grammar bug in the narrative ("1 additional note
  were recorded" → "was recorded"), caught by actually reading the
  rendered output in the browser, not by a test.
- `worksync/tests/test_parity.py`'s source scan now skips `._*` files —
  unrelated to the redesign, but hit while testing on this filesystem
  (macOS AppleDouble sidecar files from a cross-volume copy were being
  picked up by the `*.py` glob and crashing the UTF-8 read).

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
