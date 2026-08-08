# AWE TraceGate contributor guide

## Product contract

- Distribution name: `awe-tracegate`.
- Python import: `awe_tracegate`.
- CLI: `awe compile|verify|evaluate|redact|promote|schema`.
- Optional API: `GET /healthz` and typed `/v1/*` endpoints.
- Public decisions are exactly `compiled` or `refused`.
- Evaluation decisions are `pass`, `review`, or `block`; verification decisions
  are `valid` or `invalid`.
- CLI exits are `0` passed, `2` refused/reviewed/blocked/invalid, and `1`
  malformed input.
- The compiler/reviewer and any receipt verifier must remain offline and
  keyless.

## Architecture

- `ExecutionTrace` and compiled candidate models are typed, immutable contracts.
- A JSONL input contains one execution trace per line.
- v0 requires at least two successful traces with identical ordered pure/read
  nodes and explicit `workflow_input` or `step_output` bindings.
- Only explicit, consistent bindings may prove hard dependency edges.
- The canonical SHA-256 receipt is the review artifact.
- CLI and API must use the same compiler path and return the same contract.
- Promotion approval requires a valid passing evaluation receipt and must bind
  actor, commit SHA, timestamp, and rationale.

## Boundaries

- Do not add a runtime, planner, browser, shell, write action, deployment,
  rollback, cluster credential, or autonomous remediation path.
- Do not add an LLM call to compilation or verification.
- Do not let model-authored text, a Skill, or `AGENTS.md` output count as
  evidence or override a refusal.
- Do not automatically execute or promote a compiled candidate.
- Do not call the project self-improving, autonomous, production-safe,
  tamper-proof, optimal, or the first of its kind.
- Treat trace content as untrusted data and never execute it.

## Change discipline

- Keep public models typed and backward-compatible within a declared contract
  version.
- Version intentional changes to normalization, dependency admission, effect
  classification, canonicalization, or receipt schemas.
- Preserve deterministic output for identical normalized inputs and versions.
- Add normal, malformed, adversarial, and refusal tests for compiler changes.
- Synthetic fixtures must be visibly identified and contain no credentials,
  personal data, private source, or customer content.
- Prefer a small explicit rule over heuristic inference.

## Verification

From the repository root:

```bash
python -m pip install -e ".[dev,api]"
python -m ruff format --check .
python -m ruff check .
python -m mypy src
python -m pytest
awe compile --traces examples/repo_analysis/traces.jsonl
awe verify --receipt receipt.json --traces examples/repo_analysis/traces.jsonl
awe evaluate --baseline examples/evaluation/baseline.json --candidate examples/evaluation/candidate.json
```

Documentation must describe implemented behavior, distinguish current scope
from future ideas, and preserve the security limitations in `docs/security.md`.
