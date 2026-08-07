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
    # Fine-grained BEACON industry (ten-value vocabulary) that produced this
    # profile. ``matched_categories`` above is resolved against the four coarse
    # MISP ``cfr-target-category`` buckets, so this field preserves the original
    # industry resolution for reporting / downstream re-ranking (BEACON 4.3.0).
    fine_industry: str = ""


def map_threats(
    elements: ExtractedElements,
    taxonomy: dict | None = None,
) -> ThreatProfile:
    """Derive threat profile from industry + geography using MISP-derived taxonomy.

    Actor-level prioritization (I×C×O likelihood scores per actor) is handled by
    `beacon.analysis.actor_triage.prioritize_actors()` and wired at the PIR
    generation layer (`beacon.generator.pir_builder.build_pirs()`). This function
    returns category-level threat tags; actor_triage adds per-actor ranked output.
    """
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
        if not _fine_industry_matches(info, industry):
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
        fine_industry=industry,
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


def _fine_industry_matches(info: dict, fine_industry: str) -> bool:
    """Optional fine-grained sector narrowing (BEACON 4.3.0, forward-compatible).

    The MISP-derived taxonomy currently carries only the four coarse
    ``cfr-target-category`` buckets in ``target_industries``, so BEACON's ten
    industries collapse onto four and industry resolution is lost at the
    category level (e.g. ``healthcare`` and ``manufacturing`` both become
    ``Private sector``). When a future ``beacon taxonomy-refresh`` populates a
    finer ``target_sectors`` list (BEACON's ten-value industry vocabulary) on an
    actor category, this predicate narrows matches to it. When the field is
    absent — as in every taxonomy shipped up to 4.3.0 — it returns ``True``,
    preserving current matching behaviour exactly (no change to P1/P2 selection).
    Regenerating the taxonomy with ``target_sectors`` requires network access to
    MITRE ATT&CK / MISP Galaxy and is a maintainer/user handoff step.
    """
    target_sectors = info.get("target_sectors", [])
    if not target_sectors:
        return True
    return fine_industry in target_sectors


def _geography_matches(info: dict, org_geographies: list[str]) -> bool:
    target_geographies = info.get("target_geographies", [])
    if not target_geographies or target_geographies == ["Global"]:
        return True
    if not org_geographies:
        return False
    return any(g in target_geographies for g in org_geographies)
