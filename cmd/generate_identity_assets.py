"""Generate identity_assets.json from a BEACON context document.

Initiative A (Identity-Asset HasAccess edge) — produces the BEACON-side
authoritative artifact (``source = beacon`` precedence in SAGE).

Usage:
    # From Markdown (requires LLM / Vertex AI; the Identities section
    # of context.md is read alongside the rest of the doc).
    uv run python cmd/generate_identity_assets.py --context input/context.md
    uv run python cmd/generate_identity_assets.py --context input/context.json

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
from datetime import datetime
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
        help="Path to context document (.md or .json)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Output path for identity_assets.json (default: StorageBackend assets/<timestamp>.json)"
        ),
    )
    args = parser.parse_args(argv)

    try:
        ctx = parse(args.context)
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
    json_str = json.dumps(payload, indent=2, ensure_ascii=False)

    identity_count = len(payload["identities"])
    edge_count = len(payload["has_access"])

    if args.output is None:
        # Use StorageBackend with timestamp filename
        from beacon.config import load_config  # noqa: PLC0415
        from beacon.storage import create_storage_backend  # noqa: PLC0415

        cfg = load_config()
        storage = create_storage_backend(cfg)
        ts = datetime.now().strftime("%Y%m%d%H%M")
        filename = f"identity_assets_{ts}.json"
        storage.save("assets", filename, json_str)
        logger.info(
            "identity_assets_json_written",
            path=f"assets/{filename}",
            identities=identity_count,
            has_access=edge_count,
        )
        print(
            f"identity_assets.json written: assets/{filename} "
            f"({identity_count} identities, {edge_count} edges)\n"
            f"Validate before loading into SAGE:\n"
            f"  cd ../TRACE && uv run python cmd/validate_identity_assets.py \\\n"
            f"    --identity-assets <resolved_path> \\\n"
            f"    --assets ../BEACON/output/assets.json"
        )
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json_str, encoding="utf-8")
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
