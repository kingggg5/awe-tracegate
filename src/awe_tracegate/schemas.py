"""Versioned JSON Schema export for integration authors."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from .contracts import (
    AdapterConformanceReceipt,
    CapabilitiesDocument,
    ComparisonPolicy,
    ComparisonReceipt,
    ComparisonVerification,
    CompilationCandidate,
    CompilationReceipt,
    DatasetConsentRecord,
    EvaluationBundle,
    EvaluationPolicy,
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
    GovernedRedactionSummary,
    PromotionReceipt,
    QualityPolicy,
    ReceiptVerification,
    RedactionPolicy,
    RedactionSummary,
    ReviewBundleReport,
    SensitivityPolicy,
    SensitivityReceipt,
    SignatureVerification,
    SignedReceiptBundle,
    SkillBom,
)

SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "adapter-conformance-v1.schema.json": AdapterConformanceReceipt,
    "capabilities-v1.schema.json": CapabilitiesDocument,
    "candidate-v1.schema.json": CompilationCandidate,
    "compilation-receipt-v1.schema.json": CompilationReceipt,
    "comparison-policy-v1.schema.json": ComparisonPolicy,
    "comparison-receipt-v1.schema.json": ComparisonReceipt,
    "comparison-verification-v1.schema.json": ComparisonVerification,
    "dataset-consent-v1.schema.json": DatasetConsentRecord,
    "evidence-envelope-v1.schema.json": EvidenceEnvelope,
    "evidence-package-v1.schema.json": EvidencePackage,
    "evaluation-bundle-v1.schema.json": EvaluationBundle,
    "evaluation-policy-v1.schema.json": EvaluationPolicy,
    "evaluation-receipt-v1.schema.json": EvaluationReceipt,
    "execution-trace-v1.schema.json": ExecutionTrace,
    "experiment-manifest-v1.schema.json": ExperimentManifest,
    "experiment-quality-evidence-v1.schema.json": ExperimentQualityEvidence,
    "experiment-quality-receipt-v1.schema.json": ExperimentQualityReceipt,
    "explanation-receipt-v1.schema.json": ExplanationReceipt,
    "gate-receipt-v1.schema.json": GateReceipt,
    "gate-receipt-v2.schema.json": GateReceiptV2,
    "governed-redaction-summary-v1.schema.json": GovernedRedactionSummary,
    "promotion-receipt-v2.schema.json": PromotionReceipt,
    "receipt-verification-v2.schema.json": ReceiptVerification,
    "redaction-summary-v1.schema.json": RedactionSummary,
    "redaction-policy-v1.schema.json": RedactionPolicy,
    "review-bundle-report-v1.schema.json": ReviewBundleReport,
    "signature-verification-v1.schema.json": SignatureVerification,
    "sensitivity-policy-v1.schema.json": SensitivityPolicy,
    "sensitivity-receipt-v1.schema.json": SensitivityReceipt,
    "signed-receipt-bundle-v1.schema.json": SignedReceiptBundle,
    "skill-bom-v1.schema.json": SkillBom,
    "quality-policy-v1.schema.json": QualityPolicy,
}

JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"


def schema_identifier(filename: str) -> str:
    """Return a stable, non-network identifier for one versioned contract."""

    name = filename.removesuffix(".schema.json")
    return f"urn:awe-tracegate:schema:{name}"


def export_schemas(output_directory: Path) -> tuple[Path, ...]:
    """Write deterministic JSON Schema documents and return their paths."""

    output_directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for filename, model in sorted(SCHEMA_MODELS.items()):
        output_path = output_directory / filename
        schema = model.model_json_schema(mode="serialization")
        schema["$id"] = schema_identifier(filename)
        schema["$schema"] = JSON_SCHEMA_DIALECT
        output_path.write_text(
            json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        written.append(output_path)
    return tuple(written)
