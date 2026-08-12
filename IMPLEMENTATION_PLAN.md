# AWE TraceGate implementation plan

**Snapshot:** PR #14 current branch (implementation checkpoint `0149a50`)
**Updated:** 2026-08-12
**Positioning:** reproducible evidence infrastructure for agent experiments;
TraceGate is the offline decision core and external hosts remain responsible
for execution.

This is the source-of-truth plan for the current release candidate. A checked
box means the repository contains the contract, tests, and reproducible local
or CI verification. It does not turn a synthetic fixture into an external
adopter result.

## Completed in the repository

- [x] Atomic Gate v1 with exact trace replay and candidate linkage.
- [x] Gate v2 with held-input `ComparisonReceipt` verification and typed
  terminal outcomes.
- [x] Judge/human calibration, bounded seed/environment sensitivity, and
  deterministic `awe explain` evidence graphs.
- [x] Consent-bound Discovery adapter for Codex, Claude Code, and generic JSONL.
- [x] Discovery intervention -> independent approval -> expiring replay handoff.
- [x] Ed25519 evidence-package bridge for exact `signature_verified` targets.
- [x] PostgreSQL/Alembic runner reference implementation with disposable schema,
  forward/rollback/data-preservation/tests lanes, and PostgreSQL 16 CI.
- [x] Codex/Claude Skills, npm/Python installers, plugin metadata, reproducible
  artifact tooling, SBOM/checksums, and release workflow.
- [x] Full local verification: `184 passed, 1 skipped`; Ruff and mypy clean.
- [x] Hosted PR checks for commit `0149a50`: Windows, Ubuntu, Docker, SDK,
  npm/Git install, PostgreSQL harness, CodeQL, and dependency review passed.
- [x] Cross-platform canonical fixture comparison for Ubuntu, Windows, and
  macOS is enforced in CI.

## Remaining P0: external state, not missing core code

### 1. Independent pilot

Use the [external pilot runbook](docs/EXTERNAL_PILOT_RUNBOOK.md) with a
non-sensitive migration task. The pilot is complete only when:

1. Codex/Claude or another external host runs 3-5 cases with explicit trace and
   evaluation consent.
2. Each case has forward migration, rollback, data-preservation, and tests
   evidence, including timeout/refusal/infrastructure/missing outcomes.
3. The failure cluster -> intervention -> independent approval -> replay
   request -> candidate run -> comparison -> Gate v2 -> explain loop is
   completed once.
4. A person other than the producer replays the held artifacts from a clean
   checkout and obtains identical receipt hashes.
5. Only redacted, consented artifacts are published; raw prompts, commands,
   source, credentials, PII, and customer data stay private.

### 2. Immutable release

Follow [the release runbook](docs/RELEASE_RUNBOOK.md) after protected `main`
contains the changes:

1. Configure npm/PyPI trusted publishers and protected environments.
2. Create protected immutable tag `v0.3.0` from the tested `main` tip.
3. Let `release.yml` build and clean-install Python, npm, plugin, and schema
   artifacts; publish only after the exact-tag CI succeeds.
4. Verify the downloaded artifacts from a clean machine and record checksums.

The branch checkpoint is not a release tag. Do not claim registry availability
until the tag and publish jobs have completed.

## After the first pilot

- [ ] Add multiple repositories/task families and separate repeated technical
  runs from independent samples.
- [ ] Add explicit missingness, timeout, refusal, infrastructure, and censoring
  policy across the comparison and quality contracts.
- [ ] Add richer evaluator reliability and blinded adjudication evidence.
- [ ] Add demand-driven adapters for Promptfoo, Phoenix, LangSmith, or custom
  JSONL only after an adopter asks for them.
- [ ] Add authenticated actor provenance and an append-only decision ledger
  before offering a shared network service.

## Intentionally deferred

QLoRA, OwnLM, model routing, autonomous remediation, browser/shell execution,
deployment control, causal attribution, and unseen-task claims are separate
research/product tracks. They are not required to close AWE's evidence-gate
release and would weaken the current security boundary if added prematurely.
