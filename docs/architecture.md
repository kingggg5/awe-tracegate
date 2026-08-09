# Architecture

AWE TraceGate is deliberately smaller than a general agent platform. Its
v0 contract is a pure, read-only transformation:

```text
ExecutionTrace JSONL
        |
        v
typed validation and normalization
        |
        v
cross-trace structure and binding analysis
        |
        v
effect and evidence gate
       / \
      v   v
compiled  refused
      \   /
       v v
canonical SHA-256 receipt -> replay verifier
                               |
frozen evaluation bundles -> policy gate -> pass / review / block
                               |
exact-trace replay + human actor + commit SHA -> promotion receipt
```

The compiler, verifier, evaluator, redactor, and promotion recorder have no
model, tool, browser, network, or workflow-execution loop. Given the same
supported inputs and contract versions, they must return the same canonical
decision.

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

### `CompileReceipt`

The public result is a typed receipt with a `compiled` or `refused` decision,
`compiler_version`, `input_bundle_digest`, refusal `reasons`, an optional
`candidate`, and `receipt_hash`. A compiled candidate contains its own digest,
source trace IDs, admitted edges, and dependency evidence.

The input bundle is normalized into trace-ID order before hashing, so caller
ordering does not change the receipt. The receipt hash detects modification
after creation. It is not a digital signature and does not establish who
produced the receipt.

### Evaluation and promotion receipts

An `EvaluationBundle` binds external trial outcomes to one subject and frozen
dataset digest. The evaluator first enforces dataset/case parity and hard safety
and success gates, then marks excessive latency or cost regression for review.
It does not run the trials or grade model output itself.

A promotion receipt recomputes the compilation verification from the supplied
source traces rather than trusting a caller's assertion. Approval requires a
valid exact-trace replay, a `pass` evaluation for the same candidate digest, and
valid hashes for every chained receipt. It binds the compilation/input bundle,
verification, dataset, policy, actor, candidate, evaluation, commit SHA, UTC
timestamp, and rationale. It neither authenticates the actor nor executes the
candidate.

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
awe compile --traces examples/repo_analysis/traces.jsonl
```

The receipt is emitted to standard output so callers can redirect it, hash it,
or attach it to a review. Exit `0` means compiled, `2` means refused, and `1`
means malformed input or invocation.

### HTTP API

The optional API is a thin adapter over the same compiler:

- `GET /healthz`
- `POST /v1/compile`
- `POST /v1/verify`
- `POST /v1/evaluate`
- `POST /v1/experiments/import/generic`
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

Determinism here applies to the offline compiler and verifier only. It is not a
claim that external agents or model-backed workflows are deterministic.

## Possible later integration

A downstream evaluator may run a candidate in its own isolated environment and
return independent outcome, safety, latency, and cost evidence. TraceGate can
record a promotion only after the compilation, exact-trace verification, and
evaluation artifacts agree on the same candidate. No future evaluator should
let a model approve its own change.

## AWE ecosystem boundary

TraceGate is the evidence and promotion gate in the broader AWE ecosystem; it
is not the agent runtime. **AWE Workspace** is a separate companion application
and process boundary for the goal/command composer, sessions, tools, and future
agent runtimes. It is not part of the `awe-tracegate` package. Workspace
execution permissions,
model keys, persistence, and tool capabilities must remain outside this
repository's trusted core.

Workspace evidence may cross the boundary only through the same versioned,
typed contracts as any other producer. Agent prose, tool output, and workspace
state cannot mutate TraceGate policy or convert a refusal into approval.
Repeated success is evidence, not permission: a candidate still needs exact
verification, evaluation, and an explicit human decision before a downstream
registry could treat it as reusable software. Native desktop packaging is an
interface decision for Workspace, not a reason to rewrite this canonical
decision engine.

## Experiment interoperability

`ExperimentManifest` is the normalization boundary for external Discovery Loop
evidence. It binds one repository and commit to a frozen dataset split, exact
harness, strategy, model configuration, environment, grader, trials, traces,
tokens, latency, cost, and safety outcomes. The manifest is content-addressed;
changing any trial or provenance field invalidates its digest.

Two independent adapters currently emit this contract:

- explicit provider-neutral JSON;
- OTLP JSON annotated against OpenTelemetry GenAI revision
  `1d85c963ea51e9c7d24cc330ff67057f6e90e6c5`.

The OTLP adapter consumes `invoke_agent` or `invoke_workflow` spans but requires
separate `awe.eval.*` task and grader evidence. Transport/span success is not
ground truth. Missing or mixed experiment metadata is rejected rather than
filled with zeroes or inferred values.

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
