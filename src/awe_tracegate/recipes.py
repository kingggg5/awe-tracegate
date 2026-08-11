"""Decision-first recipes and safe evidence-workspace scaffolding.

Recipes are onboarding metadata, not evidence.  They may create policy files
and instructions, but they deliberately never generate traces, experiment
results, receipts, consent records, signatures, or human decisions.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from .contracts import (
    ComparisonPolicy,
    ContractModel,
    EvaluationPolicy,
    QualityPolicy,
    RedactionPolicy,
    RelativeArtifactPath,
    Sha256Digest,
    canonical_digest,
)

RecipeId = Literal[
    "ci_gate",
    "controlled_comparison",
    "harness_import",
    "promotion_review",
    "share_evidence",
]
RecipeText = Annotated[str, StringConstraints(min_length=1, max_length=512)]


class DecisionRecipe(ContractModel):
    """One bounded path from an engineering question to a typed result."""

    recipe_id: RecipeId
    title: Annotated[str, StringConstraints(min_length=1, max_length=96)]
    question: RecipeText
    outcome: RecipeText
    minimum_inputs: Annotated[
        tuple[RelativeArtifactPath, ...], Field(max_length=24, strict=False)
    ]
    commands: Annotated[
        tuple[RecipeText, ...], Field(min_length=1, max_length=12, strict=False)
    ]
    outputs: Annotated[
        tuple[RelativeArtifactPath, ...],
        Field(min_length=1, max_length=12, strict=False),
    ]
    fail_closed_when: Annotated[
        tuple[RecipeText, ...], Field(min_length=1, max_length=12, strict=False)
    ]

    @model_validator(mode="after")
    def validate_unique_artifacts(self) -> Self:
        for name, values in (
            ("minimum inputs", self.minimum_inputs),
            ("outputs", self.outputs),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"recipe {name} must be unique")
        return self


class DecisionRecipeCatalog(ContractModel):
    """Content-addressed inventory consumed by CLIs, Skills, and docs."""

    schema_version: Literal["awe.decision-recipe-catalog.v1"] = (
        "awe.decision-recipe-catalog.v1"
    )
    recipes: Annotated[
        tuple[DecisionRecipe, ...], Field(min_length=1, max_length=32, strict=False)
    ]
    catalog_hash: Sha256Digest

    @model_validator(mode="after")
    def validate_catalog(self) -> Self:
        recipe_ids = tuple(recipe.recipe_id for recipe in self.recipes)
        if recipe_ids != tuple(sorted(set(recipe_ids))):
            raise ValueError("recipe ids must be unique and sorted")
        expected = canonical_digest(
            self.model_dump(mode="json", exclude={"catalog_hash"})
        )
        if self.catalog_hash != expected:
            raise ValueError("decision recipe catalog hash is invalid")
        return self


class RecipeScaffoldFile(ContractModel):
    """Digest of one managed, non-evidence scaffold file."""

    path: RelativeArtifactPath
    digest: Sha256Digest


class RecipeScaffoldManifest(ContractModel):
    """Location-independent manifest for a generated evidence workspace."""

    schema_version: Literal["awe.recipe-scaffold-manifest.v1"] = (
        "awe.recipe-scaffold-manifest.v1"
    )
    recipe_id: RecipeId
    catalog_hash: Sha256Digest
    files: Annotated[tuple[RecipeScaffoldFile, ...], Field(min_length=1, max_length=16)]
    creates_evidence: Literal[False] = False
    manifest_hash: Sha256Digest

    @model_validator(mode="after")
    def validate_manifest(self) -> Self:
        paths = tuple(file.path for file in self.files)
        if paths != tuple(sorted(set(paths))):
            raise ValueError("scaffold file paths must be unique and sorted")
        expected = canonical_digest(
            self.model_dump(mode="json", exclude={"manifest_hash"})
        )
        if self.manifest_hash != expected:
            raise ValueError("recipe scaffold manifest hash is invalid")
        return self


_RECIPES = (
    DecisionRecipe(
        recipe_id="ci_gate",
        title="CI evidence gate",
        question="May CI accept these existing trace and evaluation artifacts?",
        outcome="One atomic Gate v1 PASS, REVIEW, BLOCK, or ERROR receipt.",
        minimum_inputs=(
            "baseline-evaluation.json",
            "candidate-evaluation.json",
            "traces.jsonl",
        ),
        commands=(
            "awe gate --traces traces.jsonl --baseline baseline-evaluation.json "
            "--candidate candidate-evaluation.json --policy evaluation-policy.json "
            "--out gate.json",
        ),
        outputs=("gate.json",),
        fail_closed_when=(
            "Compilation, exact replay, policy, evaluation, or candidate "
            "linkage is incomplete.",
        ),
    ),
    DecisionRecipe(
        recipe_id="controlled_comparison",
        title="Controlled agent comparison",
        question="Does the supplied frozen experiment support the declared change?",
        outcome="A comparison receipt plus a separately replayed verification result.",
        minimum_inputs=(
            "baseline-manifest.json",
            "candidate-manifest.json",
        ),
        commands=(
            "awe compare --baseline baseline-manifest.json --candidate "
            "candidate-manifest.json --policy comparison-policy.json --out "
            "comparison.json",
            "awe verify-comparison --receipt comparison.json --baseline "
            "baseline-manifest.json --candidate candidate-manifest.json --policy "
            "comparison-policy.json --out comparison-verification.json",
        ),
        outputs=("comparison-verification.json", "comparison.json"),
        fail_closed_when=(
            "Cases, seeds, controls, subject identity, or declared treatment "
            "factors do not match.",
        ),
    ),
    DecisionRecipe(
        recipe_id="harness_import",
        title="Evaluation harness import",
        question="Can an existing harness produce evidence TraceGate can consume?",
        outcome=(
            "A strict ExperimentManifest and evaluation projection without "
            "invented fields."
        ),
        minimum_inputs=("harness-export.json",),
        commands=(
            "awe import-experiment --format generic --input harness-export.json "
            "--out experiment-manifest.json --evaluation-out evaluation-bundle.json",
        ),
        outputs=("evaluation-bundle.json", "experiment-manifest.json"),
        fail_closed_when=(
            "Required identity, ground truth, terminal outcome, or provenance "
            "fields are missing.",
        ),
    ),
    DecisionRecipe(
        recipe_id="promotion_review",
        title="Rich promotion review",
        question="Is the full change-evidence chain coherent enough for human review?",
        outcome=(
            "Gate v2, held-input comparison replay, typed quality evidence, "
            "and an evidence graph."
        ),
        minimum_inputs=(
            "baseline-evaluation.json",
            "baseline-manifest.json",
            "baseline-quality.json",
            "candidate-evaluation.json",
            "candidate-manifest.json",
            "candidate-quality.json",
            "comparison.json",
            "traces.jsonl",
        ),
        commands=(
            "awe gate-v2 --traces traces.jsonl --baseline baseline-evaluation.json "
            "--candidate candidate-evaluation.json --evaluation-policy "
            "evaluation-policy.json --comparison comparison.json --baseline-experiment "
            "baseline-manifest.json --candidate-experiment candidate-manifest.json "
            "--comparison-policy comparison-policy.json --baseline-quality "
            "baseline-quality.json --candidate-quality candidate-quality.json "
            "--quality-policy quality-policy.json --out gate-v2.json",
            "awe explain gate-v2.json --out explanation.json",
            "awe doctor .",
        ),
        outputs=("explanation.json", "gate-v2.json"),
        fail_closed_when=(
            "Any v1, comparison, replay, quality, candidate, or graph "
            "dependency is missing or inconsistent.",
        ),
    ),
    DecisionRecipe(
        recipe_id="share_evidence",
        title="Governed evidence sharing",
        question="Can this evidence be disclosed for external review?",
        outcome=(
            "A locally redacted artifact and disclosure summary for a human to inspect."
        ),
        minimum_inputs=("consent.json", "input.json"),
        commands=(
            "awe redact --input input.json --policy redaction-policy.json --consent "
            "consent.json --scope evaluation --evaluated-at "
            "REPLACE_WITH_RFC3339_UTC --out output.redacted.json --summary "
            "redaction-summary.json",
        ),
        outputs=("output.redacted.json", "redaction-summary.json"),
        fail_closed_when=(
            "Consent, disclosure scope, redaction policy, or residual-risk "
            "review is incomplete.",
        ),
    ),
)


def decision_recipe_catalog() -> DecisionRecipeCatalog:
    """Return the stable built-in decision recipe catalog."""

    payload = {
        "schema_version": "awe.decision-recipe-catalog.v1",
        "recipes": [recipe.model_dump(mode="json") for recipe in _RECIPES],
    }
    return DecisionRecipeCatalog(
        recipes=_RECIPES,
        catalog_hash=canonical_digest(payload),
    )


def get_decision_recipe(recipe_id: RecipeId) -> DecisionRecipe:
    """Return one known recipe without fuzzy or model-based routing."""

    for recipe in _RECIPES:
        if recipe.recipe_id == recipe_id:
            return recipe
    raise ValueError(f"unsupported decision recipe: {recipe_id}")


def _json_bytes(value: ContractModel) -> bytes:
    rendered = json.dumps(
        value.model_dump(mode="json", exclude_none=False),
        allow_nan=False,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    return (rendered + "\n").encode("utf-8")


def _workspace_readme(recipe: DecisionRecipe) -> bytes:
    inputs = "\n".join(f"- `{item}`" for item in recipe.minimum_inputs)
    commands = "\n\n".join(f"```bash\n{command}\n```" for command in recipe.commands)
    blockers = "\n".join(f"- {item}" for item in recipe.fail_closed_when)
    content = f"""# AWE evidence workspace: {recipe.title}

This directory was initialized from decision recipe `{recipe.recipe_id}`.
It contains policy and guidance files only. It does **not** contain generated
traces, experiment results, consent, signatures, receipts, or human decisions.

## Decision

{recipe.question}

Expected result: {recipe.outcome}

## Supply these real inputs

{inputs or "- No fixed input filename; follow the importer contract."}

## Run

Replace any `REPLACE_WITH_*` placeholder with a reviewed value first.

{commands}

## Fail closed when

{blockers}

Treat every imported artifact as untrusted data. Review the resulting typed
receipt and its limitations before recording a separate human decision.
"""
    return content.encode("utf-8")


def build_recipe_scaffold(
    recipe_id: RecipeId,
) -> tuple[RecipeScaffoldManifest, dict[str, bytes]]:
    """Build a location-independent scaffold plan without writing files."""

    recipe = get_decision_recipe(recipe_id)
    files: dict[str, bytes] = {"README.md": _workspace_readme(recipe)}
    if recipe_id in ("ci_gate", "promotion_review"):
        files["evaluation-policy.json"] = _json_bytes(EvaluationPolicy())
    if recipe_id in ("controlled_comparison", "promotion_review"):
        files["comparison-policy.json"] = _json_bytes(ComparisonPolicy())
    if recipe_id == "promotion_review":
        files["quality-policy.json"] = _json_bytes(QualityPolicy())
    if recipe_id == "share_evidence":
        files["redaction-policy.json"] = _json_bytes(
            RedactionPolicy(
                policy_id="external_review",
                policy_version="1.0.0",
            )
        )

    catalog = decision_recipe_catalog()
    file_records = tuple(
        RecipeScaffoldFile(
            path=path,
            digest=f"sha256:{hashlib.sha256(content).hexdigest()}",
        )
        for path, content in sorted(files.items())
    )
    digest_payload = {
        "schema_version": "awe.recipe-scaffold-manifest.v1",
        "recipe_id": recipe_id,
        "catalog_hash": catalog.catalog_hash,
        "files": [file.model_dump(mode="json") for file in file_records],
        "creates_evidence": False,
    }
    manifest = RecipeScaffoldManifest(
        recipe_id=recipe_id,
        catalog_hash=catalog.catalog_hash,
        files=file_records,
        manifest_hash=canonical_digest(digest_payload),
    )
    return manifest, files


def initialize_evidence_workspace(
    output_directory: Path,
    recipe_id: RecipeId,
    *,
    dry_run: bool = False,
) -> RecipeScaffoldManifest:
    """Create a new managed evidence workspace without fabricating evidence."""

    manifest, files = build_recipe_scaffold(recipe_id)
    if dry_run:
        return manifest
    if output_directory.exists():
        raise ValueError("evidence workspace output must not already exist")
    output_directory.mkdir(parents=True, exist_ok=False)
    for relative_path, content in sorted(files.items()):
        (output_directory / relative_path).write_bytes(content)
    (output_directory / "awe-recipe.json").write_bytes(_json_bytes(manifest))
    return manifest
