"""Generate the checked-in, synthetic end-to-end Gate v2 fixture."""

from __future__ import annotations

import argparse
from pathlib import Path

from awe_tracegate.demo import generate_demo


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    for path in generate_demo(_parse_args().out, replace_managed_files=True):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
