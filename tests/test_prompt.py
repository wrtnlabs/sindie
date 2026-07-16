from jsonschema import Draft202012Validator

from sindie.prompt import load_prompt_bundle, load_reference_output


def test_prompt_and_schema_are_one_versioned_contract() -> None:
    bundle = load_prompt_bundle()

    assert bundle.prompt_version == "0.1.0"
    assert bundle.schema_version == "0.1.0"
    assert bundle.schema["properties"]["prompt_version"]["const"] == bundle.prompt_version
    assert bundle.schema["properties"]["schema_version"]["const"] == bundle.schema_version
    assert "You are Sindie" in bundle.system_prompt


def test_reference_output_conforms_to_authoritative_schema() -> None:
    bundle = load_prompt_bundle()

    Draft202012Validator(bundle.schema).validate(load_reference_output())
