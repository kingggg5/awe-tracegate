# Roadmap

TraceGate grows at evidence boundaries, not by becoming another agent runtime.
An item is implemented only when its contract, negative cases, and reproducible
tests exist.

## v0.3.0 — Portable Agent Skill evidence gate

Implemented in source:

- one atomic `awe gate` receipt over compilation, exact replay, frozen
  evaluation, policy, and candidate linkage;
- optional Skill BOM binding for the exact Agent Skill file tree;
- provider-neutral evidence envelopes and packages with repository, commit,
  producer, environment, capture time, provenance, and freshness checks;
- deterministic adapter conformance receipts and stable JSON Schema exports;
- machine-readable capabilities and version output;
- five focused Agent Skills with explicit evidence-touching invocation and 25
  routing/effect evaluation cases;
- zero-dependency npm and Python Skill installers with managed hashes, dry-run,
  check, atomic update, and refusal to overwrite unmanaged content;
- Git-backed Codex and Claude Code marketplace metadata with deterministic
  host-adapter parity checks;
- a GitHub Action that cannot PASS without the complete linked gate chain;
- reproducible plugin/npm bundle tooling, checksums, and an SPDX release SBOM;
- existing governed redaction, consent, signing, human decisions, API,
  TypeScript client, container, and optional local review UI.

Release gates that require maintainer or external state:

- merge and review the release commit;
- publish immutable GitHub, npm, and Python artifacts from a protected tag;
- attest the released artifacts and gate predicate in the privileged tag-release
  workflow;
- smoke-test installation from the immutable tag and registry packages;
- complete one independent external-adopter pilot with a first valid receipt in
  ten minutes or less.

Until these gates are complete, documentation must describe v0.3.0 as source or
pre-release functionality rather than a published stable release.

## P1 — Ecosystem interoperability

Priorities after the v0.3.0 release:

1. Prove two independent exporters produce the same canonical evidence contract.
2. Add demand-driven mappings for Promptfoo first, followed by Langfuse,
   Braintrust, or OpenAI Evals; adapters stay outside the verifier.
3. Publish compatibility results across Codex and at least one other Agent
   Skills host, including positive, negative, near-miss, and follow-up triggers.
4. Contribute the experimental Skill lifecycle vocabulary upstream to the
   OpenTelemetry GenAI discussion instead of claiming it as a TraceGate standard.
5. Add a portable read-only receipt viewer only after CLI/Action adoption proves
   that another UI materially reduces review time.

Exit criteria:

- byte-identical receipts for identical inputs on supported operating systems;
- every seeded digest, revision, freshness, dataset, and candidate mismatch
  fails closed;
- no false PASS in the adversarial corpus;
- two non-maintainer integrations complete the conformance suite.

## P2 — Durable shared review

Only after local/CI demand is demonstrated:

- append-only PostgreSQL receipt and decision ledger;
- authenticated actor identity and revocable decision policy;
- tenant isolation, request limits, audit logging, and retention controls for a
  shared network deployment;
- transactional outbox for idempotent review notifications;
- consented, redacted benchmark fixtures with frozen splits and adjudication.

These capabilities require a separate production threat model. The current
loopback API and asserted reviewer identifier are not substitutes.

## Explicit non-goals

- agent, browser, shell, email, deployment, or rollback execution;
- automatic promotion or self-modifying Discovery Loops;
- a built-in LLM grader, model router, memory service, or prompt compressor;
- another eval runner, trace store, dashboard, Skill registry, or package manager;
- vendor SDKs, model credentials, or dynamic adapter code in the trusted core;
- claims that `PASS` means safe, compliant, certified, or causally correct.

External runtimes may generate evidence. TraceGate verifies the supplied chain
and records a separate human decision; it never grants itself permission to act.
