---
name: awe-review-evidence
description: Compile, replay, and review existing agent or workflow traces and evaluation artifacts with AWE TraceGate, checking exact revision, provenance, freshness, comparability, and counter-evidence. Use when evidence already exists or a candidate is proposed for reuse. Do not fabricate missing inputs, execute the candidate, or override TraceGate or a human reviewer.
---

# AWE Evidence Review

Run the deterministic checks when artifacts are available. Agent prose is never the authority.

## Workflow

1. Inventory the traces, compilation receipt, baseline, candidate, policy, repository revision, dataset digest, harness, grader, and model configuration.
2. Establish provenance and freshness. Mark mutable, stale, self-reported, inaccessible, or mismatched artifacts explicitly.
3. Run `awe compile`, `awe verify`, and `awe evaluate` only for supplied local artifacts. Use [the receipt contract](references/receipt-contract.md) and preserve command exit codes and output paths.
4. Inspect failed trials and counter-evidence before aggregate scores. Record every uncontrolled variable.
5. Report the exact TraceGate state. Do not reinterpret `refused`, `invalid`, `review`, or `block` as a pass.
6. Request a human decision only when the evidence chain is compiled, exactly replayed, and evaluation status is `pass`.

## Return

- **Claim under review**
- **Revision and artifact inventory**
- **Commands and exit codes**
- **Supporting evidence**
- **Counter-evidence and uncertainty**
- **TraceGate state and receipt hashes**
- **Next verification or human decision needed**

## Boundaries

- Never turn missing evidence into a zero or pass.
- Never accept a branch name where an immutable commit is required.
- Redact secrets, personal data, and customer content before quoting artifacts.
- Never promote, deploy, publish, or execute a candidate.
