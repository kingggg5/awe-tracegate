# Contributing to AWE TraceGate

Thank you for helping improve AWE. The project is pre-alpha, so small,
well-tested changes that tighten the evidence contract are more valuable than
broad feature additions.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Before opening a change

- Search existing issues and pull requests.
- Open a design issue before changing a public schema, canonical receipt,
  dependency rule, effect classification, or safety boundary.
- Report vulnerabilities privately using [SECURITY.md](SECURITY.md).
- Do not submit real credentials, personal data, customer traces, or private
  source content as fixtures.

## Development setup

Requires Python 3.11 or newer.

```bash
python -m venv .venv
```

Activate the environment, then install the development and API extras:

```bash
python -m pip install -e ".[dev,api]"
python -m ruff format --check .
python -m ruff check .
python -m mypy src
python -m pytest
awe schema --out-dir schemas
```

Exercise the public CLI against the repository fixture:

```bash
awe compile --traces examples/repo_analysis/traces.jsonl
awe evaluate --baseline examples/evaluation/baseline.json --candidate examples/evaluation/candidate.json
```

## Pull-request expectations

A focused pull request should include:

- a clear problem statement and the reason the change belongs in v0;
- tests for normal, boundary, malformed, and refusal behavior;
- golden receipt updates for intentional canonical-output changes;
- documentation for public contract or CLI changes;
- no unrelated formatting or dependency churn.

Compiler changes must remain deterministic. The same normalized evidence under
the same compiler and contract versions must produce the same decision and
canonical receipt. Never weaken a refusal rule only to make a fixture compile.

## Project boundaries

The current project does not accept features that add:

- model calls to the verifier;
- shell, browser, deployment, rollback, or write-tool execution;
- an autonomous planner, runtime, or self-modifying loop;
- automatic promotion of compiled candidates;
- unsupported claims of safety, optimality, or research novelty.

A proposal outside these boundaries needs a separate threat model and explicit
maintainer agreement before implementation.

## Documentation style

Use short, factual language. Label synthetic examples. Distinguish implemented
behavior from a roadmap. Say “content-addressed” rather than “tamper-proof”
unless an external signature or transparency mechanism exists.

## Review and release

Maintainers may request changes, narrow a proposal, or decline work that expands
the trusted boundary without proportional evidence. A merged change is not a
promise of backward compatibility until the relevant contract is declared
stable.
