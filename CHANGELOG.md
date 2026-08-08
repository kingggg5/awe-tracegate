# Changelog

All notable changes will be documented in this file. The project follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and intends to use
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) after the first
stable contract release.

## [Unreleased]

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
