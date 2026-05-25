"""Generate a SAGE-compatible assets.json from a BEACON context document.

Reads a BusinessContext (Markdown or JSON) and converts the Critical Assets
section into the JSON format expected by SAGE's cmd/load_assets.py.

Usage:
    uv run python cmd/generate_assets.py --context input/context.md
    uv run python cmd/generate_assets.py --context input/context.json

    # Specify output path
    uv run python cmd/generate_assets.py --context input/context.md --output output/assets.json

After generating, review the output and fill in:
  - owner (team or email address per asset)
  - security_controls and security_control_ids
  - asset_vulnerabilities (after running STIX ETL)
  - actor_targets (after running STIX ETL)

Then load into SAGE Spanner:
    uv run python cmd/load_assets.py --file output/assets.json

.. deprecated:: 1.0.0
    Invoke as ``beacon assets-generate`` instead. The
    ``python -m cmd.generate_assets`` form is preserved for 1.x backward
    compatibility and will be removed in BEACON 2.0.0.
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


def main(argv: list[str] | None = None, *, _from_beacon_cli: bool = False) -> None:
    if not _from_beacon_cli:
        print(
            "DeprecationWarning: `python -m cmd.generate_assets` is deprecated; "
            "use `beacon assets-generate` instead (removal scheduled for 2.0.0).",
            file=sys.stderr,
        )
    parser = argparse.ArgumentParser(
        description="Generate SAGE assets.json from a BEACON context document"
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
        help="Output path for assets.json (default: StorageBackend assets/<timestamp>.json)",
    )
    args = parser.parse_args(argv)

    try:
        ctx = parse(args.context)
    except (FileNotFoundError, NotImplementedError) as exc:
        logger.error("context_parse_failed", error=str(exc))
        sys.exit(1)

    if not ctx.critical_assets:
        logger.warning(
            "no_critical_assets",
            hint="Add a 'Critical Assets' section to the context document",
        )

    assets_data = generate_assets_json(ctx)
    json_str = json.dumps(assets_data, indent=2, ensure_ascii=False)
    asset_count = len(assets_data["assets"])

    if args.output is None:
        # Use StorageBackend with timestamp filename
        from beacon.config import load_config  # noqa: PLC0415
        from beacon.storage import create_storage_backend  # noqa: PLC0415

        cfg = load_config()
        storage = create_storage_backend(cfg)
        ts = datetime.now().strftime("%Y%m%d%H%M")
        filename = f"assets_{ts}.json"
        storage.save("assets", filename, json_str)
        logger.info("assets_json_written", path=f"assets/{filename}", assets=asset_count)
        print(
            f"assets.json written: assets/{filename} ({asset_count} assets)\n"
            f"Review and complete the file, then load into SAGE:\n"
            f"  uv run python cmd/load_assets.py --file <resolved_path>"
        )
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json_str, encoding="utf-8")
        logger.info("assets_json_written", path=str(args.output), assets=asset_count)
        print(
            f"assets.json written: {args.output} ({asset_count} assets)\n"
            f"Review and complete the file, then load into SAGE:\n"
            f"  uv run python cmd/load_assets.py --file {args.output}"
        )


if __name__ == "__main__":
    main()
