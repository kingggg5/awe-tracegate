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
                    "demo",
                    "doctor",
                    "discovery.build-migration-bundle",
                    "discovery.ingest-trace",
                    "evaluate",
                    "gate",
                    "gate-v2",
                    "init",
                    "import-experiment",
                    "promote",
                    "redact",
                    "recipes",
                    "schema",
                    "serve",
                    "sign",
                    "sensitivity",
                    "skill.inspect",
                    "status",
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
                    "consented_agent_trace_import",
                    "comparison_exact_input_replay",
                    "comparison_held_input_verification",
                    "content_addressed_receipts",
                    "deterministic_evidence_graphs",
                    "decision_recipe_catalog",
                    "exact_input_gate_replay",
                    "evidence_only_scaffolding",
                    "offline_keyless_gate",
                    "paired_experiment_comparison",
                    "postgres_alembic_evidence_projection",
                    "review_bundle_exact_input_replay",
                    "typed_terminal_outcome_assessment",
                    "workspace_operational_status",
                    "strict_typed_contracts",
                )
            )
        ),
        exclusions=tuple(
            sorted(
                (
                    "artifact_execution",
                    "agent_execution",
                    "autonomous_promotion",
                    "deployment_runtime",
                    "llm_authority",
                    "remote_network_calls",
                )
            )
        ),
    )
