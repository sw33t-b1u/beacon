"""CLI: Submit PIR output for review by creating GHE Issues."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import structlog
from dotenv import load_dotenv

load_dotenv()
logger = structlog.get_logger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Submit PIR output for review by creating GitHub/GHE Issues."
    )
    parser.add_argument(
        "--pir",
        required=True,
        metavar="FILE",
        help="Path to pir_output.json",
    )
    parser.add_argument(
        "--collection-plan",
        default=None,
        metavar="FILE",
        help="Path to collection_plan.md to attach as comment",
    )
    args = parser.parse_args(argv)

    from beacon.config import load_config  # noqa: PLC0415
    from beacon.review.github import GHEClient, submit_pirs_for_review  # noqa: PLC0415

    pir_path = Path(args.pir)
    if not pir_path.exists():
        print(f"Error: PIR file not found: {pir_path}", file=sys.stderr)
        return 1

    pirs = json.loads(pir_path.read_text(encoding="utf-8"))
    if not isinstance(pirs, list):
        print("Error: PIR file must contain a JSON array.", file=sys.stderr)
        return 1

    collection_plan_text: str | None = None
    if args.collection_plan:
        cp_path = Path(args.collection_plan)
        if not cp_path.exists():
            print(f"Error: collection plan file not found: {cp_path}", file=sys.stderr)
            return 1
        collection_plan_text = cp_path.read_text(encoding="utf-8")

    cfg = load_config()

    try:
        client = GHEClient(
            token=cfg.ghe_token,
            repo=cfg.ghe_repo,
            api_base=cfg.ghe_api_base,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    results = submit_pirs_for_review(pirs, client, collection_plan_text)

    for r in results:
        print(f"Created Issue #{r.issue_number} for {r.pir_id}: {r.html_url}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
