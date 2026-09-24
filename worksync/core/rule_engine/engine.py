"""Loads a vertical's rules.yaml and evaluates it against a case's features.

The engine itself is vertical-agnostic: it knows nothing about loans, KYC or
insurance. Everything vertical-specific lives in the YAML file it is handed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from worksync.core.rule_engine.conditions import evaluate_condition, referenced_fields
from worksync.core.schemas.models import ComplianceFlag, Severity


class RuleDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    description: str
    source_regulation: str
    severity: Severity
    condition: dict[str, Any]
    action: str
    verified: bool = False


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
                verified=rule.verified,
                triggered=True,
                evidence=evidence,
            )
        )
    return flags
