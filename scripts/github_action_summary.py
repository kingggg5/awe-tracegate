"""Render AWE receipts into GitHub Action outputs and a job summary."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _append(path: str | None, text: str) -> None:
    if path:
        with Path(path).open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--evaluation", type=Path)
    args = parser.parse_args()

    receipt = _load(args.receipt)
    compile_status = receipt.get("status")
    decision = "PASS" if compile_status == "compiled" else "BLOCK"
    reasons = list(receipt.get("reasons") or [])
    evaluation_status = "not supplied"

    if args.evaluation is not None:
        evaluation = _load(args.evaluation)
        evaluation_status = str(evaluation.get("status", "invalid"))
        decision = {
            "block": "BLOCK",
            "pass": decision,
            "review": "REVIEW",
        }.get(evaluation_status, "ERROR")
        reasons.extend(evaluation.get("reasons") or [])

    output = os.environ.get("GITHUB_OUTPUT")
    _append(output, f"decision={decision}\n")
    _append(output, f"receipt-hash={receipt.get('receipt_hash', '')}\n")
    _append(output, f"receipt-path={args.receipt}\n")

    reason_text = "<br>".join(f"`{reason}`" for reason in sorted(set(reasons)))
    if not reason_text:
        reason_text = "No blocking or review reasons."
    summary = (
        "## AWE TraceGate\n\n"
        f"**Decision: {decision}**\n\n"
        "| Evidence | Result |\n"
        "| --- | --- |\n"
        f"| Compilation | `{compile_status}` |\n"
        f"| Evaluation | `{evaluation_status}` |\n"
        f"| Receipt | `{receipt.get('receipt_hash', '')}` |\n\n"
        f"{reason_text}\n"
    )
    _append(os.environ.get("GITHUB_STEP_SUMMARY"), summary)
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
