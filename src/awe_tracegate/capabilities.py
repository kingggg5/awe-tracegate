"""Machine-readable capability statement for host and installer checks."""

from __future__ import annotations

from .contracts import CapabilitiesDocument


def describe_capabilities(package_version: str) -> CapabilitiesDocument:
    """Return the stable capabilities of this installed core version."""

    return CapabilitiesDocument(
        package_version=package_version,
        commands=tuple(
            sorted(
                (
                    "capabilities",
                    "assess-quality",
                    "compare",
                    "compile",
                    "conformance",
                    "evaluate",
                    "gate",
                    "gate-v2",
                    "import-experiment",
                    "promote",
                    "redact",
                    "schema",
                    "serve",
                    "sign",
                    "sensitivity",
                    "skill.inspect",
                    "verify",
                    "verify-comparison",
                    "verify-signature",
                    "explain",
                )
            )
        ),
        guarantees=tuple(
            sorted(
                (
                    "canonical_json",
                    "comparison_exact_input_replay",
                    "comparison_held_input_verification",
                    "content_addressed_receipts",
                    "deterministic_evidence_graphs",
                    "exact_input_gate_replay",
                    "offline_keyless_gate",
                    "paired_experiment_comparison",
                    "typed_terminal_outcome_assessment",
                    "strict_typed_contracts",
                )
            )
        ),
        exclusions=tuple(
            sorted(
                (
                    "artifact_execution",
                    "autonomous_promotion",
                    "deployment_runtime",
                    "llm_authority",
                    "remote_network_calls",
                )
            )
        ),
    )
