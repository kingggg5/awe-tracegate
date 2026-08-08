# Roadmap

AWE is developed in evidence-sized increments. Dates are intentionally omitted;
each milestone ships only after its acceptance criteria are demonstrated.

## v0.1 — Reviewable candidate

- Strict, versioned trace and workflow contracts.
- Evidence-gated compilation of repeated read-only traces.
- Canonical, reproducible candidate receipts.
- Explicit refusal for write, high-impact, and ambiguous effects.
- Offline fixture, CLI, HTTP API, and golden/property-oriented tests.

Exit criteria: the same supported input produces a byte-identical receipt on
Windows and Linux, and every seeded unsupported effect is rejected.

## v0.2 — Evaluation and promotion

- Frozen evaluation suites with baseline and candidate trials.
- Hard safety gates followed by quality non-regression checks.
- Append-only PostgreSQL run ledger and idempotent worker/outbox processing.
- Actor-bound human approval and promotion receipts.

Exit criteria: no candidate can be promoted without linked evidence, policy,
evaluation, and actor identity.

## v0.3 — Verifiable integration

- Import adapters for two independent trace/evaluation formats.
- in-toto-compatible attestations and signature verification.
- GitHub Action that publishes a commit-bound review without an LLM key.
- OpenTelemetry correlation with sensitive-data redaction.

Exit criteria: adapters produce the same canonical contract and tampered or
commit-mismatched evidence can never pass.

## Later, only with adoption evidence

- Integrations with existing durable runtimes such as LangGraph or Temporal.
- A small candidate/evaluation review UI.
- Carefully sandboxed execution for explicitly approved effect classes.

AWE will not build a general workflow runtime, autonomous browser agent,
deployment/rollback controller, adaptive model router, or vector-memory system
without a demonstrated use case and a separately reviewed threat model.
