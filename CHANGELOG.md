# Changelog

Design decisions and their reasons, logged as we go, for the project report.

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
