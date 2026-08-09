"""Command-line interface for AWE TraceGate's offline evidence path."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from .adapters import (
    evaluation_bundle_from_manifest,
    import_generic_evaluation,
    import_otel_genai_evaluation,
)
from .compiler import compile_traces
from .contracts import (
    CompilationReceipt,
    CompileRequest,
    DatasetConsentRecord,
    EvaluationBundle,
    EvaluationPolicy,
    EvaluationReceipt,
    ExecutionTrace,
    GovernedRedactionSummary,
    ReceiptVerification,
    RedactionPolicy,
    RedactionSummary,
    SignedReceiptBundle,
)
from .evaluation import evaluate_candidate
from .promotion import create_promotion_receipt
from .redaction import redact_governed_json, redact_json
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


def _port(value: str) -> int:
    port = int(value)
    if not 1 <= port <= 65_535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


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

    serve_parser = subcommands.add_parser(
        "serve", help="start the local keyless Review Workspace"
    )
    serve_parser.add_argument(
        "--host",
        choices=("127.0.0.1", "localhost", "::1"),
        default="127.0.0.1",
        help="loopback address only (default: 127.0.0.1)",
    )
    serve_parser.add_argument("--port", type=_port, default=8765)

    import_parser = subcommands.add_parser(
        "import-experiment",
        help="import generic or pinned OpenTelemetry experiment evidence",
    )
    import_parser.add_argument("--input", type=Path, required=True)
    import_parser.add_argument(
        "--format", choices=("generic", "otel-genai"), required=True
    )
    import_parser.add_argument(
        "--evaluation-out",
        type=Path,
        help="also write the stable v1 evaluator projection",
    )
    _add_output(import_parser)

    evaluate_parser = subcommands.add_parser(
        "evaluate", help="compare candidate results with a frozen baseline"
    )
    evaluate_parser.add_argument("--baseline", type=Path, required=True)
    evaluate_parser.add_argument("--candidate", type=Path, required=True)
    evaluate_parser.add_argument("--policy", type=Path)
    _add_output(evaluate_parser)

    promote_parser = subcommands.add_parser(
        "promote", help="record a human decision from a replayed evidence chain"
    )
    promote_parser.add_argument("--compilation", type=Path, required=True)
    promote_parser.add_argument("--verification", type=Path, required=True)
    promote_parser.add_argument("--traces", type=Path, required=True)
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
    redact_parser.add_argument("--policy", type=Path)
    redact_parser.add_argument("--consent", type=Path)
    redact_parser.add_argument(
        "--scope", choices=("evaluation", "research", "training")
    )
    redact_parser.add_argument("--evaluated-at")
    _add_output(redact_parser)

    sign_parser = subcommands.add_parser(
        "sign", help="create a repository- and commit-bound Ed25519 bundle"
    )
    sign_parser.add_argument("--artifact", type=Path, required=True)
    sign_parser.add_argument(
        "--kind",
        choices=(
            "compilation",
            "verification",
            "evaluation",
            "experiment",
            "promotion",
        ),
        required=True,
    )
    sign_parser.add_argument("--private-key", type=Path, required=True)
    sign_parser.add_argument(
        "--private-key-password-env",
        help="environment variable containing the PEM password",
    )
    sign_parser.add_argument("--signer", required=True)
    sign_parser.add_argument("--repository", required=True)
    sign_parser.add_argument("--commit-sha", required=True)
    sign_parser.add_argument("--issued-at", required=True)
    _add_output(sign_parser)

    signature_parser = subcommands.add_parser(
        "verify-signature", help="verify a bundle against an explicitly trusted key"
    )
    signature_parser.add_argument("--bundle", type=Path, required=True)
    signature_parser.add_argument("--public-key", type=Path, required=True)
    signature_parser.add_argument("--signer", required=True)
    signature_parser.add_argument("--repository", required=True)
    signature_parser.add_argument("--commit-sha", required=True)
    _add_output(signature_parser)
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


def _serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn
    except ImportError as error:
        raise ValueError("the Review Workspace requires awe-tracegate[api]") from error

    display_host = "[::1]" if args.host == "::1" else args.host
    print(f"AWE TraceGate Review Workspace: http://{display_host}:{args.port}")
    print("Loopback only; no model credential or external service is required.")
    uvicorn.run(
        "awe_tracegate.api:app",
        host=args.host,
        port=args.port,
        log_level="info",
    )
    return 0


def _import_experiment(args: argparse.Namespace) -> int:
    payload = _load_json(args.input)
    importer = (
        import_generic_evaluation
        if args.format == "generic"
        else import_otel_genai_evaluation
    )
    manifest = importer(payload)
    _emit(manifest, args.out)
    if args.evaluation_out is not None:
        _emit(evaluation_bundle_from_manifest(manifest), args.evaluation_out)
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
    compilation = _load_model(args.compilation, CompilationReceipt)
    verification = _load_model(args.verification, ReceiptVerification)
    traces = _load_jsonl(args.traces)
    evaluation = _load_model(args.evaluation, EvaluationReceipt)
    issued_at = datetime.fromisoformat(args.issued_at.replace("Z", "+00:00"))
    receipt = create_promotion_receipt(
        compilation,
        verification,
        traces,
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
    redacted: Any
    summary: GovernedRedactionSummary | RedactionSummary
    governed_values = (args.policy, args.consent, args.scope, args.evaluated_at)
    if any(value is not None for value in governed_values):
        if not all(value is not None for value in governed_values):
            raise ValueError(
                "governed redaction requires policy, consent, scope, and evaluated-at"
            )
        policy = _load_model(args.policy, RedactionPolicy)
        consent = _load_model(args.consent, DatasetConsentRecord)
        evaluated_at = datetime.fromisoformat(args.evaluated_at.replace("Z", "+00:00"))
        redacted, summary = redact_governed_json(
            _load_json(args.input),
            policy,
            consent,
            scope=args.scope,
            evaluated_at=evaluated_at,
        )
    else:
        redacted, summary = redact_json(_load_json(args.input))
    _emit(redacted, args.out)
    if args.summary is not None:
        _emit(summary, args.summary)
    return 0


def _sign(args: argparse.Namespace) -> int:
    try:
        from .signing import create_signed_bundle
    except ImportError as error:
        raise ValueError("signing requires awe-tracegate[signing]") from error

    password: bytes | None = None
    if args.private_key_password_env is not None:
        value = os.environ.get(args.private_key_password_env)
        if value is None:
            raise ValueError(
                f"password environment variable is not set: "
                f"{args.private_key_password_env}"
            )
        password = value.encode("utf-8")
    bundle = create_signed_bundle(
        _load_json(args.artifact),
        artifact_kind=args.kind,
        repository_uri=args.repository,
        commit_sha=args.commit_sha,
        signer_id=args.signer,
        issued_at=datetime.fromisoformat(args.issued_at.replace("Z", "+00:00")),
        private_key_pem=args.private_key.read_bytes(),
        private_key_password=password,
    )
    _emit(bundle, args.out)
    return 0


def _verify_signature(args: argparse.Namespace) -> int:
    try:
        from .signing import verify_signed_bundle
    except ImportError as error:
        raise ValueError(
            "signature verification requires awe-tracegate[signing]"
        ) from error

    bundle = _load_model(args.bundle, SignedReceiptBundle)
    result = verify_signed_bundle(
        bundle,
        trusted_public_key_pem=args.public_key.read_bytes(),
        expected_signer_id=args.signer,
        expected_repository_uri=args.repository,
        expected_commit_sha=args.commit_sha,
    )
    _emit(result, args.out)
    return 0 if result.status == "valid" else 2


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    handlers = {
        "compile": _compile,
        "evaluate": _evaluate,
        "import-experiment": _import_experiment,
        "promote": _promote,
        "redact": _redact,
        "schema": _schema,
        "serve": _serve,
        "sign": _sign,
        "verify": _verify,
        "verify-signature": _verify_signature,
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
