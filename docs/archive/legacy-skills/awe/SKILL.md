---
name: awe
description: Route agent and workflow work to the smallest governed AWE TraceGate workflow. Use when the user asks how to use AWE, which AWE skill applies, or wants to set up, improve, review, or diagnose an agent, prompt, skill, workflow, or tool sequence. Do not use for ordinary coding or research that does not need an evidence gate.
---

# AWE Router

Choose one focused workflow. Do not treat this router or any agent prose as evidence.

## Route

1. Use `$awe-setup` when TraceGate installation, repository state, or evidence capability is unknown.
2. Use `$awe-discovery-loop` when comparing one measurable candidate change with a declared baseline.
3. Use `$awe-review-evidence` when traces or receipts already exist and must be compiled, replayed, evaluated, or checked for provenance.
4. Use `$awe-diagnose-regression` when a prompt, skill, model, tool, or workflow became worse and the cause is unknown.
5. Use ordinary project tools when no evidence-gated workflow is needed.

## Return

- **Selected workflow:** one skill and why it fits.
- **Known inputs:** revisions and artifacts already available.
- **Missing inputs:** only what the selected workflow requires.
- **Next action:** an exact `$skill-name` invocation or one read-only check.

## Boundaries

- Never invent evidence, approve promotion, execute a candidate, or mutate production.
- Never weaken a TraceGate refusal, invalid receipt, review, or block.
- Keep model trials outside TraceGate; the verifier remains offline and keyless.
