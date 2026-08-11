"""Command-line interface for AWE TraceGate's offline evidence path."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, NoReturn, TypeVar

from pydantic import BaseModel, TypeAdapter, ValidationError

from . import __version__
from .adapters import (
    evaluation_bundle_from_manifest,
    import_generic_evaluation,
    import_otel_genai_evaluation,
)
from .capabilities import describe_capabilities
from .compiler import compile_traces
from .contracts import (
    ComparisonPolicy,
    ComparisonReceipt,
    CompilationReceipt,
    CompileRequest,
    DatasetConsentRecord,
    EvaluationBundle,
    EvaluationPolicy,
    EvaluationReceipt,
    EvidencePackage,
    ExecutionTrace,
    ExperimentManifest,
    ExperimentQualityEvidence,
    ExperimentQualityReceipt,
    GateReceipt,
    GateReceiptV2,
    GitCommitSha,
    GovernedRedactionSummary,
    QualityPolicy,
    ReceiptVerification,
    RedactionPolicy,
    RedactionSummary,
    RepositoryUri,
    SensitivityPolicy,
    SensitivityReceipt,
    SignedReceiptBundle,
    SkillBom,
)
from .demo import generate_demo, inspect_review_bundle
from .evaluation import (
    compare_experiments,
    evaluate_candidate,
    verify_comparison_receipt_inputs,
)
from .evidence import validate_evidence_envelope
from .explain import ExplainableReceipt, explain_receipt
from .gate import gate_evidence, gate_evidence_v2
from .promotion import create_promotion_receipt
from .quality import assess_experiment_quality
from .recipes import (
    RecipeId,
    decision_recipe_catalog,
    get_decision_recipe,
    initialize_evidence_workspace,
)
from .redaction import redact_governed_json, redact_json
from .schemas import export_schemas
from .sensitivity import assess_sensitivity
from .skill_bom import inspect_skill
from .verifier import verify_compilation_receipt

ModelT = TypeVar("ModelT", bound=BaseModel)


class _AweArgumentParser(argparse.ArgumentParser):
    """Route malformed CLI usage to the contract's exit code 1."""

    def error(self, message: str) -> NoReturn:
        raise ValueError(message)


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


def _load_explainable_receipt(path: Path) -> ExplainableReceipt:
    """Load one known receipt type without accepting an untyped JSON blob."""

    payload = _load_json(path)
    schema_version = (
        payload.get("schema_version") if isinstance(payload, dict) else None
    )
    models: dict[str, type[BaseModel]] = {
        "awe.comparison-receipt.v1": ComparisonReceipt,
        "awe.experiment-quality-receipt.v1": ExperimentQualityReceipt,
        "awe.gate-receipt.v1": GateReceipt,
        "awe.gate-receipt.v2": GateReceiptV2,
        "awe.sensitivity-receipt.v1": SensitivityReceipt,
    }
    model = models.get(schema_version) if isinstance(schema_version, str) else None
    if model is None:
        raise ValueError("unsupported receipt schema for explain")
    return model.model_validate(payload)  # type: ignore[return-value]


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
        output.write_bytes(rendered.encode("utf-8"))
        print(output)


def _add_output(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--out", type=Path, help="write JSON to this path")


def _port(value: str) -> int:
    port = int(value)
    if not 1 <= port <= 65_535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def _build_parser() -> argparse.ArgumentParser:
    parser = _AweArgumentParser(
        prog="awe",
        description="AWE TraceGate evidence compiler and verifier",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    capabilities_parser = subcommands.add_parser(
        "capabilities", help="print the machine-readable offline core surface"
    )
    capabilities_parser.add_argument(
        "--json",
        action="store_true",
        help="emit JSON (the only stable output format)",
    )

    demo_parser = subcommands.add_parser(
        "demo", help="generate and run the complete offline synthetic Gate v2 demo"
    )
    demo_parser.add_argument(
        "--out",
        type=Path,
        default=Path("awe-demo"),
        help="empty output directory (default: ./awe-demo)",
    )
    demo_parser.add_argument(
        "--json", action="store_true", help="emit the machine-readable fixture summary"
    )

    doctor_parser = subcommands.add_parser(
        "doctor", help="replay every decision-bearing link in a Gate v2 bundle"
    )
    doctor_parser.add_argument("bundle", type=Path, nargs="?", default=Path("awe-demo"))
    doctor_parser.add_argument(
        "--json", action="store_true", help="emit the versioned readiness report"
    )

    recipes_parser = subcommands.add_parser(
        "recipes", help="list decision-first evidence paths without running an agent"
    )
    recipes_parser.add_argument(
        "--show",
        choices=(
            "ci_gate",
            "controlled_comparison",
            "harness_import",
            "promotion_review",
            "share_evidence",
        ),
        help="show one complete recipe",
    )
    recipes_parser.add_argument(
        "--json", action="store_true", help="emit the versioned catalog or recipe"
    )

    init_parser = subcommands.add_parser(
        "init", help="create a policy-only evidence workspace from a decision recipe"
    )
    init_parser.add_argument(
        "--recipe",
        required=True,
        choices=(
            "ci_gate",
            "controlled_comparison",
            "harness_import",
            "promotion_review",
            "share_evidence",
        ),
    )
    init_parser.add_argument("--out", type=Path, required=True)
    init_parser.add_argument(
        "--dry-run", action="store_true", help="show the managed files without writing"
    )
    init_parser.add_argument(
        "--json", action="store_true", help="emit the versioned scaffold manifest"
    )

    gate_parser = subcommands.add_parser(
        "gate", help="atomically compile, replay, and evaluate exact evidence"
    )
    gate_parser.add_argument("--traces", type=Path, required=True)
    gate_parser.add_argument("--baseline", type=Path, required=True)
    gate_parser.add_argument("--candidate", type=Path, required=True)
    gate_parser.add_argument("--policy", type=Path)
    gate_parser.add_argument("--skill-bom", type=Path)
    gate_parser.add_argument("--evidence-package", type=Path)
    gate_parser.add_argument("--repository")
    gate_parser.add_argument("--commit-sha")
    gate_parser.add_argument("--max-age-seconds", type=int)
    gate_parser.add_argument(
        "--minimum-provenance",
        choices=("asserted",),
        help=(
            "enforce declared provenance only; cryptographic and attestation "
            "verification are not yet implemented"
        ),
    )
    gate_parser.add_argument(
        "--evaluated-at",
        help="explicit RFC 3339 UTC time used by the max-age check",
    )
    _add_output(gate_parser)

    conformance_parser = subcommands.add_parser(
        "conformance", help="validate a provider-neutral evidence envelope"
    )
    conformance_parser.add_argument("--envelope", type=Path, required=True)
    _add_output(conformance_parser)

    skill_parser = subcommands.add_parser(
        "skill", help="inspect portable Agent Skill artifacts without execution"
    )
    skill_subcommands = skill_parser.add_subparsers(dest="skill_command", required=True)
    skill_inspect_parser = skill_subcommands.add_parser(
        "inspect", help="create a content-addressed Skill BOM"
    )
    skill_inspect_parser.add_argument("--path", type=Path, required=True)
    _add_output(skill_inspect_parser)

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

    compare_parser = subcommands.add_parser(
        "compare",
        help="assess success evidence on controlled frozen paired cases",
    )
    compare_parser.add_argument("--baseline", type=Path, required=True)
    compare_parser.add_argument("--candidate", type=Path, required=True)
    compare_parser.add_argument("--policy", type=Path)
    _add_output(compare_parser)

    verify_comparison_parser = subcommands.add_parser(
        "verify-comparison",
        help="replay a comparison receipt against explicit held experiment inputs",
    )
    verify_comparison_parser.add_argument("--receipt", type=Path, required=True)
    verify_comparison_parser.add_argument("--baseline", type=Path, required=True)
    verify_comparison_parser.add_argument("--candidate", type=Path, required=True)
    verify_comparison_parser.add_argument("--policy", type=Path)
    _add_output(verify_comparison_parser)

    quality_parser = subcommands.add_parser(
        "assess-quality",
        help="assess typed terminal outcomes and asserted judge calibration",
    )
    quality_parser.add_argument("--experiment", type=Path, required=True)
    quality_parser.add_argument("--evidence", type=Path, required=True)
    quality_parser.add_argument("--policy", type=Path)
    _add_output(quality_parser)

    sensitivity_parser = subcommands.add_parser(
        "sensitivity",
        help="measure supplied environment and seed sensitivity without execution",
    )
    sensitivity_parser.add_argument(
        "--experiment", type=Path, required=True, action="append"
    )
    sensitivity_parser.add_argument("--policy", type=Path)
    _add_output(sensitivity_parser)

    gate_v2_parser = subcommands.add_parser(
        "gate-v2",
        help="combine Gate v1, held-input comparison replay, and quality evidence",
    )
    gate_v2_parser.add_argument("--traces", type=Path, required=True)
    gate_v2_parser.add_argument("--baseline", type=Path, required=True)
    gate_v2_parser.add_argument("--candidate", type=Path, required=True)
    gate_v2_parser.add_argument("--evaluation-policy", type=Path)
    gate_v2_parser.add_argument("--comparison", type=Path, required=True)
    gate_v2_parser.add_argument("--baseline-experiment", type=Path, required=True)
    gate_v2_parser.add_argument("--candidate-experiment", type=Path, required=True)
    gate_v2_parser.add_argument("--comparison-policy", type=Path)
    gate_v2_parser.add_argument("--baseline-quality", type=Path)
    gate_v2_parser.add_argument("--candidate-quality", type=Path)
    gate_v2_parser.add_argument("--quality-policy", type=Path)
    gate_v2_parser.add_argument("--skill-bom", type=Path)
    gate_v2_parser.add_argument("--evidence-package", type=Path)
    gate_v2_parser.add_argument("--repository")
    gate_v2_parser.add_argument("--commit-sha")
    gate_v2_parser.add_argument("--max-age-seconds", type=int)
    gate_v2_parser.add_argument("--minimum-provenance", choices=("asserted",))
    gate_v2_parser.add_argument("--evaluated-at")
    _add_output(gate_v2_parser)

    explain_parser = subcommands.add_parser(
        "explain", help="emit a deterministic evidence graph for a parsed receipt"
    )
    explain_parser.add_argument(
        "receipt_path", type=Path, nargs="?", help="receipt path shorthand"
    )
    explain_parser.add_argument("--receipt", type=Path, help="receipt path")
    _add_output(explain_parser)

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
            "gate",
            "evidence_package",
            "promotion",
            "skill_bom",
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


def _capabilities(args: argparse.Namespace) -> int:
    _emit(describe_capabilities(__version__))
    return 0


def _demo(args: argparse.Namespace) -> int:
    generate_demo(args.out)
    metadata = _load_json(args.out / "fixture.json")
    if args.json:
        _emit(metadata)
        return 0
    expected = metadata["expected"]
    print("AWE TraceGate synthetic demo")
    print(f"  Gate v2             {expected['gate_v2_status']}")
    print(f"  Comparison          {expected['comparison_status']}")
    print(f"  Comparison replay   {expected['comparison_verification_status']}")
    print(
        "  Quality             "
        f"baseline={expected['baseline_quality_status']} "
        f"candidate={expected['candidate_quality_status']}"
    )
    print(f"  Receipt              {expected['gate_v2_receipt_hash']}")
    print(f"  Evidence graph       {expected['explanation_hash']}")
    print(f"  Artifacts             {args.out.resolve()}")
    print("  Scope                 synthetic, offline, no model or network calls")
    print(f"\nNext: awe doctor {args.out}")
    return 0


def _doctor(args: argparse.Namespace) -> int:
    report = inspect_review_bundle(args.bundle)
    if args.json:
        _emit(report)
    else:
        print(f"AWE review bundle: {report.status}")
        for check in report.checks:
            marker = "PASS" if check.status == "pass" else "FAIL"
            print(f"  [{marker}] {check.check_id}: {check.detail}")
        if report.gate_v2_status is not None:
            print(f"\n  Decision      {report.gate_v2_status}")
            print(f"  Receipt       {report.gate_v2_receipt_hash}")
            print(f"  Evidence graph {report.explanation_hash}")
        for action in report.next_actions:
            print(f"\nNext: {action}")
    return 0 if report.status == "READY" else 2


def _recipes(args: argparse.Namespace) -> int:
    if args.show:
        recipe = get_decision_recipe(args.show)
        if args.json:
            _emit(recipe)
            return 0
        print(f"{recipe.title} ({recipe.recipe_id})")
        print(f"  Decision: {recipe.question}")
        print(f"  Result:   {recipe.outcome}")
        print("\nCommands:")
        for command in recipe.commands:
            print(f"  {command}")
        print("\nFail closed when:")
        for condition in recipe.fail_closed_when:
            print(f"  - {condition}")
        return 0

    catalog = decision_recipe_catalog()
    if args.json:
        _emit(catalog)
        return 0
    print("AWE decision recipes")
    print("Choose the engineering decision first; TraceGate never runs the agent.\n")
    for recipe in catalog.recipes:
        print(f"  {recipe.recipe_id:<24} {recipe.question}")
    print("\nInspect: awe recipes --show promotion_review")
    print("Create:  awe init --recipe promotion_review --out awe-evidence")
    return 0


def _init(args: argparse.Namespace) -> int:
    recipe_id: RecipeId = args.recipe
    manifest = initialize_evidence_workspace(
        args.out,
        recipe_id,
        dry_run=args.dry_run,
    )
    if args.json:
        _emit(manifest)
        return 0
    action = "Would create" if args.dry_run else "Created"
    print(f"{action} AWE evidence workspace for {recipe_id}")
    for file in manifest.files:
        print(f"  {file.path}")
    print("  awe-recipe.json")
    print("\nNo traces, results, consent, receipts, or decisions were generated.")
    if not args.dry_run:
        print(f"Next: review {args.out / 'README.md'}")
    return 0


def _gate(args: argparse.Namespace) -> int:
    policy = (
        _load_model(args.policy, EvaluationPolicy)
        if args.policy
        else EvaluationPolicy()
    )
    evidence_package = (
        _load_model(args.evidence_package, EvidencePackage)
        if args.evidence_package
        else None
    )
    skill_bom = _load_model(args.skill_bom, SkillBom) if args.skill_bom else None
    evaluated_at = (
        datetime.fromisoformat(args.evaluated_at.replace("Z", "+00:00"))
        if args.evaluated_at
        else None
    )
    repository = (
        TypeAdapter(RepositoryUri).validate_python(args.repository)
        if args.repository
        else None
    )
    commit_sha = (
        TypeAdapter(GitCommitSha).validate_python(args.commit_sha)
        if args.commit_sha
        else None
    )
    receipt = gate_evidence(
        _load_jsonl(args.traces),
        _load_model(args.baseline, EvaluationBundle),
        _load_model(args.candidate, EvaluationBundle),
        policy,
        evidence_package=evidence_package,
        expected_repository=repository,
        expected_commit_sha=commit_sha,
        evaluated_at=evaluated_at,
        maximum_age_seconds=args.max_age_seconds,
        minimum_provenance_level=args.minimum_provenance,
        skill_bom=skill_bom,
    )
    _emit(receipt, args.out)
    if receipt.status == "PASS":
        return 0
    if receipt.status in ("REVIEW", "BLOCK"):
        return 2
    return 1


def _conformance(args: argparse.Namespace) -> int:
    receipt = validate_evidence_envelope(_load_json(args.envelope))
    _emit(receipt, args.out)
    return 0 if receipt.status == "valid" else 2


def _skill(args: argparse.Namespace) -> int:
    if args.skill_command != "inspect":
        raise ValueError(f"unsupported skill command: {args.skill_command}")
    _emit(inspect_skill(args.path), args.out)
    return 0


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


def _compare(args: argparse.Namespace) -> int:
    baseline = _load_model(args.baseline, ExperimentManifest)
    candidate = _load_model(args.candidate, ExperimentManifest)
    policy = (
        _load_model(args.policy, ComparisonPolicy)
        if args.policy
        else ComparisonPolicy()
    )
    receipt = compare_experiments(baseline, candidate, policy)
    _emit(receipt, args.out)
    return 0 if receipt.status == "pass" else 2


def _verify_comparison(args: argparse.Namespace) -> int:
    policy = (
        _load_model(args.policy, ComparisonPolicy)
        if args.policy
        else ComparisonPolicy()
    )
    result = verify_comparison_receipt_inputs(
        _load_model(args.receipt, ComparisonReceipt),
        _load_model(args.baseline, ExperimentManifest),
        _load_model(args.candidate, ExperimentManifest),
        policy,
    )
    _emit(result, args.out)
    return 0 if result.status == "valid" else 2


def _assess_quality(args: argparse.Namespace) -> int:
    policy = _load_model(args.policy, QualityPolicy) if args.policy else QualityPolicy()
    receipt = assess_experiment_quality(
        _load_model(args.experiment, ExperimentManifest),
        _load_model(args.evidence, ExperimentQualityEvidence),
        policy,
    )
    _emit(receipt, args.out)
    return 0 if receipt.status == "pass" else 2


def _sensitivity(args: argparse.Namespace) -> int:
    policy = (
        _load_model(args.policy, SensitivityPolicy)
        if args.policy
        else SensitivityPolicy()
    )
    receipt = assess_sensitivity(
        tuple(_load_model(path, ExperimentManifest) for path in args.experiment),
        policy,
    )
    _emit(receipt, args.out)
    return 0 if receipt.status == "pass" else 2


def _gate_v2(args: argparse.Namespace) -> int:
    evaluation_policy = (
        _load_model(args.evaluation_policy, EvaluationPolicy)
        if args.evaluation_policy
        else EvaluationPolicy()
    )
    comparison_policy = (
        _load_model(args.comparison_policy, ComparisonPolicy)
        if args.comparison_policy
        else ComparisonPolicy()
    )
    quality_policy = (
        _load_model(args.quality_policy, QualityPolicy)
        if args.quality_policy
        else QualityPolicy()
    )
    evidence_package = (
        _load_model(args.evidence_package, EvidencePackage)
        if args.evidence_package
        else None
    )
    skill_bom = _load_model(args.skill_bom, SkillBom) if args.skill_bom else None
    provenance_requested = any(
        value is not None
        for value in (
            args.repository,
            args.commit_sha,
            args.evaluated_at,
            args.max_age_seconds,
            args.minimum_provenance,
        )
    )
    if evidence_package is None and provenance_requested:
        raise ValueError("repository, commit, and age checks require evidence package")
    evaluated_at = (
        datetime.fromisoformat(args.evaluated_at.replace("Z", "+00:00"))
        if args.evaluated_at
        else None
    )
    receipt = gate_evidence_v2(
        _load_jsonl(args.traces),
        _load_model(args.baseline, EvaluationBundle),
        _load_model(args.candidate, EvaluationBundle),
        evaluation_policy,
        _load_model(args.comparison, ComparisonReceipt),
        _load_model(args.baseline_experiment, ExperimentManifest),
        _load_model(args.candidate_experiment, ExperimentManifest),
        comparison_policy,
        baseline_quality_evidence=(
            _load_model(args.baseline_quality, ExperimentQualityEvidence)
            if args.baseline_quality
            else None
        ),
        candidate_quality_evidence=(
            _load_model(args.candidate_quality, ExperimentQualityEvidence)
            if args.candidate_quality
            else None
        ),
        quality_policy=quality_policy,
        evidence_package=evidence_package,
        expected_repository=(
            TypeAdapter(RepositoryUri).validate_python(args.repository)
            if args.repository
            else None
        ),
        expected_commit_sha=(
            TypeAdapter(GitCommitSha).validate_python(args.commit_sha)
            if args.commit_sha
            else None
        ),
        evaluated_at=evaluated_at,
        maximum_age_seconds=args.max_age_seconds,
        minimum_provenance_level=args.minimum_provenance,
        skill_bom=skill_bom,
    )
    _emit(receipt, args.out)
    if receipt.status == "PASS":
        return 0
    if receipt.status in ("REVIEW", "BLOCK"):
        return 2
    return 1


def _explain(args: argparse.Namespace) -> int:
    if args.receipt is not None and args.receipt_path is not None:
        raise ValueError("explain accepts either a receipt path or --receipt, not both")
    receipt_path = args.receipt or args.receipt_path
    if receipt_path is None:
        raise ValueError("explain requires a receipt path")
    _emit(explain_receipt(_load_explainable_receipt(receipt_path)), args.out)
    return 0


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
    try:
        args = _build_parser().parse_args(argv)
        handlers = {
            "capabilities": _capabilities,
            "assess-quality": _assess_quality,
            "compare": _compare,
            "compile": _compile,
            "conformance": _conformance,
            "demo": _demo,
            "doctor": _doctor,
            "evaluate": _evaluate,
            "gate": _gate,
            "gate-v2": _gate_v2,
            "init": _init,
            "import-experiment": _import_experiment,
            "promote": _promote,
            "redact": _redact,
            "recipes": _recipes,
            "schema": _schema,
            "serve": _serve,
            "sign": _sign,
            "sensitivity": _sensitivity,
            "skill": _skill,
            "verify": _verify,
            "verify-comparison": _verify_comparison,
            "verify-signature": _verify_signature,
            "explain": _explain,
        }
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
