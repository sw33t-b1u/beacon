"""CLI: Generate SAGE-compatible PIR JSON from a business context file.

.. deprecated:: 1.0.0
    Invoke as ``beacon pir-generate`` instead. The ``python -m cmd.generate_pir``
    form is preserved for 1.x backward compatibility and will be removed in
    BEACON 2.0.0. See ``docs/api-stability.md`` §3.7.
"""

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


def main(argv: list[str] | None = None, *, _from_beacon_cli: bool = False) -> int:
    if not _from_beacon_cli:
        print(
            "DeprecationWarning: `python -m cmd.generate_pir` is deprecated; "
            "use `beacon pir-generate` instead (removal scheduled for 2.0.0). "
            "See docs/api-stability.md §3.7.",
            file=sys.stderr,
        )
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
        "--sources-candidate",
        default="output/sources_candidate.yaml",
        metavar="FILE",
        help=(
            "Path to write sources_candidate.yaml for TRACE merge"
            " (default: output/sources_candidate.yaml)"
        ),
    )
    parser.add_argument(
        "--save-context",
        default=None,
        metavar="FILE",
        help="Save the parsed BusinessContext as JSON for review"
        " (e.g. output/business_context.json)",
    )
    parser.add_argument(
        "--use-sage",
        action="store_true",
        help="Query SAGE Analysis API (SAGE_API_URL) to boost likelihood from observation data.",
    )
    parser.add_argument(
        "--no-sage",
        action="store_true",
        help=(
            "Skip the SAGE /api/incidents IR-boost call for actor_triage"
            " (air-gapped / SAGE-not-deployed). Sets data_quality.ir_boost_skipped"
            " on every prioritized_actor; IR factors default to neutral 1.0."
        ),
    )
    args = parser.parse_args(argv)

    # Lazy imports to keep startup fast
    from beacon.analysis.actor_triage import prioritize_actors  # noqa: PLC0415
    from beacon.analysis.asset_mapper import (
        load_asset_tags,
        map_asset_tags,
    )
    from beacon.analysis.element_extractor import extract
    from beacon.analysis.risk_scorer import score
    from beacon.analysis.threat_mapper import load_taxonomy, map_threats
    from beacon.generator.pir_builder import PIROutputDocument, build_pirs
    from beacon.generator.report_builder import build_collection_plan, write_collection_plan
    from beacon.generator.sources_yaml_builder import (  # noqa: PLC0415
        build_sources_candidate_yaml,
        write_sources_candidate,
    )
    from beacon.ingest.context_parser import parse
    from beacon.ingest.misp_client import MispClient  # noqa: PLC0415

    context_path = Path(args.context)
    if not context_path.exists():
        print(f"Error: context file not found: {context_path}", file=sys.stderr)
        return 1

    try:
        ctx = parse(context_path)
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

    use_llm = True
    cfg = load_config()

    # SAGE client setup. Two independent code paths consume SAGE:
    #   - risk_scorer (--use-sage): observation-count boost (fail-open).
    #   - actor_triage IR-boost (always-on unless --no-sage):
    #       per-actor /api/incidents lookup (fail-soft on the actor entry).
    sage_client = None
    use_sage = False
    if args.use_sage:
        if not cfg.sage_api_url:
            print("Error: --use-sage requires SAGE_API_URL to be set.", file=sys.stderr)
            return 1
        from beacon.sage.client import SageAPIClient  # noqa: PLC0415

        sage_client = SageAPIClient(cfg.sage_api_url)
        use_sage = True

    # Resolve actor_triage IR-boost path: --no-sage or unset SAGE_API_URL
    # → skip the SAGE call; otherwise reuse `sage_client` (if --use-sage)
    # or construct one for the IR-boost call alone.
    triage_sage_client = None
    ir_boost_skipped = bool(args.no_sage) or not cfg.sage_api_url
    if not ir_boost_skipped:
        if sage_client is not None:
            triage_sage_client = sage_client
        else:
            from beacon.sage.client import SageAPIClient  # noqa: PLC0415

            triage_sage_client = SageAPIClient(cfg.sage_api_url)

    elements = extract(ctx)
    asset_tag_list = map_asset_tags(elements, asset_tags_dict)
    threat = map_threats(elements, taxonomy)

    # Actor triage — rank threat actors via I×C×O triad (plan §3.2).
    # surface_ttp_map and MISP cache are loaded from default paths; absent files
    # are handled gracefully (empty surface map / degraded MISP mode).
    _beacon_root = Path(__file__).resolve().parent.parent
    _surface_map_path = _beacon_root / "schema" / "surface_ttp_map.json"
    _surface_ttp_map: dict = (
        json.loads(_surface_map_path.read_text(encoding="utf-8"))
        if _surface_map_path.exists()
        else {}
    )
    _misp_cache = _beacon_root / "cache" / "misp-threat-actor.json"
    _misp_client = MispClient(cache_path=_misp_cache if _misp_cache.exists() else None)
    _actors = prioritize_actors(
        ctx,
        taxonomy,
        _surface_ttp_map,
        _misp_client,
        window_days=cfg.activity_window_days,
        sage_client=triage_sage_client,
        ir_lookback_days=cfg.ir_lookback_days,
        ir_boost_skipped=ir_boost_skipped,
    )
    _top_likelihood = max((a.likelihood for a in _actors), default=0.0)

    risk = score(
        elements,
        threat,
        use_llm=use_llm,
        use_sage=use_sage,
        sage_client=sage_client,
        top_actor_likelihood=_top_likelihood,
    )
    pirs = build_pirs(
        elements,
        threat,
        risk,
        asset_tag_list,
        asset_tags_dict,
        use_llm=use_llm,
        prioritized_actors=_actors,
    )

    # Determine whether to use StorageBackend or direct file I/O.
    # --output bypasses StorageBackend for backward compatibility.
    use_storage_backend = args.output is None

    if use_storage_backend:
        from beacon.storage import create_storage_backend  # noqa: PLC0415

        storage = create_storage_backend(cfg)
        ts = datetime.now().strftime("%Y%m%d%H%M")
        pir_filename = f"pir_output_{ts}.json"
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
        doc = PIROutputDocument(pirs=pirs)
        if use_storage_backend:
            storage.save("pir", pir_filename, doc.model_dump_json(indent=2))
            print(f"Generated {len(pirs)} PIR(s) → pir/{pir_filename}")
        else:
            output_path.write_text(doc.model_dump_json(indent=2), encoding="utf-8")
            print(f"Generated {len(pirs)} PIR(s) → {output_path}")

    if args.collection_plan:
        plan_md = build_collection_plan(elements, threat, risk, pirs)
        if use_storage_backend:
            cp_filename = f"collection_plan_{ts}.md"
            storage.save("plans", cp_filename, plan_md)
            print(f"Collection plan → plans/{cp_filename}")
        else:
            collection_plan_path = Path(args.collection_plan)
            collection_plan_path.parent.mkdir(parents=True, exist_ok=True)
            write_collection_plan(plan_md, collection_plan_path)
            print(f"Collection plan → {args.collection_plan}")

    if args.sources_candidate:
        yaml_str = build_sources_candidate_yaml(pirs, elements)
        if use_storage_backend:
            sc_filename = f"sources_candidate_{ts}.yaml"
            storage.save("plans", sc_filename, yaml_str)
            print(f"Sources candidate → plans/{sc_filename}")
        else:
            sources_path = Path(args.sources_candidate)
            write_sources_candidate(yaml_str, sources_path)
            print(f"Sources candidate → {args.sources_candidate}")

    # --- Emit companion artifacts from the same parsed context ---
    from beacon.analysis.assets_generator import generate_assets_json  # noqa: PLC0415
    from beacon.analysis.identity_assets_generator import (  # noqa: PLC0415
        generate_identity_assets_json,
    )
    from beacon.analysis.user_accounts_generator import (  # noqa: PLC0415
        generate_user_accounts_json,
    )

    assets_data = generate_assets_json(ctx)
    identity_data = generate_identity_assets_json(ctx)
    accounts_data = generate_user_accounts_json(ctx)

    assets_json_str = json.dumps(assets_data, indent=2, ensure_ascii=False)
    identity_json_str = json.dumps(identity_data, indent=2, ensure_ascii=False)
    accounts_json_str = json.dumps(accounts_data, indent=2, ensure_ascii=False)

    if use_storage_backend:
        assets_filename = f"assets_{ts}.json"
        identity_filename = f"identity_assets_{ts}.json"
        accounts_filename = f"user_accounts_{ts}.json"
        storage.save("assets", assets_filename, assets_json_str)
        print(f"Assets draft → assets/{assets_filename}")
        storage.save("assets", identity_filename, identity_json_str)
        print(f"Identity assets draft → assets/{identity_filename}")
        storage.save("assets", accounts_filename, accounts_json_str)
        print(f"User accounts draft → assets/{accounts_filename}")
    else:
        output_dir = output_path.parent
        assets_out = output_dir / "assets.json"
        identity_out = output_dir / "identity_assets.json"
        accounts_out = output_dir / "user_accounts.json"
        assets_out.write_text(assets_json_str, encoding="utf-8")
        print(f"Assets draft → {assets_out}")
        identity_out.write_text(identity_json_str, encoding="utf-8")
        print(f"Identity assets draft → {identity_out}")
        accounts_out.write_text(accounts_json_str, encoding="utf-8")
        print(f"User accounts draft → {accounts_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
