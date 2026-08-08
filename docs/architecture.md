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
human actor + commit SHA ----> promotion receipt
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

A promotion receipt records a human decision only after verifying the
evaluation receipt hash. Approval requires a `pass` result and binds the actor,
candidate, evaluation, commit SHA, UTC timestamp, and rationale. It neither
authenticates the actor nor executes the candidate.

## Compilation rules

The preview intentionally admits a narrow corpus:

- at least two successful traces;
- identical ordered node identities across the supporting traces;
- only pure or read effects;
- explicit and consistent bindings;
- no forward, missing, or conflicting `step_output` references;
- no unsupported operation or incomplete required evidence.

If every gate passes, AWE emits a candidate preserving the proven structure.
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

It introduces no alternate decision path and should return the same typed
receipt for the same request.

## Determinism and versioning

Canonical serialization sorts object keys and excludes presentation-only
variation before hashing. Any intentional change to validation, normalization,
edge admission, effect classification, or receipt serialization requires a
contract/compiler version change and reviewed golden-receipt updates.

Determinism here applies to the offline compiler and verifier only. It is not a
claim that external agents or model-backed workflows are deterministic.

## Possible later integration

A downstream evaluator may run a candidate in its own isolated environment and
return independent outcome, safety, latency, and cost evidence. A promotion
system may then require both the compile receipt and evaluation receipt. Neither
capability belongs to the v0 compiler, and no future evaluator should let a
model approve its own change.
