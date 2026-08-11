"""Read-only day-two status for AWE evidence workspaces."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, ValidationError, model_validator

from .contracts import (
    ContractModel,
    GateStatus,
    Identifier,
    Reason,
    Sha256Digest,
    canonical_digest,
)
from .demo import inspect_review_bundle
from .recipes import (
    RecipeId,
    RecipeScaffoldManifest,
    build_recipe_scaffold,
    decision_recipe_catalog,
    get_decision_recipe,
)


class WorkspaceStatusCheck(ContractModel):
    """One observed condition, without elevating file presence to evidence."""

    check_id: Identifier
    status: Literal["pass", "warn", "fail"]
    detail: Reason


class WorkspaceStatusReport(ContractModel):
    """Content-addressed operational summary for one local evidence directory."""

    schema_version: Literal["awe.workspace-status.v1"] = "awe.workspace-status.v1"
    state: Literal["READY", "ACTION_REQUIRED", "INVALID"]
    scope: Literal["review_bundle", "recipe", "unknown"]
    checks: Annotated[
        tuple[WorkspaceStatusCheck, ...],
        Field(min_length=1, max_length=64, strict=False),
    ]
    next_actions: Annotated[tuple[Reason, ...], Field(max_length=8, strict=False)] = ()
    recipe_id: RecipeId | None = None
    decision: GateStatus | None = None
    receipt_hash: Sha256Digest | None = None
    status_hash: Sha256Digest

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        check_ids = tuple(check.check_id for check in self.checks)
        if check_ids != tuple(sorted(set(check_ids))):
            raise ValueError("workspace status check ids must be unique and sorted")
        has_warning = any(check.status == "warn" for check in self.checks)
        has_failure = any(check.status == "fail" for check in self.checks)
        if self.state == "READY" and (has_warning or has_failure):
            raise ValueError("ready workspace cannot contain warnings or failures")
        if self.state == "ACTION_REQUIRED" and (not has_warning or has_failure):
            raise ValueError(
                "action-required workspace needs warnings without failures"
            )
        if self.state == "INVALID" and not has_failure:
            raise ValueError("invalid workspace requires a failed check")
        if self.scope == "recipe" and self.recipe_id is None:
            raise ValueError("recipe workspace status requires a recipe id")
        if self.scope != "recipe" and self.recipe_id is not None:
            raise ValueError("recipe id is only valid for recipe workspaces")
        if (self.decision is None) != (self.receipt_hash is None):
            raise ValueError("decision and receipt hash must be supplied together")
        expected = canonical_digest(
            self.model_dump(mode="json", exclude={"status_hash"})
        )
        if self.status_hash != expected:
            raise ValueError("workspace status hash is invalid")
        return self


def _report(
    *,
    state: Literal["READY", "ACTION_REQUIRED", "INVALID"],
    scope: Literal["review_bundle", "recipe", "unknown"],
    checks: tuple[WorkspaceStatusCheck, ...],
    next_actions: tuple[str, ...] = (),
    recipe_id: RecipeId | None = None,
    decision: GateStatus | None = None,
    receipt_hash: str | None = None,
) -> WorkspaceStatusReport:
    ordered_checks = tuple(sorted(checks, key=lambda check: check.check_id))
    payload = {
        "schema_version": "awe.workspace-status.v1",
        "state": state,
        "scope": scope,
        "checks": [check.model_dump(mode="json") for check in ordered_checks],
        "next_actions": list(next_actions),
        "recipe_id": recipe_id,
        "decision": decision,
        "receipt_hash": receipt_hash,
    }
    return WorkspaceStatusReport(
        state=state,
        scope=scope,
        checks=ordered_checks,
        next_actions=next_actions,
        recipe_id=recipe_id,
        decision=decision,
        receipt_hash=receipt_hash,
        status_hash=canonical_digest(payload),
    )


def _raw_digest(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _inspect_recipe_workspace(directory: Path) -> WorkspaceStatusReport:
    try:
        manifest = RecipeScaffoldManifest.model_validate_json(
            (directory / "awe-recipe.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, ValidationError) as error:
        return _report(
            state="INVALID",
            scope="unknown",
            checks=(
                WorkspaceStatusCheck(
                    check_id="recipe_manifest",
                    status="fail",
                    detail=f"Recipe manifest is invalid: {error}",
                ),
            ),
            next_actions=("Recreate the workspace in a new directory with awe init.",),
        )

    checks: list[WorkspaceStatusCheck] = []
    failures = False
    catalog_matches = manifest.catalog_hash == decision_recipe_catalog().catalog_hash
    checks.append(
        WorkspaceStatusCheck(
            check_id="catalog_version",
            status="pass" if catalog_matches else "fail",
            detail=(
                "Recipe catalog digest matches this installed TraceGate."
                if catalog_matches
                else "Recipe catalog digest differs from this installed TraceGate."
            ),
        )
    )
    failures = failures or not catalog_matches

    expected_manifest, _ = build_recipe_scaffold(manifest.recipe_id)
    definition_matches = manifest == expected_manifest
    checks.append(
        WorkspaceStatusCheck(
            check_id="scaffold_definition",
            status="pass" if definition_matches else "fail",
            detail=(
                "Managed paths and digests match the built-in recipe definition."
                if definition_matches
                else (
                    "Managed paths or digests differ from the built-in recipe "
                    "definition."
                )
            ),
        )
    )
    failures = failures or not definition_matches
    if not definition_matches:
        return _report(
            state="INVALID",
            scope="recipe",
            checks=tuple(checks),
            next_actions=(
                "Create a new workspace; never follow paths from the modified "
                "manifest.",
            ),
            recipe_id=manifest.recipe_id,
        )

    managed_files_valid = True
    for managed_file in expected_manifest.files:
        path = directory / managed_file.path
        if (
            not path.is_file()
            or path.is_symlink()
            or _raw_digest(path) != managed_file.digest
        ):
            managed_files_valid = False
            break
    checks.append(
        WorkspaceStatusCheck(
            check_id="scaffold_integrity",
            status="pass" if managed_files_valid else "fail",
            detail=(
                "Every managed guidance and policy file matches its raw digest."
                if managed_files_valid
                else (
                    "A managed guidance or policy file is missing, linked, or modified."
                )
            ),
        )
    )
    failures = failures or not managed_files_valid

    recipe = get_decision_recipe(manifest.recipe_id)
    missing_inputs = tuple(
        artifact
        for artifact in recipe.minimum_inputs
        if not (directory / artifact).is_file()
    )
    checks.append(
        WorkspaceStatusCheck(
            check_id="real_inputs",
            status="warn",
            detail=(
                f"Missing {len(missing_inputs)} required real input file(s)."
                if missing_inputs
                else "Required input filenames are present but have not been verified."
            ),
        )
    )

    if failures:
        return _report(
            state="INVALID",
            scope="recipe",
            checks=tuple(checks),
            next_actions=(
                "Create a new workspace; do not overwrite the modified scaffold.",
            ),
            recipe_id=manifest.recipe_id,
        )
    next_action = (
        f"Supply the real inputs listed by awe recipes --show {manifest.recipe_id}."
        if missing_inputs
        else (
            f"Run and verify the {manifest.recipe_id} recipe; file presence "
            "is not evidence."
        )
    )
    return _report(
        state="ACTION_REQUIRED",
        scope="recipe",
        checks=tuple(checks),
        next_actions=(next_action,),
        recipe_id=manifest.recipe_id,
    )


def inspect_workspace_status(directory: Path) -> WorkspaceStatusReport:
    """Inspect one local directory without executing artifacts or making calls."""

    if not directory.is_dir() or directory.is_symlink():
        return _report(
            state="INVALID",
            scope="unknown",
            checks=(
                WorkspaceStatusCheck(
                    check_id="workspace_directory",
                    status="fail",
                    detail="Workspace must be an existing non-symlink directory.",
                ),
            ),
            next_actions=("Select a local evidence directory.",),
        )
    if (directory / "gate-v2.json").is_file():
        review = inspect_review_bundle(directory)
        state: Literal["READY", "ACTION_REQUIRED", "INVALID"]
        if review.status == "READY":
            state = "READY"
        elif review.status == "INCOMPLETE":
            state = "ACTION_REQUIRED"
        else:
            state = "INVALID"
        checks = tuple(
            WorkspaceStatusCheck(
                check_id=check.check_id,
                status=(
                    "pass"
                    if check.status == "pass"
                    else "warn"
                    if review.status == "INCOMPLETE"
                    else "fail"
                ),
                detail=check.detail,
            )
            for check in review.checks
        )
        return _report(
            state=state,
            scope="review_bundle",
            checks=checks,
            next_actions=review.next_actions,
            decision=review.gate_v2_status,
            receipt_hash=review.gate_v2_receipt_hash,
        )
    if (directory / "awe-recipe.json").is_file():
        return _inspect_recipe_workspace(directory)
    return _report(
        state="ACTION_REQUIRED",
        scope="unknown",
        checks=(
            WorkspaceStatusCheck(
                check_id="workspace_layout",
                status="warn",
                detail=(
                    "No managed recipe manifest or canonical Gate v2 bundle was found."
                ),
            ),
        ),
        next_actions=(
            "Run awe recipes, awe init, or point awe status at an existing "
            "review bundle.",
        ),
    )
