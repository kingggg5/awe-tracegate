# Roadmap

TraceGate is developed in evidence-sized increments. Features move from this
roadmap only when their acceptance criteria are covered by reproducible tests.

## v0.1 — Release candidate

Implemented:

- Strict, versioned trace, candidate, receipt, evaluation, and promotion models.
- Fail-closed compilation of repeated read-only traces.
- Offline receipt verification with optional exact-trace replay.
- Frozen baseline/candidate evaluation with safety and non-regression policy.
- Actor- and commit-bound human promotion records.
- Conservative secret, PII, and customer-field redaction.
- JSON Schema export, CLI, typed API, Docker image, and composite GitHub Action.
- Cross-platform golden receipt, adversarial tests, CodeQL, dependency review,
  release artifacts, and GitHub/Sigstore build provenance.

Release criteria:

- byte-identical golden receipt on Windows and Linux;
- no seeded tamper, dataset mismatch, unsafe effect, or safety violation passes;
- clean install, package build, container health, and Action smoke test;
- public security boundaries and synthetic-data labels remain accurate.

## v0.2 — Stronger evidence chain

Implemented for the next release:

- Content-addressed verification receipts, including exact-trace replay state.
- Replay-gated promotion that recomputes verification and rejects mismatched
  compilation, evidence, candidate, or evaluation artifacts.
- Promotion receipts binding the compilation/input bundle, verification,
  evaluation, dataset, policy, actor, and commit.
- Typed promotion API and a GitHub Action that replays the compilation receipt
  before it can report `PASS`.

## v0.3 — External evidence interoperability

- Two independent import adapters, beginning with generic evaluation JSON and a
  version-pinned OpenTelemetry GenAI mapping.
- Signed receipt bundles that verify subject, signer identity, repository, and
  commit—not only content digests.
- Pluggable redaction policies with allow/deny reports and corpus consent IDs.
- One real external pilot and usability measurements for time-to-first receipt.

Exit criteria: two exporters produce the same canonical contract; tampered or
commit-mismatched evidence never passes; a new adopter reaches a verified
receipt in ten minutes or less.

## v0.4 — Durable review history

- Append-only PostgreSQL receipt and decision ledger.
- Transactional outbox with idempotent delivery for review notifications.
- Authenticated actor identity and revocable promotion policy.
- A small read-only review UI after CLI/Action demand is demonstrated.

Exit criteria: every accepted decision has immutable evidence, policy, actor,
and delivery provenance, tested under a non-owner database role.

## Explicitly deferred

- General agent runtime, planner, or scheduler.
- Browser, shell, deployment, rollback, or autonomous write execution.
- Heuristic branching inferred from sparse traces.
- Adaptive model routing, vector memory, or self-modification.

Existing runtimes already own execution and recovery. TraceGate will integrate
at evidence boundaries instead of expanding its trusted surface without user
demand and a separately reviewed threat model.
