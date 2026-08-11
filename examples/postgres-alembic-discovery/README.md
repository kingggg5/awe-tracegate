# PostgreSQL/Alembic discovery adapter

This synthetic fixture demonstrates the first narrow AWE Discovery Loop:
**coding-agent reliability for PostgreSQL/Alembic migrations**. It exercises
real AWE contracts and CLI code without starting an agent, running migration
code, or connecting to a database.

```text
consented Workspace handoff + Codex / Claude Code / generic JSONL trace
        -> awe-discovery ingest-trace
        -> redacted, SHA-bound agent trace receipt
        + isolated forward / rollback / data / test results
        -> awe-discovery build-migration-bundle
        -> ExperimentManifest + typed outcomes + failure clusters
        -> awe compare / awe verify-comparison / awe gate-v2
```

## Run the checked-in synthetic fixture

From the repository root:

```bash
python -m pip install -e .

awe-discovery ingest-trace \
  --format codex.exec-jsonl \
  --input examples/postgres-alembic-discovery/codex-trace.jsonl \
  --handoff examples/postgres-alembic-discovery/handoff.json \
  --repository https://github.com/example/postgres-migrations \
  --commit-sha aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
  --evaluated-at 2026-08-11T03:00:00Z \
  --out agent-trace-receipt.json

awe-discovery build-migration-bundle \
  --trace agent-trace-receipt.json \
  --input examples/postgres-alembic-discovery/migration-results.json \
  --out-dir migration-discovery
```

The second command emits four files:

| File | What it proves |
| --- | --- |
| `experiment-manifest.json` | Exact repository/SHA, harness, model, environment, grader, cases, seeds, latency, cost, and token identity |
| `experiment-quality-evidence.json` | `success`, `failure`, `timeout`, `refusal`, `infrastructure_error`, or `missing` per trial |
| `failure-cluster-report.json` | Deterministic grouping by migration evidence lane and terminal outcome; it is not a causal diagnosis |
| `migration-discovery-bundle.json` | One content-addressed package joining the consented trace and evaluation artifacts |

The fixture intentionally contains a rollback failure. A successful forward
migration therefore cannot hide a failed rollback lane.

## Capture from a real agent host

Create and approve a handoff in AWE Workspace first. Trace consent is **off by
default**; select `Capture a redacted agent trace`, and select the separate
`Evaluate PostgreSQL/Alembic evidence` scope only when the migration result may
enter a Discovery bundle.

Codex can emit JSONL in non-interactive mode:

```bash
codex exec --ephemeral --sandbox workspace-write --json \
  "Implement the approved migration task and run the declared verification plan" \
  > codex-trace.jsonl
```

See the official [Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode)
reference for event and sandbox behavior.

Claude Code can emit stream JSON:

```bash
claude -p \
  --output-format stream-json \
  --permission-mode default \
  --allowedTools "Read,Edit,Bash" \
  --max-turns 20 \
  "Implement the approved migration task and run the declared verification plan" \
  > claude-trace.jsonl
```

See the official [Claude Code CLI reference](https://docs.anthropic.com/en/docs/claude-code/cli-usage)
for permission and output-format semantics.

Runner sandboxing and tool approval remain the host's responsibility. AWE does
not distribute credentials or weaken those prompts. Store raw JSONL only in an
approved location: it may contain prompts, commands, source snippets, secrets,
PII, or customer data. `awe-discovery ingest-trace` writes only allowlisted
event metadata, typed outcomes, usage counters, and canonical payload digests.
The repository and commit arguments are recorded as caller-asserted identity;
they are not a runner attestation.
Payload digests provide integrity, **not anonymity**; low-entropy secrets may be
guessable and must be removed before capture.

## Isolated migration harness contract

The external harness, not TraceGate, runs the database work. For every frozen
case it must supply all four sorted checks:

1. `forward_migration`: run `alembic upgrade head`, then
   `alembic current --check-heads`.
2. `rollback`: run the case's declared `alembic downgrade <revision>` and verify
   the expected schema state.
3. `data_preservation`: compare separately declared row counts, keys, and/or
   checksums before and after each direction. Alembic success is not proof of
   preserved data.
4. `tests`: run the repository's frozen migration/application test suite.

The command names follow the official
[Alembic command API](https://alembic.sqlalchemy.org/en/latest/api/commands.html).

Use a disposable PostgreSQL instance, a least-privilege test role, pinned image
and dependency digests, seeded data, a bounded timeout, and a fresh database per
case. Never point this harness at production.

This fixture is synthetic and is not an external pilot or benchmark result.
