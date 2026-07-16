"""Inspect AI task for running the canonical Sindie visual-review prompt."""

from __future__ import annotations

import json
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.model import ChatMessageUser, ContentImage, ContentText, GenerateConfig
from inspect_ai.scorer import CORRECT, INCORRECT, Score, Target, accuracy, scorer
from inspect_ai.solver import TaskState, generate, system_message

from sindie.cases import (
    EvalCase,
    canonical_json_sha256,
    discover_cases,
    render_model_request,
)
from sindie.prompt import load_prompt_bundle
from sindie.validation import ValidationIssue, validate_output

ROOT = Path(__file__).resolve().parents[1]


def _case_sample(case: EvalCase) -> Sample:
    bundle = load_prompt_bundle(ROOT / "PROMPT.md")
    content: list[ContentText | ContentImage] = [
        ContentText(text=render_model_request(case, bundle.schema))
    ]
    for artifact_id in case.artifact_ids:
        content.extend(
            (
                ContentText(text=f"ARTIFACT {artifact_id}"),
                ContentImage(image=str(case.attachments[artifact_id])),
            )
        )
    return Sample(
        id=case.id,
        input=[ChatMessageUser(content=content)],
        target=json.dumps(case.expected, ensure_ascii=False),
        metadata={
            "case_path": str(case.path),
            "request": case.request,
            "expected": case.expected,
            "request_hash": canonical_json_sha256(case.request),
            "prompt_version": bundle.prompt_version,
            "prompt_hash": f"sha256:{sha256(bundle.system_prompt.encode('utf-8')).hexdigest()}",
            "schema_version": bundle.schema_version,
            "schema_hash": canonical_json_sha256(bundle.schema),
            "attachment_hashes": {
                artifact_id: f"sha256:{sha256(path.read_bytes()).hexdigest()}"
                for artifact_id, path in case.attachments.items()
            },
        },
    )


def _expectation_issues(
    output: dict[str, object], expected: dict[str, object]
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    statuses = expected.get("review_status")
    if isinstance(statuses, str):
        statuses = [statuses]
    if isinstance(statuses, list) and output.get("review_status") not in statuses:
        issues.append(
            ValidationIssue(
                "expected",
                "/review_status",
                f"Expected one of {statuses}, got {output.get('review_status')!r}.",
            )
        )
    expected_winner = expected.get("pairwise_winner")
    comparison = output.get("comparison")
    if expected_winner is not None:
        actual_winner = comparison.get("winner") if isinstance(comparison, dict) else None
        if actual_winner != expected_winner:
            issues.append(
                ValidationIssue(
                    "expected",
                    "/comparison/winner",
                    f"Expected {expected_winner!r}, got {actual_winner!r}.",
                )
            )

    expected_constraints = expected.get("hard_constraint_statuses")
    artifacts = output.get("artifacts")
    artifacts_by_id = (
        {
            artifact.get("id"): artifact
            for artifact in artifacts
            if isinstance(artifact, dict) and isinstance(artifact.get("id"), str)
        }
        if isinstance(artifacts, list)
        else {}
    )
    if isinstance(expected_constraints, dict):
        for artifact_id, constraints in expected_constraints.items():
            artifact = artifacts_by_id.get(artifact_id)
            checks = artifact.get("hard_constraint_checks") if isinstance(artifact, dict) else []
            checks_by_id = (
                {
                    check.get("constraint_id"): check.get("status")
                    for check in checks
                    if isinstance(check, dict)
                }
                if isinstance(checks, list)
                else {}
            )
            if not isinstance(constraints, dict):
                continue
            for constraint_id, allowed in constraints.items():
                if isinstance(allowed, str):
                    allowed = [allowed]
                if isinstance(allowed, list) and checks_by_id.get(constraint_id) not in allowed:
                    issues.append(
                        ValidationIssue(
                            "expected",
                            f"/artifacts/{artifact_id}/hard_constraint_checks/{constraint_id}",
                            f"Expected one of {allowed}, got {checks_by_id.get(constraint_id)!r}.",
                        )
                    )
    return issues


@scorer(metrics=[accuracy()])
def sindie_protocol():
    """Score protocol correctness without introducing a second taste model."""

    bundle = load_prompt_bundle(ROOT / "PROMPT.md")

    async def score(state: TaskState, target: Target) -> Score:
        request = state.metadata.get("request")
        expected = state.metadata.get("expected", {})
        report = validate_output(
            state.output.completion,
            bundle=bundle,
            request=request if isinstance(request, dict) else None,
        )
        issues = list(report.issues)
        if report.data is not None and isinstance(expected, dict):
            issues.extend(_expectation_issues(report.data, expected))
        explanation = "Protocol valid."
        if issues:
            explanation = "\n".join(
                f"[{issue.code}] {issue.path or '/'}: {issue.message}" for issue in issues
            )
        return Score(
            value=CORRECT if not issues else INCORRECT,
            answer=state.output.completion,
            explanation=explanation,
            metadata={"issues": [asdict(issue) for issue in issues]},
        )

    return score


@task
def sindie(
    cases: str = "evals/cases",
    max_tokens: int = 16_000,
    temperature: float = 0.0,
) -> Task:
    """Evaluate every case below ``cases`` with the canonical prompt."""

    bundle = load_prompt_bundle(ROOT / "PROMPT.md")
    case_path = Path(cases)
    if not case_path.is_absolute():
        case_path = ROOT / case_path
    dataset = [_case_sample(case) for case in discover_cases(case_path)]
    return Task(
        dataset=dataset,
        solver=[system_message(bundle.system_prompt), generate()],
        scorer=sindie_protocol(),
        config=GenerateConfig(max_tokens=max_tokens, temperature=temperature),
    )
