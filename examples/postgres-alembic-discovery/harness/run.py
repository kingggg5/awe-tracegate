"""Run a disposable PostgreSQL/Alembic migration case and emit AWE evidence."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from pathlib import Path
from typing import Any

try:
    import psycopg
    from alembic import command
    from alembic.config import Config
except ImportError as error:  # pragma: no cover - exercised by install docs
    raise SystemExit(
        "Install harness dependencies from harness/requirements.txt first"
    ) from error

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parents[3] / "src"))
from awe_tracegate.contracts import canonical_digest  # noqa: E402


def _json_safe(value: Any) -> Any:
    """Normalize driver-specific scalar values before hashing evidence."""

    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return value


def _check(name: str, outcome: str, evidence: Any) -> dict[str, Any]:
    return {
        "name": name,
        "outcome": outcome,
        "duration_ms": 0,
        "evidence_digest": canonical_digest(_json_safe(evidence)),
    }


def _run_alembic(dsn: str, schema: str, revision: str) -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    os.environ["AWE_HARNESS_DATABASE_URL"] = dsn
    os.environ["AWE_HARNESS_SCHEMA"] = schema
    if revision == "head":
        command.upgrade(config, "head")
    else:
        command.downgrade(config, revision)


def _column_exists(
    connection: psycopg.Connection[Any], schema: str, column: str
) -> bool:
    row = connection.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = %s AND table_name = 'accounts' AND column_name = %s
        """,
        (schema, column),
    ).fetchone()
    return row is not None


def run(args: argparse.Namespace) -> dict[str, Any]:
    if len(args.commit_sha) not in (40, 64):
        raise ValueError("commit-sha must be a 40- or 64-character hexadecimal SHA")
    try:
        int(args.commit_sha, 16)
    except ValueError as error:
        raise ValueError("commit-sha must be hexadecimal") from error

    schema = "awe_harness_" + secrets.token_hex(8)
    checks: dict[str, dict[str, Any]] = {}
    try:
        with psycopg.connect(args.dsn, autocommit=True) as connection:
            connection.execute(f'CREATE SCHEMA "{schema}"')
            connection.execute(f'SET search_path TO "{schema}"')
            connection.execute(
                "CREATE TABLE accounts (id integer PRIMARY KEY, email text NOT NULL)"
            )
            with connection.cursor() as cursor:
                cursor.executemany(
                    "INSERT INTO accounts (id, email) VALUES (%s, %s)",
                    [(1, "one@example.test"), (2, "two@example.test")],
                )
            before = connection.execute(
                "SELECT id, email FROM accounts ORDER BY id"
            ).fetchall()

            try:
                _run_alembic(args.dsn, schema, "head")
                head_ok = _column_exists(connection, schema, "display_name")
                checks["forward_migration"] = _check(
                    "forward_migration",
                    "success" if head_ok else "failure",
                    {"column": head_ok},
                )
            except Exception as error:
                checks["forward_migration"] = _check(
                    "forward_migration",
                    "infrastructure_error",
                    {"error": type(error).__name__},
                )

            after_forward = connection.execute(
                "SELECT id, email FROM accounts ORDER BY id"
            ).fetchall()
            checks["data_preservation"] = _check(
                "data_preservation",
                "success" if before == after_forward else "failure",
                {"before": before, "after_forward": after_forward},
            )

            try:
                _run_alembic(args.dsn, schema, "base")
                rollback_ok = not _column_exists(connection, schema, "display_name")
                checks["rollback"] = _check(
                    "rollback",
                    "success" if rollback_ok else "failure",
                    {"column_absent": rollback_ok},
                )
            except Exception as error:
                checks["rollback"] = _check(
                    "rollback",
                    "infrastructure_error",
                    {"error": type(error).__name__},
                )

            after_rollback = connection.execute(
                "SELECT id, email FROM accounts ORDER BY id"
            ).fetchall()
            checks["tests"] = _check(
                "tests",
                "success" if before == after_rollback else "failure",
                {"rows_preserved_after_rollback": before == after_rollback},
            )
    finally:
        try:
            with psycopg.connect(args.dsn, autocommit=True) as cleanup:
                cleanup.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        except Exception:
            pass

    ordered_checks = [
        checks[name]
        for name in ("data_preservation", "forward_migration", "rollback", "tests")
    ]
    return {
        "schema_version": "awe.postgres-alembic-experiment.v1",
        "experiment_id": "postgres-alembic-real-fixture-v1",
        "repository_uri": args.repository,
        "commit_sha": args.commit_sha,
        "subject_digest": canonical_digest(
            {"fixture": "accounts", "migration": "add_display_name"}
        ),
        "dataset_digest": canonical_digest({"seed_rows": 2}),
        "dataset_split_digest": canonical_digest({"split": "migration-fixture-v1"}),
        "harness_name": "awe-postgres-alembic-harness",
        "harness_version": "1.0.0",
        "harness_digest": canonical_digest(
            {"source": Path(__file__).read_text(encoding="utf-8")}
        ),
        "strategy_name": "external-coding-agent",
        "strategy_digest": canonical_digest({"strategy": "external-coding-agent"}),
        "model_provider": "external",
        "model_name": "external-coding-agent",
        "model_config_digest": canonical_digest({"config": "caller-supplied"}),
        "environment_digest": canonical_digest({"postgres": "caller-supplied"}),
        "grader_digest": canonical_digest({"grader": "four-lane-sql-checks-v1"}),
        "trials": [
            {
                "trial_id": "postgres-alembic-real-fixture-trial",
                "case_id": "add-column-preserve-rows",
                "seed": 7,
                "checks": ordered_checks,
                "cost_microusd": 0,
                "input_tokens": 0,
                "cached_input_tokens": 0,
                "output_tokens": 0,
            }
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args)
        if args.out.exists():
            raise ValueError(f"refusing to overwrite {args.out}")
        args.out.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
