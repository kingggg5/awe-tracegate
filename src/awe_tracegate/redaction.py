"""Conservative deterministic redaction for JSON evidence before sharing."""

from __future__ import annotations

import re
from collections import Counter
from copy import deepcopy
from typing import Any

from .contracts import RedactionSummary, canonical_digest

_SENSITIVE_KEYS = {
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


def _redact_string(value: str, counts: Counter[str]) -> str:
    redacted = value
    for category, pattern in _VALUE_PATTERNS:
        redacted, replacements = pattern.subn(f"[REDACTED:{category}]", redacted)
        if replacements:
            counts[category] += replacements
    return redacted


def _walk(value: Any, counts: Counter[str]) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for raw_key, child in value.items():
            key = str(raw_key)
            category = _SENSITIVE_KEYS.get(key.lower())
            if category is not None and child is not None:
                counts[category] += 1
                result[key] = f"[REDACTED:{category}]"
            else:
                result[key] = _walk(child, counts)
        return result
    if isinstance(value, list):
        return [_walk(child, counts) for child in value]
    if isinstance(value, str):
        return _redact_string(value, counts)
    return value


def redact_json(value: Any) -> tuple[Any, RedactionSummary]:
    """Redact common secret/PII patterns without mutating the caller's object."""

    source = deepcopy(value)
    counts: Counter[str] = Counter()
    redacted = _walk(source, counts)
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
