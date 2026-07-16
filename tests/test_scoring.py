from sindie.prompt import load_reference_output
from sindie.scoring import aggregate_artifact


def test_host_computes_normalized_composite_after_validation() -> None:
    score = aggregate_artifact(load_reference_output(), "A")

    assert score.host_aggregation_eligible
    assert score.hard_constraint_summary == "pass"
    assert score.decision_eligible
    assert score.coverage == 1.0
    assert score.composite_100 == 75
    assert score.host_score_status == "computed"
    assert score.host_withheld_reasons == ()


def test_unresolved_hard_constraint_withholds_aggregation() -> None:
    output = load_reference_output()
    output["artifacts"][0]["hard_constraint_checks"][0]["status"] = "unknown"
    score = aggregate_artifact(output, "A")

    assert not score.host_aggregation_eligible
    assert score.hard_constraint_summary == "unresolved"
    assert not score.decision_eligible
    assert score.composite_100 is None
    assert "hard_constraint_unresolved" in score.host_withheld_reasons


def test_failed_constraint_keeps_diagnostic_score_but_blocks_decision() -> None:
    output = load_reference_output()
    output["artifacts"][0]["hard_constraint_checks"][0]["status"] = "fail"
    score = aggregate_artifact(output, "A")

    assert score.host_aggregation_eligible
    assert score.hard_constraint_summary == "fail"
    assert not score.decision_eligible
    assert score.composite_100 == 75
