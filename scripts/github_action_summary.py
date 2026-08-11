"""Validate an atomic AWE gate receipt and render GitHub Action metadata."""

from __future__ import annotations

import argparse
import html
import os
from pathlib import Path

from awe_tracegate.contracts import GateReceipt, GateReceiptV2

MAX_RECEIPT_BYTES = 16 * 1024 * 1024
MAX_OUTPUT_PATH_CHARS = 4_096


def _safe_path_text(path: str | Path, *, label: str) -> str:
    value = str(path)
    if not value or len(value) > MAX_OUTPUT_PATH_CHARS:
        raise ValueError(
            f"{label} must contain between 1 and {MAX_OUTPUT_PATH_CHARS} characters"
        )
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValueError(f"{label} contains a control character")
    return value


def _load(path: Path) -> GateReceipt | GateReceiptV2:
    if path.stat().st_size > MAX_RECEIPT_BYTES:
        raise ValueError(f"{path} exceeds the {MAX_RECEIPT_BYTES}-byte receipt limit")
    payload = path.read_text(encoding="utf-8")
    try:
        return GateReceipt.model_validate_json(payload)
    except ValueError:
        return GateReceiptV2.model_validate_json(payload)


def _append(path: str | None, text: str) -> None:
    if path:
        destination = Path(_safe_path_text(path, label="GitHub metadata path"))
        with destination.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(text)


def _code(value: object) -> str:
    return f"<code>{html.escape(str(value), quote=True)}</code>"


def _render_v1(receipt: GateReceipt, receipt_path: Path) -> str:
    reasons = "<br>".join(_code(reason) for reason in receipt.reasons)
    if not reasons:
        reasons = "No blocking or review reasons."
    replay = (
        f"{receipt.verification.status}; "
        f"traces_verified={str(receipt.verification.traces_verified).lower()}"
    )
    provenance = (
        f"declared={receipt.evidence_provenance_level or 'not supplied'}; "
        f"enforceable_minimum={receipt.minimum_provenance_level or 'not required'}"
    )
    skill_bom = getattr(receipt, "skill_bom_digest", None) or "not supplied"
    return (
        "## AWE TraceGate\n\n"
        f"**Decision: {receipt.status}**\n\n"
        "| Evidence | Result |\n"
        "| --- | --- |\n"
        f"| Compilation | {_code(receipt.compilation.status)} |\n"
        f"| Exact trace replay | {_code(replay)} |\n"
        f"| Frozen evaluation | {_code(receipt.evaluation.status)} |\n"
        f"| Declared provenance | {_code(provenance)} |\n"
        f"| Skill BOM | {_code(skill_bom)} |\n"
        f"| Gate receipt | {_code(receipt.receipt_hash)} |\n"
        f"| Receipt path | {_code(receipt_path)} |\n\n"
        f"{reasons}\n"
    )


def _render_v2(receipt: GateReceiptV2, receipt_path: Path) -> str:
    reasons = "<br>".join(_code(reason) for reason in receipt.reasons)
    if not reasons:
        reasons = "No blocking or review reasons."
    baseline_quality = (
        receipt.baseline_quality.status if receipt.baseline_quality else "not supplied"
    )
    candidate_quality = (
        receipt.candidate_quality.status
        if receipt.candidate_quality
        else "not supplied"
    )
    quality = f"baseline={baseline_quality}; candidate={candidate_quality}"
    comparison = f"{receipt.comparison.status}: {receipt.comparison.conclusion}"
    comparison_replay = _code(receipt.comparison_verification.status)
    return (
        "## AWE TraceGate\n\n"
        f"**Decision: {receipt.status}**\n\n"
        "| Evidence | Result |\n"
        "| --- | --- |\n"
        f"| Gate v1 | {_code(receipt.v1_gate.status)} |\n"
        f"| Held-input comparison replay | {comparison_replay} |\n"
        f"| Frozen experiment comparison | {_code(comparison)} |\n"
        f"| Typed outcomes and judge calibration | {_code(quality)} |\n"
        f"| Gate v2 receipt | {_code(receipt.receipt_hash)} |\n"
        f"| Receipt path | {_code(receipt_path)} |\n\n"
        f"{reasons}\n"
    )


def render(receipt: GateReceipt | GateReceiptV2, receipt_path: Path) -> str:
    """Render only receipts whose complete typed decision chain has validated."""

    return (
        _render_v2(receipt, receipt_path)
        if isinstance(receipt, GateReceiptV2)
        else _render_v1(receipt, receipt_path)
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()

    receipt_path = _safe_path_text(args.receipt, label="receipt path")
    receipt = _load(Path(receipt_path))
    output = os.environ.get("GITHUB_OUTPUT")
    _append(output, f"decision={receipt.status}\n")
    _append(output, f"receipt-hash={receipt.receipt_hash}\n")
    _append(output, f"receipt-path={receipt_path}\n")

    summary = render(receipt, Path(receipt_path))
    _append(os.environ.get("GITHUB_STEP_SUMMARY"), summary)
    print(summary)
    return {"PASS": 0, "REVIEW": 2, "BLOCK": 2, "ERROR": 1}[receipt.status]


if __name__ == "__main__":
    raise SystemExit(main())
