"""Command-line interface for offline AWE trace compilation."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from .compiler import compile_traces
from .contracts import CompileRequest, ExecutionTrace


def _load_jsonl(path: Path) -> tuple[ExecutionTrace, ...]:
    traces: list[ExecutionTrace] = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                traces.append(ExecutionTrace.model_validate_json(line))
            except ValidationError as error:
                raise ValueError(
                    f"invalid trace at {path}:{line_number}: {error}"
                ) from error
    return CompileRequest(traces=tuple(traces)).traces


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="awe",
        description="AWE evidence-gated workflow compiler",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    compile_parser = subcommands.add_parser(
        "compile",
        help="compile repeated read-only execution traces",
    )
    compile_parser.add_argument(
        "--traces",
        type=Path,
        required=True,
        help="UTF-8 JSONL file containing one awe.trace.v1 object per line",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command != "compile":
        return 1

    try:
        traces = _load_jsonl(args.traces)
        receipt = compile_traces(traces)
    except (OSError, ValueError, ValidationError) as error:
        print(f"awe: {error}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            receipt.model_dump(mode="json", exclude_none=False),
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if receipt.status == "compiled" else 2


if __name__ == "__main__":
    raise SystemExit(main())
