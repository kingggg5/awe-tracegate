# Changelog

All notable changes will be documented in this file. The project follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and intends to use
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) after the first
stable contract release.

## [Unreleased]

### Added

- A local Review Workspace that drives the real compile, exact replay, frozen
  evaluation, and human-decision API path, with local evidence-file loading.
- A content-addressed experiment manifest with frozen split, harness, strategy,
  model, environment, grader, token, cost, latency, trace, and commit evidence.
- Provider-neutral JSON and revision-pinned OpenTelemetry GenAI OTLP importers.
- Optional Ed25519 receipt bundles verified against explicit key, identity,
  repository, and commit expectations.
- Consent-, scope-, expiry-, and revocation-gated redaction policies.
- A generated TypeScript API client with OpenAPI drift and dependency-audit CI.
- A current desktop capture of the complete Review Workspace evidence chain.
- Explicit resource bounds for untrusted OTLP attributes, spans, and nested
  redaction input.
- A command-led app shell with deterministic review commands, a truthful tools
  inventory, responsive navigation, and `awe serve` loopback startup.
- A digest-only `pallets/itsdangerous` compatibility pilot at an exact commit,
  including 297 passing upstream tests and replayable TraceGate receipts.
- A public external-pilot issue form with explicit privacy and claim boundaries.

### Changed

- Indexed dependency observations in one pass, removing repeated cross-trace
  scans for large candidates while preserving canonical receipts.
- Cached the packaged Review Workspace document per process and sourced the
  OpenAPI version from the package version.
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
