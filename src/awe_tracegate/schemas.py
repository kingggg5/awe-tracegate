"""Versioned JSON Schema export for integration authors."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from .contracts import (
    CompilationCandidate,
    CompilationReceipt,
    EvaluationBundle,
    EvaluationPolicy,
    EvaluationReceipt,
    ExecutionTrace,
    PromotionReceipt,
    ReceiptVerification,
    RedactionSummary,
)

SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "candidate-v1.schema.json": CompilationCandidate,
    "compilation-receipt-v1.schema.json": CompilationReceipt,
    "evaluation-bundle-v1.schema.json": EvaluationBundle,
    "evaluation-policy-v1.schema.json": EvaluationPolicy,
    "evaluation-receipt-v1.schema.json": EvaluationReceipt,
    "execution-trace-v1.schema.json": ExecutionTrace,
    "promotion-receipt-v2.schema.json": PromotionReceipt,
    "receipt-verification-v2.schema.json": ReceiptVerification,
    "redaction-summary-v1.schema.json": RedactionSummary,
}


def export_schemas(output_directory: Path) -> tuple[Path, ...]:
    """Write deterministic JSON Schema documents and return their paths."""

    output_directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for filename, model in sorted(SCHEMA_MODELS.items()):
        output_path = output_directory / filename
        schema = model.model_json_schema(mode="serialization")
        output_path.write_text(
            json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        written.append(output_path)
    return tuple(written)
