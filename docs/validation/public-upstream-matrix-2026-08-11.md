# Public upstream compatibility matrix

This is a maintainer-run, reproducible test report for public Python projects.
Every snapshot is an immutable release commit. Each project was cloned into a
fresh directory, installed into a separate CPython 3.12 virtual environment,
and tested without modifying upstream source. Durations below are useful local
observations, not benchmarks.

| Project | Pinned public snapshot | Test scope | Result | Test time | TraceGate evidence |
| --- | --- | --- | --- | ---: | --- |
| [itsdangerous](https://github.com/pallets/itsdangerous) | [`672971d`](https://github.com/pallets/itsdangerous/commit/672971d66a2ef9f85151e53283113f33d642dabd) | Full `pytest -q` suite | **297 passed** | 0.74 s | `compiled`; exact replay `valid` |
| [MarkupSafe](https://github.com/pallets/markupsafe) | [`28ace20`](https://github.com/pallets/markupsafe/commit/28ace20b140d15c083e1cbc163ee6b7778ba098c) | Full `pytest -q` suite | **78 passed** | 0.22 s | Not claimed — no agent experiment artifacts supplied |
| [pluggy](https://github.com/pytest-dev/pluggy) | [`f8aa4a0`](https://github.com/pytest-dev/pluggy/commit/f8aa4a009716a7994f2f6c1947d9fa69feccbdd5) | Full `pytest -q` suite | **109 passed** | 0.33 s | Not claimed — no agent experiment artifacts supplied |
| [Click](https://github.com/pallets/click) | [`934813e`](https://github.com/pallets/click/commit/934813e4d421071a1b3db3973c02fe2721359a6e) | Full `pytest -q` suite | **Platform-limited:** 622 passed, 15 failed, 12 skipped, 1 xfailed | 1.75 s | Not claimed — Windows pager newline mismatch |

## How to interpret this matrix

The first three rows are successful isolated upstream test runs. The Click row
is deliberately retained as a non-green result: its failing tests use Unix
`cat` as a pager and expect `LF`, while this Windows run produced `CRLF`. That
is a platform constraint in this environment, not evidence that Click or
TraceGate is broken.

Only itsdangerous has a TraceGate compilation/replay result because it has a
checked-in, digest-only read-only trace bundle. Producing a gate receipt for
the other repositories without their actual agent traces, frozen baseline and
candidate evaluations, and policy would fabricate evidence. Their upstream
test results therefore remain useful compatibility signals, not AWE verdicts.

The full itsdangerous evidence and commands are in the
[individual compatibility report](itsdangerous-compatibility-2026-08-11.md).

## Repeat the method

For any public project, pin an immutable revision, create an isolated
environment, install only the declared project test dependencies, and preserve
the exact command plus exit code. Then supply TraceGate only with genuine,
separately held agent experiment artifacts:

```bash
git clone --filter=blob:none <repository-url> upstream
git -C upstream checkout --detach <full-commit-sha>

python -m venv upstream/.venv
upstream/.venv/bin/python -m pip install -e ./upstream <test-dependencies>
upstream/.venv/bin/python -m pytest -q --basetemp /tmp/upstream-tests

# Only when real agent traces/evaluations exist:
awe gate --traces traces.jsonl --baseline baseline.json --candidate candidate.json
```

Do not use test success alone as an AWE `PASS`; `awe gate` is intentionally
fail-closed when required trace/evaluation linkage is absent.

## Limits

- These results are not third-party endorsements, an independent adopter
  pilot, security certification, or a performance benchmark.
- The test result is locally observed metadata, not an authenticated evaluator
  receipt.
- HTTPX `0.28.1` setup was intentionally not included: the selected non-network
  suite exceeded a two-minute run budget, so no partial result is published.
- Networked tests were not run. See the [security model](../security.md) for
  the trusted-core boundary.
