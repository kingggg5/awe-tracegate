from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from awe_tracegate.discovery import (
    AgentTraceReceipt,
    PostgresAlembicExperiment,
    build_migration_discovery_bundle,
    import_agent_trace,
)
from awe_tracegate.discovery_cli import main

REPOSITORY = "https://github.com/example/postgres-migrations"
COMMIT_SHA = "a" * 40
EVALUATED_AT = datetime(2026, 8, 11, 3, 0, tzinfo=UTC)
PROJECT_ROOT = Path(__file__).parents[1]


def _digest(character: str) -> str:
    return f"sha256:{character * 64}"


def _handoff(
    *,
    status: str = "active",
    expires_at: str | None = None,
    runner: str = "codex",
) -> dict[str, object]:
    consent: dict[str, object] = {
        "schema_version": "awe.trace-capture-consent.v1",
        "consent_id": "consent_01",
        "run_id": "run_01",
        "actor_id": "ari@example.com",
        "runner": runner,
        "scopes": ["capture_trace", "evaluate_migration"],
        "status": status,
        "granted_at": "2026-08-11T02:00:00Z",
    }
    if expires_at is not None:
        consent["expires_at"] = expires_at
    if status == "revoked":
        consent["revoked_at"] = "2026-08-11T02:30:00Z"
    return {
        "schema_version": "awe.runtime-handoff.v2",
        "run_id": "run_01",
        "state": "handoff_ready",
        "runner": runner,
        "trace_consent": consent,
    }


def _capture_only_handoff() -> dict[str, object]:
    handoff = _handoff()
    consent = handoff["trace_consent"]
    assert isinstance(consent, dict)
    consent["scopes"] = ["capture_trace"]
    return handoff


def _codex_lines() -> list[str]:
    return [
        json.dumps({"type": "thread.started", "thread_id": "thread-1"}),
        json.dumps({"type": "turn.started"}),
        json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "id": "item-1",
                    "type": "command_execution",
                    "command": "alembic upgrade head --secret never-store-this",
                    "status": "completed",
                    "aggregated_output": "customer@example.com",
                },
            }
        ),
        json.dumps(
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": 120,
                    "cached_input_tokens": 20,
                    "output_tokens": 30,
                },
            }
        ),
    ]


def _trace() -> AgentTraceReceipt:
    return import_agent_trace(
        _codex_lines(),
        source_format="codex.exec-jsonl",
        handoff=_handoff(),
        repository_uri=REPOSITORY,
        commit_sha=COMMIT_SHA,
        evaluated_at=EVALUATED_AT,
    )


def _migration() -> PostgresAlembicExperiment:
    return PostgresAlembicExperiment.model_validate(
        {
            "schema_version": "awe.postgres-alembic-experiment.v1",
            "experiment_id": "migration-exp-01",
            "repository_uri": REPOSITORY,
            "commit_sha": COMMIT_SHA,
            "subject_digest": _digest("1"),
            "dataset_digest": _digest("2"),
            "dataset_split_digest": _digest("3"),
            "harness_name": "postgres-alembic-harness",
            "harness_version": "1.0.0",
            "harness_digest": _digest("4"),
            "strategy_name": "baseline",
            "strategy_digest": _digest("5"),
            "model_provider": "openai",
            "model_name": "external-coding-agent",
            "model_config_digest": _digest("6"),
            "environment_digest": _digest("7"),
            "grader_digest": _digest("8"),
            "trials": [
                {
                    "trial_id": "migration-trial-01",
                    "case_id": "add-column-preserve-rows",
                    "seed": 7,
                    "checks": [
                        {
                            "name": "data_preservation",
                            "outcome": "failure",
                            "duration_ms": 12,
                            "evidence_digest": _digest("9"),
                        },
                        {
                            "name": "forward_migration",
                            "outcome": "success",
                            "duration_ms": 35,
                            "evidence_digest": _digest("a"),
                        },
                        {
                            "name": "rollback",
                            "outcome": "success",
                            "duration_ms": 31,
                            "evidence_digest": _digest("b"),
                        },
                        {
                            "name": "tests",
                            "outcome": "success",
                            "duration_ms": 80,
                            "evidence_digest": _digest("c"),
                        },
                    ],
                    "input_tokens": 120,
                    "cached_input_tokens": 20,
                    "output_tokens": 30,
                    "cost_microusd": 40,
                }
            ],
        }
    )


def test_imports_codex_jsonl_without_retaining_raw_content() -> None:
    receipt = _trace()

    assert receipt.terminal_outcome == "success"
    assert receipt.revision_binding == "caller_asserted"
    assert receipt.usage.input_tokens == 120
    assert receipt.events[2].operation == "alembic_upgrade"
    serialized = receipt.model_dump_json()
    assert "never-store-this" not in serialized
    assert "customer@example.com" not in serialized
    assert receipt == _trace()


def test_imports_claude_stream_json_usage_without_retaining_result_text() -> None:
    lines = [
        json.dumps({"type": "system", "subtype": "init", "session_id": "session-1"}),
        json.dumps({"type": "assistant", "message": {"content": "private output"}}),
        json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "duration_ms": 250,
                "total_cost_usd": "0.012",
                "usage": {"input_tokens": 90, "output_tokens": 24},
                "result": "do not retain this result",
            }
        ),
    ]

    receipt = import_agent_trace(
        lines,
        source_format="claude.stream-json",
        handoff=_handoff(runner="claude_code"),
        repository_uri=REPOSITORY,
        commit_sha=COMMIT_SHA,
        evaluated_at=EVALUATED_AT,
    )

    assert receipt.terminal_outcome == "success"
    assert receipt.usage.cost_microusd == 12_000
    assert receipt.usage.duration_ms == 250
    assert "private output" not in receipt.model_dump_json()
    assert "do not retain this result" not in receipt.model_dump_json()


@pytest.mark.parametrize(
    ("handoff", "message"),
    [
        (_handoff(status="revoked"), "revoked"),
        (_handoff(expires_at="2026-08-11T02:59:00Z"), "expired"),
    ],
)
def test_trace_import_fails_closed_without_active_consent(
    handoff: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        import_agent_trace(
            _codex_lines(),
            source_format="codex.exec-jsonl",
            handoff=handoff,
            repository_uri=REPOSITORY,
            commit_sha=COMMIT_SHA,
            evaluated_at=EVALUATED_AT,
        )


def test_trace_import_rejects_unapproved_handoff_and_duplicate_json_keys() -> None:
    handoff = _handoff()
    handoff["state"] = "awaiting_approval"
    with pytest.raises(ValueError, match="approved handoff"):
        import_agent_trace(
            _codex_lines(),
            source_format="codex.exec-jsonl",
            handoff=handoff,
            repository_uri=REPOSITORY,
            commit_sha=COMMIT_SHA,
            evaluated_at=EVALUATED_AT,
        )

    with pytest.raises(ValueError, match="duplicate key"):
        import_agent_trace(
            ['{"type":"turn.completed","type":"turn.failed"}'],
            source_format="codex.exec-jsonl",
            handoff=_handoff(),
            repository_uri=REPOSITORY,
            commit_sha=COMMIT_SHA,
            evaluated_at=EVALUATED_AT,
        )


def test_builds_a_deterministic_migration_bundle_and_failure_cluster() -> None:
    bundle = build_migration_discovery_bundle(_trace(), _migration())

    assert bundle.experiment_manifest.trials[0].succeeded is False
    assert bundle.experiment_manifest.trials[0].safety_violations == 1
    assert bundle.quality_evidence.trials[0].terminal_outcome == "failure"
    assert bundle.failure_report.clusters[0].category == "data_preservation"
    assert bundle == build_migration_discovery_bundle(_trace(), _migration())


def test_bundle_rejects_a_different_exact_commit() -> None:
    migration = _migration().model_copy(update={"commit_sha": "b" * 40})
    with pytest.raises(ValueError, match="commits differ"):
        build_migration_discovery_bundle(_trace(), migration)


def test_capture_only_consent_cannot_authorize_migration_evaluation() -> None:
    trace = import_agent_trace(
        _codex_lines(),
        source_format="codex.exec-jsonl",
        handoff=_capture_only_handoff(),
        repository_uri=REPOSITORY,
        commit_sha=COMMIT_SHA,
        evaluated_at=EVALUATED_AT,
    )
    with pytest.raises(ValueError, match="evaluate_migration"):
        build_migration_discovery_bundle(trace, _migration())


def test_migration_contract_requires_all_four_sorted_checks() -> None:
    payload = _migration().model_dump(mode="json")
    payload["trials"][0]["checks"] = list(reversed(payload["trials"][0]["checks"]))
    with pytest.raises(ValidationError, match="sorted order"):
        PostgresAlembicExperiment.model_validate(payload)


def test_discovery_cli_writes_portable_outputs_and_refuses_overwrite(
    tmp_path: Path,
) -> None:
    handoff_path = tmp_path / "handoff.json"
    trace_input = tmp_path / "codex.jsonl"
    trace_path = tmp_path / "trace-receipt.json"
    migration_path = tmp_path / "migration.json"
    out_dir = tmp_path / "bundle"
    handoff_path.write_text(json.dumps(_handoff()), encoding="utf-8")
    trace_input.write_text("\n".join(_codex_lines()) + "\n", encoding="utf-8")
    migration_path.write_text(_migration().model_dump_json(), encoding="utf-8")

    assert (
        main(
            [
                "ingest-trace",
                "--format",
                "codex.exec-jsonl",
                "--input",
                str(trace_input),
                "--handoff",
                str(handoff_path),
                "--repository",
                REPOSITORY,
                "--commit-sha",
                COMMIT_SHA,
                "--evaluated-at",
                "2026-08-11T03:00:00Z",
                "--out",
                str(trace_path),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "build-migration-bundle",
                "--trace",
                str(trace_path),
                "--input",
                str(migration_path),
                "--out-dir",
                str(out_dir),
            ]
        )
        == 0
    )
    assert (out_dir / "experiment-manifest.json").is_file()
    assert (out_dir / "failure-cluster-report.json").is_file()
    assert (
        main(
            [
                "build-migration-bundle",
                "--trace",
                str(trace_path),
                "--input",
                str(migration_path),
                "--out-dir",
                str(out_dir),
            ]
        )
        == 1
    )


def test_checked_in_postgres_alembic_example_runs_end_to_end(tmp_path: Path) -> None:
    fixture = PROJECT_ROOT / "examples" / "postgres-alembic-discovery"
    trace_path = tmp_path / "agent-trace-receipt.json"
    out_dir = tmp_path / "bundle"

    assert (
        main(
            [
                "ingest-trace",
                "--format",
                "codex.exec-jsonl",
                "--input",
                str(fixture / "codex-trace.jsonl"),
                "--handoff",
                str(fixture / "handoff.json"),
                "--repository",
                REPOSITORY,
                "--commit-sha",
                COMMIT_SHA,
                "--evaluated-at",
                "2026-08-11T03:00:00Z",
                "--out",
                str(trace_path),
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "build-migration-bundle",
                "--trace",
                str(trace_path),
                "--input",
                str(fixture / "migration-results.json"),
                "--out-dir",
                str(out_dir),
            ]
        )
        == 0
    )
    bundle = json.loads((out_dir / "migration-discovery-bundle.json").read_text())
    assert bundle["quality_evidence"]["trials"][0]["terminal_outcome"] == "failure"
    assert bundle["failure_report"]["clusters"][0]["category"] == "rollback"


def test_real_postgres_harness_contract_is_checked_in_and_non_executing() -> None:
    harness = PROJECT_ROOT / "examples" / "postgres-alembic-discovery" / "harness"
    assert (harness / "run.py").is_file()
    requirements = (harness / "requirements.txt").read_text(encoding="utf-8")
    assert "alembic" in requirements
    source = (harness / "run.py").read_text(encoding="utf-8")
    assert "awe.postgres-alembic-experiment.v1" in source
    assert "DROP SCHEMA IF EXISTS" in source
    assert "AWE_HARNESS_DATABASE_URL" in source
