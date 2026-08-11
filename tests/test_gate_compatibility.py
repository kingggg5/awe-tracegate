from __future__ import annotations

import copy
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from pydantic import ValidationError as PydanticValidationError

from awe_tracegate.cli import main as cli_main
from awe_tracegate.contracts import (
    EvaluationBundle,
    EvaluationPolicy,
    ExecutionTrace,
    GateReceipt,
    canonical_digest,
)
from awe_tracegate.gate import validate_gate_receipt_inputs
from awe_tracegate.schemas import export_schemas

ROOT = Path(__file__).parents[1]
GOLDEN = ROOT / "tests" / "compatibility" / "gate-receipt-v1.json"


def _traces() -> tuple[ExecutionTrace, ...]:
    return tuple(
        ExecutionTrace.model_validate_json(line)
        for line in (ROOT / "examples/repo_analysis/traces.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    )


def _bundle(name: str) -> EvaluationBundle:
    return EvaluationBundle.model_validate_json(
        (ROOT / f"examples/evaluation/{name}.json").read_text(encoding="utf-8")
    )


def _policy() -> EvaluationPolicy:
    return EvaluationPolicy.model_validate_json(
        (ROOT / "examples/evaluation/policy.json").read_text(encoding="utf-8")
    )


def _golden_receipt() -> GateReceipt:
    return GateReceipt.model_validate_json(GOLDEN.read_text(encoding="utf-8"))


def test_real_cli_keeps_gate_receipt_v1_golden_compatible(tmp_path: Path) -> None:
    generated = tmp_path / "gate-receipt-v1.json"

    assert (
        cli_main(
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
                str(generated),
            ]
        )
        == 0
    )
    assert generated.read_bytes() == GOLDEN.read_bytes()
    assert _golden_receipt().receipt_hash == (
        "sha256:20846ba82b0d81a8946989e3e55c28a9899033154cf7e8ab5b1d358992572638"
    )


def test_exported_v1_schema_accepts_golden_and_rejects_unknown_contracts(
    tmp_path: Path,
) -> None:
    export_schemas(tmp_path)
    schema = json.loads(
        (tmp_path / "gate-receipt-v1.schema.json").read_text(encoding="utf-8")
    )
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)

    validator.validate(golden)
    for path, value in (
        (("schema_version",), "awe.gate-receipt.v2"),
        (("evaluation", "schema_version"), "awe.evaluation-receipt.v2"),
        (("unexpected",), True),
    ):
        incompatible = copy.deepcopy(golden)
        _set_path(incompatible, path, value)
        with pytest.raises(JsonSchemaValidationError):
            validator.validate(incompatible)
        with pytest.raises(PydanticValidationError):
            GateReceipt.model_validate(incompatible)


def _reverse_object_order(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _reverse_object_order(item)
            for key, item in reversed(tuple(value.items()))
        }
    if isinstance(value, list):
        return [_reverse_object_order(item) for item in value]
    return value


def test_canonical_receipt_ignores_json_order_and_whitespace_drift() -> None:
    canonical = _golden_receipt()
    reordered = _reverse_object_order(canonical.model_dump(mode="json"))
    alternate_json = json.dumps(reordered, ensure_ascii=True, separators=(", ", ": "))
    reparsed = GateReceipt.model_validate_json(alternate_json)

    assert reparsed == canonical
    assert canonical_digest(reparsed) == canonical_digest(canonical)
    assert reparsed.receipt_hash == canonical.receipt_hash


JsonPath = tuple[str | int, ...]


def _scalar_paths(value: Any, path: JsonPath = ()) -> Iterator[JsonPath]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _scalar_paths(item, (*path, key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _scalar_paths(item, (*path, index))
    else:
        yield path


def _set_path(value: Any, path: JsonPath, replacement: Any) -> None:
    parent = value
    for segment in path[:-1]:
        parent = parent[segment]
    parent[path[-1]] = replacement


def _mutate_scalar(value: Any) -> Any:
    if value is None:
        return "unexpected"
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, str):
        if value.startswith("sha256:") and len(value) == 71:
            return f"{value[:-1]}{'0' if value[-1] != '0' else '1'}"
        return f"{value}_tampered"
    raise AssertionError(f"unsupported scalar fixture value: {value!r}")


def test_every_scalar_tamper_fails_internal_validation_without_rehash() -> None:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    accepted: list[JsonPath] = []

    for path in _scalar_paths(golden):
        tampered = copy.deepcopy(golden)
        parent = tampered
        for segment in path:
            parent = parent[segment]
        _set_path(tampered, path, _mutate_scalar(parent))
        try:
            GateReceipt.model_validate(tampered)
        except PydanticValidationError:
            continue
        accepted.append(path)

    assert accepted == []


def test_rehashed_nested_tamper_still_fails_exact_input_replay() -> None:
    tampered = json.loads(GOLDEN.read_text(encoding="utf-8"))
    tampered["evaluation"]["candidate"]["success_count"] = 0
    evaluation_payload = {
        key: value
        for key, value in tampered["evaluation"].items()
        if key != "receipt_hash"
    }
    tampered["evaluation"]["receipt_hash"] = canonical_digest(evaluation_payload)
    gate_payload = {
        key: value for key, value in tampered.items() if key != "receipt_hash"
    }
    tampered["receipt_hash"] = canonical_digest(gate_payload)

    structurally_valid = GateReceipt.model_validate(tampered)
    with pytest.raises(ValueError, match="does not match exact input replay"):
        validate_gate_receipt_inputs(
            structurally_valid,
            _traces(),
            _bundle("baseline"),
            _bundle("candidate"),
            _policy(),
        )


@pytest.mark.parametrize("changed_input", ["traces", "baseline", "candidate", "policy"])
def test_consumer_replay_rejects_each_exact_input_mismatch(changed_input: str) -> None:
    receipt = _golden_receipt()
    traces = _traces()
    baseline = _bundle("baseline")
    candidate = _bundle("candidate")
    policy = _policy()

    assert (
        validate_gate_receipt_inputs(receipt, traces, baseline, candidate, policy)
        == receipt
    )
    if changed_input == "traces":
        traces = (
            traces[0].model_copy(update={"trace_id": "repo_analysis_changed"}),
            *traces[1:],
        )
    elif changed_input == "baseline":
        first = baseline.trials[0].model_copy(
            update={"latency_ms": baseline.trials[0].latency_ms + 1}
        )
        baseline = baseline.model_copy(update={"trials": (first, *baseline.trials[1:])})
    elif changed_input == "candidate":
        first = candidate.trials[0].model_copy(
            update={"cost_microusd": candidate.trials[0].cost_microusd + 1}
        )
        candidate = candidate.model_copy(
            update={"trials": (first, *candidate.trials[1:])}
        )
    else:
        policy = policy.model_copy(
            update={"maximum_cost_increase_bps": policy.maximum_cost_increase_bps + 1}
        )

    with pytest.raises(ValueError, match="does not match exact input replay"):
        validate_gate_receipt_inputs(receipt, traces, baseline, candidate, policy)
