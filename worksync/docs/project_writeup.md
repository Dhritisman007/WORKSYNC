# WorkSync.AI — project write-up

## Objective

Build one four-agent pipeline — Analyst (risk scoring), Compliance (rule
checking), Manager (decisioning), Audit (tamper-evident logging) — and
reuse it, structurally unchanged, across four BFSI verticals: loan
approval, KYC/AML onboarding, credit card/BNPL decisioning, and insurance
claims. The project's success criterion, stated at the outset: the
Compliance, Manager and Audit agents need no structural changes across all
four verticals. `tests/test_parity.py` checks this mechanically rather than
by assertion — see `docs/parity_report.md`.

## Architecture

```
Vertical raw input → Ingestion (per-vertical adapter)
                    → CaseRecord (one versioned JSON contract)
                    → Analyst Agent (score + SHAP)  ─┐
                    → Compliance Agent (rule flags)  ┴→ Manager Agent → Decision
                                                         (approve/reject/escalate)
```

The Audit Agent observes every agent's input, output and timestamp without
altering the flow, writing an append-only, hash-chained log.

- **Contracts** (`core/schemas/models.py`): `CaseRecord`, `RiskOutput`,
  `ComplianceFlags`, `Decision`, `AuditEntry`, `Envelope` — pydantic v2
  models with JSON Schema exported alongside them
  (`core/schemas/export_json_schema.py`).
- **Rule engine** (`core/rule_engine/`): a closed YAML condition DSL
  (`field`/`op`/`value` + `all`/`any`/`not`), not `eval()` — rules are
  AI-authored and start `verified: false`, so they must not be able to
  execute arbitrary code.
- **Manager authority** (`docs/manager_authority.md`): bounded authority —
  hard compliance flags always win; the Manager only auto-decides
  high-confidence, out-of-grey-band scores; everything else escalates to a
  human. The precedence order is fixed in `core/agents/manager.py`; only
  thresholds are per-vertical config.
- **Audit** (`core/agents/audit.py`): `sha256(entry + prev_hash)` chaining,
  `verify_chain()` for tamper detection, `replay()` for reproducibility —
  proven with real tampering/deletion tests, not just happy-path tests.

## What was built, phase by phase

| Phase | Weeks (planned) | Outcome |
|---|---|---|
| 1. Lock the contract | 1–2 | Schemas, JSON Schema exports, Manager authority doc, `BaseAgent` interface |
| 2. Shared core | 3–4 | Rule engine, hash-chained Audit Agent, Manager Agent, orchestrator, dummy-vertical proof |
| 3. Loan reference | 5–8 | Home Credit adapter, calibrated LightGBM + XGBoost, SHAP, RBI-style rules, 20 real cases end to end |
| 4a. KYC/AML | 9–10 | Seeded synthetic identity + PEP/sanctions data, same model shape, AML rules |
| 4b. Credit card/BNPL | 11–12 | Kaggle fraud dataset, amount-only ruleset (no invented meaning for opaque features) |
| 4c. Insurance claims | 13–14 | Kaggle claims-fraud dataset, IRDAI-style rules incl. first compound rule condition |
| 5. Parity + demo | 15–17 | Structural-parity test, this report, Streamlit demo app |

See `CHANGELOG.md` for the full log of design decisions and their reasons,
recorded as the project went, not reconstructed afterward.

## Results

| Vertical | Data | AUC (calibrated) | KS | Brier |
|---|---|---|---|---|
| Loan | Real (307,511 rows) + bureau.csv join | 0.7616 | 0.3953 | 0.0674 |
| KYC/AML | Synthetic (5,000 rows) | 0.6700 | 0.2967 | 0.1142 |
| Credit card/BNPL | Real (284,807 rows) | 0.9357 | 0.8433 | 0.0009 |
| Insurance claims | Real (15,420 rows) | 0.7909 | 0.4979 | 0.0527 |

88 automated tests pass (grown from 69 at Phase 5 completion as the demo
app gained upload-detection and canonicalization logic), including the
9-test structural-parity suite, per-vertical unit and end-to-end tests,
and Audit Agent tamper/replay tests.

## Key findings for the report

1. **Zero `core/` changes were needed across four structurally different
   datasets** — one with no categorical features and no entity identifier
   (BNPL), one entirely synthetic (KYC/AML), one with heavily pre-binned
   string columns (insurance). This is the strongest evidence for the
   framework-first claim: the datasets differ maximally, the core doesn't
   move at all.
2. **Every compliance rule declares its basis.** A `regulation` rule cites
   the section as copied from the regulator's official text, with the source
   URL and the date it was checked; an `internal_policy` rule is a threshold
   no regulation prescribes and can never be marked verified. The schema
   rejects a "verified" rule without a source, and a unit test per vertical
   enforces the split, so an AI-drafted rule can't look more authoritative
   than it is.
3. **The Manager Agent's decision logic is fixed in code; only thresholds
   are configuration** — this is what makes "the Manager needs no
   structural changes" checkable rather than just asserted.
4. **Honest reporting of failure cases**: one forced known-fraud insurance
   case was auto-approved in the Phase 4c checkpoint (a real false
   negative), and a real `numpy` type-serialization bug was found via the
   Streamlit app (not the test suite) in Phase 5, tied to `.iloc[]` vs.
   `.iterrows()` row-access differences in pandas. Both are documented
   rather than hidden — see `CHANGELOG.md`'s Phase 4c and Phase 5 entries.

## Known limitations / open items

- **Every regulatory rule needs human verification** against the current
  RBI/IRDAI/PMLA Master Directions before this system could be trusted
  beyond a class demo — that was explicit in the brief and remains
  outstanding.
- **Manager authority (bounded authority) is still the team's default
  proposal**, pending mentor sign-off (`docs/manager_authority.md`).
- **Loan joins `bureau.csv`** (credit-bureau history, aggregated per
  applicant — a real AUC improvement, 0.756→0.762), but not
  `previous_application.csv` / `POS_CASH_balance.csv` / etc. — a further
  extension not yet taken, kept to the brief's "keep feature engineering
  simple" instruction for everything beyond that one join.
- **KYC/AML's label is synthetic** — its metrics are a pipeline-correctness
  check, not a real-world detection-performance claim.
- **OCR / document-image processing** was out of scope (stretch goal per
  the brief) — documents are metadata-only (`doc_type`, `verified`) in
  `CaseRecord.documents`.
