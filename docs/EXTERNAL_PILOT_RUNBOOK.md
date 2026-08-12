# External pilot runbook

This runbook is for a **read-only, non-sensitive** pilot. It is a compatibility
and reproducibility exercise, not a production-safety certification or a model
benchmark.

## Before the run

- Select a public or disposable repository and pin its exact 40-character SHA.
- Create an AWE Workspace handoff with `capture_trace` and
  `evaluate_migration` consent. Never put credentials or customer data in the
  handoff.
- Prepare a fresh PostgreSQL database/role per case and pin the image and
  dependency versions.
- Define the baseline, candidate intervention, held-out split, reviewer, and
  stop conditions before running the external host.

## Execute one case

```bash
# External host: produce a consented JSONL trace; do not point at production.
codex exec --ephemeral --sandbox workspace-write --json \
  "Implement the approved migration task and run the declared verification plan" \
  > codex-trace.jsonl

# Normalize and redact the trace.
awe-discovery ingest-trace \
  --format codex.exec-jsonl \
  --input codex-trace.jsonl \
  --handoff handoff.json \
  --repository https://github.com/example/repository \
  --commit-sha <40-hex-sha> \
  --evaluated-at 2026-08-12T03:00:00Z \
  --out agent-trace-receipt.json

# Run the isolated PostgreSQL/Alembic harness separately.
python examples/postgres-alembic-discovery/harness/run.py \
  --dsn postgresql://pilot:pilot@127.0.0.1:5432/pilot \
  --repository https://github.com/example/repository \
  --commit-sha <40-hex-sha> \
  --out migration-results.json

awe-discovery build-migration-bundle \
  --trace agent-trace-receipt.json \
  --input migration-results.json \
  --out-dir migration-discovery
```

The harness must report `success` for `forward_migration`,
`data_preservation`, `rollback`, and `tests`. Do not replace a missing lane
with `success`; preserve `timeout`, `refusal`, `infrastructure_error`, and
`missing` exactly.

## Close the discovery loop

```text
failure-cluster-report.json
        ↓
propose-intervention (hypothesis + change digest)
        ↓ independent reviewer
approve-intervention (time-bounded approval)
        ↓
prepare-replay (held manifest + split + exact SHA)
        ↓ external runner executes candidate
new trace + baseline/candidate results
        ↓
awe verify-comparison → awe gate-v2 → awe explain
```

The trusted core only validates supplied artifacts. It never starts Codex,
Claude, a database, a shell, or a deployment.

## Replay by a second person

The producer should publish only a redacted bundle, checksums, environment
metadata, and exact commands. The second person must use a clean checkout and
independently run the same CLI commands. Compare every receipt hash and verify
that the repository URI, commit SHA, manifest digest, split digest, and consent
scope are identical. A replay that cannot be reproduced is `REVIEW`, not PASS.
