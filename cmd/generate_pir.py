"""CLI: Generate SAGE-compatible PIR JSON from a business context file."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import structlog
from dotenv import load_dotenv

load_dotenv()
logger = structlog.get_logger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate SAGE-compatible PIR JSON from a business context file."
    )
    parser.add_argument(
        "--context",
        required=True,
        metavar="FILE",
        help="Path to strategy document (.md) or business_context.json",
    )
    parser.add_argument(
        "--taxonomy",
        default=None,
        metavar="FILE",
        help="Path to threat_taxonomy.json (default: schema/threat_taxonomy.json)",
    )
    parser.add_argument(
        "--asset-tags",
        default=None,
        metavar="FILE",
        help="Path to asset_tags.json (default: schema/asset_tags.json)",
    )
    parser.add_argument(
        "--output",
        default=None,
        metavar="FILE",
        help=("Output path for PIR JSON (default: output/pir_output_<YYYYMMDD_HHMMSS>.json)"),
    )
    parser.add_argument(
        "--collection-plan",
        default="output/collection_plan.md",
        metavar="FILE",
        help="Path to write collection_plan.md (default: output/collection_plan.md)",
    )
    parser.add_argument(
        "--save-context",
        default=None,
        metavar="FILE",
        help="Save the parsed BusinessContext as JSON for review"
        " (e.g. output/business_context.json)",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Use dictionary-only mode (no Vertex AI calls). JSON input only.",
    )
    parser.add_argument(
        "--use-sage",
        action="store_true",
        help="Query SAGE Analysis API (SAGE_API_URL) to boost likelihood from observation data.",
    )
    args = parser.parse_args(argv)

    # Lazy imports to keep startup fast
    from beacon.analysis.asset_mapper import (
        load_asset_tags,
        map_asset_tags,
    )
    from beacon.analysis.element_extractor import extract
    from beacon.analysis.risk_scorer import score
    from beacon.analysis.threat_mapper import load_taxonomy, map_threats
    from beacon.generator.pir_builder import build_pirs
    from beacon.generator.report_builder import build_collection_plan, write_collection_plan
    from beacon.ingest.context_parser import parse

    context_path = Path(args.context)
    if not context_path.exists():
        print(f"Error: context file not found: {context_path}", file=sys.stderr)
        return 1

    try:
        ctx = parse(context_path, no_llm=args.no_llm)
    except NotImplementedError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # Optionally save the parsed BusinessContext for analyst review / editing
    if args.save_context:
        save_path = Path(args.save_context)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_text(
            json.dumps(ctx.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Business context → {save_path}")

    taxonomy_path = Path(args.taxonomy) if args.taxonomy else None
    asset_tags_path = Path(args.asset_tags) if args.asset_tags else None

    taxonomy = load_taxonomy(taxonomy_path)
    asset_tags_dict = load_asset_tags(asset_tags_path)

    from beacon.config import load_config  # noqa: PLC0415

    use_llm = not args.no_llm
    cfg = load_config()

    # SAGE client setup
    sage_client = None
    use_sage = False
    if args.use_sage:
        if not cfg.sage_api_url:
            print("Error: --use-sage requires SAGE_API_URL to be set.", file=sys.stderr)
            return 1
        from beacon.sage.client import SageAPIClient  # noqa: PLC0415

        sage_client = SageAPIClient(cfg.sage_api_url)
        use_sage = True

    elements = extract(ctx)
    asset_tag_list = map_asset_tags(elements, asset_tags_dict)
    threat = map_threats(elements, taxonomy)
    risk = score(elements, threat, use_llm=use_llm, use_sage=use_sage, sage_client=sage_client)
    pirs = build_pirs(elements, threat, risk, asset_tag_list, asset_tags_dict, use_llm=use_llm)

    if args.output is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = Path("output") / f"pir_output_{ts}.json"
    else:
        output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not pirs:
        print(
            f"No PIRs generated (composite score {risk.composite} < 12). "
            "Check collection_plan.md for lower-priority items.",
            file=sys.stderr,
        )
    else:
        output_data = [p.model_dump() for p in pirs]
        output_path.write_text(
            json.dumps(output_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Generated {len(pirs)} PIR(s) → {output_path}")

    if args.collection_plan:
        collection_plan_path = Path(args.collection_plan)
        collection_plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan = build_collection_plan(elements, threat, risk, pirs)
        write_collection_plan(plan, collection_plan_path)
        print(f"Collection plan → {args.collection_plan}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
