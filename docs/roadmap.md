# Roadmap

**North star:** AWE is reproducible evidence infrastructure for agent
experiments. It should help a reviewer decide whether an agent change improved
and whether the evidence supports that conclusion. TraceGate remains the small,
offline trusted core.

The roadmap is deliberately narrower than an agent framework or observability
suite. An item is implemented only when its versioned contract, adversarial
cases, and reproducible tests exist. Research-shaped ideas stay marked as
planned until those semantics land.

## Current foundation — implemented in source

The pre-alpha source currently provides:

- one atomic `awe gate` receipt over trace compilation, exact-input gate replay,
  frozen baseline/candidate outcomes, policy, and candidate linkage;
- an additive full-manifest `awe compare` receipt with exact declared controls,
  case-and-seed pairing, an exact sign test, a fixed 95% paired-case
  normal-approximation interval, sample/flakiness checks, p95 latency and
  total-cost review thresholds, exact-input replay, a 10,000-case bound, and
  deterministic fixed-context arithmetic;
- opt-in `awe gate-v2`, which preserves `awe.gate-receipt.v1` while composing it
  with a supplied `ComparisonReceipt` replayed from held manifests and exact
  evaluator-projection linkage;
- `awe verify-comparison` for a typed held-input replay result, plus quality
  sidecars that preserve timeout, refusal, infrastructure failure, missing,
  and ordinary failure outcomes rather than collapsing them into a boolean;
- deterministic asserted judge coverage/disagreement/human-calibration checks,
  bounded supplied-environment/seed sensitivity receipts, and `awe explain`
  graphs with explicit evidence limitations;
- optional Skill BOM and evidence-package binding for repository, commit,
  producer, environment, capture time, provenance, and freshness;
- provider-neutral evidence envelopes, stable schema exports, generic JSON and
  revision-pinned OpenTelemetry GenAI importers;
- five focused Agent Skills, zero-dependency npm/Python installers, and Codex and
  Claude Code marketplace metadata;
- a GitHub Action that cannot report `PASS` without the complete linked gate
  chain;
- a one-command synthetic Gate v2 demo plus a fail-closed review-bundle doctor
  with a versioned machine-readable report;
- a content-addressed decision-recipe catalog and refusal-safe `awe init`
  scaffold that creates policies and guidance without generating evidence;
- a read-only `awe status` day-two view over recipe integrity and canonical Gate
  v2 replay, with explicit `READY`, `ACTION_REQUIRED`, and `INVALID` states;
- governed redaction, consent records, signing, separate human-decision
  receipts, a loopback API, generated TypeScript types, and a local review UI;
- reproducible release-bundle tooling, checksums, an SPDX SBOM, clean-install
  smoke tests, and an unprivileged exact-tag CI prerequisite.
- a consented external Discovery adapter for Codex, Claude Code, and generic
  JSONL plus one PostgreSQL/Alembic reliability contract covering forward,
  rollback, data-preservation, and test evidence without executing a runner or
  database inside TraceGate.

This foundation re-verifies supplied artifacts and produces deterministic,
content-addressed decisions. Comparison v1 estimates evidence reliability only
under its declared frozen controls and statistical assumptions. It does not
reconstruct live agent calls, establish causality, or prove universal
improvement.

## P0 — Ship and prove the narrow gate

1. Publish immutable GitHub, npm, Python, Codex, and Claude artifacts from one
   protected SemVer tag; retain Action tag `3` only for compatibility.
2. Smoke-test every install path from released artifacts, not the working tree.
3. Complete an independent external-adopter pilot that produces and re-checks a
   valid receipt in ten minutes or less.
4. Add one canonical end-to-end agent-change fixture whose baseline, candidate,
   source traces, policy, repository revision, and expected receipt are public.
5. Exercise Gate v2 against released artifacts and one independent adopter,
   including its held-input comparison verifier and fail-closed quality sidecars.
6. Run the PostgreSQL/Alembic adapter against one consented external coding-agent
   pilot and publish redacted artifacts, harness/environment digests, negative
   cases, and an adjudicated result.

Exit criteria:

- identical supported inputs produce byte-identical receipts across supported
  operating systems;
- every seeded digest, revision, freshness, dataset, identity, and candidate
  mismatch fails closed;
- no false `PASS` in the adversarial corpus;
- one non-maintainer completes the released workflow successfully.

## P1 — Deepen conclusion reliability

- richer evaluator/judge calibration evidence such as per-grader reliability,
  blinded adjudication sampling, and confidence intervals without trusting a
  model's self-reported confidence;
- multi-seed and multi-environment sensitivity analysis with explicit resource
  budgets and repeated-run variance, beyond the current bounded range report;
- explicit resource-budget and runtime-variance evidence;
- dimension-level inference and regression policy for success, recovery, tool
  use, safety, latency, token use, and cost;
- declared missingness and censoring rules for incomplete trials;
- typed evidence graph linking external change, run, trace, evaluation,
  counter-evidence, policy result, and human decision beyond the current local
  receipt-dependency graph;
- authenticated actor provenance and an append-only decision ledger before any
  shared network deployment.

Exit criteria:

- AWE can distinguish an observed improvement from insufficient evidence using
  documented deterministic rules;
- unstable or disagreeing evaluations cannot silently produce `PASS`;
- every decision can cite the evidence and counter-evidence that affected it.

## P2 — Diagnose failures and interoperate

- extend the implemented migration/terminal taxonomy into a stable failure
  taxonomy covering planning, tool selection, tool arguments,
  retrieval, environment, verification, recovery, policy, timeout,
  infrastructure, and evaluator disagreement;
- deterministic failure grouping from declared features, with provenance for
  every group and no LLM-generated cause treated as fact;
- demand-driven adapters for established eval systems such as Promptfoo,
  Braintrust, LangSmith, or Phoenix, kept outside the trusted verifier;
- cross-adapter conformance showing that equivalent inputs normalize to the
  same contract;
- contamination, split-leakage, and fixture-lineage checks for published
  evaluation data;
- seed and environment sensitivity reports suitable for research review.

Counterfactual replay and causal attribution remain research work. They must not
be marketed as implemented until interventions, assumptions, uncertainty, and
failure cases are represented in a reviewed contract.

## P3 — A public experiment people can reproduce

Publish one focused comparison of a verified local/open model and one or two
hosted models using the same agent harness and frozen suite. The demo should
include every trial, failed run, experiment identity, evaluation policy,
TraceGate receipt, and a short explanation of what was and was not controlled.

The memorable result is not a model leaderboard. It is a defensible example
where an apparent aggregate gain is accepted, rejected, or sent to review
because reliability or a critical dimension tells a different story. Model
targets must come from verified model cards; AWE remains independent of any
single model release.

## Explicit non-goals

- agent, browser, shell, email, deployment, or rollback execution;
- automatic promotion or self-modifying Discovery Loops;
- a chatbot, Codex/Claude clone, generic agent builder, or drag-and-drop workflow
  product;
- a built-in LLM grader, model router, memory service, prompt compressor,
  training framework, or inference runtime;
- another trace store, broad observability dashboard, Skill registry, or package
  manager;
- vendor SDKs, model credentials, or dynamically loaded adapter code in the
  trusted core;
- claims that `PASS` means safe, compliant, certified, statistically proven, or
  causally correct.

External runtimes may generate evidence. TraceGate verifies the supplied chain
and records a separate human decision; it never grants itself permission to act.
