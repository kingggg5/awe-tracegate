"""AWE TraceGate's keyless, evidence-gated workflow review core."""

from .compiler import compile_traces
from .contracts import (
    CompilationCandidate,
    CompilationReceipt,
    CompileRequest,
    EvaluationReceipt,
    ExecutionTrace,
    ReceiptVerification,
)
from .evaluation import evaluate_candidate
from .verifier import verify_compilation_receipt

__all__ = [
    "CompilationCandidate",
    "CompilationReceipt",
    "CompileRequest",
    "EvaluationReceipt",
    "ExecutionTrace",
    "ReceiptVerification",
    "compile_traces",
    "evaluate_candidate",
    "verify_compilation_receipt",
]

__version__ = "0.1.0"
