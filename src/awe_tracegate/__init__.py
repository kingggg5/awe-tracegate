"""AWE TraceGate's keyless, evidence-gated workflow review core."""

__version__ = "0.3.0"

from .adapters import import_generic_evaluation, import_otel_genai_evaluation
from .compiler import compile_traces
from .contracts import (
    AdapterConformanceReceipt,
    CapabilitiesDocument,
    CompilationCandidate,
    CompilationReceipt,
    CompileRequest,
    EvaluationReceipt,
    EvidenceEnvelope,
    EvidencePackage,
    ExecutionTrace,
    ExperimentManifest,
    GateReceipt,
    PromotionReceipt,
    ReceiptVerification,
    SkillBom,
)
from .evaluation import evaluate_candidate
from .evidence import (
    create_evidence_envelope,
    create_evidence_package,
    validate_evidence_envelope,
)
from .gate import gate_evidence
from .skill_bom import inspect_skill
from .verifier import verify_compilation_receipt

__all__ = [
    "AdapterConformanceReceipt",
    "CapabilitiesDocument",
    "CompilationCandidate",
    "CompilationReceipt",
    "CompileRequest",
    "EvaluationReceipt",
    "EvidenceEnvelope",
    "EvidencePackage",
    "ExecutionTrace",
    "ExperimentManifest",
    "GateReceipt",
    "PromotionReceipt",
    "ReceiptVerification",
    "SkillBom",
    "compile_traces",
    "create_evidence_envelope",
    "create_evidence_package",
    "evaluate_candidate",
    "gate_evidence",
    "import_generic_evaluation",
    "import_otel_genai_evaluation",
    "inspect_skill",
    "validate_evidence_envelope",
    "verify_compilation_receipt",
]
