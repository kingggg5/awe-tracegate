"""AWE's keyless, evidence-gated workflow compilation core."""

from .compiler import compile_traces
from .contracts import (
    CompilationCandidate,
    CompilationReceipt,
    CompileRequest,
    ExecutionTrace,
)

__all__ = [
    "CompilationCandidate",
    "CompilationReceipt",
    "CompileRequest",
    "ExecutionTrace",
    "compile_traces",
]

__version__ = "0.1.0"
