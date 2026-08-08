from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from awe_tracegate.api import app
from awe_tracegate.contracts import ExecutionTrace

EXAMPLE_TRACES = (
    Path(__file__).parents[1] / "examples" / "repo_analysis" / "traces.jsonl"
)
CLIENT = TestClient(app)
EVALUATION_DIRECTORY = Path(__file__).parents[1] / "examples" / "evaluation"


def request_payload() -> dict[str, object]:
    traces = [
        ExecutionTrace.model_validate_json(line).model_dump(mode="json")
        for line in EXAMPLE_TRACES.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return {"traces": traces}


def test_compile_endpoint_returns_typed_receipt() -> None:
    response = CLIENT.post("/v1/compile", json=request_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "compiled"
    assert body["candidate"]["effect_scope"] == "pure_or_read"
    assert body["receipt_hash"].startswith("sha256:")


def test_compile_endpoint_rejects_unknown_contract_fields() -> None:
    payload = request_payload()
    payload["unexpected"] = True

    response = CLIENT.post("/v1/compile", json=payload)

    assert response.status_code == 422


def test_compile_endpoint_returns_refusal_for_one_valid_trace() -> None:
    payload = request_payload()
    payload["traces"] = payload["traces"][:1]

    response = CLIENT.post("/v1/compile", json=payload)

    assert response.status_code == 200
    assert response.json()["status"] == "refused"
    assert response.json()["reasons"] == ["insufficient_trace_evidence"]


def test_health_is_explicitly_keyless() -> None:
    response = CLIENT.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "mode": "offline_keyless"}


def test_verify_endpoint_replays_source_traces() -> None:
    compile_response = CLIENT.post("/v1/compile", json=request_payload())

    response = CLIENT.post(
        "/v1/verify",
        json={
            "receipt": compile_response.json(),
            "traces": request_payload()["traces"],
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "valid"
    assert response.json()["traces_verified"] is True


def test_evaluate_endpoint_returns_policy_decision() -> None:
    baseline = (EVALUATION_DIRECTORY / "baseline.json").read_text(encoding="utf-8")
    candidate = (EVALUATION_DIRECTORY / "candidate.json").read_text(encoding="utf-8")
    policy = (EVALUATION_DIRECTORY / "policy.json").read_text(encoding="utf-8")

    response = CLIENT.post(
        "/v1/evaluate",
        content=(
            f'{{"baseline":{baseline},"candidate":{candidate},"policy":{policy}}}'
        ),
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "pass"
