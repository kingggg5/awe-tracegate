# Product

<!-- impeccable:product-schema 1 -->

## Platform

Codex Skill/Plugin suite, CLI, GitHub Action, typed API, and optional local web
review surface.

## Users

Agent, evaluation, and platform engineers reviewing whether repeated agent
behavior is reliable enough to become a reusable workflow candidate. They need
to inspect decisions and evidence without trusting model-authored summaries.

## Product Purpose

AWE TraceGate turns typed, repeated read-only execution traces into a candidate
that can be independently replayed, evaluated against frozen trials, and
recorded with a human promotion decision. Success means an operator can follow
the complete evidence chain and reproduce every deterministic decision without
an LLM credential.

## Positioning

TraceGate is an evidence and governance boundary, not an agent runtime. Its
distinctive mechanism is a fail-closed chain from explicit trace bindings to
content-addressed compilation, exact replay, frozen evaluation, and a
human-recorded promotion receipt.

## Operating Context

The product is used locally, in CI, or behind a private typed API. Its inputs
are JSONL execution traces and JSON evaluation artifacts. Its outputs are
versioned candidates and receipts intended for review, storage, and independent
replay. All included demonstration evidence is synthetic and visibly labeled.

## Capabilities and Constraints

- Public decisions are compiled/refused, valid/invalid, and pass/review/block.
- Compilation and verification are deterministic, offline, and keyless.
- Only explicit, consistent bindings across repeated pure/read traces may prove
  dependencies.
- Trace content is untrusted data and is never executed.
- TraceGate does not plan work, run agents, invoke tools, promote candidates
  automatically, or authorize production actions.
- AWE Skills orchestrate setup, Discovery, evidence review, and diagnosis but
  remain outside the evidence boundary. Skill text cannot issue a decision.
- TraceGate Review uses explicit buttons and forms and is optional; it is not an
  agent chat or goal composer.
- Promotion records an asserted reviewer identifier and reviewed evidence
  chain; it is not an identity-provider-backed authorization.

## Brand Commitments

The product name is AWE TraceGate. Its voice is precise, calm, and explicit
about uncertainty. Evidence is shown before claims, and unsupported behavior is
described as refused rather than inferred.

## Evidence on Hand

- A synthetic repository-analysis trace set and frozen evaluation fixtures in
  `examples/`.
- A maintainer-run public `pallets/itsdangerous` compatibility pilot at an exact
  commit, with upstream test results and replayable digest-only evidence.
- Golden canonical receipts and adversarial tests in `tests/`.
- TraceGate Review with explicit evidence controls, plus the released CLI,
  FastAPI surface, Docker image, and GitHub Action at v0.2.0.
- A repository-local Codex plugin and five focused Skills with explicit
  invocation policy and deterministic installer tests.
- No customer, production benchmark, or real-corpus claim is available and none
  may be fabricated.

## Product Principles

- Repeated success is evidence, not permission.
- Unknown or unsupported evidence fails closed.
- One typed core owns decision semantics across every interface.
- Discovery may propose; deterministic evidence and humans govern reuse.
- Product claims never exceed reproducible artifacts.

## Accessibility & Inclusion

The web review surface must support keyboard operation, visible focus, semantic
status text in addition to color, reduced motion, and responsive layouts from
small mobile screens through desktop.
