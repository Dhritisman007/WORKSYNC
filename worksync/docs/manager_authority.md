# Manager Agent — authority model

Status: **default proposal, not yet confirmed with mentor** (Dr. Azra Nazir).
Do not treat this as settled until that sign-off happens — see Phase 1
checkpoint.

## Model: bounded authority

The Manager Agent may only auto-decide clear-cut cases. Everything else goes
to a human reviewer. Concretely, for a given case:

1. **Auto-approve** only if:
   - the risk probability falls in the vertical's configured "clearly good"
     band (outside the grey zone), **and**
   - the model's confidence band for that case is "high", **and**
   - the Compliance Agent raised no `hard` severity flag.
2. **Auto-reject** only if:
   - the risk probability falls in the vertical's configured "clearly bad"
     band (outside the grey zone), **and**
   - the model's confidence band for that case is "high", **and**
   - no `hard` flag *requires* escalation instead of reject (see below).
3. **Hard compliance flags always win.** Any triggered flag with
   `severity: hard` forces the outcome dictated by that rule's own `action`
   field (`reject` or `escalate`) — it overrides whatever the score alone
   would suggest. A hard flag never gets auto-approved through.
4. **Everything else escalates to a human reviewer.** This includes:
   - scores inside the grey band,
   - low/medium confidence, regardless of score,
   - any case with a `soft` flag but no `hard` flag, if the vertical config
     says soft flags should escalate rather than just annotate (config
     decides this per vertical).

## Why bounded authority (not full autonomy)

- It is the easiest position to defend in a regulated BFSI setting: the
  system only ever fully automates decisions the rules and the model agree
  are unambiguous, and a human stays in the loop for everything else.
- It keeps the Manager Agent's logic identical across verticals — "bounded
  authority" itself never changes; only the thresholds and which soft flags
  escalate are config, not code. This is required by the project's core
  structural-parity claim.
- It gives the Audit Agent a clean signal: every escalation is either "score
  ambiguity" or "named hard flag," both machine-readable reason codes.

## What is configurable per vertical (`manager_config.yaml`)

- The grey-band boundaries (probability thresholds for "clearly good" /
  "clearly bad").
- What counts as "high" confidence for that vertical's model.
- Whether a `soft` flag on its own forces escalation, or only gets recorded
  as a reason code alongside an otherwise-automatic decision.
- The default outcome (`reject` vs `escalate`) for each individual hard rule
  — set on the rule itself in `rules.yaml`, not in the Manager.

## What is NOT configurable (fixed in `core/agents/manager.py`)

- The four-step precedence above: hard flags > confidence gate > score band
  > default escalate.
- That a hard flag can never be auto-approved through, regardless of config.
- That the Manager never inspects vertical-specific feature fields directly
  — it only ever reads `RiskOutput` and `ComplianceFlags`, both of which are
  vertical-agnostic contracts.

## Open item

**Action for the team:** confirm this default with Dr. Azra Nazir before
Phase 2 starts. If she asks for a different authority model (e.g. narrower
or broader auto-decision bounds), this document and
`core/agents/manager.py`'s threshold-evaluation logic are the only two
places that should need to change — the Envelope/Decision contracts should
not.
