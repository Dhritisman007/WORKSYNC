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
