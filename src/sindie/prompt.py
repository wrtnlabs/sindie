"""Load the deployed prompt and authoritative schema from PROMPT.md."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

BEGIN_MARKER = "<!-- BEGIN SYSTEM PROMPT -->"
END_MARKER = "<!-- END SYSTEM PROMPT -->"
SCHEMA_HEADING = "### Provider-neutral model-output schema"
REFERENCE_HEADING = "## Structured-output reference"


class PromptContractError(ValueError):
    """Raised when PROMPT.md no longer contains one coherent runtime contract."""


@dataclass(frozen=True, slots=True)
class PromptBundle:
    """The exact deployed prompt and its authoritative output schema."""

    path: Path
    system_prompt: str
    schema: dict[str, Any]
    prompt_version: str
    schema_version: str


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_prompt_path() -> Path:
    return repository_root() / "PROMPT.md"


def _single_fenced_json(section: str, label: str) -> dict[str, Any]:
    matches = re.findall(r"```json\s*\n(.*?)\n```", section, re.DOTALL)
    if not matches:
        raise PromptContractError(f"No JSON block found in {label}.")
    try:
        value = json.loads(matches[0])
    except json.JSONDecodeError as error:
        raise PromptContractError(f"Invalid JSON in {label}: {error}") from error
    if not isinstance(value, dict):
        raise PromptContractError(f"Expected a JSON object in {label}.")
    return value


def _constant(system_prompt: str, name: str) -> str:
    match = re.search(rf"- `{re.escape(name)}`: `([^`]+)`", system_prompt)
    if match is None:
        raise PromptContractError(f"Missing canonical {name} inside the deployed prompt.")
    return match.group(1)


def load_prompt_bundle(path: str | Path | None = None) -> PromptBundle:
    """Extract and validate the sole prompt/schema source of truth."""

    prompt_path = Path(path) if path is not None else default_prompt_path()
    prompt_path = prompt_path.resolve()
    text = prompt_path.read_text(encoding="utf-8")

    if text.count(BEGIN_MARKER) != 1 or text.count(END_MARKER) != 1:
        raise PromptContractError("PROMPT.md must contain exactly one prompt marker pair.")
    before, remainder = text.split(BEGIN_MARKER, 1)
    system_prompt, after = remainder.split(END_MARKER, 1)
    if before.find(END_MARKER) >= 0 or after.find(BEGIN_MARKER) >= 0:
        raise PromptContractError("Prompt markers are out of order.")
    system_prompt = system_prompt.strip()

    if SCHEMA_HEADING not in after:
        raise PromptContractError(f"Missing {SCHEMA_HEADING!r} after the deployed prompt.")
    schema_section = after.split(SCHEMA_HEADING, 1)[1]
    schema = _single_fenced_json(schema_section, SCHEMA_HEADING)
    Draft202012Validator.check_schema(schema)

    prompt_version = _constant(system_prompt, "prompt_version")
    schema_version = _constant(system_prompt, "schema_version")
    properties = schema.get("properties", {})
    schema_prompt_version = properties.get("prompt_version", {}).get("const")
    schema_schema_version = properties.get("schema_version", {}).get("const")
    if schema_prompt_version != prompt_version:
        raise PromptContractError(
            "The schema prompt_version constant does not match the deployed prompt."
        )
    if schema_schema_version != schema_version:
        raise PromptContractError(
            "The schema schema_version constant does not match the deployed prompt."
        )

    return PromptBundle(
        path=prompt_path,
        system_prompt=system_prompt,
        schema=schema,
        prompt_version=prompt_version,
        schema_version=schema_version,
    )


def load_reference_output(path: str | Path | None = None) -> dict[str, Any]:
    """Load the compact canonical single-artifact output used by offline tests."""

    prompt_path = Path(path) if path is not None else default_prompt_path()
    text = prompt_path.resolve().read_text(encoding="utf-8")
    if REFERENCE_HEADING not in text:
        raise PromptContractError(f"Missing {REFERENCE_HEADING!r}.")
    section = text.split(REFERENCE_HEADING, 1)[1].split("## Operator notes", 1)[0]
    return _single_fenced_json(section, REFERENCE_HEADING)
