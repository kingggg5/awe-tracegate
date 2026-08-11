from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from awe_tracegate.cli import main as cli_main
from scripts.github_action_summary import _load
from scripts.github_action_summary import main as summary_main

ROOT = Path(__file__).parents[1]


def test_action_keeps_v1_and_exposes_opt_in_held_input_gate_v2() -> None:
    action = (ROOT / "action.yml").read_text(encoding="utf-8")

    assert (
        "baseline-evaluation:\n"
        "    description: Path to the frozen baseline evaluation bundle.\n"
        "    required: true"
    ) in action
    assert (
        "candidate-evaluation:\n"
        "    description: Path to the candidate evaluation bundle.\n"
        "    required: true"
    ) in action
    assert "args=(\n            gate" in action
    assert "comparison-receipt:" in action
    assert "baseline-experiment:" in action
    assert "candidate-experiment:" in action
    assert "gate-v2" in action
    assert 'awe "${args[@]}"' in action
    assert "awe compile" not in action
    assert "awe verify" not in action
    assert "awe evaluate" not in action


def _gate_receipt(tmp_path: Path) -> Path:
    receipt = tmp_path / "gate.json"
    exit_code = cli_main(
        [
            "gate",
            "--traces",
            str(ROOT / "examples/repo_analysis/traces.jsonl"),
            "--baseline",
            str(ROOT / "examples/evaluation/baseline.json"),
            "--candidate",
            str(ROOT / "examples/evaluation/candidate.json"),
            "--policy",
            str(ROOT / "examples/evaluation/policy.json"),
            "--out",
            str(receipt),
        ]
    )
    assert exit_code == 0
    return receipt


def test_action_summary_uses_the_atomic_gate_decision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt = _gate_receipt(tmp_path)
    github_output = tmp_path / "github-output.txt"
    github_summary = tmp_path / "github-summary.md"
    monkeypatch.setenv("GITHUB_OUTPUT", str(github_output))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(github_summary))
    monkeypatch.setattr(
        sys, "argv", ["github_action_summary.py", "--receipt", str(receipt)]
    )

    assert summary_main() == 0

    outputs = github_output.read_text(encoding="utf-8")
    assert "decision=PASS\n" in outputs
    assert "receipt-hash=sha256:" in outputs
    assert f"receipt-path={receipt}\n" in outputs
    summary = github_summary.read_text(encoding="utf-8")
    assert "Frozen evaluation" in summary
    assert "<code>pass</code>" in summary


def test_action_summary_rejects_integrity_only_receipt(tmp_path: Path) -> None:
    payload = json.loads(_gate_receipt(tmp_path).read_text(encoding="utf-8"))
    del payload["evaluation"]
    malformed = tmp_path / "integrity-only.json"
    malformed.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValidationError):
        _load(malformed)


def test_action_summary_rejects_output_command_injection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt = _gate_receipt(tmp_path)
    github_output = tmp_path / "github-output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(github_output))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "github_action_summary.py",
            "--receipt",
            f"{receipt}\nreceipt-hash=sha256:{'f' * 64}",
        ],
    )

    with pytest.raises(ValueError, match="control character"):
        summary_main()
    assert not github_output.exists()
