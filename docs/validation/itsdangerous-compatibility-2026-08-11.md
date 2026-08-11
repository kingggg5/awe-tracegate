# Public upstream compatibility report — itsdangerous

| Field | Result |
| --- | --- |
| Status | **PASS** |
| Date | 2026-08-11 |
| Upstream | [`pallets/itsdangerous`](https://github.com/pallets/itsdangerous) |
| Snapshot | [`672971d66a2ef9f85151e53283113f33d642dabd`](https://github.com/pallets/itsdangerous/commit/672971d66a2ef9f85151e53283113f33d642dabd) |
| Test environment | Isolated CPython 3.12 virtual environment on Windows |
| Upstream command | `python -m pytest -q --basetemp <isolated-temp-dir>` |
| Upstream result | **297 passed** in **0.74 s** (`1.02 s` measured test-command wall time) |
| TraceGate compilation | `compiled` — `sha256:23b00749f0116765775356bbdcfed980639d1b6630af407d24252faf37809948` |
| Exact trace replay | `valid`, `traces_verified=true` — `sha256:de3cfaf5cce7769a88ec139cad92bc4b1b49346e2b0f48ef1888ab238e1a357c` |

## What was verified

1. Cloned the public upstream repository at the exact detached commit above.
2. Recomputed SHA-256 for its public `pyproject.toml` and `README.md`; both
   matched the retained digest-only evidence.
3. Installed the snapshot in a fresh virtual environment with the project test
   dependencies, then ran the upstream test suite.
4. Recompiled the checked-in read-only TraceGate traces and replayed the
   compilation receipt from the same local evidence.

The retained machine-readable evidence is in
[`examples/external_pilot/itsdangerous/`](../../examples/external_pilot/itsdangerous/).
It stores paths, sizes, digests, commands, receipt hashes, and limits; it does
not redistribute upstream source files.

## Reproduce

```bash
git clone --filter=blob:none https://github.com/pallets/itsdangerous.git upstream
git -C upstream checkout --detach 672971d66a2ef9f85151e53283113f33d642dabd

python -m venv upstream/.venv
upstream/.venv/bin/python -m pip install -e ./upstream pytest freezegun
upstream/.venv/bin/python -m pytest -q --basetemp /tmp/itsdangerous-tests

python -m awe_tracegate.cli compile \
  --traces examples/external_pilot/itsdangerous/traces.jsonl \
  --out /tmp/compilation.json
python -m awe_tracegate.cli verify \
  --receipt /tmp/compilation.json \
  --traces examples/external_pilot/itsdangerous/traces.jsonl \
  --out /tmp/verification.json
```

On Windows, use `.venv\Scripts\python.exe` and a temporary path instead of
`/tmp`. Dependency resolution, hardware, and platform can affect timing; the
test count and content-addressed AWE receipts are the reproducibility checks.

## Boundaries

This is a **maintainer-run public compatibility test**, not a third-party
endorsement or independent pilot. It does not establish agent quality, model
safety, benchmark performance, or adoption by the upstream project. The
upstream test result is recorded local evidence, not an authenticated evaluator
receipt. See the [security model](../security.md) for the complete trust
boundary.
