from __future__ import annotations

from awe_tracegate.redaction import redact_json


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
