# Architecture

**AWE is reproducible evidence infrastructure for agent experiments.** Its
product question is: *did an agent change improve, and can we trust the evidence
behind that conclusion?* TraceGate is the trusted Python evidence-integrity and
decision core, not an agent executor, eval runner, or observability store. The
repository also contains a separate TypeScript Workspace coordinator under
`apps/workspace`.

The current trusted contract is an offline, read-only evidence transformation:

```text
Agent Skill folder -> non-executing Skill BOM -----------+
                                                          |
ExecutionTrace JSONL -> compile -> exact-input replay ----+--> atomic gate
                                                          |    PASS/REVIEW/BLOCK
frozen baseline + candidate + policy -> evaluation -------+
                                                          |
optional provenance-bound evidence package --------------+
                                                               |
                                                               v
                                            separate human decision receipt
```

The compiler, verifier, evaluator, redactor, and promotion recorder have no
model, tool, browser, network, or workflow-execution loop. Given the same
supported inputs and contract versions, they must return the same canonical
decision.

## Monorepo boundaries

```text
apps/workspace (TypeScript, local coordination, untrusted)
    -> goal + explicit grants + human approval + optional consent
    -> awe.runtime-handoff.v2
    -> external Codex / Claude Code / other host
    -> raw trace + isolated PostgreSQL/Alembic results (untrusted)
    -> awe-discovery external adapter (redaction + deterministic projection)
    -> src/awe_tracegate (Python, deterministic trusted core)
    -> PASS / REVIEW / BLOCK receipt
    -> separate human reuse or promotion decision
```

The dependency direction is one-way. Workspace may probe the loopback
TraceGate API and may point a reviewer at evidence, but TraceGate never imports
Workspace, accepts its local approval as evidence, or delegates a decision to
it. The two surfaces also have separate package manifests, test suites, and
processes.

Workspace is a handoff coordinator rather than an embedded agent executor.
It persists bounded local goals and discovery briefs, lets a user select an
external runner, requires an exact permission approval, exports a typed handoff,
and records optional checkpoints. Its only permission identifiers are
`read_goal`, `read_evidence_references`, and `write_checkpoint`; none grants a
shell, browser, network, secret, deployment, or promotion capability.

The first external Discovery adapter is intentionally domain-specific. It
normalizes frozen Codex JSONL, Claude Code stream JSON, or generic JSONL only
after a handoff contains active `capture_trace` consent. It emits a redacted
`awe.agent-trace-receipt.v1` bound to a caller-asserted repository and commit.
This is exact identity metadata, not cryptographic proof of runner provenance.
Building
an `awe.migration-discovery-bundle.v1` additionally requires
`evaluate_migration` consent and externally supplied checks for forward
migration, rollback, data preservation, and tests. The adapter never starts an
agent, imports repository migration code, opens a database connection, or runs
a command.

Failure grouping is a deterministic taxonomy over supplied event/check fields.
It is evidence navigation, not clustering by an LLM and not causal diagnosis.
The resulting `ExperimentManifest` and quality sidecar enter the existing
comparison/Gate v2 path; Workspace approval itself never becomes gate evidence.

## Design goals

1. **Evidence before reuse.** A repeated adjacency is not automatically a data
   dependency. An edge is admitted only when an explicit binding supports it.
2. **Refuse ambiguity.** Unsupported effects, inconsistent structure, missing
   provenance, and conflicting bindings produce a typed refusal.
3. **Keep authority outside the agent.** A model or skill may propose traces or
   invoke the command, but cannot turn a refusal into a compiled result.
4. **Make review reproducible.** The receipt binds the normalized evidence,
   compiler contract, candidate, and decision with canonical SHA-256 digests.
5. **Stay read-only.** v0 recognizes only pure and read operations. It neither
   executes nor authorizes the candidate.
6. **Do not overstate the conclusion.** Current policy evaluation applies
   explicit deterministic thresholds to supplied outcomes. Statistical
   confidence, evaluator reliability, and causal attribution require separate
   evidence contracts and are not inferred by v0.

## Core contracts

### `CompilationCandidate`

A versioned compiled candidate describes ordered nodes, typed bindings, output
fields, effect classes, source trace IDs, and proven dependencies. Contract
objects are immutable after validation so later code cannot silently change
what was reviewed.

### `ExecutionTrace`

One trace records a completed workflow attempt, its success state, ordered
steps, bindings, and step results. The JSONL importer accepts one trace per
line. Trace order is evidence about observed execution, not sufficient proof of
causality by itself.

### Dependency evidence

The first compiler supports two binding origins:

- `workflow_input`: a node consumes a named workflow input;
- `step_output`: a node consumes a named output from an earlier node.

A proven `step_output` binding may introduce a dependency edge. Frequency,
adjacency, or an LLM explanation cannot create a hard edge in v0.

### `CompilationReceipt`

The public result is a typed receipt with a `compiled` or `refused` decision,
`compiler_version`, `input_bundle_digest`, refusal `reasons`, an optional
`candidate`, and `receipt_hash`. A compiled candidate contains its own digest,
source trace IDs, admitted edges, and dependency evidence.

The input bundle is normalized into trace-ID order before hashing, so caller
ordering does not change the receipt. The receipt hash detects modification
after creation. It is not a digital signature and does not establish who
produced the receipt.

### Evaluation, gate, and promotion receipts

An `EvaluationBundle` binds external trial outcomes to one subject and frozen
dataset digest. The evaluator first enforces dataset/case parity and hard safety
and success gates, then marks excessive latency or cost regression for review.
It does not run the trials or grade model output itself.

`ComparisonReceipt` is a separate experimental v1 contract over two complete
`ExperimentManifest` objects. It preserves controls discarded by the stable
`EvaluationBundle`: repository, commit, harness, strategy, model,
environment, grader, source revision, case, and seed identity. The comparator:

- permits only explicitly declared treatment factors;
- keeps the agent subject fixed for a model-only treatment and requires it to
  change for commit or strategy treatments;
- requires exact repository/dataset/split/harness/environment/grader/source
  controls and exact case-and-seed pairing;
- reports case-level improvement/regression counts, an exact two-sided sign
  test, a fixed 95% paired-case normal-approximation interval, sample
  sufficiency, and observed flakiness;
- defines its success estimand as the equal-weight macro average of the
  candidate-minus-baseline success-rate delta across the supplied frozen paired
  cases; repeated seeds affect the within-case rate, not the case's weight;
- sends an otherwise favorable conclusion to `REVIEW` when p95 latency or total
  cost exceeds the declared policy threshold;
- refuses comparisons above 10,000 paired cases, fixes its local decimal
  context, and uses exact integer cross-multiplication for efficiency thresholds;
- returns `BLOCK` for confounded/incomparable evidence, `REVIEW` for weak or
  unstable evidence, and `PASS` only when the declared objective and safety
  rules are satisfied.

This is a bounded estimate under frozen v1 assumptions, not universal proof or
causal attribution. `validate_comparison_receipt_inputs` recomputes the receipt
from separately held manifests and policy and requires the same hash. The
estimand does not cover unseen tasks or generalization beyond the supplied case
set. The comparison receipt is not consumed by `GateReceipt` v1.

### Gate v2 and quality sidecars

`GateReceiptV2` is a new opt-in contract; it does not reinterpret or replace
`GateReceipt` v1. It embeds a normal v1 receipt, a supplied
`ComparisonReceipt`, and a typed `ComparisonVerification` generated by
deterministically replaying that comparison from explicitly held manifests and
policy. It also checks that each full-manifest projection equals the stable
evaluation bundle used by the embedded v1 gate. A mismatch is `BLOCK`.

Gate v2 can add one immutable `ExperimentQualityEvidence` sidecar per
manifest. A sidecar maps each existing trial ID to exactly one terminal outcome:
`success`, `failure`, `timeout`, `refusal`, `infrastructure_error`, or
`missing`. Absence is represented as *unreported*, never success. Optional
versioned judge votes and a human verdict are asserted labels. The local
`QualityPolicy` calculates coverage, multi-judge disagreement, and calibration
against the supplied human labels; it neither invokes a grader nor authenticates
the asserted identities.

`SensitivityReceipt` evaluates only the supplied frozen manifests. It requires
all controls except `environment_digest` to match, then reports aggregate
success-rate ranges across environment and seed IDs. It is not a claim of
provider determinism, causal attribution, or behavior in unsupplied
environments. `ExplanationReceipt` turns a parsed receipt into a sorted,
content-addressed local dependency graph with its explicit limitations; it does
not generate an LLM explanation.

`GateReceipt` v1 is the original atomic PASS contract. It embeds and revalidates the
compilation, exact-input replay verification, and frozen evaluation, and
requires the evaluation candidate digest to match the compiled candidate. It
can also bind a Skill BOM and an evidence package containing repository,
commit, producer, environment, capture-time, and provenance metadata.
Compilation or integrity verification alone is never reported as PASS.

A consumer that has the source artifacts uses `validate_gate_receipt_inputs`
to rerun the deterministic v1 gate and require the same receipt hash. Parsing
the receipt or validating its JSON Schema proves structure and internal hash
consistency only; it does not prove producer identity or that separately held
traces, evaluation bundles, policy, Skill BOM, and evidence package match.
Package-bearing replay requires `GateReplayExpectations` populated from the
consumer's protected repository, exact commit, evaluation time, maximum age,
and minimum-provenance policy. These values must never be copied from the
receipt. A keyless receipt cannot weaken those external controls by changing
and recomputing its own hash.

`EvidenceEnvelope` and `EvidencePackage` are provider-neutral adapter boundaries.
They bind payload digests and provenance without loading adapter code into the
verifier. The `asserted`, `signature_verified`, and `attested` labels describe
the supplied provenance level; non-asserted labels also require an external
verification-artifact digest. An operator must still validate that external
artifact against its own trust policy. Version 0.3 records non-asserted labels
but does not let them satisfy a gate minimum without a trusted verifier.

`SkillBom` inventories the exact regular files, roles, sizes, external URLs, and
SHA-256 digests in an Agent Skill folder without importing or executing it. It
establishes content identity, not semantic safety.

A promotion receipt recomputes the compilation verification from the supplied
source traces rather than trusting a caller's assertion. Approval requires a
valid exact-input gate replay, a `pass` evaluation for the same candidate
digest, and valid hashes for every chained receipt. It binds the
compilation/input bundle, verification, dataset, policy, actor, candidate,
evaluation, commit SHA, UTC timestamp, and rationale. It neither authenticates
the actor nor executes the candidate.

## Compilation rules

The preview intentionally admits a narrow corpus:

- at least two successful traces;
- identical ordered node identities across the supporting traces;
- only pure or read effects;
- explicit and consistent bindings;
- no forward, missing, or conflicting `step_output` references;
- no unsupported operation or incomplete required evidence.

If every gate passes, TraceGate emits a candidate preserving the proven
structure.
Otherwise it emits a refusal with machine-readable reasons. Future versions may
support controlled branching, but must not infer it from sparse observations.

## Interfaces

### CLI

```bash
awe gate \
  --traces examples/repo_analysis/traces.jsonl \
  --baseline examples/evaluation/baseline.json \
  --candidate examples/evaluation/candidate.json \
  --policy examples/evaluation/policy.json \
  --out gate.json
```

The receipt is emitted to standard output or an explicit output path. For the
atomic gate, exit `0` means PASS, `2` means REVIEW or BLOCK, and `1` means a
malformed input or invocation. Diagnostic `compile`, `verify`, and `evaluate`
commands remain available, but their individual outputs are not an atomic pass.

`awe demo` generates a self-contained synthetic Gate v2 chain without a model
or network call. `awe doctor` then reloads the standard review-bundle layout and
fails closed unless its typed artifacts, held-input comparison, Gate v2 receipt,
and explanation graph reproduce. The doctor reports bundle integrity, not model
quality or production safety.

`awe recipes` is a content-addressed, machine-readable catalog over five
decision paths. It uses exact recipe IDs rather than fuzzy natural-language
routing. `awe init` materializes only the selected recipe README and explicit
policy defaults in a new directory, then records their raw SHA-256 digests in
`awe.recipe-scaffold-manifest.v1`. The scaffold is outside the evidence trust
chain: it sets up a review, but cannot create traces, outcomes, consent,
signatures, receipts, or a human decision.

`awe status` adds a read-only operational projection over these layouts. For a
recipe workspace it validates the manifest against the installed built-in
definition *before* resolving managed paths, then verifies raw file digests and
reports missing real inputs. For a canonical Gate v2 directory it reuses the
doctor replay path. The status report is content-addressed
`awe.workspace-status.v1`; `READY` describes reproducible bundle integrity, not
authorization or universal agent quality.

`awe skill inspect`, `awe conformance`, and `awe capabilities --json` provide
non-executing integration surfaces for Skill authors, adapters, and installers.

### Agent host adapters

`skills/` is the canonical Codex/Agent Skills source. The Codex plugin consumes
it directly. Claude Code requires host-specific invocation metadata, so
`scripts/sync_claude_plugin.py` deterministically renders a namespaced adapter
under `integrations/claude-code/`. CI requires byte parity after the documented
frontmatter and invocation-name transformation. The adapter adds no hooks, MCP
servers, tool grants, agent runtime, or alternate decision path.

Evidence-changing Claude Skills set `disable-model-invocation: true`; only the
read-only readiness check remains eligible for host selection. Both hosts call
the same installed `awe` CLI, whose receipt remains authoritative.

### HTTP API

The optional API is a thin adapter over the same compiler:

- `GET /healthz`
- `POST /v1/compile`
- `POST /v1/verify`
- `POST /v1/evaluate`
- `POST /v1/experiments/import/generic`
- `POST /v1/experiments/import/otlp`
- `POST /v1/promote`

It introduces no alternate decision path and should return the same typed
receipt for the same request.

### Local TraceGate Review

`GET /` serves **TraceGate Review**, a dependency-free review UI packaged with
the Python distribution. It sends typed requests to the same local endpoints
used by API integrators and presents candidate structure, evaluation metrics,
chained digests, an optional experiment manifest, and the human-decision form.
The form starts with no decision selected. Its Reviewer identifier is an
asserted receipt field, not an authenticated identity.

Bundled inputs are labeled as sample data; selected files are parsed in the
browser, size-limited, and sent only to the same-origin API. Explicit buttons
and forms select evidence, run validation, export artifacts, and record the
human decision. There is no natural-language command composer or model
conversation in this process. The tools view reports implemented integration
surfaces without claiming provider accounts are connected. The packaged
Atkinson Hyperlegible Next font is served locally; the UI has no font-CDN
dependency. The page does not add a planner, runtime, persistence layer, or
alternate decision rule.

## Determinism and versioning

Canonical serialization sorts object keys and excludes presentation-only
variation before hashing. Any intentional change to validation, normalization,
edge admission, effect classification, or receipt serialization requires a
contract/compiler version change and reviewed golden-receipt updates.
Exported schemas use JSON Schema 2020-12 and stable
`urn:awe-tracegate:schema:*` identifiers; a new semantic contract requires a new
identifier rather than changing an existing version in place.

Determinism here applies to the offline compiler and verifier only. It is not a
claim that external agents or model-backed workflows are deterministic.

## Possible later integration

A downstream evaluator may run a candidate in its own isolated environment and
return independent outcome, safety, latency, and cost evidence. TraceGate can
record a promotion only after compilation verification, exact-input gate replay,
and evaluation artifacts agree on the same candidate. No future evaluator
should let a model approve its own change.

## AWE product boundary

TraceGate is AWE's trusted evidence-integrity and decision core; it is not an
agent runtime. Existing harnesses, CI systems, model providers, and
observability platforms remain external evidence producers. Any optional
workspace or review surface has the same untrusted producer/consumer status and
receives no special authority.

External evidence may cross the boundary only through versioned typed
contracts. Agent prose, tool output, UI state, or a provider's score cannot
mutate TraceGate policy or convert a refusal into approval. Repeated success is
evidence, not permission: a candidate still needs exact-input verification,
evaluation, and a separate human decision before a downstream system may treat
it as reusable.

A generic chatbot, command center, workflow builder, model router, desktop
agent, or package registry is not part of this repository's product direction.
Those systems may integrate with AWE as evidence producers or consumers.

## Conclusion reliability boundary

The current source has two distinct decision paths:

- `awe gate` revalidates the stable v1 trace/evaluation evidence chain but does
  not bind every `ExperimentManifest` identity field;
- experimental `awe compare` holds declared controls, cases, and seeds equal and
  emits bounded v1 uncertainty and flakiness evidence over full manifests.

Neither path runs trials or grades outputs. Judge agreement/calibration, typed
timeout/refusal/infrastructure outcomes, multi-environment variance, automatic
failure clustering, and counterfactual causal attribution remain planned work.
Until those contracts exist, AWE must not infer them from prose, provider
metadata, or a model's confidence.

## Experiment interoperability

`ExperimentManifest` is the normalization boundary for external Discovery Loop
evidence. It binds one repository and commit to a frozen dataset split, exact
harness, strategy, model configuration, environment, grader, trials, traces,
tokens, latency, cost, and safety outcomes. The manifest is content-addressed;
changing any trial or provenance field invalidates its digest. The HTTP API
exposes both import paths; malformed or unannotated OTLP input returns `422`
without attempting to infer missing ground truth.

Two independent adapters currently emit this contract:

- explicit provider-neutral JSON;
- OTLP JSON annotated against OpenTelemetry GenAI revision
  `1d85c963ea51e9c7d24cc330ff67057f6e90e6c5`.

The OTLP adapter consumes `invoke_agent` or `invoke_workflow` spans but requires
separate `awe.eval.*` task and grader evidence. Transport/span success is not
ground truth. Missing or mixed experiment metadata is rejected rather than
filled with zeroes or inferred values.

Third-party exporters should produce `awe.evidence-envelope.v1` outside the
trusted process and run `awe conformance` over it. Promptfoo, Langfuse,
Braintrust, OpenAI Evals, or any future adapter remains a producer—not a plugin
loaded into the deterministic core.

## Signed bundles and governed export

Optional signed bundles use Ed25519 over canonical JSON. Verification requires
an operator-supplied trusted public key and expected signer, repository, and
commit. An embedded public key proves neither identity nor authorization.

Governed redaction is similarly explicit: an immutable consent record must be
active, granted for the requested scope, and unexpired at the caller-provided
UTC evaluation time. The policy can restrict exported top-level fields and add
sensitive or denied key classes. The summary binds input/output, policy, and
consent digests without claiming complete data-loss prevention.

## Language boundary

Python/Pydantic remains the only decision engine. `sdk/typescript` is generated
from the FastAPI OpenAPI document and checked for drift in CI. It provides
compile-time request/response types; untrusted JSON still crosses the Python
runtime-validation boundary before it can affect a decision.
