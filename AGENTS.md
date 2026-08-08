# AWE Agent Harness contributor guide

## Product contract

- Distribution name: `awe-harness`.
- Python import: `awe_harness`.
- CLI: `awe compile --traces <jsonl>`.
- Optional API: `GET /healthz` and `POST /v1/compile`.
- Public decisions are exactly `compiled` or `refused`.
- CLI exits are `0` compiled, `2` refused, and `1` malformed input.
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
```

Documentation must describe implemented behavior, distinguish current scope
from future ideas, and preserve the security limitations in `docs/security.md`.
