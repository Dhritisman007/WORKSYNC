"""Loads a vertical's rules.yaml and evaluates it against a case's features.

The engine itself is vertical-agnostic: it knows nothing about loans, KYC or
insurance. Everything vertical-specific lives in the YAML file it is handed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

from worksync.core.rule_engine.conditions import evaluate_condition, referenced_fields
from worksync.core.schemas.models import ComplianceFlag, Severity


class RuleDef(BaseModel):
    """One compliance rule.

    `basis` separates two different kinds of rule:
      - "regulation": the rule implements a requirement in a named
        regulation. `verified: true` means the cited section was checked
        against the regulator's official text — that needs `reference_url`
        (where) and `verified_on` (when) so anyone can re-check it.
      - "internal_policy": a risk-appetite choice (e.g. a threshold) that no
        regulation prescribes. There is no citation to verify, so it can
        never be `verified`; `reference_url` may point at a related
        regulation for context.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    description: str
    source_regulation: str
    severity: Severity
    condition: dict[str, Any]
    action: str
    basis: Literal["regulation", "internal_policy"] = "regulation"
    verified: bool = False
    reference_url: str | None = None
    verified_on: str | None = None

    @model_validator(mode="after")
    def _verification_is_backed(self) -> RuleDef:
        if self.basis == "internal_policy" and self.verified:
            raise ValueError(f"{self.id}: an internal-policy rule has no citation to verify")
        if self.verified and not (self.reference_url and self.verified_on):
            raise ValueError(f"{self.id}: verified rules need reference_url and verified_on")
        return self


class RuleSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    vertical: str
    rules: list[RuleDef]


def load_ruleset(path: str | Path) -> RuleSet:
    data = yaml.safe_load(Path(path).read_text())
    return RuleSet.model_validate(data)


def evaluate_ruleset(ruleset: RuleSet, context: dict[str, Any]) -> list[ComplianceFlag]:
    """Evaluate every rule against `context` (typically CaseRecord.features).

    Only rules whose condition is true produce a flag — non-triggered rules
    are silent, not returned as `triggered=False` entries, to keep the
    output focused on what actually fired for this case.
    """
    flags: list[ComplianceFlag] = []
    for rule in ruleset.rules:
        if not evaluate_condition(rule.condition, context):
            continue
        evidence = {f: context.get(f) for f in referenced_fields(rule.condition)}
        flags.append(
            ComplianceFlag(
                rule_id=rule.id,
                description=rule.description,
                source_regulation=rule.source_regulation,
                severity=rule.severity,
                action=rule.action,
                basis=rule.basis,
                verified=rule.verified,
                triggered=True,
                evidence=evidence,
            )
        )
    return flags
