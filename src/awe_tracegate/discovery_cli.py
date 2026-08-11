"""External-process CLI for consented coding-agent discovery artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, NoReturn

from pydantic import ValidationError

from .discovery import (
    MAX_AGENT_TRACE_BYTES,
    AgentTraceReceipt,
    PostgresAlembicExperiment,
    build_migration_discovery_bundle,
    import_agent_trace,
)


class DiscoveryArgumentParser(argparse.ArgumentParser):
    """Keep exit 2 available to TraceGate decisions, not malformed CLI use."""

    def error(self, message: str) -> NoReturn:
        raise ValueError(message)


def _parser() -> argparse.ArgumentParser:
    parser = DiscoveryArgumentParser(
        prog="awe-discovery",
        description=(
            "Normalize consented external coding-agent traces and frozen "
            "PostgreSQL/Alembic check results without executing them."
        ),
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    trace = subcommands.add_parser(
        "ingest-trace", help="redact and bind a frozen external agent JSONL stream"
    )
    trace.add_argument(
        "--format",
        choices=("codex.exec-jsonl", "claude.stream-json", "awe.agent-jsonl"),
        required=True,
    )
    trace.add_argument("--input", type=Path, required=True)
    trace.add_argument("--handoff", type=Path, required=True)
    trace.add_argument("--repository", required=True)
    trace.add_argument("--commit-sha", required=True)
    trace.add_argument("--evaluated-at", required=True)
    trace.add_argument("--out", type=Path, required=True)

    bundle = subcommands.add_parser(
        "build-migration-bundle",
        help="project isolated PostgreSQL/Alembic results into TraceGate artifacts",
    )
    bundle.add_argument("--trace", type=Path, required=True)
    bundle.add_argument("--input", type=Path, required=True)
    bundle.add_argument("--out-dir", type=Path, required=True)
    return parser


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError(f"cannot read valid JSON from {path}") from error


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("evaluated-at must be an RFC 3339 timestamp") from error
    if parsed.utcoffset() is None:
        raise ValueError("evaluated-at must include a timezone")
    return parsed


def _write_json(path: Path, value: Any) -> None:
    if path.exists():
        raise ValueError(f"refusing to overwrite {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
    path.write_bytes(
        (
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
    )


def _ingest_trace(args: argparse.Namespace) -> int:
    handoff = _load_json(args.handoff)
    if not isinstance(handoff, dict):
        raise ValueError("handoff must be a JSON object")
    try:
        if args.input.stat().st_size > MAX_AGENT_TRACE_BYTES:
            raise ValueError("agent trace exceeds the 32 MB total input limit")
        lines = args.input.read_bytes().splitlines()
    except OSError as error:
        raise ValueError(f"cannot read agent trace from {args.input}") from error
    receipt = import_agent_trace(
        lines,
        source_format=args.format,
        handoff=handoff,
        repository_uri=args.repository,
        commit_sha=args.commit_sha,
        evaluated_at=_timestamp(args.evaluated_at),
    )
    _write_json(args.out, receipt)
    print(args.out)
    return 0


def _build_bundle(args: argparse.Namespace) -> int:
    out_dir: Path = args.out_dir
    if out_dir.exists() and any(out_dir.iterdir()):
        raise ValueError(f"refusing non-empty output directory {out_dir}")
    trace = AgentTraceReceipt.model_validate(_load_json(args.trace))
    migration = PostgresAlembicExperiment.model_validate(_load_json(args.input))
    bundle = build_migration_discovery_bundle(trace, migration)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_json(out_dir / "migration-discovery-bundle.json", bundle)
    _write_json(out_dir / "experiment-manifest.json", bundle.experiment_manifest)
    _write_json(out_dir / "experiment-quality-evidence.json", bundle.quality_evidence)
    _write_json(out_dir / "failure-cluster-report.json", bundle.failure_report)
    print(out_dir)
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        if args.command == "ingest-trace":
            return _ingest_trace(args)
        if args.command == "build-migration-bundle":
            return _build_bundle(args)
        raise ValueError("unsupported discovery command")
    except (OSError, TypeError, ValueError, ValidationError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
