# Isolated PostgreSQL/Alembic harness

This directory is an external runner reference implementation. It is not
imported by TraceGate and it never receives production credentials. The runner
creates a fresh schema in the PostgreSQL database supplied by `--dsn`, seeds
two rows, executes the checked-in Alembic migration in both directions, and
emits the four-lane `awe.postgres-alembic-experiment.v1` artifact.

Install the optional runner dependencies:

```bash
python -m pip install -r examples/postgres-alembic-discovery/harness/requirements.txt
```

Run it only against an ephemeral PostgreSQL database:

```bash
python examples/postgres-alembic-discovery/harness/run.py \
  --dsn postgresql://awe_runner:awe_runner@127.0.0.1:5432/awe_runner \
  --repository https://github.com/your-org/your-repository \
  --commit-sha <40-hex-commit> \
  --out migration-results.json
```

The DSN is used only in memory and is never written to the result. The runner
drops its temporary schema in a `finally` block. A non-zero exit means the
artifact must not be consumed. The result is still only caller-asserted
provenance; sign it with the operator's trusted key before a Gate can require
signature verification. The CI job runs this exact runner against PostgreSQL
16 and fails unless all four lanes report `success`.
