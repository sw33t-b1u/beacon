"""Generate identity_assets.json from a BEACON context document.

Initiative A (Identity-Asset HasAccess edge) — produces the BEACON-side
authoritative artifact (``source = beacon`` precedence in SAGE).

Usage:
    # From Markdown (requires LLM / Vertex AI; the Identities section
    # of context.md is read alongside the rest of the doc).
    uv run python cmd/generate_identity_assets.py --context input/context.md

    # From JSON (no LLM required; identities[] / has_access[] must be
    # present in the JSON).
    uv run python cmd/generate_identity_assets.py \\
        --context input/context.json --no-llm

After generating, validate the output with TRACE before loading into SAGE:

    cd ../TRACE && uv run python cmd/validate_identity_assets.py \\
        --identity-assets ../BEACON/output/identity_assets.json \\
        --assets ../BEACON/output/assets.json

.. deprecated:: 1.0.0
    Invoke as ``beacon identity-generate`` instead. The
    ``python -m cmd.generate_identity_assets`` form is preserved for 1.x
    backward compatibility and will be removed in BEACON 2.0.0.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import structlog
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from beacon.analysis.identity_assets_generator import generate_identity_assets_json
from beacon.ingest.context_parser import parse

load_dotenv()
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]
)
logger = structlog.get_logger(__name__)

_DEFAULT_OUTPUT = Path(__file__).parent.parent / "output" / "identity_assets.json"


def main(argv: list[str] | None = None, *, _from_beacon_cli: bool = False) -> None:
    if not _from_beacon_cli:
        print(
            "DeprecationWarning: `python -m cmd.generate_identity_assets` is deprecated; "
            "use `beacon identity-generate` instead (removal scheduled for 2.0.0).",
            file=sys.stderr,
        )
    parser = argparse.ArgumentParser(
        description="Generate identity_assets.json from a BEACON context document"
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
        help=f"Output path for identity_assets.json (default: {_DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Skip LLM processing — only valid for JSON context files",
    )
    args = parser.parse_args(argv)

    try:
        ctx = parse(args.context, no_llm=args.no_llm)
    except (FileNotFoundError, NotImplementedError) as exc:
        logger.error("context_parse_failed", error=str(exc))
        sys.exit(1)

    if not ctx.identities:
        logger.warning(
            "no_identities",
            hint=(
                "Add an 'Identities and Access' section to context.md "
                "(or 'identities' / 'has_access' arrays in context.json)"
            ),
        )

    payload = generate_identity_assets_json(ctx)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    identity_count = len(payload["identities"])
    edge_count = len(payload["has_access"])
    logger.info(
        "identity_assets_json_written",
        path=str(args.output),
        identities=identity_count,
        has_access=edge_count,
    )
    print(
        f"identity_assets.json written: {args.output} "
        f"({identity_count} identities, {edge_count} edges)\n"
        f"Validate before loading into SAGE:\n"
        f"  cd ../TRACE && uv run python cmd/validate_identity_assets.py \\\n"
        f"    --identity-assets {args.output} \\\n"
        f"    --assets ../BEACON/output/assets.json"
    )


if __name__ == "__main__":
    main()
