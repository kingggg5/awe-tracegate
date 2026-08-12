# Changelog

All notable changes will be documented in this file. The project follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and intends to use
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) after the first
stable contract release.

## [Unreleased]

### Documentation

- Locked the product direction to reproducible evidence infrastructure for
  agent experiments, with TraceGate as the trusted evidence-integrity and
  decision core.
- Documented competitor overlap honestly: established platforms already cover
  tracing, experiments, comparisons, and CI; AWE focuses on evidence linkage,
  deterministic re-checking, and the reliability of the resulting conclusion.
- Clarified that current exact-input replay re-runs the offline gate from source
  artifacts; it does not reconstruct live model/tool calls or establish
  causality. Documented comparison v1 as a bounded estimate under declared
  frozen conditions, separate from gate v1.
- Replaced the broad ecosystem roadmap with a scoped P0–P3 sequence covering
  release proof, conclusion reliability, failure evidence/interoperability, and
  one public reproducible experiment.
- Added a copy-ready GitHub Marketplace Action example for release tag `3`,
  its exact full-SHA production pin, and clearer Agent Workflow Experimentation
  positioning without claiming that the trusted verifier runs experiments.
- Expanded the plugin guide with cross-host benefits, token and credential
  boundaries, five copy-ready developer workflows, and their auditable outputs.

### Added

- `awe-discovery` as an external, non-executing adapter for consented Codex,
  Claude Code, and generic JSONL traces. It emits redacted exact-revision trace
  receipts and PostgreSQL/Alembic Discovery bundles with forward, rollback,
  data-preservation, test, typed terminal-outcome, and deterministic failure
  evidence.
- Added a disposable PostgreSQL/Alembic runner reference implementation and a
  PostgreSQL 16 CI job. It runs forward, preservation, rollback, and test lanes
  against a fresh schema, then removes the schema before returning evidence.
- Added consent-bound Discovery intervention proposals, independent human
  approval, and external replay handoffs; no runner or migration is executed by
  the trusted core.
- Added an Ed25519 evidence-package verification bridge. A gate may require
  `signature_verified` only when the signature target matches the exact package
  digest, repository, and commit.
- Recorded the PR #14 implementation checkpoint as `0149a50`; immutable
  release-tag publication and an independent external pilot remain open
  release criteria.
- AWE Workspace handoff v2 with separate opt-in `capture_trace` and
  `evaluate_migration` consent, asserted reviewer identity, local revocation,
  and explicit non-retroactive deletion warnings.

- `awe status` and `awe.workspace-status.v1` as a read-only day-two view over
  managed recipe integrity, missing real inputs, canonical Gate v2 replay,
  decision identity, and one bounded next action.
- Fail-closed recipe-definition validation before managed paths are resolved,
  including an adversarial rehashed `../` path regression test.
- `awe recipes` and `awe.decision-recipe-catalog.v1` as a small,
  machine-readable front door for CI gating, controlled comparison, harness
  import, promotion review, and governed sharing.
- `awe init` and `awe.recipe-scaffold-manifest.v1` for refusal-safe,
  policy-only evidence workspaces. The scaffold records raw file hashes and
  never generates traces, results, consent, signatures, receipts, or decisions.
- An original evidence-loop diagram and a shorter decision-first README path,
  informed by successful open-source onboarding patterns while keeping runtime
  coordination outside the trusted TraceGate core.
- A private TypeScript package at `apps/workspace` for local goals, discovery
  briefs, exact permission approval, typed Codex/Claude/external handoffs, and
  checkpoints. It has a separate process and CI job and cannot execute tools or
  issue evidence decisions.
- `awe demo` as a zero-network, zero-model front door for the complete
  synthetic Gate v2 chain, plus `awe doctor` and
  `awe.review-bundle-report.v1` for replaying the standard held-input bundle
  layout without trusting its precomputed decision.
- A compact decision-recipe guide that maps common agent-change questions to
  the minimum valid inputs, commands, outputs, and fail-closed boundaries.
- An opt-in `awe.gate-receipt.v2` that composes the unchanged v1 gate with a
  supplied `ComparisonReceipt`, deterministic held-input replay, manifest-to-
  evaluation projection checks, and optional typed quality sidecars.
- `awe verify-comparison`, `awe assess-quality`, `awe sensitivity`, and
  `awe explain` CLI surfaces. They respectively emit typed held-input replay,
  terminal/judge quality, supplied environment/seed range, and deterministic
  evidence-graph receipts without executing a model, grader, trace, or tool.
- Versioned sidecars for terminal outcomes (`timeout`, `refusal`,
  `infrastructure_error`, and `missing` are no longer collapsed into a boolean),
  asserted judge votes/human calibration, and bounded sensitivity results.
- Optional GitHub Action Gate v2 inputs; the existing v1 Action route and its
  `awe.gate-receipt.v1` behavior remain available unchanged.
- An additive `awe compare` path over full experiment manifests with declared
  treatment factors, exact confound controls, case-and-seed pairing, an exact
  two-sided sign test, a fixed 95% paired-case normal-approximation interval,
  sample/flakiness evidence, p95-latency and total-cost review thresholds, and a
  content-addressed comparison receipt. Exact-input comparison replay, a 10,000
  paired-case cap, fixed local numeric context, and exact integer efficiency
  threshold comparisons keep verification bounded and deterministic.
- A zero-side-effect `awe-tracegate --version` command; archive and Git-install
  CI/release smoke tests now assert the packaged version before copying Skills.
- Added a real-CLI v1 gate compatibility fixture, Draft 2020-12 consumer-schema
  validation, exhaustive nested-tamper coverage, and exact-input receipt replay
  across trace, candidate, baseline, policy, identity, and freshness boundaries.
- Added consumer-owned package replay expectations so a rehashed receipt cannot
  weaken protected repository, commit, freshness, or provenance policy.
- An atomic `awe gate` contract that requires compilation, exact-input gate replay,
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
- A local TraceGate Review UI that drives the real compile, exact-input replay, frozen
  evaluation, and human-decision API path, with local evidence-file loading.
- A content-addressed experiment manifest with frozen split, harness, strategy,
  model, environment, grader, token, cost, latency, trace, and commit evidence.
- Provider-neutral JSON and revision-pinned OpenTelemetry GenAI OTLP importers.
- A typed local API endpoint for the same OTLP importer, with `422` fail-closed
  responses for malformed or unannotated spans.
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

- Hardened the SemVer release workflow with cross-manifest version checks,
  reproducible Python/npm/plugin/schema builds, clean package install smoke
  tests, basename-only checksums, an SPDX SBOM, and artifact attestations while
  leaving the existing Action tag `3` untouched.
- Required the exact tagged source to pass the complete reusable, read-only CI
  workflow before granting the release job write or OIDC permissions.
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
  human-decision form. External agent hosts own goal/command composition.
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
