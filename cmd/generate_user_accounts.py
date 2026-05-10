"""Generate user_accounts.json from a BEACON context document.

Initiative B (User-Account SCO) — produces the BEACON-side
authoritative artifact (``source = beacon`` precedence in SAGE).

Usage:
    # From Markdown (requires LLM / Vertex AI; the User Accounts section
    # of context.md is read alongside the rest of the doc).
    uv run python cmd/generate_user_accounts.py --context input/context.md

    # From JSON (no LLM required; user_accounts[] / account_on_asset[]
    # must be present in the JSON).
    uv run python cmd/generate_user_accounts.py \\
        --context input/context.json --no-llm

After generating, validate with TRACE before loading into SAGE:

    cd ../TRACE && uv run python cmd/validate_user_accounts.py \\
        --user-accounts ../BEACON/output/user_accounts.json \\
        --assets ../BEACON/output/assets.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import structlog
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from beacon.analysis.user_accounts_generator import generate_user_accounts_json
from beacon.ingest.context_parser import parse

load_dotenv()
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]
)
logger = structlog.get_logger(__name__)

_DEFAULT_OUTPUT = Path(__file__).parent.parent / "output" / "user_accounts.json"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate user_accounts.json from a BEACON context document"
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
        help=f"Output path for user_accounts.json (default: {_DEFAULT_OUTPUT})",
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

    if not ctx.user_accounts:
        logger.warning(
            "no_user_accounts",
            hint=(
                "Add a 'User Accounts' section to context.md (or "
                "'user_accounts' / 'account_on_asset' arrays in context.json)"
            ),
        )

    payload = generate_user_accounts_json(ctx)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    ua_count = len(payload["user_accounts"])
    edge_count = len(payload["account_on_asset"])
    logger.info(
        "user_accounts_json_written",
        path=str(args.output),
        user_accounts=ua_count,
        account_on_asset=edge_count,
    )
    print(
        f"user_accounts.json written: {args.output} "
        f"({ua_count} accounts, {edge_count} edges)\n"
        f"Validate before loading into SAGE:\n"
        f"  cd ../TRACE && uv run python cmd/validate_user_accounts.py \\\n"
        f"    --user-accounts {args.output} \\\n"
        f"    --assets ../BEACON/output/assets.json"
    )


if __name__ == "__main__":
    main()
