"""Conservative deterministic redaction for JSON evidence before sharing."""

from __future__ import annotations

import re
from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any

from .contracts import (
    DatasetConsentRecord,
    DatasetScope,
    GovernedRedactionSummary,
    RedactionCategory,
    RedactionPolicy,
    RedactionSummary,
    canonical_digest,
)

_SENSITIVE_KEYS: dict[str, RedactionCategory] = {
    "access_token": "secret",
    "api_key": "secret",
    "authorization": "secret",
    "client_secret": "secret",
    "customer_email": "customer_data",
    "customer_name": "customer_data",
    "email": "pii",
    "password": "secret",
    "phone": "pii",
    "refresh_token": "secret",
    "secret": "secret",
    "ssn": "pii",
    "token": "secret",
}
_VALUE_PATTERNS = (
    (
        "secret",
        re.compile(
            r"(?i)\b(?:gh[pousr]_[A-Za-z0-9]{20,}|"
            r"github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|"
            r"AKIA[0-9A-Z]{16})\b"
        ),
    ),
    ("secret", re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}")),
    (
        "pii",
        re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"),
    ),
)
_MAX_JSON_DEPTH = 64


def _redact_string(value: str, counts: Counter[str]) -> str:
    redacted = value
    for category, pattern in _VALUE_PATTERNS:
        redacted, replacements = pattern.subn(f"[REDACTED:{category}]", redacted)
        if replacements:
            counts[category] += replacements
    return redacted


def _walk_with_rules(
    value: Any,
    counts: Counter[str],
    sensitive_keys: dict[str, RedactionCategory],
    denied_keys: dict[str, RedactionCategory],
    depth: int = 0,
) -> Any:
    if depth > _MAX_JSON_DEPTH:
        raise ValueError(f"JSON nesting exceeds {_MAX_JSON_DEPTH} levels")
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for raw_key, child in value.items():
            key = str(raw_key)
            normalized_key = key.lower()
            category = denied_keys.get(normalized_key) or sensitive_keys.get(
                normalized_key
            )
            if category is not None and child is not None:
                counts[category] += 1
                result[key] = f"[REDACTED:{category}]"
            else:
                result[key] = _walk_with_rules(
                    child, counts, sensitive_keys, denied_keys, depth + 1
                )
        return result
    if isinstance(value, list):
        return [
            _walk_with_rules(child, counts, sensitive_keys, denied_keys, depth + 1)
            for child in value
        ]
    if isinstance(value, str):
        return _redact_string(value, counts)
    return value


def redact_json(value: Any) -> tuple[Any, RedactionSummary]:
    """Redact common secret/PII patterns without mutating the caller's object."""

    source = deepcopy(value)
    counts: Counter[str] = Counter()
    redacted = _walk_with_rules(source, counts, _SENSITIVE_KEYS, {})
    input_digest = canonical_digest(source)
    output_digest = canonical_digest(redacted)
    summary = RedactionSummary(
        input_digest=input_digest,
        output_digest=output_digest,
        changed=input_digest != output_digest,
        replacements=sum(counts.values()),
        categories=dict(sorted(counts.items())),
    )
    return redacted, summary


def redact_governed_json(
    value: Any,
    policy: RedactionPolicy,
    consent: DatasetConsentRecord,
    *,
    scope: DatasetScope,
    evaluated_at: datetime,
) -> tuple[Any, GovernedRedactionSummary]:
    """Redact only after an explicit, current, scope-matching consent check."""

    if evaluated_at.utcoffset() != timedelta(0):
        raise ValueError("evaluated_at must include the UTC timezone")
    if consent.status != "active":
        raise ValueError("dataset consent is revoked")
    if evaluated_at < consent.granted_at:
        raise ValueError("dataset consent is not active yet")
    if consent.expires_at is not None and evaluated_at >= consent.expires_at:
        raise ValueError("dataset consent has expired")
    if scope not in consent.scopes:
        raise ValueError(f"dataset consent does not grant {scope} scope")

    source = deepcopy(value)
    export_value = source
    removed_fields = 0
    counts: Counter[str] = Counter()
    if policy.allowed_top_level_keys and isinstance(source, dict):
        allowed = set(policy.allowed_top_level_keys)
        export_value = {}
        for raw_key, child in source.items():
            key = str(raw_key)
            if key.lower() in allowed:
                export_value[key] = child
            else:
                removed_fields += 1
                counts["policy_denied"] += 1

    sensitive_keys: dict[str, RedactionCategory] = {
        **_SENSITIVE_KEYS,
        **policy.additional_sensitive_keys,
    }
    redacted = _walk_with_rules(
        export_value,
        counts,
        sensitive_keys,
        policy.denied_keys,
    )
    input_digest = canonical_digest(source)
    output_digest = canonical_digest(redacted)
    summary = GovernedRedactionSummary(
        input_digest=input_digest,
        output_digest=output_digest,
        changed=input_digest != output_digest,
        replacements=sum(counts.values()) - removed_fields,
        removed_fields=removed_fields,
        categories=dict(sorted(counts.items())),
        policy_digest=canonical_digest(policy),
        consent_record_digest=canonical_digest(consent),
        consent_id=consent.consent_id,
        scope=scope,
        evaluated_at=evaluated_at,
    )
    return redacted, summary
