"""Step 3: Threat Mapping — resolve threat tags from industry, geography, and triggers."""

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
    matched_categories: list[str]  # e.g. ["state_sponsored.China", "ransomware"]


def map_threats(
    elements: ExtractedElements,
    taxonomy: dict | None = None,
    *,
    use_llm: bool = False,
    config=None,
) -> ThreatProfile:
    """Derive threat profile from industry, geography, and business triggers.

    When use_llm=True and the dictionary match yields no matched_categories,
    falls back to Vertex AI (gemini-2.5-flash-lite) for tag completion.
    """
    if taxonomy is None:
        taxonomy = load_taxonomy()

    industry = elements.org_industry
    geographies = elements.org_geographies
    triggers = elements.active_triggers

    industry_map: dict = taxonomy.get("industry_threat_map", {})
    geo_map: dict = taxonomy.get("geography_threat_map", {})
    trigger_map: dict = taxonomy.get("business_trigger_map", {})
    actor_cats: dict = taxonomy.get("actor_categories", {})

    # Step 3a: resolve applicable categories from industry
    industry_info = industry_map.get(industry, {})
    applicable_categories: list[str] = industry_info.get("applicable_categories", [])

    tags: set[str] = set(industry_info.get("additional_tags", []))
    priority_ttps: set[str] = set(industry_info.get("priority_ttps", []))
    notable_groups: set[str] = set()
    matched_categories: list[str] = []

    # Step 3b: resolve actor details for each applicable category
    for cat_path in applicable_categories:
        info = _resolve_category(actor_cats, cat_path)
        if not info:
            continue

        # Check if this actor's geographies overlap with org geographies
        target_geos: list[str] = info.get("target_geographies", [])
        if target_geos and target_geos != ["Global"] and geographies:
            if not any(g in target_geos for g in geographies):
                continue  # geography mismatch — skip this actor

        matched_categories.append(cat_path)
        tags.update(info.get("tags", []))
        priority_ttps.update(info.get("priority_ttps", []))
        notable_groups.update(info.get("mitre_groups", []))

    # Step 3c: add geography-specific APT tags
    for geo in geographies:
        geo_info = geo_map.get(geo, {})
        tags.update(geo_info.get("apt_tags", []))
        notable_groups.update(geo_info.get("notable_groups", []))

    # Step 3d: apply business trigger tags
    for trigger in triggers:
        trigger_info = trigger_map.get(trigger, {})
        tags.update(trigger_info.get("additional_tags", []))

    logger.info(
        "threats_mapped",
        industry=industry,
        geographies=geographies,
        matched_categories=matched_categories,
        tags=sorted(tags),
    )

    profile = ThreatProfile(
        threat_actor_tags=sorted(tags),
        notable_groups=sorted(notable_groups),
        priority_ttps=sorted(priority_ttps),
        active_triggers=triggers,
        matched_categories=matched_categories,
    )

    # LLM fallback: if no categories matched and LLM mode is on, ask Gemini
    if use_llm and not matched_categories:
        profile = _llm_fallback(profile, elements, config)

    return profile


def _llm_fallback(
    profile: ThreatProfile,
    elements: ExtractedElements,
    config=None,
) -> ThreatProfile:
    """Call Vertex AI to complete threat tags when dictionary has no match."""
    from beacon.llm.client import call_llm_json, load_prompt  # noqa: PLC0415

    template = load_prompt("threat_tag_completion.md")
    prompt = (
        template.replace("{{INDUSTRY}}", elements.org_industry)
        .replace("{{GEOGRAPHY}}", ", ".join(elements.org_geographies))
        .replace("{{TRIGGERS}}", ", ".join(elements.active_triggers) or "none")
        .replace("{{EXISTING_TAGS}}", ", ".join(profile.threat_actor_tags) or "none")
    )

    logger.info("threat_tag_llm_fallback", industry=elements.org_industry)
    result = call_llm_json("simple", prompt, config=config)

    llm_tags: list[str] = result.get("threat_actor_tags", [])
    llm_groups: list[str] = result.get("notable_groups", [])
    llm_categories: list[str] = result.get("matched_categories", [])

    # Merge: LLM result extends dictionary result
    merged_tags = sorted(set(profile.threat_actor_tags) | set(llm_tags))
    merged_groups = sorted(set(profile.notable_groups) | set(llm_groups))
    merged_categories = sorted(set(profile.matched_categories) | set(llm_categories))

    logger.info("threat_tags_llm_merged", added_tags=llm_tags, categories=llm_categories)

    return ThreatProfile(
        threat_actor_tags=merged_tags,
        notable_groups=merged_groups,
        priority_ttps=profile.priority_ttps,
        active_triggers=profile.active_triggers,
        matched_categories=merged_categories,
    )


def _resolve_category(actor_cats: dict, cat_path: str) -> dict | None:
    """Resolve 'state_sponsored.China' → actor_cats['state_sponsored']['China']."""
    parts = cat_path.split(".")
    node: dict | None = actor_cats
    for part in parts:
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node if isinstance(node, dict) else None
