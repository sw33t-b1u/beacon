"""Generate user_accounts.json from a BEACON context document.

Initiative B (User-Account SCO) — produces the BEACON-side
authoritative artifact (``source = beacon`` precedence in SAGE).

Invoke via the unified CLI: ``beacon accounts-generate``.

After generating, validate with TRACE before loading into SAGE:

    cd ../TRACE && uv run trace validate-accounts \\
        --user-accounts ../BEACON/output/user_accounts.json \\
        --assets ../BEACON/output/assets.json
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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Generate user_accounts.json from a BEACON context document"
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
            "Output path for user_accounts.json (default: StorageBackend assets/<timestamp>.json)"
        ),
    )
    args = parser.parse_args(argv)

    try:
        ctx = parse(args.context)
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
    json_str = json.dumps(payload, indent=2, ensure_ascii=False)

    ua_count = len(payload["user_accounts"])
    edge_count = len(payload["account_on_asset"])

    if args.output is None:
        # Use StorageBackend with timestamp filename
        from beacon.config import load_config  # noqa: PLC0415
        from beacon.storage import create_storage_backend  # noqa: PLC0415

        cfg = load_config()
        storage = create_storage_backend(cfg)
        ts = datetime.now().strftime("%Y%m%d%H%M")
        filename = f"user_accounts_{ts}.json"
        storage.save("assets", filename, json_str)
        logger.info(
            "user_accounts_json_written",
            path=f"assets/{filename}",
            user_accounts=ua_count,
            account_on_asset=edge_count,
        )
        print(
            f"user_accounts.json written: assets/{filename} "
            f"({ua_count} accounts, {edge_count} edges)\n"
            f"Validate before loading into SAGE:\n"
            f"  cd ../TRACE && uv run trace validate-accounts \\\n"
            f"    --user-accounts <resolved_path> \\\n"
            f"    --assets ../BEACON/output/assets.json"
        )
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json_str, encoding="utf-8")
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
            f"  cd ../TRACE && uv run trace validate-accounts \\\n"
            f"    --user-accounts {args.output} \\\n"
            f"    --assets ../BEACON/output/assets.json"
        )
