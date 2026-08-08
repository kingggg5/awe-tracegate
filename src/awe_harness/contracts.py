"""Strict contracts shared by AWE's compiler, CLI, and HTTP API."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Identifier = Annotated[
    str,
    StringConstraints(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$"),
]
TraceIdentifier = Annotated[
    str,
    StringConstraints(
        min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$"
    ),
]
ToolName = Annotated[
    str,
    StringConstraints(min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_.-]*$"),
]
ToolVersion = Annotated[
    str,
    StringConstraints(
        min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9.+_-]*$"
    ),
]
JsonPointer = Annotated[
    str,
    StringConstraints(
        min_length=2,
        max_length=256,
        pattern=r"^/(?:[^~\x00-\x1f]|~[01])+$",
    ),
]
Sha256Digest = Annotated[
    str,
    StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$"),
]
Reason = Annotated[str, StringConstraints(min_length=1, max_length=512)]

EffectClass = Literal["pure", "read", "write", "high_impact"]
BindingSource = Literal["workflow_input", "step_output", "model_decision"]


class ContractModel(BaseModel):
    """Reject coercion and unknown fields, and prevent attribute mutation."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        validate_default=True,
    )


class FieldEvidence(ContractModel):
    """Content digest observed at a JSON field boundary."""

    field: JsonPointer
    value_digest: Sha256Digest


class TraceBinding(ContractModel):
    """Observed input binding for one executed step."""

    input_name: Identifier
    source_kind: BindingSource
    source_field: JsonPointer
    observed_value_digest: Sha256Digest
    source_node: Identifier | None = None

    @model_validator(mode="after")
    def validate_source_node(self) -> Self:
        if self.source_kind == "step_output" and self.source_node is None:
            raise ValueError("step_output bindings require source_node")
        if self.source_kind != "step_output" and self.source_node is not None:
            raise ValueError("source_node is only valid for step_output bindings")
        return self


class TraceStep(ContractModel):
    """One typed activity observed in an execution trace."""

    node_id: Identifier
    tool: ToolName
    tool_version: ToolVersion
    effect: EffectClass
    inputs: Annotated[tuple[TraceBinding, ...], Field(strict=False)] = ()
    outputs: Annotated[
        tuple[FieldEvidence, ...],
        Field(min_length=1, strict=False),
    ]

    @model_validator(mode="after")
    def validate_unique_fields(self) -> Self:
        input_names = [binding.input_name for binding in self.inputs]
        if len(input_names) != len(set(input_names)):
            raise ValueError("step input names must be unique")
        output_fields = [evidence.field for evidence in self.outputs]
        if len(output_fields) != len(set(output_fields)):
            raise ValueError("step output fields must be unique")
        return self


class ExecutionTrace(ContractModel):
    """Immutable evidence from a single workflow execution."""

    schema_version: Literal["awe.trace.v1"] = "awe.trace.v1"
    trace_id: TraceIdentifier
    intent: Identifier
    succeeded: bool
    workflow_inputs: Annotated[
        tuple[FieldEvidence, ...],
        Field(min_length=1, strict=False),
    ]
    steps: Annotated[
        tuple[TraceStep, ...],
        Field(min_length=1, strict=False),
    ]

    @model_validator(mode="after")
    def validate_unique_trace_fields(self) -> Self:
        input_fields = [evidence.field for evidence in self.workflow_inputs]
        if len(input_fields) != len(set(input_fields)):
            raise ValueError("workflow input fields must be unique")
        node_ids = [step.node_id for step in self.steps]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("trace node ids must be unique")
        return self


class CompileRequest(ContractModel):
    """Trace set proposed for compilation."""

    traces: Annotated[
        tuple[ExecutionTrace, ...],
        Field(min_length=1, strict=False),
    ]

    @model_validator(mode="after")
    def validate_unique_trace_ids(self) -> Self:
        trace_ids = [trace.trace_id for trace in self.traces]
        if len(trace_ids) != len(set(trace_ids)):
            raise ValueError("trace ids must be unique")
        return self


class CompiledBinding(ContractModel):
    """Binding retained in a declarative compiled candidate."""

    input_name: Identifier
    source_kind: Literal["workflow_input", "step_output"]
    source_field: JsonPointer
    source_node: Identifier | None = None

    @model_validator(mode="after")
    def validate_source_node(self) -> Self:
        if self.source_kind == "step_output" and self.source_node is None:
            raise ValueError("step_output bindings require source_node")
        if self.source_kind == "workflow_input" and self.source_node is not None:
            raise ValueError("workflow_input bindings cannot have source_node")
        return self


class CompiledNode(ContractModel):
    """Read-only node emitted into a candidate workflow."""

    node_id: Identifier
    tool: ToolName
    tool_version: ToolVersion
    effect: Literal["pure", "read"]
    inputs: Annotated[tuple[CompiledBinding, ...], Field(strict=False)] = ()
    output_fields: Annotated[
        tuple[JsonPointer, ...],
        Field(min_length=1, strict=False),
    ]


class DependencyEvidence(ContractModel):
    """Auditable producer-to-consumer dependency observed in every trace."""

    producer_node: Identifier
    producer_field: JsonPointer
    consumer_node: Identifier
    consumer_input: Identifier
    observation_count: Annotated[int, Field(ge=2)]
    trace_ids: Annotated[
        tuple[TraceIdentifier, ...],
        Field(min_length=2, strict=False),
    ]
    evidence_digest: Sha256Digest


class CompilationCandidate(ContractModel):
    """Declarative candidate; it is safe to evaluate, not auto-promote."""

    schema_version: Literal["awe.candidate.v1"] = "awe.candidate.v1"
    candidate_digest: Sha256Digest
    intent: Identifier
    effect_scope: Literal["pure_or_read"] = "pure_or_read"
    source_trace_ids: Annotated[
        tuple[TraceIdentifier, ...],
        Field(min_length=2, strict=False),
    ]
    nodes: Annotated[
        tuple[CompiledNode, ...],
        Field(min_length=1, strict=False),
    ]
    dependencies: Annotated[
        tuple[DependencyEvidence, ...],
        Field(strict=False),
    ] = ()


class CompilationReceipt(ContractModel):
    """Deterministic receipt for either compilation or a safe refusal."""

    schema_version: Literal["awe.compilation-receipt.v1"] = "awe.compilation-receipt.v1"
    compiler_version: Literal["awe.compiler.v1"] = "awe.compiler.v1"
    input_bundle_digest: Sha256Digest
    status: Literal["compiled", "refused"]
    reasons: Annotated[tuple[Reason, ...], Field(strict=False)] = ()
    candidate: CompilationCandidate | None = None
    receipt_hash: Sha256Digest

    @model_validator(mode="after")
    def validate_status_payload(self) -> Self:
        if self.status == "compiled" and self.candidate is None:
            raise ValueError("compiled receipts require a candidate")
        if self.status == "compiled" and self.reasons:
            raise ValueError("compiled receipts cannot contain refusal reasons")
        if self.status == "refused" and self.candidate is not None:
            raise ValueError("refused receipts cannot contain a candidate")
        if self.status == "refused" and not self.reasons:
            raise ValueError("refused receipts require at least one reason")
        return self


class HealthResponse(ContractModel):
    status: Literal["ok"] = "ok"
    mode: Literal["offline_keyless"] = "offline_keyless"


def canonical_json(value: Any) -> str:
    """Serialize JSON without platform- or insertion-order-dependent output."""

    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json", exclude_none=False)
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def canonical_digest(value: Any) -> str:
    """Return a stable SHA-256 digest for a JSON-compatible value."""

    encoded = canonical_json(value).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"
