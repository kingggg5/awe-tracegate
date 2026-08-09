# AWE TraceGate contributor guide

## Product contract

- Distribution name: `awe-tracegate`.
- Python import: `awe_tracegate`.
- CLI: atomic `awe gate`, diagnostic compile/verify/evaluate, evidence
  conformance, Skill inspection, redaction, signing, promotion, and schema export.
- Optional API: `GET /healthz` and typed `/v1/*` endpoints.
- Codex plugin: `.codex-plugin/plugin.json` with focused skills under `skills/`.
- Atomic gate decisions are `PASS`, `REVIEW`, `BLOCK`, or `ERROR`.
- Diagnostic compilation decisions remain `compiled` or `refused`.
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
- PASS requires compilation, exact trace replay, a passing frozen evaluation,
  and identical candidate linkage. Optional Skill BOM and evidence-package
  inputs must be digest-bound into the same gate receipt.
- CLI and API must use the same compiler path and return the same contract.
- Skills may orchestrate the CLI but never produce evidence or own decisions.
- Promotion approval requires a compiled receipt, a valid locally replayed
  verification receipt, and a passing evaluation for the same candidate. It
  must bind compilation/input, verification, dataset/policy, actor, commit SHA,
  timestamp, and rationale.

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
python scripts/install_skills.py --list
npm run test:installer
awe gate \
  --traces examples/repo_analysis/traces.jsonl \
  --baseline examples/evaluation/baseline.json \
  --candidate examples/evaluation/candidate.json \
  --policy examples/evaluation/policy.json
```

Documentation must describe implemented behavior, distinguish current scope
from future ideas, and preserve the security limitations in `docs/security.md`.
