from __future__ import annotations

import json
from pathlib import Path

from awe_tracegate.schemas import SCHEMA_MODELS, export_schemas


def test_exports_every_versioned_schema(tmp_path: Path) -> None:
    written = export_schemas(tmp_path)

    assert {path.name for path in written} == set(SCHEMA_MODELS)
    for path in written:
        schema = json.loads(path.read_text(encoding="utf-8"))
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
