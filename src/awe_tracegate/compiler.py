"""Evidence-gated compiler for repeated pure/read-only traces."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .contracts import (
    PENDING_SHA256_DIGEST,
    CompilationCandidate,
    CompilationReceipt,
    CompiledBinding,
    CompiledNode,
    DependencyEvidence,
    ExecutionTrace,
    TraceStep,
    canonical_digest,
)


def candidate_payload(candidate: CompilationCandidate) -> dict[str, Any]:
    """Return the exact hash payload for a candidate."""

    return {
        "schema_version": candidate.schema_version,
        "intent": candidate.intent,
        "effect_scope": candidate.effect_scope,
        "source_trace_ids": list(candidate.source_trace_ids),
        "nodes": [node.model_dump(mode="json") for node in candidate.nodes],
        "dependencies": [
            dependency.model_dump(mode="json") for dependency in candidate.dependencies
        ],
    }


def receipt_payload(receipt: CompilationReceipt) -> dict[str, Any]:
    """Return the exact hash payload for a compilation receipt."""

    return receipt.model_dump(mode="json", exclude={"receipt_hash"})


def input_bundle_digest(traces: Sequence[ExecutionTrace]) -> str:
    ordered_traces = sorted(traces, key=lambda trace: trace.trace_id)
    return canonical_digest([trace.model_dump(mode="json") for trace in ordered_traces])


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


def _refused(input_digest: str, *reasons: str) -> CompilationReceipt:
    receipt = CompilationReceipt(
        input_bundle_digest=input_digest,
        status="refused",
        reasons=tuple(sorted(set(reasons))),
        receipt_hash=PENDING_SHA256_DIGEST,
    )
    return receipt.model_copy(
        update={"receipt_hash": canonical_digest(receipt_payload(receipt))}
    )


def _compiled(
    candidate: CompilationCandidate,
    input_digest: str,
) -> CompilationReceipt:
    receipt = CompilationReceipt(
        input_bundle_digest=input_digest,
        status="compiled",
        candidate=candidate,
        receipt_hash=PENDING_SHA256_DIGEST,
    )
    return receipt.model_copy(
        update={"receipt_hash": canonical_digest(receipt_payload(receipt))}
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
            source_position = node_positions.get(source_node)
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
    observations_by_binding: dict[tuple[str, str], list[dict[str, str]]] = {}

    # Shapes are proven equal before candidate construction. Index each observed
    # binding once instead of rescanning every trace for every reference node.
    for trace in traces:
        for step in trace.steps:
            for binding in step.inputs:
                if binding.source_kind != "step_output":
                    continue
                key = (step.node_id, binding.input_name)
                observations_by_binding.setdefault(key, []).append(
                    {
                        "trace_id": trace.trace_id,
                        "value_digest": binding.observed_value_digest,
                    }
                )

    for step in reference.steps:
        for binding in sorted(step.inputs, key=lambda item: item.input_name):
            if binding.source_kind != "step_output":
                continue
            source_node = binding.source_node
            if source_node is None:
                raise ValueError("validated step_output binding lacks source_node")
            observations = observations_by_binding[(step.node_id, binding.input_name)]
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
    input_digest = input_bundle_digest(ordered_traces)
    if len(ordered_traces) < 2:
        return _refused(input_digest, "insufficient_trace_evidence")

    trace_ids = [trace.trace_id for trace in ordered_traces]
    if len(trace_ids) != len(set(trace_ids)):
        return _refused(input_digest, "duplicate_trace_ids")

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
        return _refused(input_digest, *reasons)

    reference = ordered_traces[0]
    nodes = _build_nodes(reference)
    dependencies = _build_dependencies(ordered_traces)
    candidate = CompilationCandidate(
        candidate_digest=PENDING_SHA256_DIGEST,
        intent=reference.intent,
        source_trace_ids=tuple(trace_ids),
        nodes=nodes,
        dependencies=dependencies,
    )
    candidate = candidate.model_copy(
        update={"candidate_digest": canonical_digest(candidate_payload(candidate))}
    )
    return _compiled(candidate, input_digest)
