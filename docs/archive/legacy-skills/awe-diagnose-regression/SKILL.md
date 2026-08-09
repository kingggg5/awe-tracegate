---
name: awe-diagnose-regression
description: Diagnose a measurable regression between baseline and candidate agent, prompt, skill, workflow, model, or tool behavior using existing traces and frozen evaluation results. Use when success, safety, reliability, latency, or cost became worse and the changed factor is unclear. Do not use for general debugging without a baseline or to change production automatically.
---

# AWE Regression Diagnosis

Find the smallest evidence-supported explanation before proposing a fix.

## Workflow

1. Bind baseline and candidate to immutable revisions and list every changed variable.
2. Confirm comparability: same cases, runner conditions, limits, metrics, and trial policy.
3. Run or inspect `awe evaluate` for the supplied frozen artifacts. Preserve its receipt and exit code.
4. Segment failures by case, stage, tool, error class, latency, token, and cost bands where available.
5. Compare the earliest divergent observable step. Use [the regression contract](references/regression-contract.md) to separate input drift, runner drift, model variance, tool failure, policy refusal, context loss, and grader drift.
6. Rank hypotheses with supporting and counter-evidence, then propose one discriminating test that changes one variable.
7. Use `$awe-discovery-loop` only when the user wants to evaluate the proposed improvement.

## Return

- **Regression definition and observed delta**
- **Comparability check**
- **Failure clusters and artifact references**
- **Ranked hypotheses with counter-evidence**
- **One discriminating test**
- **Limitations and confounders**

## Boundaries

- Analyze by default; do not edit the candidate unless separately requested.
- Never rerun live production actions as an experiment.
- Never discard failed, timed-out, or refused trials.
- Never issue a promotion decision.
