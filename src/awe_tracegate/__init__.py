"""AWE TraceGate's keyless, evidence-gated workflow review core."""

__version__ = "0.2.0"

from .adapters import import_generic_evaluation, import_otel_genai_evaluation
from .compiler import compile_traces
from .contracts import (
    CompilationCandidate,
    CompilationReceipt,
    CompileRequest,
    EvaluationReceipt,
    ExecutionTrace,
    ExperimentManifest,
    PromotionReceipt,
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
    "ExperimentManifest",
    "PromotionReceipt",
    "ReceiptVerification",
    "compile_traces",
    "evaluate_candidate",
    "import_generic_evaluation",
    "import_otel_genai_evaluation",
    "verify_compilation_receipt",
]
