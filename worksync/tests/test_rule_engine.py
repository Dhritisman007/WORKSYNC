import pytest

from worksync.core.rule_engine.conditions import ConditionError, evaluate_condition
from worksync.core.rule_engine.engine import evaluate_ruleset, load_ruleset

FIXTURE = "worksync/tests/fixtures/dummy_vertical/rules.yaml"


def test_leaf_operators():
    ctx = {"amount": 150000, "on_watchlist": True, "country": "IN"}
    assert evaluate_condition({"field": "amount", "op": "gt", "value": 100000}, ctx)
    assert not evaluate_condition({"field": "amount", "op": "lt", "value": 100000}, ctx)
    assert evaluate_condition({"field": "on_watchlist", "op": "eq", "value": True}, ctx)
    assert evaluate_condition({"field": "country", "op": "in", "value": ["IN", "US"]}, ctx)
    assert evaluate_condition({"field": "missing", "op": "exists"}, ctx) is False


def test_combinators():
    ctx = {"amount": 150000, "on_watchlist": False}
    cond = {
        "any": [
            {"field": "on_watchlist", "op": "eq", "value": True},
            {"all": [{"field": "amount", "op": "gt", "value": 100000}]},
        ]
    }
    assert evaluate_condition(cond, ctx) is True

    cond_not = {"not": {"field": "on_watchlist", "op": "eq", "value": True}}
    assert evaluate_condition(cond_not, ctx) is True


def test_unknown_operator_raises():
    with pytest.raises(ConditionError):
        evaluate_condition({"field": "x", "op": "frobnicate", "value": 1}, {"x": 1})


def test_missing_field_is_false_not_error():
    assert evaluate_condition({"field": "nope", "op": "eq", "value": 1}, {}) is False


def test_ruleset_fires_only_matching_rules():
    ruleset = load_ruleset(FIXTURE)
    flags = evaluate_ruleset(ruleset, {"on_watchlist": True, "amount": 50000})
    assert len(flags) == 1
    assert flags[0].rule_id == "DUMMY-HARD-001"
    assert flags[0].verified is False

    flags = evaluate_ruleset(ruleset, {"on_watchlist": True, "amount": 150000})
    fired_ids = {f.rule_id for f in flags}
    assert fired_ids == {"DUMMY-HARD-001", "DUMMY-SOFT-001"}

    flags = evaluate_ruleset(ruleset, {"on_watchlist": False, "amount": 1000})
    assert flags == []


def _rule(**overrides):
    base = dict(id="R1", description="d", source_regulation="s", severity="hard",
                condition={"field": "x", "op": "eq", "value": 1}, action="reject")
    base.update(overrides)
    return base


def test_verified_rule_without_a_source_url_is_rejected():
    import pytest
    from pydantic import ValidationError

    from worksync.core.rule_engine.engine import RuleDef

    with pytest.raises(ValidationError):
        RuleDef.model_validate(_rule(verified=True))


def test_internal_policy_rule_cannot_claim_verification():
    import pytest
    from pydantic import ValidationError

    from worksync.core.rule_engine.engine import RuleDef

    with pytest.raises(ValidationError):
        RuleDef.model_validate(_rule(basis="internal_policy", verified=True,
                                     reference_url="https://x", verified_on="2026-10-06"))


def test_flag_carries_the_rules_basis():
    from worksync.core.rule_engine.engine import RuleSet, evaluate_ruleset

    rs = RuleSet.model_validate({"version": "1", "vertical": "t",
                                 "rules": [_rule(basis="internal_policy")]})
    flags = evaluate_ruleset(rs, {"x": 1})
    assert flags[0].basis == "internal_policy"
