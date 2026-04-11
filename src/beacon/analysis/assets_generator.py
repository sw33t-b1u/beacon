"""Generate a SAGE-compatible assets.json from BEACON BusinessContext.

Converts CriticalAsset objects in BusinessContext to the JSON format expected
by SAGE's cmd/load_assets.py.  Fields requiring manual review after generation:
- owner: set to "" — fill in team or email address
- security_control_ids: empty list — add EDR/SIEM/firewall IDs after defining them
- asset_vulnerabilities: empty list — populate after running STIX ETL
- actor_targets: empty list — populate after running STIX ETL
"""

from __future__ import annotations

from typing import Any

import structlog

from beacon.analysis.asset_mapper import load_asset_tags
from beacon.ingest.schema import BusinessContext, CriticalAsset

logger = structlog.get_logger(__name__)

# Map CriticalAsset.criticality (categorical) to SAGE criticality (float 0-10)
_CRITICALITY_MAP: dict[str, float] = {
    "low": 3.0,
    "medium": 5.0,
    "high": 8.0,
    "critical": 10.0,
}

# Map CriticalAsset.type to SAGE asset_type string
_ASSET_TYPE_MAP: dict[str, str] = {
    "server": "server",
    "database": "server",
    "network_device": "network-device",
    "application": "application",
    "endpoint": "endpoint",
    "storage": "server",
    "identity_system": "server",
    "ot_device": "network-device",
    "cloud_service": "cloud",
    "other": "other",
}

# Stable segment IDs derived from network zone names
_ZONE_SEGMENT_ID: dict[str, str] = {
    "internet": "seg-0001-inet0-0000-000000000001",
    "dmz": "seg-0002-dmz00-0000-000000000001",
    "corporate": "seg-0003-corp0-0000-000000000001",
    "ot": "seg-0004-ot000-0000-000000000001",
    "cloud": "seg-0005-cloud-0000-000000000001",
    "restricted": "seg-0006-restr-0000-000000000001",
    "unknown": "seg-0007-unkn0-0000-000000000001",
}

# Representative CIDR blocks per zone (for documentation; not used by SAGE routing)
_ZONE_CIDR: dict[str, str] = {
    "internet": "0.0.0.0/0",
    "dmz": "10.0.1.0/24",
    "corporate": "10.0.2.0/24",
    "ot": "192.168.10.0/24",
    "cloud": "10.100.0.0/16",
    "restricted": "10.0.3.0/24",
    "unknown": "10.0.0.0/24",
}

# Zones that indicate internet exposure
_INTERNET_EXPOSED_ZONES: frozenset[str] = frozenset({"internet", "dmz"})


def _normalize_asset_id(raw_id: str) -> str:
    """Ensure the asset ID carries an 'asset-' prefix for SAGE conventions."""
    return raw_id if raw_id.startswith("asset-") else f"asset-{raw_id}"


def _derive_asset_tags(ca: CriticalAsset, asset_tags_data: dict) -> list[str]:
    """Return SAGE asset tags for a single CriticalAsset.

    Uses the same three-pass logic as asset_mapper.map_asset_tags:
    1. Network zone → network_zone_tag_map
    2. Data types → data_type_tag_map
    3. Keyword match on function + name → asset_type_map
    """
    tags: set[str] = set()
    type_map: dict = asset_tags_data.get("asset_type_map", {})
    data_type_map: dict = asset_tags_data.get("data_type_tag_map", {})
    zone_map: dict = asset_tags_data.get("network_zone_tag_map", {})

    # 1. Network zone
    for tag in zone_map.get(ca.network_zone, []):
        tags.add(tag)

    # 2. Data types
    for dt in ca.data_types:
        for tag in data_type_map.get(dt, []):
            tags.add(tag)

    # 3. Keyword match on function + name text
    search_text = (ca.function + " " + ca.name).lower()
    for _key, info in type_map.items():
        if any(kw in search_text for kw in info.get("keywords", [])):
            for tag in info.get("sage_tags", []):
                tags.add(tag)

    return sorted(tags)


def generate_assets_json(ctx: BusinessContext) -> dict[str, Any]:
    """Convert BusinessContext → SAGE assets.json dict.

    Args:
        ctx: Validated BusinessContext from BEACON context parser.

    Returns:
        Dict matching the SAGE assets.json schema, ready for JSON serialisation.
        Write to output/assets.json, then load via:
            uv run python cmd/load_assets.py --file output/assets.json
    """
    asset_tags_data = load_asset_tags()

    # --- Network segments (one per unique network zone found in assets) ---
    zones_seen: set[str] = {ca.network_zone for ca in ctx.critical_assets}
    network_segments = [
        {
            "id": _ZONE_SEGMENT_ID.get(zone, _ZONE_SEGMENT_ID["unknown"]),
            "name": zone.capitalize(),
            "cidr": _ZONE_CIDR.get(zone, "10.0.0.0/24"),
            "zone": zone if zone in {"dmz", "ot"} else "internal",
        }
        for zone in sorted(zones_seen)
    ]

    # --- Assets ---
    assets: list[dict] = []
    asset_id_set: set[str] = set()
    for ca in ctx.critical_assets:
        asset_id = _normalize_asset_id(ca.id)
        asset_id_set.add(asset_id)
        assets.append(
            {
                "id": asset_id,
                "name": ca.name,
                "asset_type": _ASSET_TYPE_MAP.get(ca.type, "other"),
                "environment": "cloud" if ca.network_zone == "cloud" else "onprem",
                "criticality": _CRITICALITY_MAP.get(ca.criticality, 5.0),
                "owner": "",  # fill in manually
                "network_segment_id": _ZONE_SEGMENT_ID.get(
                    ca.network_zone, _ZONE_SEGMENT_ID["unknown"]
                ),
                "exposed_to_internet": ca.network_zone in _INTERNET_EXPOSED_ZONES,
                "tags": _derive_asset_tags(ca, asset_tags_data),
                "security_control_ids": [],  # fill in manually
            }
        )

    # --- Asset connections from dependencies ---
    asset_connections: list[dict] = []
    for ca in ctx.critical_assets:
        src_id = _normalize_asset_id(ca.id)
        for dep in ca.dependencies:
            dst_id = _normalize_asset_id(dep)
            if dst_id in asset_id_set:
                asset_connections.append(
                    {
                        "src": src_id,
                        "dst": dst_id,
                        "protocol": "tcp",
                        "port": 0,
                    }
                )

    result: dict[str, Any] = {
        "_comment": (
            f"Generated by BEACON from context: {ctx.organization.name}. "
            "Review and complete: owner, security_controls, security_control_ids, "
            "asset_vulnerabilities (after STIX ETL), actor_targets."
        ),
        "network_segments": network_segments,
        "security_controls": [],  # define your EDR/SIEM/firewall entries here
        "assets": assets,
        "asset_vulnerabilities": [],  # populate after running STIX ETL
        "asset_connections": asset_connections,
        "actor_targets": [],  # populate after running STIX ETL
    }

    logger.info(
        "assets_json_generated",
        org=ctx.organization.name,
        assets=len(assets),
        segments=len(network_segments),
        connections=len(asset_connections),
    )
    return result
