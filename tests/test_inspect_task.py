import json
from copy import deepcopy

from inspect_ai import eval as inspect_eval
from inspect_ai.model import (
    ChatMessageUser,
    ContentImage,
    ContentText,
    ModelOutput,
    get_model,
)

from evals.sindie import _case_sample, _expectation_issues, sindie
from sindie.cases import EvalCase, load_case
from sindie.prompt import load_reference_output
from sindie.validation import validate_output


def test_inspect_task_loads_text_before_the_visual_attachment() -> None:
    task = sindie(cases="evals/cases/smoke")
    samples = list(task.dataset)

    assert len(samples) == 1
    sample = samples[0]
    assert sample.id == "smoke-poster-001"
    assert len(sample.input) == 1
    assert isinstance(sample.input[0], ChatMessageUser)
    assert isinstance(sample.input[0].content[0], ContentText)
    assert isinstance(sample.input[0].content[1], ContentText)
    assert sample.input[0].content[1].text == "ARTIFACT A"
    assert isinstance(sample.input[0].content[2], ContentImage)
    assert '"expected"' not in sample.input[0].content[0].text
    assert "artifact.png" not in sample.input[0].content[0].text
    assert sample.metadata["request_hash"].startswith("sha256:")
    assert sample.metadata["prompt_hash"].startswith("sha256:")
    assert sample.metadata["schema_hash"].startswith("sha256:")
    assert sample.metadata["attachment_hashes"]["A"].startswith("sha256:")


def test_pairwise_images_are_adjacent_to_explicit_slot_labels() -> None:
    single = load_case("evals/cases/smoke")
    request = deepcopy(single.request)
    request["task"]["mode"] = "pairwise"
    artifact_b = deepcopy(request["artifacts"][0])
    artifact_b["id"] = "B"
    artifact_b["image"] = "attachment:B"
    request["artifacts"].append(artifact_b)
    request["comparison_question"] = "Which better serves the supplied intent?"
    pairwise = EvalCase(
        id="pairwise-transport",
        path=single.path,
        request=request,
        attachments={"A": single.attachments["A"], "B": single.attachments["A"]},
        expected={"review_status": ["ready"]},
        case_version=single.case_version,
    )

    content = _case_sample(pairwise).input[0].content

    assert [type(item) for item in content] == [
        ContentText,
        ContentText,
        ContentImage,
        ContentText,
        ContentImage,
    ]
    assert content[1].text == "ARTIFACT A"
    assert content[3].text == "ARTIFACT B"


def test_inspect_runs_and_scores_a_known_good_mock_response(tmp_path) -> None:
    case = load_case("evals/cases/smoke")
    output = load_reference_output()
    output["evaluation_contract"] = deepcopy(case.request["evaluation_contract"])
    artifact = output["artifacts"][0]
    base_assessment = artifact["criterion_assessments"][0]
    artifact["criterion_assessments"] = []
    for criterion in output["evaluation_contract"]["scored_criteria"]:
        assessment = deepcopy(base_assessment)
        assessment["criterion_id"] = criterion["id"]
        artifact["criterion_assessments"].append(assessment)
    artifact["hard_constraint_checks"][0]["constraint_id"] = "required_copy"
    assert validate_output(output, request=case.request).valid

    model = get_model(
        "mockllm/model",
        memoize=False,
        custom_outputs=[ModelOutput.from_content("mockllm/model", json.dumps(output))],
    )
    logs = inspect_eval(
        sindie(cases="evals/cases/smoke"),
        model=model,
        log_dir=str(tmp_path),
        display="none",
    )

    result = logs[0].results.scores[0]
    assert logs[0].status == "success"
    assert result.scored_samples == 1
    assert result.metrics["accuracy"].value == 1.0


def test_expected_hard_constraint_statuses_are_scored_without_a_taste_judge() -> None:
    output = {
        "review_status": "ready",
        "artifacts": [
            {
                "id": "A",
                "hard_constraint_checks": [{"constraint_id": "labels", "status": "fail"}],
            }
        ],
    }
    expected = {
        "review_status": ["ready"],
        "hard_constraint_statuses": {"A": {"labels": ["fail"]}},
    }

    assert _expectation_issues(output, expected) == []
    output["artifacts"][0]["hard_constraint_checks"][0]["status"] = "pass"
    issues = _expectation_issues(output, expected)
    assert len(issues) == 1
    assert issues[0].path == "/artifacts/A/hard_constraint_checks/labels"
