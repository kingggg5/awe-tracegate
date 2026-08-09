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
                    "compile",
                    "conformance",
                    "evaluate",
                    "gate",
                    "import-experiment",
                    "promote",
                    "redact",
                    "schema",
                    "serve",
                    "sign",
                    "skill.inspect",
                    "verify",
                    "verify-signature",
                )
            )
        ),
        guarantees=tuple(
            sorted(
                (
                    "canonical_json",
                    "content_addressed_receipts",
                    "exact_trace_replay",
                    "offline_keyless_gate",
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
