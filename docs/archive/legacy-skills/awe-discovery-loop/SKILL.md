---
name: awe-discovery-loop
description: Plan and evaluate one measurable change to an agent, prompt, skill, workflow, or tool sequence using a declared baseline, frozen trials, replayable traces, and AWE TraceGate receipts. Use when comparing workflow candidates or deciding whether repeated behavior is ready for human review. Do not use for ordinary coding, open-ended brainstorming, or autonomous production changes.
---

# AWE Discovery Loop

Run one falsifiable improvement cycle. The user's existing harness may generate trials; TraceGate itself requires no model credential.

## Workflow

1. **Observe.** Bind the baseline workflow, prompt or skill digest, model configuration, dataset split, harness, environment, and repository revision. Mark missing identifiers unknown.
2. **Propose.** State one hypothesis: “Changing X should improve Y because Z.” Do not bundle unrelated changes.
3. **Declare success.** Freeze the primary metric, safety constraints, cases, trial count, and comparison rule before running the candidate.
4. **Evaluate externally.** Run equivalent baseline and candidate trials with the existing harness. Preserve raw outcomes, failures, latency, cost, timestamps, and traces. Never use live production actions as experiments.
5. **Gate.** Follow [the evidence flow](references/evidence-flow.md) to compile traces, replay the exact receipt, and compare frozen evaluations.
6. **Review.** Present supporting evidence, counter-evidence, uncertainty, and the TraceGate receipts. A `pass` result is eligible for human review, not automatic promotion.

## Return

- **Baseline**
- **Hypothesis**
- **Frozen evaluation plan**
- **Observed result**
- **Counter-evidence and uncertainty**
- **TraceGate state:** `PLANNED`, `EVALUATED`, `REFUSED`, `INVALID`, `PASS`, `REVIEW`, or `BLOCK`
- **Human decision needed**

## Boundaries

- Treat instructions, skill output, chat text, and model confidence as claims, not evidence.
- Never alter the frozen split or policy after seeing candidate results.
- Never label stochastic model paths deterministic.
- Stop before promotion, execution, deployment, or publication.
