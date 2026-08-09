"""Fail-closed adapters from external experiment evidence into AWE contracts."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any, cast

from .contracts import (
    EvaluationBundle,
    EvaluationTrial,
    ExperimentManifest,
    ExperimentRun,
    ExperimentTrial,
    canonical_digest,
)

GENERIC_EVALUATION_REVISION = "v1"
OTEL_GENAI_SEMCONV_REVISION = "1d85c963ea51e9c7d24cc330ff67057f6e90e6c5"

_OTEL_EVALUATION_OPERATIONS = frozenset({"invoke_agent", "invoke_workflow"})
_MAX_OTLP_ATTRIBUTES = 512
_MAX_OTLP_RESOURCE_SPANS = 1_024
_MAX_OTLP_SCOPE_SPANS = 4_096
_MAX_OTLP_SPANS = 100_000
_COMMON_OTEL_ATTRIBUTES = {
    "experiment_id": "awe.eval.experiment.id",
    "repository_uri": "awe.eval.repository.uri",
    "commit_sha": "awe.eval.commit.sha",
    "subject_digest": "awe.eval.subject.digest",
    "dataset_digest": "awe.eval.dataset.digest",
    "dataset_split_digest": "awe.eval.dataset_split.digest",
    "harness_name": "awe.eval.harness.name",
    "harness_version": "awe.eval.harness.version",
    "harness_digest": "awe.eval.harness.digest",
    "strategy_name": "awe.eval.strategy.name",
    "strategy_digest": "awe.eval.strategy.digest",
    "model_config_digest": "awe.eval.model_config.digest",
    "environment_digest": "awe.eval.environment.digest",
    "grader_digest": "awe.eval.grader.digest",
}


def _finalize_manifest(
    run: ExperimentRun,
    *,
    source_format: str,
    source_revision: str,
) -> ExperimentManifest:
    manifest_payload = {
        **run.model_dump(mode="json"),
        "schema_version": "awe.experiment-manifest.v1",
        "source_format": source_format,
        "source_revision": source_revision,
    }
    return ExperimentManifest.model_validate(
        {**manifest_payload, "manifest_digest": canonical_digest(manifest_payload)}
    )


def import_generic_evaluation(payload: Any) -> ExperimentManifest:
    """Import the explicit provider-neutral JSON representation."""

    run = ExperimentRun.model_validate(payload)
    return _finalize_manifest(
        run,
        source_format="awe.generic-evaluation",
        source_revision=GENERIC_EVALUATION_REVISION,
    )


def evaluation_bundle_from_manifest(manifest: ExperimentManifest) -> EvaluationBundle:
    """Project rich evidence into the stable v1 evaluator contract."""

    return EvaluationBundle(
        subject_digest=manifest.subject_digest,
        dataset_digest=manifest.dataset_digest,
        trials=tuple(
            EvaluationTrial(
                trial_id=trial.trial_id,
                case_id=trial.case_id,
                succeeded=trial.succeeded,
                safety_violations=trial.safety_violations,
                latency_ms=trial.latency_ms,
                cost_microusd=trial.cost_microusd,
            )
            for trial in manifest.trials
        ),
    )


def _otel_value(encoded: Any) -> str | int | bool | float:
    if not isinstance(encoded, Mapping):
        raise ValueError("OTLP attribute value must be an object")
    supported = (
        ("stringValue", str),
        ("intValue", int),
        ("boolValue", bool),
        ("doubleValue", float),
    )
    present = [name for name, _ in supported if name in encoded]
    if len(present) != 1:
        raise ValueError("OTLP attributes must contain one supported scalar value")
    name = present[0]
    value = encoded[name]
    if name == "intValue":
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise ValueError("OTLP intValue must be a base-10 integer")
        try:
            return int(value)
        except ValueError as error:
            raise ValueError("OTLP intValue must be a base-10 integer") from error
    expected = dict(supported)[name]
    if not isinstance(value, expected):
        raise ValueError(f"OTLP {name} has an invalid scalar type")
    return cast(str | int | bool | float, value)


def _otel_attributes(encoded: Any) -> dict[str, str | int | bool | float]:
    if encoded is None:
        return {}
    if not isinstance(encoded, list):
        raise ValueError("OTLP attributes must be an array")
    if len(encoded) > _MAX_OTLP_ATTRIBUTES:
        raise ValueError(
            f"OTLP attribute count exceeds {_MAX_OTLP_ATTRIBUTES} per object"
        )
    result: dict[str, str | int | bool | float] = {}
    for attribute in encoded:
        if not isinstance(attribute, Mapping):
            raise ValueError("OTLP attribute must be an object")
        key = attribute.get("key")
        if not isinstance(key, str) or not key:
            raise ValueError("OTLP attribute key must be a non-empty string")
        if key in result:
            raise ValueError(f"duplicate OTLP attribute: {key}")
        result[key] = _otel_value(attribute.get("value"))
    return result


def _required(attributes: Mapping[str, Any], name: str, expected: type[Any]) -> Any:
    if name not in attributes:
        raise ValueError(f"missing required OTLP attribute: {name}")
    value = attributes[name]
    if expected is int and isinstance(value, bool):
        raise ValueError(f"OTLP attribute {name} must be int")
    if not isinstance(value, expected):
        raise ValueError(f"OTLP attribute {name} must be {expected.__name__}")
    return value


def _optional_int(attributes: Mapping[str, Any], name: str) -> int | None:
    value = attributes.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"OTLP attribute {name} must be int")
    return cast(int, value)


def _iter_otlp_spans(
    payload: Any,
) -> Iterator[tuple[Mapping[str, Any], dict[str, str | int | bool | float]]]:
    if not isinstance(payload, Mapping):
        raise ValueError("OTLP JSON document must be an object")
    resource_spans = payload.get("resourceSpans")
    if not isinstance(resource_spans, list):
        raise ValueError("OTLP JSON requires resourceSpans")
    if len(resource_spans) > _MAX_OTLP_RESOURCE_SPANS:
        raise ValueError(
            f"OTLP resourceSpans exceeds {_MAX_OTLP_RESOURCE_SPANS} entries"
        )
    seen_spans = 0
    for resource_span in resource_spans:
        if not isinstance(resource_span, Mapping):
            raise ValueError("OTLP resourceSpans entry must be an object")
        resource = resource_span.get("resource", {})
        if not isinstance(resource, Mapping):
            raise ValueError("OTLP resource must be an object")
        resource_attributes = _otel_attributes(resource.get("attributes"))
        scope_spans = resource_span.get("scopeSpans")
        if not isinstance(scope_spans, list):
            raise ValueError("OTLP resourceSpans entry requires scopeSpans")
        if len(scope_spans) > _MAX_OTLP_SCOPE_SPANS:
            raise ValueError(f"OTLP scopeSpans exceeds {_MAX_OTLP_SCOPE_SPANS} entries")
        for scope_span in scope_spans:
            if not isinstance(scope_span, Mapping):
                raise ValueError("OTLP scopeSpans entry must be an object")
            spans = scope_span.get("spans")
            if not isinstance(spans, list):
                raise ValueError("OTLP scopeSpans entry requires spans")
            if seen_spans + len(spans) > _MAX_OTLP_SPANS:
                raise ValueError(f"OTLP span count exceeds {_MAX_OTLP_SPANS}")
            seen_spans += len(spans)
            for span in spans:
                if not isinstance(span, Mapping):
                    raise ValueError("OTLP span must be an object")
                span_attributes = _otel_attributes(span.get("attributes"))
                merged = {**resource_attributes, **span_attributes}
                yield span, merged


def import_otel_genai_evaluation(payload: Any) -> ExperimentManifest:
    """Import annotated OTLP JSON against one pinned GenAI convention revision."""

    common: dict[str, Any] | None = None
    trials: list[ExperimentTrial] = []
    for span, attributes in _iter_otlp_spans(payload):
        operation = attributes.get("gen_ai.operation.name")
        if operation not in _OTEL_EVALUATION_OPERATIONS:
            continue
        if "awe.eval.trial.id" not in attributes:
            continue

        current_common = {
            field: _required(attributes, attribute, str)
            for field, attribute in _COMMON_OTEL_ATTRIBUTES.items()
        }
        current_common["model_provider"] = _required(
            attributes, "gen_ai.provider.name", str
        )
        model_name = attributes.get("gen_ai.response.model") or attributes.get(
            "gen_ai.request.model"
        )
        if not isinstance(model_name, str) or not model_name:
            raise ValueError(
                "OTLP evaluation span requires gen_ai.response.model or "
                "gen_ai.request.model"
            )
        current_common["model_name"] = model_name
        if common is None:
            common = current_common
        elif current_common != common:
            raise ValueError("OTLP evaluation spans contain mixed experiment metadata")

        start_ns = int(_required(span, "startTimeUnixNano", str))
        end_ns = int(_required(span, "endTimeUnixNano", str))
        if end_ns < start_ns:
            raise ValueError("OTLP span end time precedes start time")
        trace_id = _required(span, "traceId", str)
        cached_input_tokens = _optional_int(attributes, "awe.eval.cached_input_tokens")
        trials.append(
            ExperimentTrial(
                trial_id=_required(attributes, "awe.eval.trial.id", str),
                case_id=_required(attributes, "awe.eval.case.id", str),
                succeeded=_required(attributes, "awe.eval.succeeded", bool),
                safety_violations=_required(
                    attributes, "awe.eval.safety_violations", int
                ),
                latency_ms=(end_ns - start_ns) // 1_000_000,
                cost_microusd=_required(attributes, "awe.eval.cost.microusd", int),
                input_tokens=_required(attributes, "gen_ai.usage.input_tokens", int),
                output_tokens=_required(attributes, "gen_ai.usage.output_tokens", int),
                cached_input_tokens=(
                    0 if cached_input_tokens is None else cached_input_tokens
                ),
                trace_id=trace_id,
                grader_result_digest=_required(
                    attributes, "awe.eval.grader_result.digest", str
                ),
                seed=_optional_int(attributes, "awe.eval.seed"),
            )
        )

    if common is None or not trials:
        raise ValueError("OTLP JSON contains no annotated AWE evaluation spans")
    run = ExperimentRun.model_validate({**common, "trials": trials})
    return _finalize_manifest(
        run,
        source_format="otel.genai.otlp-json",
        source_revision=OTEL_GENAI_SEMCONV_REVISION,
    )
