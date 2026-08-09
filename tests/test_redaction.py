from __future__ import annotations

from datetime import UTC, datetime

import pytest

from awe_tracegate.contracts import DatasetConsentRecord, RedactionPolicy
from awe_tracegate.redaction import redact_governed_json, redact_json


def policy() -> RedactionPolicy:
    return RedactionPolicy(
        policy_id="public-eval-export",
        policy_version="1.0.0",
        allowed_top_level_keys=("metadata", "result"),
        additional_sensitive_keys={"internal_note": "customer_data"},
        denied_keys={"tenant_id": "customer_data"},
    )


def consent(*, status: str = "active") -> DatasetConsentRecord:
    revoked_at = datetime(2026, 8, 9, 1, tzinfo=UTC) if status == "revoked" else None
    return DatasetConsentRecord.model_validate(
        {
            "consent_id": "consent-001",
            "data_subject_digest": "sha256:" + "a" * 64,
            "scopes": ["evaluation", "research"],
            "status": status,
            "actor_id": "maintainer@example.com",
            "granted_at": datetime(2026, 8, 9, tzinfo=UTC),
            "expires_at": datetime(2026, 9, 9, tzinfo=UTC),
            "revoked_at": revoked_at,
        }
    )


def test_redacts_sensitive_keys_and_values_without_mutating_input() -> None:
    synthetic_github_token = "ghp_" + "abcdefghijklmnopqrstuvwxyz"
    source = {
        "authorization": "Bearer top-secret-value-123456",
        "message": f"Contact engineer@example.com with {synthetic_github_token}",
        "nested": {"customer_name": "Ada Lovelace", "safe": "release-42"},
    }

    redacted, summary = redact_json(source)

    assert source["authorization"] == "Bearer top-secret-value-123456"
    assert redacted["authorization"] == "[REDACTED:secret]"
    assert redacted["nested"]["customer_name"] == "[REDACTED:customer_data]"
    assert "engineer@example.com" not in redacted["message"]
    assert "ghp_" not in redacted["message"]
    assert redacted["nested"]["safe"] == "release-42"
    assert summary.changed is True
    assert summary.replacements == 4


def test_safe_payload_is_byte_stable() -> None:
    source = {"repository": "example/service", "risk": 42}

    first, first_summary = redact_json(source)
    second, second_summary = redact_json(source)

    assert first == second == source
    assert first_summary == second_summary
    assert first_summary.changed is False


def test_redaction_refuses_excessive_json_depth() -> None:
    source: dict[str, object] = {}
    cursor = source
    for _ in range(66):
        child: dict[str, object] = {}
        cursor["next"] = child
        cursor = child

    with pytest.raises(ValueError, match="JSON nesting exceeds"):
        redact_json(source)


def test_governed_export_applies_allowlist_policy_and_consent() -> None:
    source = {
        "metadata": {"tenant_id": "customer-42", "safe": "synthetic"},
        "result": {"internal_note": "not for export", "score": 1},
        "raw_prompt": "remove this entire top-level field",
    }

    redacted, summary = redact_governed_json(
        source,
        policy(),
        consent(),
        scope="evaluation",
        evaluated_at=datetime(2026, 8, 9, 2, tzinfo=UTC),
    )

    assert "raw_prompt" not in redacted
    assert redacted["metadata"]["tenant_id"] == "[REDACTED:customer_data]"
    assert redacted["result"]["internal_note"] == "[REDACTED:customer_data]"
    assert summary.removed_fields == 1
    assert summary.replacements == 2
    assert summary.consent_id == "consent-001"
    assert summary.policy_digest.startswith("sha256:")
    assert source["raw_prompt"].startswith("remove")


def test_governed_export_fails_closed_after_revocation() -> None:
    with pytest.raises(ValueError, match="consent is revoked"):
        redact_governed_json(
            {"result": "synthetic"},
            policy(),
            consent(status="revoked"),
            scope="evaluation",
            evaluated_at=datetime(2026, 8, 9, 2, tzinfo=UTC),
        )


def test_governed_export_requires_granted_scope() -> None:
    with pytest.raises(ValueError, match="training scope"):
        redact_governed_json(
            {"result": "synthetic"},
            policy(),
            consent(),
            scope="training",
            evaluated_at=datetime(2026, 8, 9, 2, tzinfo=UTC),
        )


def test_governed_export_rejects_expired_consent() -> None:
    with pytest.raises(ValueError, match="consent has expired"):
        redact_governed_json(
            {"result": "synthetic"},
            policy(),
            consent(),
            scope="evaluation",
            evaluated_at=datetime(2026, 10, 9, tzinfo=UTC),
        )
