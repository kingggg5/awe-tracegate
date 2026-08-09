from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from awe_tracegate import __version__
from awe_tracegate.api import _review_workspace_font, _review_workspace_page, app
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


def test_openapi_uses_the_package_version() -> None:
    response = CLIENT.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["version"] == __version__


def test_review_workspace_uses_the_real_api_pipeline() -> None:
    _review_workspace_page.cache_clear()
    response = CLIENT.get("/")
    cached_response = CLIENT.get("/")

    assert response.status_code == 200
    assert cached_response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "AWE TraceGate Review" in response.text
    assert "Review a workflow candidate" in response.text
    assert 'fetchJson("/v1/compile"' in response.text
    assert 'fetchJson("/v1/verify"' in response.text
    assert 'fetchJson("/v1/evaluate"' in response.text
    assert '"/v1/experiments/import/generic"' in response.text
    assert 'fetchJson("/v1/promote"' in response.text
    assert "Sample data" in response.text
    assert 'id="experimentFile"' in response.text
    assert "REQUEST_TIMEOUT_MS = 30000" in response.text
    assert "MAX_FILE_BYTES = 10 * 1024 * 1024" in response.text
    assert 'id="commandInput"' not in response.text
    assert "TraceGate Review" in response.text
    assert 'id="reviewSurface"' in response.text
    assert "Atkinson Hyperlegible Next" in response.text
    assert "Select a decision" in response.text
    assert "TraceGate does not authenticate this identity" in response.text
    assert 'id="toolsSurface"' in response.text
    assert (
        "Browser, email, shell, and deployment connectors are intentionally outside"
        in response.text
    )
    assert 'value="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"' not in response.text
    assert 'value="local-reviewer"' not in response.text
    assert _review_workspace_page.cache_info().hits == 1


def test_review_workspace_serves_the_bundled_accessible_font() -> None:
    _review_workspace_font.cache_clear()

    response = CLIENT.get("/assets/atkinson-hyperlegible-next.ttf")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("font/ttf")
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert response.content[:4] == b"\x00\x01\x00\x00"


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


def test_import_experiment_endpoint_returns_content_addressed_manifest() -> None:
    payload = (EVALUATION_DIRECTORY / "experiment.json").read_text(encoding="utf-8")

    response = CLIENT.post(
        "/v1/experiments/import/generic",
        content=payload,
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 200
    assert response.json()["source_format"] == "awe.generic-evaluation"
    assert response.json()["manifest_digest"].startswith("sha256:")


def test_promote_endpoint_requires_a_replayable_evidence_chain() -> None:
    compile_response = CLIENT.post("/v1/compile", json=request_payload())
    verification_response = CLIENT.post(
        "/v1/verify",
        json={
            "receipt": compile_response.json(),
            "traces": request_payload()["traces"],
        },
    )
    baseline = (EVALUATION_DIRECTORY / "baseline.json").read_text(encoding="utf-8")
    candidate = (EVALUATION_DIRECTORY / "candidate.json").read_text(encoding="utf-8")
    policy = (EVALUATION_DIRECTORY / "policy.json").read_text(encoding="utf-8")
    evaluation_response = CLIENT.post(
        "/v1/evaluate",
        content=(
            f'{{"baseline":{baseline},"candidate":{candidate},"policy":{policy}}}'
        ),
        headers={"content-type": "application/json"},
    )

    response = CLIENT.post(
        "/v1/promote",
        json={
            "compilation": compile_response.json(),
            "verification": verification_response.json(),
            "traces": request_payload()["traces"],
            "evaluation": evaluation_response.json(),
            "decision": "approved",
            "actor_id": "maintainer@example.com",
            "commit_sha": "a" * 40,
            "issued_at": "2026-08-08T00:00:00Z",
            "rationale": "Reviewed a locally replayed evidence chain.",
        },
    )

    assert response.status_code == 200
    assert response.json()["decision"] == "approved"
    assert response.json()["traces_verified"] is True
