"""Deterministic host aggregation for already validated Sindie output."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any


@dataclass(frozen=True, slots=True)
class HostArtifactScore:
    artifact_id: str
    host_aggregation_eligible: bool
    hard_constraint_summary: str
    decision_eligible: bool
    coverage: float | None
    composite_100: int | None
    host_score_status: str
    host_withheld_reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["host_withheld_reasons"] = list(self.host_withheld_reasons)
        return value


def _rounded_composite(weighted_sum: float, scored_weight: float) -> int:
    normalized = Decimal(str(25 * weighted_sum / scored_weight))
    return int(normalized.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def aggregate_artifact(
    result: dict[str, Any], artifact_id: str, *, min_coverage: float = 1.0
) -> HostArtifactScore:
    """Apply PROMPT.md's host-only score and hard-constraint rules."""

    if not 0 <= min_coverage <= 1:
        raise ValueError("min_coverage must be between 0 and 1.")
    artifact = next(
        (item for item in result.get("artifacts", []) if item.get("id") == artifact_id),
        None,
    )
    if artifact is None:
        raise ValueError(f"Artifact {artifact_id!r} is not present in the result.")

    contract = result["evaluation_contract"]
    criteria = {item["id"]: item for item in contract.get("scored_criteria", [])}
    assessments = {item["criterion_id"]: item for item in artifact.get("criterion_assessments", [])}

    applicable_weight = 0.0
    scored_weight = 0.0
    weighted_sum = 0.0
    required_unscored: list[str] = []
    for criterion_id, criterion in criteria.items():
        assessment = assessments.get(criterion_id)
        if assessment is None:
            if criterion.get("required_for_score"):
                required_unscored.append(criterion_id)
            continue
        if assessment.get("applicability") == "not_applicable":
            continue
        weight = float(criterion["weight"])
        applicable_weight += weight
        if assessment.get("assessment_status") == "scored":
            scored_weight += weight
            weighted_sum += weight * int(assessment["rating_0_to_4"])
        elif criterion.get("required_for_score"):
            required_unscored.append(criterion_id)

    coverage = scored_weight / applicable_weight if applicable_weight > 0 else None
    if coverage is not None:
        coverage = round(coverage, 6)

    constraint_statuses = [check["status"] for check in artifact.get("hard_constraint_checks", [])]
    if "fail" in constraint_statuses:
        hard_summary = "fail"
    elif any(status in {"unknown", "not_assessable"} for status in constraint_statuses):
        hard_summary = "unresolved"
    else:
        hard_summary = "pass"

    reasons: list[str] = []
    if contract.get("status") != "supplied" or contract.get("source") != "supplied":
        reasons.append("contract_not_supplied")
    if not contract.get("cross_run_comparable"):
        reasons.append("contract_not_cross_run_comparable")
    if result.get("review_status") != "ready":
        reasons.append("review_not_ready")
    score_inputs = artifact["score_inputs"]
    if not score_inputs.get("criterion_scoring_eligible"):
        reasons.append("criterion_scoring_ineligible")
    if score_inputs.get("model_aggregation_status") != "supported":
        reasons.append("model_aggregation_withheld")
    if applicable_weight == 0:
        reasons.append("no_applicable_weight")
    if required_unscored:
        reasons.append("required_criterion_unscored")
    if hard_summary == "unresolved":
        reasons.append("hard_constraint_unresolved")
    if coverage is not None and coverage < min_coverage:
        reasons.append("coverage_below_threshold")

    reasons = list(dict.fromkeys(reasons))
    aggregation_eligible = not reasons
    composite = (
        _rounded_composite(weighted_sum, scored_weight)
        if aggregation_eligible and scored_weight > 0
        else None
    )
    decision_eligible = aggregation_eligible and hard_summary == "pass"
    return HostArtifactScore(
        artifact_id=artifact_id,
        host_aggregation_eligible=aggregation_eligible,
        hard_constraint_summary=hard_summary,
        decision_eligible=decision_eligible,
        coverage=coverage,
        composite_100=composite,
        host_score_status="computed" if aggregation_eligible else "withheld",
        host_withheld_reasons=tuple(reasons),
    )


def aggregate_all(result: dict[str, Any], *, min_coverage: float = 1.0) -> list[HostArtifactScore]:
    return [
        aggregate_artifact(result, artifact["id"], min_coverage=min_coverage)
        for artifact in result.get("artifacts", [])
    ]
