"""Export the canonical FastAPI OpenAPI document for generated SDKs."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from awe_tracegate.api import app


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(
        (
            json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        ).encode("utf-8")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
