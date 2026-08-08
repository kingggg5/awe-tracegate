"""Command-line interface for AWE TraceGate's offline evidence path."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from .compiler import compile_traces
from .contracts import (
    CompilationReceipt,
    CompileRequest,
    EvaluationBundle,
    EvaluationPolicy,
    EvaluationReceipt,
    ExecutionTrace,
)
from .evaluation import evaluate_candidate
from .promotion import create_promotion_receipt
from .redaction import redact_json
from .schemas import export_schemas
from .verifier import verify_compilation_receipt

ModelT = TypeVar("ModelT", bound=BaseModel)


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


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_model(path: Path, model: type[ModelT]) -> ModelT:
    return model.model_validate(_load_json(path))


def _serialize(value: Any) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json", exclude_none=False)
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def _emit(value: Any, output: Path | None = None) -> None:
    rendered = _serialize(value) + "\n"
    if output is None:
        print(rendered, end="")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        print(output)


def _add_output(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--out", type=Path, help="write JSON to this path")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="awe",
        description="AWE TraceGate evidence compiler and verifier",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    compile_parser = subcommands.add_parser(
        "compile", help="compile repeated read-only execution traces"
    )
    compile_parser.add_argument("--traces", type=Path, required=True)
    _add_output(compile_parser)

    verify_parser = subcommands.add_parser(
        "verify", help="recompute a receipt and optional source traces"
    )
    verify_parser.add_argument("--receipt", type=Path, required=True)
    verify_parser.add_argument("--traces", type=Path)
    _add_output(verify_parser)

    schema_parser = subcommands.add_parser(
        "schema", help="export versioned JSON Schema documents"
    )
    schema_parser.add_argument("--out-dir", type=Path, required=True)

    evaluate_parser = subcommands.add_parser(
        "evaluate", help="compare candidate results with a frozen baseline"
    )
    evaluate_parser.add_argument("--baseline", type=Path, required=True)
    evaluate_parser.add_argument("--candidate", type=Path, required=True)
    evaluate_parser.add_argument("--policy", type=Path)
    _add_output(evaluate_parser)

    promote_parser = subcommands.add_parser(
        "promote", help="record an actor-bound human decision"
    )
    promote_parser.add_argument("--evaluation", type=Path, required=True)
    promote_parser.add_argument(
        "--decision", choices=("approved", "rejected"), required=True
    )
    promote_parser.add_argument("--actor", required=True)
    promote_parser.add_argument("--commit-sha", required=True)
    promote_parser.add_argument("--issued-at", required=True)
    promote_parser.add_argument("--rationale", required=True)
    _add_output(promote_parser)

    redact_parser = subcommands.add_parser(
        "redact", help="redact common secret and PII patterns from JSON"
    )
    redact_parser.add_argument("--input", type=Path, required=True)
    redact_parser.add_argument("--summary", type=Path)
    _add_output(redact_parser)
    return parser


def _compile(args: argparse.Namespace) -> int:
    receipt = compile_traces(_load_jsonl(args.traces))
    _emit(receipt, args.out)
    return 0 if receipt.status == "compiled" else 2


def _verify(args: argparse.Namespace) -> int:
    receipt = _load_model(args.receipt, CompilationReceipt)
    traces = _load_jsonl(args.traces) if args.traces else None
    result = verify_compilation_receipt(receipt, traces)
    _emit(result, args.out)
    return 0 if result.status == "valid" else 2


def _schema(args: argparse.Namespace) -> int:
    written = export_schemas(args.out_dir)
    print("\n".join(str(path) for path in written))
    return 0


def _evaluate(args: argparse.Namespace) -> int:
    baseline = _load_model(args.baseline, EvaluationBundle)
    candidate = _load_model(args.candidate, EvaluationBundle)
    policy = (
        _load_model(args.policy, EvaluationPolicy)
        if args.policy
        else EvaluationPolicy()
    )
    receipt = evaluate_candidate(baseline, candidate, policy)
    _emit(receipt, args.out)
    return 0 if receipt.status == "pass" else 2


def _promote(args: argparse.Namespace) -> int:
    evaluation = _load_model(args.evaluation, EvaluationReceipt)
    issued_at = datetime.fromisoformat(args.issued_at.replace("Z", "+00:00"))
    receipt = create_promotion_receipt(
        evaluation,
        decision=args.decision,
        actor_id=args.actor,
        commit_sha=args.commit_sha,
        issued_at=issued_at,
        rationale=args.rationale,
    )
    _emit(receipt, args.out)
    return 0


def _redact(args: argparse.Namespace) -> int:
    redacted, summary = redact_json(_load_json(args.input))
    _emit(redacted, args.out)
    if args.summary is not None:
        _emit(summary, args.summary)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    handlers = {
        "compile": _compile,
        "evaluate": _evaluate,
        "promote": _promote,
        "redact": _redact,
        "schema": _schema,
        "verify": _verify,
    }
    try:
        return handlers[args.command](args)
    except (
        KeyError,
        OSError,
        ValueError,
        json.JSONDecodeError,
        ValidationError,
    ) as error:
        print(f"awe: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
