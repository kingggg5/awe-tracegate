"""Evidence-gated compiler for repeated pure/read-only traces."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .contracts import (
    CompilationCandidate,
    CompilationReceipt,
    CompiledBinding,
    CompiledNode,
    DependencyEvidence,
    ExecutionTrace,
    TraceStep,
    canonical_digest,
)


def _step_shape(step: TraceStep) -> tuple[Any, ...]:
    bindings = tuple(
        sorted(
            (
                binding.input_name,
                binding.source_kind,
                binding.source_node,
                binding.source_field,
            )
            for binding in step.inputs
        )
    )
    return (
        step.node_id,
        step.tool,
        step.tool_version,
        step.effect,
        bindings,
        tuple(sorted(output.field for output in step.outputs)),
    )


def _trace_shape(trace: ExecutionTrace) -> tuple[tuple[Any, ...], ...]:
    return tuple(_step_shape(step) for step in trace.steps)


def _receipt_payload(
    *,
    input_bundle_digest: str,
    status: str,
    reasons: tuple[str, ...],
    candidate: CompilationCandidate | None,
) -> dict[str, Any]:
    return {
        "schema_version": "awe.compilation-receipt.v1",
        "compiler_version": "awe.compiler.v1",
        "input_bundle_digest": input_bundle_digest,
        "status": status,
        "reasons": list(reasons),
        "candidate": (
            candidate.model_dump(mode="json", exclude_none=False)
            if candidate is not None
            else None
        ),
    }


def _refused(input_bundle_digest: str, *reasons: str) -> CompilationReceipt:
    ordered_reasons = tuple(sorted(set(reasons)))
    payload = _receipt_payload(
        input_bundle_digest=input_bundle_digest,
        status="refused",
        reasons=ordered_reasons,
        candidate=None,
    )
    return CompilationReceipt(
        input_bundle_digest=input_bundle_digest,
        status="refused",
        reasons=ordered_reasons,
        receipt_hash=canonical_digest(payload),
    )


def _compiled(
    candidate: CompilationCandidate,
    input_bundle_digest: str,
) -> CompilationReceipt:
    payload = _receipt_payload(
        input_bundle_digest=input_bundle_digest,
        status="compiled",
        reasons=(),
        candidate=candidate,
    )
    return CompilationReceipt(
        input_bundle_digest=input_bundle_digest,
        status="compiled",
        candidate=candidate,
        receipt_hash=canonical_digest(payload),
    )


def _collect_trace_reasons(trace: ExecutionTrace) -> list[str]:
    reasons: list[str] = []
    workflow_inputs = {
        evidence.field: evidence.value_digest for evidence in trace.workflow_inputs
    }
    prior_outputs: dict[str, list[tuple[str, str]]] = {}
    for field, value_digest in workflow_inputs.items():
        prior_outputs.setdefault(value_digest, []).append(("$workflow", field))
    node_positions = {step.node_id: index for index, step in enumerate(trace.steps)}
    step_outputs = {
        step.node_id: {
            evidence.field: evidence.value_digest for evidence in step.outputs
        }
        for step in trace.steps
    }

    for position, step in enumerate(trace.steps):
        if step.effect not in ("pure", "read"):
            reasons.append(f"unsafe_effect:{step.node_id}:{step.effect}")

        for binding in step.inputs:
            if binding.source_kind == "model_decision":
                reasons.append(
                    f"model_decision_binding:{step.node_id}:{binding.input_name}"
                )
                continue

            if binding.source_kind == "workflow_input":
                expected_digest = workflow_inputs.get(binding.source_field)
                if expected_digest is None:
                    reasons.append(
                        "missing_workflow_input_evidence:"
                        f"{step.node_id}:{binding.input_name}"
                    )
                elif expected_digest != binding.observed_value_digest:
                    reasons.append(
                        "workflow_input_digest_mismatch:"
                        f"{step.node_id}:{binding.input_name}"
                    )
                else:
                    attributable_fields = sorted(
                        field
                        for field, value_digest in workflow_inputs.items()
                        if value_digest == binding.observed_value_digest
                    )
                    if attributable_fields != [binding.source_field]:
                        reasons.append(
                            "ambiguous_workflow_input:"
                            f"{step.node_id}:{binding.input_name}"
                        )
                continue

            source_node = binding.source_node
            if source_node is None:
                reasons.append(
                    f"missing_source_node:{step.node_id}:{binding.input_name}"
                )
                continue
            source_position = node_positions.get(source_node or "")
            if source_position is None or source_position >= position:
                reasons.append(
                    f"unknown_or_forward_dependency:{step.node_id}:{binding.input_name}"
                )
                continue

            expected_digest = step_outputs[source_node].get(binding.source_field)
            if expected_digest is None:
                reasons.append(
                    f"missing_output_evidence:{step.node_id}:{binding.input_name}"
                )
                continue
            if expected_digest != binding.observed_value_digest:
                reasons.append(
                    f"dependency_digest_mismatch:{step.node_id}:{binding.input_name}"
                )
                continue

            attributable_sources = prior_outputs.get(
                binding.observed_value_digest,
                [],
            )
            if attributable_sources != [(source_node, binding.source_field)]:
                reasons.append(
                    f"ambiguous_dependency:{step.node_id}:{binding.input_name}"
                )

        for output in step.outputs:
            prior_outputs.setdefault(output.value_digest, []).append(
                (step.node_id, output.field)
            )

    return reasons


def _build_dependencies(
    traces: tuple[ExecutionTrace, ...],
) -> tuple[DependencyEvidence, ...]:
    reference = traces[0]
    trace_ids = tuple(trace.trace_id for trace in traces)
    dependencies: list[DependencyEvidence] = []

    for step in reference.steps:
        for binding in sorted(step.inputs, key=lambda item: item.input_name):
            if binding.source_kind != "step_output":
                continue
            source_node = binding.source_node
            if source_node is None:
                raise ValueError("validated step_output binding lacks source_node")
            observations = [
                {
                    "trace_id": trace.trace_id,
                    "value_digest": next(
                        candidate.observed_value_digest
                        for trace_step in trace.steps
                        if trace_step.node_id == step.node_id
                        for candidate in trace_step.inputs
                        if candidate.input_name == binding.input_name
                    ),
                }
                for trace in traces
            ]
            dependencies.append(
                DependencyEvidence(
                    producer_node=source_node,
                    producer_field=binding.source_field,
                    consumer_node=step.node_id,
                    consumer_input=binding.input_name,
                    observation_count=len(traces),
                    trace_ids=trace_ids,
                    evidence_digest=canonical_digest(observations),
                )
            )

    return tuple(
        sorted(
            dependencies,
            key=lambda item: (
                item.producer_node,
                item.producer_field,
                item.consumer_node,
                item.consumer_input,
            ),
        )
    )


def _build_nodes(reference: ExecutionTrace) -> tuple[CompiledNode, ...]:
    nodes: list[CompiledNode] = []
    for step in reference.steps:
        if step.effect not in ("pure", "read"):
            raise ValueError("unsafe step reached candidate construction")
        compiled_bindings: list[CompiledBinding] = []
        for binding in sorted(step.inputs, key=lambda item: item.input_name):
            if binding.source_kind == "model_decision":
                raise ValueError("model decision reached candidate construction")
            compiled_bindings.append(
                CompiledBinding(
                    input_name=binding.input_name,
                    source_kind=binding.source_kind,
                    source_node=binding.source_node,
                    source_field=binding.source_field,
                )
            )
        nodes.append(
            CompiledNode(
                node_id=step.node_id,
                tool=step.tool,
                tool_version=step.tool_version,
                effect=step.effect,
                inputs=tuple(compiled_bindings),
                output_fields=tuple(sorted(output.field for output in step.outputs)),
            )
        )
    return tuple(nodes)


def compile_traces(traces: Sequence[ExecutionTrace]) -> CompilationReceipt:
    """Compile only when repeated traces prove one safe declarative workflow."""

    ordered_traces = tuple(sorted(traces, key=lambda trace: trace.trace_id))
    input_bundle_digest = canonical_digest(
        [trace.model_dump(mode="json") for trace in ordered_traces]
    )
    if len(ordered_traces) < 2:
        return _refused(input_bundle_digest, "insufficient_trace_evidence")

    trace_ids = [trace.trace_id for trace in ordered_traces]
    if len(trace_ids) != len(set(trace_ids)):
        return _refused(input_bundle_digest, "duplicate_trace_ids")

    reasons: list[str] = []
    for trace in ordered_traces:
        if not trace.succeeded:
            reasons.append(f"trace_not_successful:{trace.trace_id}")

    intents = {trace.intent for trace in ordered_traces}
    if len(intents) != 1:
        reasons.append("mixed_intents")

    reference_shape = _trace_shape(ordered_traces[0])
    for trace in ordered_traces[1:]:
        if _trace_shape(trace) != reference_shape:
            reasons.append(f"workflow_shape_mismatch:{trace.trace_id}")

    for trace in ordered_traces:
        reasons.extend(_collect_trace_reasons(trace))

    if reasons:
        return _refused(input_bundle_digest, *reasons)

    reference = ordered_traces[0]
    nodes = _build_nodes(reference)
    dependencies = _build_dependencies(ordered_traces)
    candidate_payload = {
        "schema_version": "awe.candidate.v1",
        "intent": reference.intent,
        "effect_scope": "pure_or_read",
        "source_trace_ids": list(trace_ids),
        "nodes": [node.model_dump(mode="json") for node in nodes],
        "dependencies": [
            dependency.model_dump(mode="json") for dependency in dependencies
        ],
    }
    candidate = CompilationCandidate(
        candidate_digest=canonical_digest(candidate_payload),
        intent=reference.intent,
        source_trace_ids=tuple(trace_ids),
        nodes=nodes,
        dependencies=dependencies,
    )
    return _compiled(candidate, input_bundle_digest)
