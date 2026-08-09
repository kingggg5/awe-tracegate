from __future__ import annotations

import json
from pathlib import Path

from awe_tracegate.schemas import (
    JSON_SCHEMA_DIALECT,
    SCHEMA_MODELS,
    export_schemas,
    schema_identifier,
)


def test_exports_every_versioned_schema(tmp_path: Path) -> None:
    written = export_schemas(tmp_path)

    assert {path.name for path in written} == set(SCHEMA_MODELS)
    for path in written:
        schema = json.loads(path.read_text(encoding="utf-8"))
        assert schema["$id"] == schema_identifier(path.name)
        assert schema["$schema"] == JSON_SCHEMA_DIALECT
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False

    gate_schema = json.loads(
        (tmp_path / "gate-receipt-v1.schema.json").read_text(encoding="utf-8")
    )
    assert "skill_bom_digest" in gate_schema["properties"]
