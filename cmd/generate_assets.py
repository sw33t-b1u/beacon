"""Generate a SAGE-compatible assets.json from a BEACON context document.

Reads a BusinessContext (Markdown or JSON) and converts the Critical Assets
section into the JSON format expected by SAGE's cmd/load_assets.py.

Usage:
    # From Markdown (requires LLM / Vertex AI)
    uv run python cmd/generate_assets.py --context input/context.md

    # From JSON (no LLM required)
    uv run python cmd/generate_assets.py --context input/context.json --no-llm

    # Specify output path
    uv run python cmd/generate_assets.py --context input/context.md --output output/assets.json

After generating, review the output and fill in:
  - owner (team or email address per asset)
  - security_controls and security_control_ids
  - asset_vulnerabilities (after running STIX ETL)
  - actor_targets (after running STIX ETL)

Then load into SAGE Spanner:
    uv run python cmd/load_assets.py --file output/assets.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import structlog
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from beacon.analysis.assets_generator import generate_assets_json
from beacon.ingest.context_parser import parse

load_dotenv()
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]
)
logger = structlog.get_logger(__name__)

_DEFAULT_OUTPUT = Path(__file__).parent.parent / "output" / "assets.json"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate SAGE assets.json from a BEACON context document"
    )
    parser.add_argument(
        "--context",
        required=True,
        metavar="PATH",
        help="Path to context document (.md requires LLM; .json works with --no-llm)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_DEFAULT_OUTPUT,
        help=f"Output path for assets.json (default: {_DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip LLM processing — only valid for JSON context files",
    )
    args = parser.parse_args()

    try:
        ctx = parse(args.context, no_llm=args.no_llm)
    except (FileNotFoundError, NotImplementedError) as exc:
        logger.error("context_parse_failed", error=str(exc))
        sys.exit(1)

    if not ctx.critical_assets:
        logger.warning(
            "no_critical_assets",
            hint="Add a 'Critical Assets' section to the context document",
        )

    assets_data = generate_assets_json(ctx)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(assets_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    asset_count = len(assets_data["assets"])
    logger.info("assets_json_written", path=str(args.output), assets=asset_count)
    print(
        f"assets.json written: {args.output} ({asset_count} assets)\n"
        f"Review and complete the file, then load into SAGE:\n"
        f"  uv run python cmd/load_assets.py --file {args.output}"
    )


if __name__ == "__main__":
    main()
