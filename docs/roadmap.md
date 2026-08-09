# Roadmap

TraceGate is developed in evidence-sized increments. Features move from this
roadmap only when their acceptance criteria are covered by reproducible tests.

## Current P0-P2 priorities

### P0 — Release truth and first-use path

Implemented on the current branch:

- TraceGate Review UI with explicit buttons and forms over the real
  deterministic API path;
- one-command loopback launch with `awe serve`;
- maintainer-run public-repository pilot with exact commit, upstream test result,
  content digests, compilation receipt, and exact replay verification;
- clean-install smoke measurement and current desktop/mobile browser QA.

External release gates that cannot be fabricated in code:

- one independent adopter completes a public pilot in under ten minutes;
- maintainers review, merge, tag v0.3.0, and smoke-test the immutable tag.

### P1 — Durable governance

- Append-only PostgreSQL receipt and decision ledger.
- Transactional outbox with idempotent review notifications.
- Authenticated actor identity, revocable promotion policy, tenancy, and rate
  limits for any networked deployment.
- Trusted publishing after the PyPI project and GitHub environment are owned and
  configured by maintainers.

### P2 — Discovery integration, not verifier expansion

- Keep AWE Workspace as a separate permissioned application and process
  boundary for the goal/command composer, task sessions, research/code/file
  tools, and future agent runtimes.
- Accept its typed traces and frozen evaluation outputs at the existing evidence
  boundary.
- Keep browser, shell, email, deployment, model routing, and automatic skill
  installation outside TraceGate and unable to override a gate decision.
- Revisit a signed Tauri desktop shell only after native integration demand is
  measured; `.exe` and `.dmg` distribution also requires platform signing,
  notarization, updater keys, and per-target sidecars.

## v0.1 — Release candidate

Implemented:

- Strict, versioned trace, candidate, receipt, evaluation, and promotion models.
- Fail-closed compilation of repeated read-only traces.
- Offline receipt verification with optional exact-trace replay.
- Frozen baseline/candidate evaluation with safety and non-regression policy.
- Human promotion records bound to an asserted reviewer identifier and commit
  SHA.
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

Implemented on the current release branch:

- Local TraceGate Review over the real evidence chain, with explicit review
  controls, sample labeling, local JSONL/JSON input support, tools inventory,
  and `awe serve`.
- Two independent import adapters: provider-neutral evaluation JSON and an OTLP
  JSON mapping pinned to OpenTelemetry GenAI revision
  `1d85c963ea51e9c7d24cc330ff67057f6e90e6c5`.
- A versioned experiment manifest binding the harness, model configuration,
  dataset split, trial set, strategy digest, token usage, latency, cost, and
  grader versions.
- Optional Ed25519 receipt bundles verified against an explicit trusted key,
  signer, repository, and commit—not an embedded key alone.
- Pluggable redaction policies with allow/deny reports plus consent scope,
  expiry, and fail-closed revocation checks.
- A generated TypeScript client whose types are checked against the committed
  OpenAPI document in CI.
- A maintainer-run `pallets/itsdangerous` compatibility pilot at an exact commit,
  including 297 passing upstream tests and exact TraceGate replay artifacts.

Still required before v0.3 release:

- One independent external adopter and measured time-to-first receipt.
- A reviewed v0.3 release tag and full Action smoke test from that immutable tag.

Exit criteria: two exporters produce the same canonical contract; tampered or
commit-mismatched evidence never passes; a new adopter reaches a verified
receipt in ten minutes or less.

## v0.4 — Durable review history

- Append-only PostgreSQL receipt and decision ledger.
- Transactional outbox with idempotent delivery for review notifications.
- Authenticated actor identity and revocable promotion policy.
- Durable read-only history in TraceGate Review after CLI/Action demand is
  demonstrated.

Exit criteria: every accepted decision has immutable evidence, policy, actor,
and delivery provenance, tested under a non-owner database role.

## Runtime and SDK strategy

The Python/Pydantic implementation remains the reference decision engine until
a replacement demonstrates byte-identical golden receipts and a measured
operational benefit. Rewriting a security boundary to follow language adoption
would add parity risk without improving the product contract.

- Keep the generated TypeScript SDK as an integration surface, not an alternate
  decision engine; all external JSON still requires server-side runtime
  validation.
- Consider a read-only .NET 10 Native AOT CLI spike only after v0.3. It must
  achieve 100% golden/property-test parity and report cold start, peak RSS,
  binary size, and p95 throughput against the Python reference before any
  migration decision.
- Keep discovery and prompt/context compression outside the trusted core.
  Headroom, LLMLingua, or a future AWE strategy may produce experiment
  evidence; TraceGate compares that evidence and governs promotion. Token
  savings alone can never produce `PASS`.

## Explicitly deferred

- General agent runtime, planner, or scheduler.
- Browser, shell, deployment, rollback, or autonomous write execution.
- Heuristic branching inferred from sparse traces.
- Adaptive model routing, vector memory, or self-modification.
- A built-in prompt compressor or provider proxy.

Existing runtimes already own execution and recovery. TraceGate will integrate
at evidence boundaries instead of expanding its trusted surface without user
demand and a separately reviewed threat model.
