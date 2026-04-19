"""Step 3: Threat Mapping — resolve threat tags from industry + geography.

Taxonomy schema is fully machine-generated from MITRE ATT&CK + MISP Galaxy
(see `cmd/update_taxonomy.py`). BEACON's narrow industry Literal is mapped to
MISP's coarse `cfr-target-category` vocabulary via `_BEACON_TO_MISP_INDUSTRY`
below; actors whose `target_industries` include that coarse value (or is empty)
and whose `target_geographies` overlap the org (or is empty / "Global") are
adopted.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import structlog

from beacon.analysis.element_extractor import ExtractedElements

logger = structlog.get_logger(__name__)

_DEFAULT_TAXONOMY_PATH = (
    Path(__file__).parent.parent.parent.parent / "schema" / "threat_taxonomy.json"
)


# BEACON `Organization.industry` Literal → MISP `cfr-target-category` coarse
# value. MISP uses only four buckets — {"Private sector", "Government",
# "Military", "Civil society"} — so BEACON's ten industries collapse onto them.
_BEACON_TO_MISP_INDUSTRY: dict[str, str] = {
    "manufacturing": "Private sector",
    "finance": "Private sector",
    "energy": "Private sector",
    "healthcare": "Private sector",
    "defense": "Military",
    "technology": "Private sector",
    "logistics": "Private sector",
    "government": "Government",
    "education": "Civil society",
    "other": "Private sector",
}


def load_taxonomy(path: Path | None = None) -> dict:
    p = path or _DEFAULT_TAXONOMY_PATH
    return json.loads(p.read_text(encoding="utf-8"))


@dataclass
class ThreatProfile:
    """Resolved threat information for the organization."""

    threat_actor_tags: list[str]
    notable_groups: list[str]
    priority_ttps: list[str]
    active_triggers: list[str]
    matched_categories: list[str]  # e.g. ["state_sponsored.China", "espionage"]


def map_threats(
    elements: ExtractedElements,
    taxonomy: dict | None = None,
) -> ThreatProfile:
    """Derive threat profile from industry + geography using MISP-derived taxonomy."""
    if taxonomy is None:
        taxonomy = load_taxonomy()

    industry = elements.org_industry
    geographies = elements.org_geographies
    triggers = elements.active_triggers

    coarse_industry = _BEACON_TO_MISP_INDUSTRY.get(industry, "Private sector")

    actor_cats: dict = taxonomy.get("actor_categories", {})
    geo_map: dict = taxonomy.get("geography_threat_map", {})

    tags: set[str] = set()
    priority_ttps: set[str] = set()
    notable_groups: set[str] = set()
    matched_categories: list[str] = []

    # Iterate every actor category (state_sponsored.<country> + non-state keys)
    for cat_path, info in _iter_actor_categories(actor_cats):
        if not _industry_matches(info, coarse_industry):
            continue
        if not _geography_matches(info, geographies):
            continue

        matched_categories.append(cat_path)
        tags.update(info.get("tags", []))
        priority_ttps.update(info.get("priority_ttps", []))
        notable_groups.update(info.get("mitre_groups", []))

    # Geography-specific APT tags / notable groups from MISP victim aggregation
    for geo in geographies:
        geo_info = geo_map.get(geo, {})
        tags.update(geo_info.get("apt_tags", []))
        notable_groups.update(geo_info.get("notable_groups", []))

    logger.info(
        "threats_mapped",
        industry=industry,
        coarse_industry=coarse_industry,
        geographies=geographies,
        matched_categories=matched_categories,
        tags=sorted(tags),
    )

    return ThreatProfile(
        threat_actor_tags=sorted(tags),
        notable_groups=sorted(notable_groups),
        priority_ttps=sorted(priority_ttps),
        active_triggers=triggers,
        matched_categories=matched_categories,
    )


def _iter_actor_categories(actor_cats: dict):
    """Yield (cat_path, info_dict) for every leaf category.

    state_sponsored entries expand to `state_sponsored.<Country>`; non-state
    entries use their top-level key directly.
    """
    for key, value in actor_cats.items():
        if key == "state_sponsored" and isinstance(value, dict):
            for country, info in value.items():
                if isinstance(info, dict):
                    yield f"state_sponsored.{country}", info
        elif isinstance(value, dict):
            yield key, value


def _industry_matches(info: dict, coarse_industry: str) -> bool:
    target_industries = info.get("target_industries", [])
    if not target_industries:
        return True  # empty means "no narrowing" — accept
    return coarse_industry in target_industries


def _geography_matches(info: dict, org_geographies: list[str]) -> bool:
    target_geographies = info.get("target_geographies", [])
    if not target_geographies or target_geographies == ["Global"]:
        return True
    if not org_geographies:
        return False
    return any(g in target_geographies for g in org_geographies)
