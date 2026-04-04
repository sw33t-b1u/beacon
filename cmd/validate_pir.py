"""CLI: Validate a PIR JSON file against the output schema."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a PIR JSON file for SAGE compatibility.")
    parser.add_argument(
        "--pir",
        required=True,
        metavar="FILE",
        help="Path to pir_output.json to validate",
    )
    args = parser.parse_args(argv)

    from beacon.generator.pir_builder import PIROutput

    pir_path = Path(args.pir)
    if not pir_path.exists():
        print(f"Error: file not found: {pir_path}", file=sys.stderr)
        return 1

    data = json.loads(pir_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        print("Error: PIR JSON must be a list of PIR objects.", file=sys.stderr)
        return 1

    errors: list[str] = []
    for i, item in enumerate(data):
        try:
            PIROutput.model_validate(item)
        except Exception as exc:
            errors.append(f"  PIR[{i}]: {exc}")

    if errors:
        print(f"Validation FAILED ({len(errors)} error(s)):", file=sys.stderr)
        for e in errors:
            print(e, file=sys.stderr)
        return 1

    print(f"Validation OK — {len(data)} PIR(s) are SAGE-compatible.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
