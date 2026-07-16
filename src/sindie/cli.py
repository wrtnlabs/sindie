"""Small offline CLI for prompt, case, result, and host-score validation."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .cases import discover_cases, load_case
from .prompt import load_prompt_bundle
from .scoring import aggregate_all
from .validation import validate_output


def _dump(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _bundle(args: argparse.Namespace):
    return load_prompt_bundle(args.prompt)


def _request(case_path: str | None) -> dict[str, Any] | None:
    return load_case(case_path).request if case_path else None


def _validate_prompt(args: argparse.Namespace) -> int:
    bundle = _bundle(args)
    _dump(
        {
            "valid": True,
            "path": str(bundle.path),
            "prompt_version": bundle.prompt_version,
            "schema_version": bundle.schema_version,
            "schema_id": bundle.schema.get("$id"),
            "prompt_characters": len(bundle.system_prompt),
            "schema_definitions": len(bundle.schema.get("$defs", {})),
        }
    )
    return 0


def _validate_case(args: argparse.Namespace) -> int:
    cases = discover_cases(args.path)
    _dump(
        {
            "valid": True,
            "count": len(cases),
            "cases": [
                {
                    "id": case.id,
                    "mode": case.mode,
                    "path": str(case.path),
                    "attachments": list(case.attachments),
                }
                for case in cases
            ],
        }
    )
    return 0


def _validate_result(args: argparse.Namespace) -> int:
    raw = Path(args.result).read_text(encoding="utf-8")
    report = validate_output(raw, bundle=_bundle(args), request=_request(args.case))
    _dump(report.as_dict())
    return 0 if report.valid else 1


def _score(args: argparse.Namespace) -> int:
    raw = Path(args.result).read_text(encoding="utf-8")
    report = validate_output(raw, bundle=_bundle(args), request=_request(args.case))
    if not report.valid or report.data is None:
        _dump(report.as_dict())
        return 1
    _dump(
        {
            "valid": True,
            "scores": [
                score.as_dict()
                for score in aggregate_all(report.data, min_coverage=args.min_coverage)
            ],
        }
    )
    return 0


def _add_prompt_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--prompt", help="Path to PROMPT.md; defaults to the repository root.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sindie-eval")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_prompt = subparsers.add_parser(
        "validate-prompt", help="Validate prompt markers, versions, and Draft 2020-12 schema."
    )
    _add_prompt_argument(validate_prompt)
    validate_prompt.set_defaults(handler=_validate_prompt)

    validate_case = subparsers.add_parser(
        "validate-case", help="Validate one case or discover every case below a directory."
    )
    validate_case.add_argument("path")
    validate_case.set_defaults(handler=_validate_case)

    validate_result = subparsers.add_parser(
        "validate-result", help="Validate one raw model JSON result."
    )
    validate_result.add_argument("result")
    validate_result.add_argument("--case", help="Optional case used to verify request echoing.")
    _add_prompt_argument(validate_result)
    validate_result.set_defaults(handler=_validate_result)

    score = subparsers.add_parser("score", help="Compute deterministic host-owned artifact scores.")
    score.add_argument("result")
    score.add_argument("--case", help="Optional case used to verify request echoing.")
    score.add_argument("--min-coverage", type=float, default=1.0)
    _add_prompt_argument(score)
    score.set_defaults(handler=_score)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
