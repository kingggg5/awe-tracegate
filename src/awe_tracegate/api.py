"""Minimal keyless HTTP surface for local AWE TraceGate integration."""

from functools import cache
from importlib.resources import files

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from . import __version__
from .adapters import import_generic_evaluation
from .compiler import compile_traces
from .contracts import (
    CompilationReceipt,
    CompileRequest,
    EvaluateRequest,
    EvaluationReceipt,
    ExperimentManifest,
    ExperimentRun,
    HealthResponse,
    PromotionReceipt,
    PromotionRequest,
    ReceiptVerification,
    VerifyRequest,
)
from .evaluation import evaluate_candidate
from .promotion import create_promotion_receipt
from .verifier import verify_compilation_receipt


@cache
def _review_workspace_page() -> str:
    """Load the immutable packaged UI once per process."""

    return (
        files("awe_tracegate")
        .joinpath("web")
        .joinpath("index.html")
        .read_text(encoding="utf-8")
    )


def create_app() -> FastAPI:
    application = FastAPI(
        title="AWE TraceGate",
        version=__version__,
        description="Evidence-gated, read-only trace compiler and verifier",
    )

    @application.get("/healthz", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse()

    @application.get("/", response_class=HTMLResponse, include_in_schema=False)
    def review_workspace() -> HTMLResponse:
        """Serve the local evidence-review surface without external assets."""

        return HTMLResponse(content=_review_workspace_page())

    @application.post("/v1/compile", response_model=CompilationReceipt)
    def compile_workflow(request: CompileRequest) -> CompilationReceipt:
        return compile_traces(request.traces)

    @application.post("/v1/verify", response_model=ReceiptVerification)
    def verify_receipt(request: VerifyRequest) -> ReceiptVerification:
        return verify_compilation_receipt(request.receipt, request.traces)

    @application.post("/v1/evaluate", response_model=EvaluationReceipt)
    def evaluate(request: EvaluateRequest) -> EvaluationReceipt:
        return evaluate_candidate(request.baseline, request.candidate, request.policy)

    @application.post(
        "/v1/experiments/import/generic", response_model=ExperimentManifest
    )
    def import_experiment(request: ExperimentRun) -> ExperimentManifest:
        return import_generic_evaluation(request.model_dump(mode="json"))

    @application.post("/v1/promote", response_model=PromotionReceipt)
    def promote(request: PromotionRequest) -> PromotionReceipt:
        return create_promotion_receipt(
            request.compilation,
            request.verification,
            request.traces,
            request.evaluation,
            decision=request.decision,
            actor_id=request.actor_id,
            commit_sha=request.commit_sha,
            issued_at=request.issued_at,
            rationale=request.rationale,
        )

    return application


app = create_app()
