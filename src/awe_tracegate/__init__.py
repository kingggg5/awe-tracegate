"""AWE TraceGate's keyless, evidence-gated workflow review core."""

__version__ = "0.3.0"

from .adapters import import_generic_evaluation, import_otel_genai_evaluation
from .compiler import compile_traces
from .contracts import (
    AdapterConformanceReceipt,
    CapabilitiesDocument,
    ComparisonPolicy,
    ComparisonReceipt,
    ComparisonVerification,
    CompilationCandidate,
    CompilationReceipt,
    CompileRequest,
    EvaluationReceipt,
    EvidenceEnvelope,
    EvidencePackage,
    ExecutionTrace,
    ExperimentManifest,
    ExperimentQualityEvidence,
    ExperimentQualityReceipt,
    ExplanationReceipt,
    GateReceipt,
    GateReceiptV2,
    PromotionReceipt,
    QualityPolicy,
    ReceiptVerification,
    ReviewBundleReport,
    SensitivityPolicy,
    SensitivityReceipt,
    SkillBom,
)
from .demo import generate_demo, inspect_review_bundle
from .evaluation import (
    compare_experiments,
    evaluate_candidate,
    validate_comparison_receipt_inputs,
    verify_comparison_receipt_inputs,
)
from .evidence import (
    create_evidence_envelope,
    create_evidence_package,
    validate_evidence_envelope,
)
from .explain import explain_receipt
from .gate import (
    GateReplayExpectations,
    gate_evidence,
    gate_evidence_v2,
    validate_gate_receipt_inputs,
    validate_gate_v2_receipt_inputs,
)
from .quality import assess_experiment_quality
from .recipes import (
    DecisionRecipe,
    DecisionRecipeCatalog,
    RecipeScaffoldManifest,
    build_recipe_scaffold,
    decision_recipe_catalog,
    initialize_evidence_workspace,
)
from .sensitivity import assess_sensitivity
from .skill_bom import inspect_skill
from .verifier import verify_compilation_receipt

__all__ = [
    "AdapterConformanceReceipt",
    "CapabilitiesDocument",
    "ComparisonPolicy",
    "ComparisonReceipt",
    "ComparisonVerification",
    "CompilationCandidate",
    "CompilationReceipt",
    "CompileRequest",
    "DecisionRecipe",
    "DecisionRecipeCatalog",
    "EvaluationReceipt",
    "EvidenceEnvelope",
    "EvidencePackage",
    "ExecutionTrace",
    "ExperimentManifest",
    "ExperimentQualityEvidence",
    "ExperimentQualityReceipt",
    "ExplanationReceipt",
    "GateReceipt",
    "GateReceiptV2",
    "GateReplayExpectations",
    "PromotionReceipt",
    "QualityPolicy",
    "ReceiptVerification",
    "RecipeScaffoldManifest",
    "ReviewBundleReport",
    "SensitivityPolicy",
    "SensitivityReceipt",
    "SkillBom",
    "assess_experiment_quality",
    "assess_sensitivity",
    "build_recipe_scaffold",
    "compare_experiments",
    "compile_traces",
    "create_evidence_envelope",
    "create_evidence_package",
    "decision_recipe_catalog",
    "evaluate_candidate",
    "explain_receipt",
    "gate_evidence",
    "gate_evidence_v2",
    "generate_demo",
    "import_generic_evaluation",
    "import_otel_genai_evaluation",
    "initialize_evidence_workspace",
    "inspect_review_bundle",
    "inspect_skill",
    "validate_comparison_receipt_inputs",
    "validate_evidence_envelope",
    "validate_gate_receipt_inputs",
    "validate_gate_v2_receipt_inputs",
    "verify_comparison_receipt_inputs",
    "verify_compilation_receipt",
]
