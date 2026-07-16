"""Validate model output against Sindie's schema and cross-reference invariants."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from typing import Any

from jsonschema import Draft202012Validator

from .prompt import PromptBundle, load_prompt_bundle


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    path: str
    message: str


@dataclass(frozen=True, slots=True)
class ValidationReport:
    data: dict[str, Any] | None
    issues: tuple[ValidationIssue, ...]

    @property
    def valid(self) -> bool:
        return not self.issues

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "issues": [asdict(issue) for issue in self.issues],
            "data": self.data,
        }


def _pointer(parts: Sequence[object]) -> str:
    if not parts:
        return ""
    encoded = [str(part).replace("~", "~0").replace("/", "~1") for part in parts]
    return "/" + "/".join(encoded)


def _duplicates(values: Iterable[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


def _compare_id_collection(
    issues: list[ValidationIssue],
    actual: list[str],
    expected: list[str],
    path: str,
    label: str,
) -> None:
    duplicates = _duplicates(actual)
    if duplicates:
        issues.append(
            ValidationIssue(
                "duplicate_id",
                path,
                f"Duplicate {label} ids: {', '.join(sorted(duplicates))}",
            )
        )
    missing = sorted(set(expected) - set(actual))
    unknown = sorted(set(actual) - set(expected))
    if missing:
        issues.append(
            ValidationIssue("missing_id", path, f"Missing {label} ids: {', '.join(missing)}")
        )
    if unknown:
        issues.append(
            ValidationIssue("unknown_id", path, f"Unknown {label} ids: {', '.join(unknown)}")
        )


def _artifact_evidence_references(artifact: dict[str, Any]) -> list[tuple[str, list[str]]]:
    references: list[tuple[str, list[str]]] = []
    groups = (
        ("hard_constraint_checks", ("evidence_ids",)),
        ("visible_risks", ("evidence_ids",)),
        ("strengths_to_preserve", ("evidence_ids",)),
        ("criterion_assessments", ("evidence_for", "evidence_against")),
        ("consequential_choices", ("evidence_ids",)),
        ("departures", ("evidence_ids",)),
        ("alternative_directions", ("evidence_ids",)),
    )
    for group, fields in groups:
        for index, item in enumerate(artifact.get(group, [])):
            for field in fields:
                references.append((f"/{group}/{index}/{field}", list(item.get(field, []))))

    diagnosis = artifact.get("priority_diagnosis", {})
    dominant = diagnosis.get("dominant")
    if isinstance(dominant, dict):
        references.append(
            ("/priority_diagnosis/dominant/evidence_ids", dominant.get("evidence_ids", []))
        )
    for index, item in enumerate(diagnosis.get("independent_tensions", [])):
        references.append(
            (
                f"/priority_diagnosis/independent_tensions/{index}/evidence_ids",
                item.get("evidence_ids", []),
            )
        )
    return references


def _semantic_issues(
    data: dict[str, Any], bundle: PromptBundle, request: dict[str, Any] | None
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if data.get("prompt_version") != bundle.prompt_version:
        issues.append(ValidationIssue("version", "/prompt_version", "Unexpected prompt version."))
    if data.get("schema_version") != bundle.schema_version:
        issues.append(ValidationIssue("version", "/schema_version", "Unexpected schema version."))

    contract = data.get("evaluation_contract", {})
    criterion_ids = [item["id"] for item in contract.get("scored_criteria", [])]
    constraint_ids = [item["id"] for item in contract.get("hard_constraints", [])]
    for values, path, label in (
        (criterion_ids, "/evaluation_contract/scored_criteria", "criterion"),
        (constraint_ids, "/evaluation_contract/hard_constraints", "constraint"),
    ):
        duplicates = _duplicates(values)
        if duplicates:
            issues.append(
                ValidationIssue(
                    "duplicate_id",
                    path,
                    f"Duplicate {label} ids: {', '.join(sorted(duplicates))}",
                )
            )

    evidence_by_artifact: dict[str, set[str]] = {}
    global_evidence: set[str] = set()
    for artifact_index, artifact in enumerate(data.get("artifacts", [])):
        artifact_id = artifact["id"]
        base = f"/artifacts/{artifact_index}"
        evidence_ids = [item["id"] for item in artifact.get("evidence", [])]
        duplicates = _duplicates(evidence_ids)
        if duplicates:
            issues.append(
                ValidationIssue(
                    "duplicate_evidence",
                    f"{base}/evidence",
                    f"Duplicate evidence ids: {', '.join(sorted(duplicates))}",
                )
            )
        for evidence_index, evidence_id in enumerate(evidence_ids):
            if not re.match(rf"^{re.escape(artifact_id)}[-._:]", evidence_id):
                issues.append(
                    ValidationIssue(
                        "evidence_prefix",
                        f"{base}/evidence/{evidence_index}/id",
                        f"Evidence id must be prefixed by artifact {artifact_id}.",
                    )
                )
            if evidence_id in global_evidence:
                issues.append(
                    ValidationIssue(
                        "duplicate_evidence",
                        f"{base}/evidence/{evidence_index}/id",
                        "Evidence ids must be unique across the response.",
                    )
                )
            global_evidence.add(evidence_id)
        evidence_set = set(evidence_ids)
        evidence_by_artifact[artifact_id] = evidence_set

        for relative_path, references in _artifact_evidence_references(artifact):
            unknown = sorted(set(references) - evidence_set)
            if unknown:
                issues.append(
                    ValidationIssue(
                        "evidence_reference",
                        f"{base}{relative_path}",
                        f"Unknown or cross-artifact evidence ids: {', '.join(unknown)}",
                    )
                )

        if data.get("review_status") in {"ready", "degraded"}:
            assessment_ids = [
                item["criterion_id"] for item in artifact.get("criterion_assessments", [])
            ]
            _compare_id_collection(
                issues,
                assessment_ids,
                criterion_ids,
                f"{base}/criterion_assessments",
                "criterion assessment",
            )
            check_ids = [
                item["constraint_id"] for item in artifact.get("hard_constraint_checks", [])
            ]
            _compare_id_collection(
                issues,
                check_ids,
                constraint_ids,
                f"{base}/hard_constraint_checks",
                "hard-constraint check",
            )

    calibration_refs = data.get("calibration", {}).get("counterevidence_ids", [])
    unknown_calibration = sorted(set(calibration_refs) - global_evidence)
    if unknown_calibration:
        issues.append(
            ValidationIssue(
                "evidence_reference",
                "/calibration/counterevidence_ids",
                f"Unknown evidence ids: {', '.join(unknown_calibration)}",
            )
        )

    comparison = data.get("comparison")
    if isinstance(comparison, dict):
        preference_ids = [
            item["criterion_id"] for item in comparison.get("criterion_preferences", [])
        ]
        if comparison.get("status") == "comparable":
            _compare_id_collection(
                issues,
                preference_ids,
                criterion_ids,
                "/comparison/criterion_preferences",
                "criterion preference",
            )
        deciding = comparison.get("deciding_criteria", [])
        unknown_deciding = sorted(set(deciding) - set(criterion_ids))
        if unknown_deciding:
            issues.append(
                ValidationIssue(
                    "unknown_id",
                    "/comparison/deciding_criteria",
                    f"Unknown deciding criteria: {', '.join(unknown_deciding)}",
                )
            )
        for index, preference in enumerate(comparison.get("criterion_preferences", [])):
            for field, artifact_id in (("evidence_a", "A"), ("evidence_b", "B")):
                references = preference.get(field, [])
                unknown = sorted(set(references) - evidence_by_artifact.get(artifact_id, set()))
                if unknown:
                    issues.append(
                        ValidationIssue(
                            "evidence_reference",
                            f"/comparison/criterion_preferences/{index}/{field}",
                            f"Evidence does not resolve to artifact {artifact_id}: "
                            f"{', '.join(unknown)}",
                        )
                    )

    if request is not None:
        requested_mode = request.get("task", {}).get("mode")
        if requested_mode is not None and data.get("mode") != requested_mode:
            issues.append(
                ValidationIssue("request_echo", "/mode", "Output mode differs from the request.")
            )
        supplied = request.get("evaluation_contract")
        if isinstance(supplied, dict):
            if contract.get("status") != "supplied" or contract.get("source") != "supplied":
                issues.append(
                    ValidationIssue(
                        "contract_echo",
                        "/evaluation_contract",
                        "A supplied contract must remain supplied in the output.",
                    )
                )
            for field in (
                "contract_id",
                "contract_version",
                "contract_hash",
                "cross_run_comparable",
                "weights_source",
                "issues",
                "scored_criteria",
                "hard_constraints",
            ):
                if field in supplied and contract.get(field) != supplied[field]:
                    issues.append(
                        ValidationIssue(
                            "contract_echo",
                            f"/evaluation_contract/{field}",
                            f"Supplied evaluation-contract field {field} was changed.",
                        )
                    )
    return issues


def validate_output(
    raw: str | bytes | dict[str, Any],
    *,
    bundle: PromptBundle | None = None,
    request: dict[str, Any] | None = None,
) -> ValidationReport:
    """Parse output, run Draft 2020-12 validation, then Sindie semantic checks."""

    bundle = bundle or load_prompt_bundle()
    if isinstance(raw, dict):
        data = raw
    else:
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            return ValidationReport(
                data=None,
                issues=(ValidationIssue("json", "", f"Invalid JSON: {error}"),),
            )
    if not isinstance(data, dict):
        return ValidationReport(
            data=None,
            issues=(ValidationIssue("json", "", "Model output must be one JSON object."),),
        )

    validator = Draft202012Validator(bundle.schema)
    schema_errors = sorted(validator.iter_errors(data), key=lambda error: list(error.path))
    issues = [
        ValidationIssue("schema", _pointer(list(error.path)), error.message)
        for error in schema_errors
    ]
    if not issues:
        issues.extend(_semantic_issues(data, bundle, request))
    return ValidationReport(data=data, issues=tuple(issues))
