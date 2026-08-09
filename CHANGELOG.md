# Changelog

All notable changes will be documented in this file. The project follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and intends to use
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) after the first
stable contract release.

## [Unreleased]

### Documentation

- Added a copy-ready GitHub Marketplace Action example for release tag `3`,
  its exact full-SHA production pin, and clearer Agent Workflow Experimentation
  positioning without claiming that the trusted verifier runs experiments.
- Expanded the plugin guide with cross-host benefits, token and credential
  boundaries, five copy-ready developer workflows, and their auditable outputs.

### Added

- An atomic `awe gate` contract that requires compilation, exact trace replay,
  frozen evaluation, policy, and identical candidate linkage before PASS.
- Evidence Envelope/Package v1 contracts with repository, commit, producer,
  environment, capture time, provenance, freshness, and conformance checks.
- A non-executing Agent Skill BOM that can be bound directly into a gate receipt.
- Five job-oriented Agent Skills for readiness, comparison, evidence verification,
  adapter integration, and controlled evidence sharing, plus 25 routing/effect
  eval cases.
- Publishable zero-dependency npm and Python installers with managed file hashes,
  dry-run/check modes, atomic updates, and refusal to overwrite unmanaged or
  locally modified content.
- Git-backed Codex marketplace metadata and machine-readable capabilities.
- A Claude Code marketplace and deterministic, namespaced Skill adapter that
  preserves explicit invocation for all evidence-changing workflows.
- Deterministic plugin/npm release bundles, SPDX SBOM generation, checksums, and
  a typed gate-attestation predicate builder.
- A local TraceGate Review UI that drives the real compile, exact replay, frozen
  evaluation, and human-decision API path, with local evidence-file loading.
- A content-addressed experiment manifest with frozen split, harness, strategy,
  model, environment, grader, token, cost, latency, trace, and commit evidence.
- Provider-neutral JSON and revision-pinned OpenTelemetry GenAI OTLP importers.
- Optional Ed25519 receipt bundles verified against explicit key, identity,
  repository, and commit expectations.
- Consent-, scope-, expiry-, and revocation-gated redaction policies.
- A generated TypeScript API client with OpenAPI drift and dependency-audit CI.
- A current desktop capture of the complete TraceGate Review evidence chain.
- Explicit resource bounds for untrusted OTLP attributes, spans, and nested
  redaction input.
- An app shell with explicit evidence buttons and forms, a truthful tools
  inventory, responsive navigation, and `awe serve` loopback startup.
- A digest-only `pallets/itsdangerous` compatibility pilot at an exact commit,
  including 297 passing upstream tests and replayable TraceGate receipts.
- A public external-pilot issue form with explicit privacy and claim boundaries.

### Changed

- Reserved CLI exit code 2 for typed REVIEW/BLOCK receipts; malformed command
  usage now exits 1. Non-asserted provenance labels are recorded but cannot
  satisfy a gate minimum until a trusted external verifier exists.
- Reframed the README around explicit Skill invocation and the CLI-first evidence
  engine, with TraceGate Review documented as an optional surface.
- Replaced independent Action compile/verify/evaluate reporting with the atomic
  gate receipt so integrity-only or unrelated evaluation evidence cannot PASS.
- Removed the broad `$awe` router and four overlapping legacy workflows in favor
  of a smaller namespaced Skill inventory.
- Indexed dependency observations in one pass, removing repeated cross-trace
  scans for large candidates while preserving canonical receipts.
- Cached the packaged TraceGate Review document per process and sourced the
  OpenAPI version from the package version.
- Removed the fixed command dock after browser QA found it could cover the
  human-decision form. The separate AWE Workspace owns the goal/command
  composer.
- Reframed the discovery-loop direction as a separate permissioned runtime that
  exports evidence to TraceGate instead of expanding the verifier's authority.

## [0.2.0] - 2026-08-09

### Added

- Replay-gated promotion receipts that bind compilation, exact trace replay,
  evaluation, dataset, policy, actor, and commit provenance.
- Content-addressed verification receipts plus typed `/v1/promote` API support.
- GitHub Action replay verification before a `PASS` decision.

### Changed

- Versioned verification and promotion schemas to v2; v0.1 schema consumers
  should remain pinned to the v0.1.0 release.

## [0.1.0] - 2026-08-08

### Added

- AWE TraceGate naming and collision-resistant repository/package identity.
- Offline compilation receipt verification with exact-trace replay.
- Frozen baseline/candidate evaluation and fail-closed policy receipts.
- Actor- and commit-bound human promotion receipts.
- Conservative JSON evidence redaction and redaction summaries.
- Versioned JSON Schema export and typed verify/evaluate API endpoints.
- Composite GitHub Action plus signed release-artifact provenance workflow.
- Cross-platform golden receipt and expanded adversarial tests.
- Real-output demo artwork and release-oriented usage documentation.
