"""Minimal keyless HTTP surface for AWE compilation."""

from fastapi import FastAPI

from .compiler import compile_traces
from .contracts import CompilationReceipt, CompileRequest, HealthResponse


def create_app() -> FastAPI:
    application = FastAPI(
        title="AWE Harness",
        version="0.1.0",
        description="Evidence-gated read-only trace compiler",
    )

    @application.get("/healthz", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse()

    @application.post("/v1/compile", response_model=CompilationReceipt)
    def compile_workflow(request: CompileRequest) -> CompilationReceipt:
        return compile_traces(request.traces)

    return application


app = create_app()
