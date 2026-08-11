"""Build deterministic evidence graphs for AWE decision receipts."""

from __future__ import annotations

from typing import TypeAlias

from .contracts import (
    ComparisonReceipt,
    EvidenceGraphEdge,
    EvidenceGraphNode,
    ExperimentQualityReceipt,
    ExplanationReceipt,
    GateReceipt,
    GateReceiptV2,
    SensitivityReceipt,
    canonical_digest,
)

ExplainableReceipt: TypeAlias = (
    GateReceipt
    | GateReceiptV2
    | ComparisonReceipt
    | ExperimentQualityReceipt
    | SensitivityReceipt
)


def _node(node_id: str, kind: str, digest: str, status: str) -> EvidenceGraphNode:
    return EvidenceGraphNode(
        node_id=node_id,
        kind=kind,
        digest=digest,
        status=status,
    )


def _edge(source: str, target: str, relation: str) -> EvidenceGraphEdge:
    return EvidenceGraphEdge(
        source=source,
        target=target,
        relation=relation,  # type: ignore[arg-type]
    )


def _finish(
    receipt: ExplainableReceipt,
    *,
    decision: str,
    reasons: tuple[str, ...],
    nodes: list[EvidenceGraphNode],
    edges: list[EvidenceGraphEdge],
    limitations: tuple[str, ...],
) -> ExplanationReceipt:
    payload = {
        "schema_version": "awe.explanation-receipt.v1",
        "receipt_schema_version": receipt.schema_version,
        "receipt_hash": receipt.receipt_hash,
        "decision": decision,
        "reasons": tuple(sorted(set(reasons))),
        "nodes": [
            node.model_dump(mode="json")
            for node in sorted(nodes, key=lambda item: item.node_id)
        ],
        "edges": [
            edge.model_dump(mode="json")
            for edge in sorted(
                edges, key=lambda item: (item.source, item.target, item.relation)
            )
        ],
        "limitations": tuple(sorted(set(limitations))),
    }
    return ExplanationReceipt.model_validate(
        {**payload, "explanation_hash": canonical_digest(payload)}
    )


def explain_receipt(receipt: ExplainableReceipt) -> ExplanationReceipt:
    """Explain dependencies of a parsed receipt without generating prose.

    The result is a small stable graph and explicit limitations. It only reads
    content-addressed fields already present in the receipt; it never executes
    supplied artifacts or makes a network request.
    """

    if isinstance(receipt, GateReceipt):
        nodes = [
            _node(
                "baseline_bundle",
                "evaluation_bundle",
                receipt.baseline_bundle_digest,
                "held",
            ),
            _node(
                "candidate_bundle",
                "evaluation_bundle",
                receipt.candidate_bundle_digest,
                "held",
            ),
            _node("traces", "execution_traces", receipt.traces_digest, "held"),
            _node(
                "compilation",
                "compilation_receipt",
                receipt.compilation.receipt_hash,
                receipt.compilation.status,
            ),
            _node(
                "verification",
                "receipt_verification",
                receipt.verification.verification_hash,
                receipt.verification.status,
            ),
            _node(
                "evaluation",
                "evaluation_receipt",
                receipt.evaluation.receipt_hash,
                receipt.evaluation.status,
            ),
            _node("gate", "gate_receipt", receipt.receipt_hash, receipt.status),
        ]
        edges = [
            _edge("traces", "compilation", "derived_from"),
            _edge("compilation", "verification", "verified_by"),
            _edge("baseline_bundle", "evaluation", "assessed_by"),
            _edge("candidate_bundle", "evaluation", "assessed_by"),
            _edge("verification", "gate", "gated_by"),
            _edge("evaluation", "gate", "gated_by"),
        ]
        return _finish(
            receipt,
            decision=receipt.status,
            reasons=receipt.reasons,
            nodes=nodes,
            edges=edges,
            limitations=(
                "frozen_inputs_only",
                "no_live_model_or_tool_reconstruction",
                "no_external_provenance_trust_without_independent_verifier",
            ),
        )
    if isinstance(receipt, ComparisonReceipt):
        nodes = [
            _node(
                "baseline_manifest",
                "experiment_manifest",
                receipt.baseline_manifest_digest,
                "held",
            ),
            _node(
                "candidate_manifest",
                "experiment_manifest",
                receipt.candidate_manifest_digest,
                "held",
            ),
            _node(
                "comparison_policy", "comparison_policy", receipt.policy_digest, "held"
            ),
            _node(
                "comparison", "comparison_receipt", receipt.receipt_hash, receipt.status
            ),
        ]
        edges = [
            _edge("baseline_manifest", "comparison", "assessed_by"),
            _edge("candidate_manifest", "comparison", "assessed_by"),
            _edge("comparison_policy", "comparison", "gated_by"),
        ]
        return _finish(
            receipt,
            decision=receipt.conclusion,
            reasons=receipt.reasons,
            nodes=nodes,
            edges=edges,
            limitations=(
                "frozen_paired_cases_only",
                "no_unseen_task_generalization",
                "no_live_model_or_tool_reconstruction",
            ),
        )
    if isinstance(receipt, ExperimentQualityReceipt):
        nodes = [
            _node("manifest", "experiment_manifest", receipt.manifest_digest, "held"),
            _node(
                "quality_evidence",
                "quality_evidence",
                receipt.quality_evidence_digest,
                "asserted",
            ),
            _node("quality_policy", "quality_policy", receipt.policy_digest, "held"),
            _node("quality", "quality_receipt", receipt.receipt_hash, receipt.status),
        ]
        edges = [
            _edge("manifest", "quality", "assessed_by"),
            _edge("quality_evidence", "quality", "assessed_by"),
            _edge("quality_policy", "quality", "gated_by"),
        ]
        return _finish(
            receipt,
            decision=receipt.status,
            reasons=receipt.reasons,
            nodes=nodes,
            edges=edges,
            limitations=(
                "judge_and_human_labels_are_asserted_evidence",
                "no_grader_execution",
                "frozen_inputs_only",
            ),
        )
    if isinstance(receipt, SensitivityReceipt):
        nodes = [
            _node(f"manifest_{index:03d}", "experiment_manifest", digest, "held")
            for index, digest in enumerate(receipt.manifest_digests, start=1)
        ]
        nodes.extend(
            [
                _node(
                    "sensitivity_policy",
                    "sensitivity_policy",
                    receipt.policy_digest,
                    "held",
                ),
                _node(
                    "sensitivity",
                    "sensitivity_receipt",
                    receipt.receipt_hash,
                    receipt.status,
                ),
            ]
        )
        edges = [
            _edge(node.node_id, "sensitivity", "assessed_by")
            for node in nodes
            if node.kind == "experiment_manifest"
        ] + [_edge("sensitivity_policy", "sensitivity", "gated_by")]
        return _finish(
            receipt,
            decision=receipt.status,
            reasons=receipt.reasons,
            nodes=nodes,
            edges=edges,
            limitations=(
                "supplied_environments_and_seeds_only",
                "no_hosted_provider_determinism_claim",
                "frozen_inputs_only",
            ),
        )

    # Gate v2 is deliberately composed rather than delegated to recursive
    # explain calls so its one graph preserves the gate decision root.
    v1 = receipt.v1_gate
    comparison = receipt.comparison
    nodes = [
        _node("traces", "execution_traces", v1.traces_digest, "held"),
        _node(
            "baseline_bundle",
            "evaluation_bundle",
            v1.baseline_bundle_digest,
            "held",
        ),
        _node(
            "candidate_bundle",
            "evaluation_bundle",
            v1.candidate_bundle_digest,
            "held",
        ),
        _node(
            "compilation",
            "compilation_receipt",
            v1.compilation.receipt_hash,
            v1.compilation.status,
        ),
        _node(
            "verification",
            "receipt_verification",
            v1.verification.verification_hash,
            v1.verification.status,
        ),
        _node(
            "evaluation",
            "evaluation_receipt",
            v1.evaluation.receipt_hash,
            v1.evaluation.status,
        ),
        _node(
            "gate_v1",
            "gate_receipt",
            v1.receipt_hash,
            v1.status,
        ),
        _node(
            "baseline_manifest",
            "experiment_manifest",
            comparison.baseline_manifest_digest,
            "held",
        ),
        _node(
            "candidate_manifest",
            "experiment_manifest",
            comparison.candidate_manifest_digest,
            "held",
        ),
        _node(
            "comparison_policy",
            "comparison_policy",
            comparison.policy_digest,
            "held",
        ),
        _node(
            "comparison",
            "comparison_receipt",
            comparison.receipt_hash,
            comparison.status,
        ),
        _node(
            "comparison_verification",
            "comparison_verification",
            receipt.comparison_verification.verification_hash,
            receipt.comparison_verification.status,
        ),
        _node("gate_v2", "gate_receipt", receipt.receipt_hash, receipt.status),
    ]
    edges = [
        _edge("traces", "compilation", "derived_from"),
        _edge("compilation", "verification", "verified_by"),
        _edge("baseline_bundle", "evaluation", "assessed_by"),
        _edge("candidate_bundle", "evaluation", "assessed_by"),
        _edge("verification", "gate_v1", "gated_by"),
        _edge("evaluation", "gate_v1", "gated_by"),
        _edge("gate_v1", "gate_v2", "gated_by"),
        _edge("baseline_manifest", "comparison", "assessed_by"),
        _edge("candidate_manifest", "comparison", "assessed_by"),
        _edge("comparison_policy", "comparison", "gated_by"),
        _edge("comparison", "comparison_verification", "verified_by"),
        _edge("comparison_verification", "gate_v2", "gated_by"),
    ]
    for prefix, quality in (
        ("baseline", receipt.baseline_quality),
        ("candidate", receipt.candidate_quality),
    ):
        if quality is not None:
            node_id = f"{prefix}_quality"
            nodes.append(
                _node(node_id, "quality_receipt", quality.receipt_hash, quality.status)
            )
            edges.append(_edge(node_id, "gate_v2", "gated_by"))
    return _finish(
        receipt,
        decision=receipt.status,
        reasons=receipt.reasons,
        nodes=nodes,
        edges=edges,
        limitations=(
            "frozen_inputs_only",
            "comparison_is_not_unseen_task_generalization",
            "no_live_model_or_tool_reconstruction",
            "judge_and_human_labels_are_asserted_evidence",
        ),
    )
