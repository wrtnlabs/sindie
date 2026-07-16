from copy import deepcopy

from sindie.prompt import load_reference_output
from sindie.validation import validate_output


def _request_for_reference(output: dict[str, object]) -> dict[str, object]:
    return {
        "task": {"mode": output["mode"]},
        "evaluation_contract": deepcopy(output["evaluation_contract"]),
    }


def test_reference_output_passes_schema_and_semantic_validation() -> None:
    output = load_reference_output()

    report = validate_output(output, request=_request_for_reference(output))

    assert report.valid
    assert report.issues == ()


def test_non_json_model_response_is_rejected() -> None:
    report = validate_output("Here is the review: looks strong.")

    assert not report.valid
    assert report.data is None
    assert report.issues[0].code == "json"


def test_unknown_evidence_reference_is_rejected() -> None:
    output = load_reference_output()
    output["artifacts"][0]["criterion_assessments"][0]["evidence_for"] = ["A-missing"]

    report = validate_output(output)

    assert not report.valid
    assert any(issue.code == "evidence_reference" for issue in report.issues)


def test_supplied_contract_cannot_be_rewritten_by_model() -> None:
    output = load_reference_output()
    request = _request_for_reference(output)
    output["evaluation_contract"]["scored_criteria"][0]["weight"] = 0.25

    report = validate_output(output, request=request)

    assert not report.valid
    assert any(
        issue.code == "contract_echo" and issue.path == "/evaluation_contract/scored_criteria"
        for issue in report.issues
    )


def test_supplied_contract_issues_cannot_be_rewritten_by_model() -> None:
    output = load_reference_output()
    request = _request_for_reference(output)
    output["evaluation_contract"]["issues"] = ["model-added issue"]

    report = validate_output(output, request=request)

    assert not report.valid
    assert any(
        issue.code == "contract_echo" and issue.path == "/evaluation_contract/issues"
        for issue in report.issues
    )


def test_model_cannot_fill_host_owned_score_fields() -> None:
    output = load_reference_output()
    output["artifacts"][0]["score_inputs"]["composite_100"] = 75

    report = validate_output(output)

    assert not report.valid
    assert any(
        issue.code == "schema" and issue.path == "/artifacts/0/score_inputs/composite_100"
        for issue in report.issues
    )
