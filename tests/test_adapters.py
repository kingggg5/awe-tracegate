from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from awe_tracegate.adapters import (
    OTEL_GENAI_SEMCONV_REVISION,
    evaluation_bundle_from_manifest,
    import_generic_evaluation,
    import_otel_genai_evaluation,
)
from awe_tracegate.contracts import ExperimentManifest

DIGESTS = {
    name: "sha256:" + character * 64
    for name, character in {
        "subject": "a",
        "dataset": "b",
        "split": "c",
        "harness": "d",
        "strategy": "e",
        "model": "f",
        "environment": "1",
        "grader": "2",
        "result": "3",
    }.items()
}


def generic_payload() -> dict[str, Any]:
    return {
        "experiment_id": "experiment-2026-08-09",
        "repository_uri": "https://github.com/example/agent",
        "commit_sha": "a" * 40,
        "subject_digest": DIGESTS["subject"],
        "dataset_digest": DIGESTS["dataset"],
        "dataset_split_digest": DIGESTS["split"],
        "harness_name": "example.harness",
        "harness_version": "1.2.0",
        "harness_digest": DIGESTS["harness"],
        "strategy_name": "headroom",
        "strategy_digest": DIGESTS["strategy"],
        "model_provider": "openai",
        "model_name": "example-model-2026",
        "model_config_digest": DIGESTS["model"],
        "environment_digest": DIGESTS["environment"],
        "grader_digest": DIGESTS["grader"],
        "trials": [
            {
                "trial_id": "trial-1",
                "case_id": "case-1",
                "succeeded": True,
                "safety_violations": 0,
                "latency_ms": 420,
                "cost_microusd": 1200,
                "input_tokens": 800,
                "output_tokens": 120,
                "cached_input_tokens": 200,
                "trace_id": "0" * 32,
                "grader_result_digest": DIGESTS["result"],
                "seed": 42,
            }
        ],
    }


def _attribute(key: str, value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        encoded = {"boolValue": value}
    elif isinstance(value, int):
        encoded = {"intValue": str(value)}
    else:
        encoded = {"stringValue": value}
    return {"key": key, "value": encoded}


def otlp_payload() -> dict[str, Any]:
    source = generic_payload()
    common = {
        "awe.eval.experiment.id": source["experiment_id"],
        "awe.eval.repository.uri": source["repository_uri"],
        "awe.eval.commit.sha": source["commit_sha"],
        "awe.eval.subject.digest": source["subject_digest"],
        "awe.eval.dataset.digest": source["dataset_digest"],
        "awe.eval.dataset_split.digest": source["dataset_split_digest"],
        "awe.eval.harness.name": source["harness_name"],
        "awe.eval.harness.version": source["harness_version"],
        "awe.eval.harness.digest": source["harness_digest"],
        "awe.eval.strategy.name": source["strategy_name"],
        "awe.eval.strategy.digest": source["strategy_digest"],
        "awe.eval.model_config.digest": source["model_config_digest"],
        "awe.eval.environment.digest": source["environment_digest"],
        "awe.eval.grader.digest": source["grader_digest"],
        "gen_ai.provider.name": source["model_provider"],
        "gen_ai.response.model": source["model_name"],
    }
    trial = source["trials"][0]
    trial_attributes = {
        "gen_ai.operation.name": "invoke_agent",
        "awe.eval.trial.id": trial["trial_id"],
        "awe.eval.case.id": trial["case_id"],
        "awe.eval.succeeded": trial["succeeded"],
        "awe.eval.safety_violations": trial["safety_violations"],
        "awe.eval.cost.microusd": trial["cost_microusd"],
        "gen_ai.usage.input_tokens": trial["input_tokens"],
        "gen_ai.usage.output_tokens": trial["output_tokens"],
        "awe.eval.cached_input_tokens": trial["cached_input_tokens"],
        "awe.eval.grader_result.digest": trial["grader_result_digest"],
        "awe.eval.seed": trial["seed"],
    }
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        _attribute(key, value) for key, value in common.items()
                    ]
                },
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": trial["trace_id"],
                                "spanId": "1" * 16,
                                "name": "invoke_agent example",
                                "startTimeUnixNano": "1000000000",
                                "endTimeUnixNano": "1420000000",
                                "attributes": [
                                    _attribute(key, value)
                                    for key, value in trial_attributes.items()
                                ],
                            }
                        ]
                    }
                ],
            }
        ]
    }


def test_generic_import_is_content_addressed_and_projects_to_v1() -> None:
    manifest = import_generic_evaluation(generic_payload())

    assert manifest.source_format == "awe.generic-evaluation"
    assert manifest.manifest_digest.startswith("sha256:")
    assert manifest.trials[0].input_tokens == 800
    projected = evaluation_bundle_from_manifest(manifest)
    assert projected.subject_digest == manifest.subject_digest
    assert projected.trials[0].latency_ms == 420


def test_otel_import_matches_generic_evidence_contract() -> None:
    generic = import_generic_evaluation(generic_payload())
    otel = import_otel_genai_evaluation(otlp_payload())

    assert otel.source_revision == OTEL_GENAI_SEMCONV_REVISION
    ignored = {"source_format", "source_revision", "manifest_digest"}
    assert otel.model_dump(exclude=ignored) == generic.model_dump(exclude=ignored)


def test_otel_import_refuses_missing_ground_truth() -> None:
    payload = otlp_payload()
    attributes = payload["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["attributes"]
    attributes[:] = [item for item in attributes if item["key"] != "awe.eval.succeeded"]

    with pytest.raises(ValueError, match=r"awe\.eval\.succeeded"):
        import_otel_genai_evaluation(payload)


def test_otel_import_refuses_deprecated_token_aliases() -> None:
    payload = otlp_payload()
    attributes = payload["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["attributes"]
    for item in attributes:
        if item["key"] == "gen_ai.usage.input_tokens":
            item["key"] = "gen_ai.usage.prompt_tokens"

    with pytest.raises(ValueError, match=r"gen_ai\.usage\.input_tokens"):
        import_otel_genai_evaluation(payload)


def test_otel_import_refuses_unbounded_attributes() -> None:
    payload = otlp_payload()
    span = payload["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    span["attributes"].extend(
        _attribute(f"awe.synthetic.padding.{index}", index) for index in range(512)
    )

    with pytest.raises(ValueError, match="attribute count exceeds"):
        import_otel_genai_evaluation(payload)


def test_manifest_rejects_tampering() -> None:
    manifest = import_generic_evaluation(generic_payload())
    tampered = manifest.model_dump(mode="json")
    tampered["trials"][0]["output_tokens"] += 1

    with pytest.raises(ValidationError, match="manifest digest"):
        ExperimentManifest.model_validate(tampered)


def test_manifest_refuses_cached_tokens_greater_than_input() -> None:
    payload = generic_payload()
    payload["trials"][0]["cached_input_tokens"] = 801

    with pytest.raises(ValidationError, match="cached input tokens"):
        import_generic_evaluation(payload)
