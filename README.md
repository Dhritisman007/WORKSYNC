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

## Status

- Phase 1 (lock the contract): schemas, JSON Schema exports, the Manager
  authority doc (default proposal, pending mentor sign-off), and the
  `BaseAgent` interface.
- Phase 2 (shared core): YAML rule engine, hash-chained Audit Agent (with
  `verify_chain()` and `replay()`), config-driven Manager Agent, the
  orchestrator, and a dummy-vertical pipeline test proving the pipeline runs
  end to end and that audit-log tampering is detected.

See `CHANGELOG.md` for the reasoning behind each decision.
