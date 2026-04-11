"""Step 2: Asset Mapping — map business elements to SAGE asset tags."""

from __future__ import annotations

import json
from pathlib import Path

import structlog

from beacon.analysis.element_extractor import ExtractedElements

logger = structlog.get_logger(__name__)

_DEFAULT_ASSET_TAGS_PATH = Path(__file__).parent.parent.parent.parent / "schema" / "asset_tags.json"


def load_asset_tags(path: Path | None = None) -> dict:
    p = path or _DEFAULT_ASSET_TAGS_PATH
    return json.loads(p.read_text(encoding="utf-8"))


def map_asset_tags(elements: ExtractedElements, asset_tags: dict | None = None) -> list[str]:
    """Return deduplicated list of SAGE asset tags derived from business elements.

    Args:
        elements: ExtractedElements from element_extractor.
        asset_tags: Parsed asset_tags.json dict. Loaded from default path if None.

    Returns:
        Sorted list of unique asset tag strings (e.g. ["cloud", "erp", "ot"]).
    """
    if asset_tags is None:
        asset_tags = load_asset_tags()

    tags: set[str] = set()
    type_map: dict = asset_tags.get("asset_type_map", {})
    data_type_map: dict = asset_tags.get("data_type_tag_map", {})
    cloud_map: dict = asset_tags.get("cloud_provider_tag_map", {})

    # From data types
    for dt in elements.project_data_types:
        for tag in data_type_map.get(dt, []):
            tags.add(tag)

    # From cloud providers
    for cp in elements.project_cloud_providers:
        for tag in cloud_map.get(cp, []):
            tags.add(tag)

    # From crown jewel systems — keyword match
    system_text = " ".join(elements.crown_jewel_systems).lower()
    for asset_type, info in type_map.items():
        keywords: list[str] = info.get("keywords", [])
        if any(kw in system_text for kw in keywords):
            for tag in info.get("sage_tags", []):
                tags.add(tag)

    # From critical assets — keyword match on function + name, and data type mapping
    for ca in elements.critical_asset_details:
        ca_text = (ca.function + " " + ca.name).lower()
        for asset_type, info in type_map.items():
            keywords = info.get("keywords", [])
            if any(kw in ca_text for kw in keywords):
                for tag in info.get("sage_tags", []):
                    tags.add(tag)
        for dt in ca.data_types:
            for tag in data_type_map.get(dt, []):
                tags.add(tag)
        if ca.network_zone == "ot":
            tags.add("ot")
        if ca.network_zone in {"internet", "dmz"}:
            tags.add("external-facing")

    # OT connectivity → always add ot tag
    if elements.has_ot_connectivity:
        tags.add("ot")

    logger.info("asset_tags_mapped", tags=sorted(tags))
    return sorted(tags)


def get_criticality_multipliers(
    asset_tag_list: list[str], asset_tags: dict | None = None
) -> list[dict]:
    """Return asset_weight_rules entries for the given tag list.

    Returns a list of {"tag": ..., "criticality_multiplier": ...} dicts.
    """
    if asset_tags is None:
        asset_tags = load_asset_tags()

    type_map: dict = asset_tags.get("asset_type_map", {})
    rules = []
    seen: set[str] = set()

    for tag in asset_tag_list:
        if tag in seen:
            continue
        info = type_map.get(tag)
        if info:
            rules.append({"tag": tag, "criticality_multiplier": info["criticality_multiplier"]})
            seen.add(tag)

    # Sort by multiplier descending for readability
    return sorted(rules, key=lambda r: r["criticality_multiplier"], reverse=True)
