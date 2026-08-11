# AWE TraceGate contributor guide

## Product contract

- Positioning: reproducible evidence infrastructure for agent experiments.
- TraceGate is the trusted evidence-integrity and decision core. It does not
  build or run agents and must not expand into a generic workspace or agent
  framework.
- Distribution name: `awe-tracegate`.
- Python import: `awe_tracegate`.
- CLI: decision-first `awe recipes`/`awe init`, atomic `awe gate`/`awe gate-v2`,
  diagnostic compile/verify/evaluate,
  held-input comparison verification, quality/sensitivity assessment, evidence
  graph explanation, conformance, Skill inspection, redaction, signing,
  promotion, and schema export.
- Optional API: `GET /healthz` and typed `/v1/*` endpoints.
- Codex plugin: `.codex-plugin/plugin.json` with focused skills under `skills/`.
- Claude Code plugin: `integrations/claude-code/.claude-plugin/plugin.json` with
  generated host-specific Skills and `.claude-plugin/marketplace.json` at the
  repository root. Run `python scripts/sync_claude_plugin.py --root . --write`
  after changing a canonical Skill; never hand-edit the generated adapter.
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
- PASS requires compilation, exact-input gate replay, a passing frozen evaluation,
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
- Describe comparison v1 as bounded evidence reliability under its declared
  frozen controls and assumptions, never as universal statistical proof.
- Do not claim live run reconstruction, trusted evaluator agreement, failure
  clustering, or causal attribution. Current quality evidence only calculates
  asserted judge/human label agreement; it does not authenticate or validate
  graders.
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
python scripts/sync_claude_plugin.py --root . --check
npm run test:installer
awe gate \
  --traces examples/repo_analysis/traces.jsonl \
  --baseline examples/evaluation/baseline.json \
  --candidate examples/evaluation/candidate.json \
  --policy examples/evaluation/policy.json
```

Documentation must describe implemented behavior, distinguish current scope
from future ideas, and preserve the security limitations in `docs/security.md`.
