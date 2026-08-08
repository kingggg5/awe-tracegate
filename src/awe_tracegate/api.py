"""Minimal keyless HTTP surface for local AWE TraceGate integration."""

from fastapi import FastAPI

from .compiler import compile_traces
from .contracts import (
    CompilationReceipt,
    CompileRequest,
    EvaluateRequest,
    EvaluationReceipt,
    HealthResponse,
    ReceiptVerification,
    VerifyRequest,
)
from .evaluation import evaluate_candidate
from .verifier import verify_compilation_receipt


def create_app() -> FastAPI:
    application = FastAPI(
        title="AWE TraceGate",
        version="0.1.0",
        description="Evidence-gated, read-only trace compiler and verifier",
    )

    @application.get("/healthz", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse()

    @application.post("/v1/compile", response_model=CompilationReceipt)
    def compile_workflow(request: CompileRequest) -> CompilationReceipt:
        return compile_traces(request.traces)

    @application.post("/v1/verify", response_model=ReceiptVerification)
    def verify_receipt(request: VerifyRequest) -> ReceiptVerification:
        return verify_compilation_receipt(request.receipt, request.traces)

    @application.post("/v1/evaluate", response_model=EvaluationReceipt)
    def evaluate(request: EvaluateRequest) -> EvaluationReceipt:
        return evaluate_candidate(request.baseline, request.candidate, request.policy)

    return application


app = create_app()
