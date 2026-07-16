import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest

from sindie.cases import (
    CaseContractError,
    discover_cases,
    evaluation_contract_hash,
    load_case,
    render_model_request,
)
from sindie.prompt import load_prompt_bundle


def test_smoke_case_is_reproducible_and_labels_stay_host_only() -> None:
    case = load_case("evals/cases/smoke")
    bundle = load_prompt_bundle()
    model_request = render_model_request(case, bundle.schema)

    assert case.id == "smoke-poster-001"
    assert case.artifact_ids == ("A",)
    assert case.attachments["A"].is_file()
    assert "artifact.png" not in model_request
    assert str(case.path) not in model_request
    assert '"expected"' not in model_request
    assert bundle.schema["$id"] in model_request
    assert "RUNTIME INPUT" in model_request
    assert "AUTHORITATIVE OUTPUT SCHEMA" in model_request


def test_smoke_contract_hash_covers_the_frozen_contract() -> None:
    contract = load_case("evals/cases/smoke").request["evaluation_contract"]

    assert evaluation_contract_hash(contract) == contract["contract_hash"]


def test_stale_supplied_contract_hash_is_rejected(tmp_path) -> None:
    source = load_case("evals/cases/smoke")
    case_data = json.loads(source.path.read_text(encoding="utf-8"))
    case_data = deepcopy(case_data)
    case_data["request"]["evaluation_contract"]["scored_criteria"][0]["weight"] = 2
    (tmp_path / "artifact.png").write_bytes(source.attachments["A"].read_bytes())
    (tmp_path / "case.json").write_text(json.dumps(case_data), encoding="utf-8")

    with pytest.raises(CaseContractError, match="hash is stale"):
        load_case(tmp_path)


def test_unknown_model_visible_request_field_is_rejected(tmp_path) -> None:
    source = load_case("evals/cases/smoke")
    case_data = json.loads(source.path.read_text(encoding="utf-8"))
    case_data["request"]["designer_label"] = "gold"
    (tmp_path / "artifact.png").write_bytes(source.attachments["A"].read_bytes())
    (tmp_path / "case.json").write_text(json.dumps(case_data), encoding="utf-8")

    with pytest.raises(CaseContractError, match="request has unknown designer_label"):
        load_case(tmp_path)


def test_unasserted_or_human_output_cases_are_rejected(tmp_path) -> None:
    source = load_case("evals/cases/smoke")
    case_data = json.loads(source.path.read_text(encoding="utf-8"))
    case_data["request"]["task"]["output_mode"] = "human"
    case_data["expected"] = {"review_stats": ["ready"]}
    (tmp_path / "artifact.png").write_bytes(source.attachments["A"].read_bytes())
    (tmp_path / "case.json").write_text(json.dumps(case_data), encoding="utf-8")

    with pytest.raises(CaseContractError, match="output_mode structured"):
        load_case(tmp_path)

    case_data["request"]["task"]["output_mode"] = "structured"
    (tmp_path / "case.json").write_text(json.dumps(case_data), encoding="utf-8")
    with pytest.raises(CaseContractError, match="expected has unknown fields review_stats"):
        load_case(tmp_path)


def test_grida_gpt_image_2_fixtures_are_hash_pinned_and_provenance_stays_host_only() -> None:
    bundle = load_prompt_bundle()
    cases = discover_cases("evals/cases/grida")

    assert {case.id for case in cases} == {
        "grida-home-gpt-image-2-coffee-poster-001",
        "grida-home-gpt-image-2-icon-grid-001",
        "grida-home-gpt-image-2-kinetic-mobile-001",
        "grida-home-gpt-image-2-punk-poster-001",
    }
    for case in cases:
        provenance_path = Path(case.path).with_name("provenance.json")
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        artifact = case.attachments["A"]
        model_request = render_model_request(case, bundle.schema)

        assert provenance["license"]["id"] == "LicenseRef-GridaLibrary"
        assert provenance["persistence"] == "repository_fixture"
        assert "asset_url" not in provenance["source"]
        assert provenance["file"]["path"] == artifact.name
        assert provenance["file"]["byte_size"] == artifact.stat().st_size
        assert provenance["file"]["sha256"] == sha256(artifact.read_bytes()).hexdigest()
        assert provenance["source"]["description"] not in model_request
        assert provenance["source"]["page_url"] not in model_request
        assert provenance["source"]["generator"] not in model_request
        assert "grida" not in model_request.lower()
        assert "gpt-image-2" not in model_request.lower()


def test_unknown_expected_hard_constraint_is_rejected(tmp_path) -> None:
    source = load_case("evals/cases/smoke")
    case_data = json.loads(source.path.read_text(encoding="utf-8"))
    case_data["expected"]["hard_constraint_statuses"] = {"A": {"not_in_contract": ["pass"]}}
    (tmp_path / "artifact.png").write_bytes(source.attachments["A"].read_bytes())
    (tmp_path / "case.json").write_text(json.dumps(case_data), encoding="utf-8")

    with pytest.raises(CaseContractError, match="unknown constraint ids not_in_contract"):
        load_case(tmp_path)
