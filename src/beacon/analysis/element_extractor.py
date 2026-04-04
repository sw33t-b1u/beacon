"""Step 1: Element Extraction — extract business elements from BusinessContext."""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from beacon.ingest.schema import BusinessContext

logger = structlog.get_logger(__name__)


@dataclass
class ExtractedElements:
    """Flat list of business elements relevant for threat mapping."""

    org_industry: str
    org_geographies: list[str]
    strategic_sensitivity: list[str]  # sensitivity levels from strategic objectives
    project_data_types: list[str]  # deduplicated data types across projects
    project_cloud_providers: list[str]
    crown_jewel_ids: list[str]
    crown_jewel_systems: list[str]
    crown_jewel_impacts: list[str]  # business_impact values
    has_ot_connectivity: bool
    has_stock_listing: bool
    active_vendors: list[str]  # vendors from in_progress projects
    active_triggers: list[str]  # detected business triggers
    source_element_ids: list[str]  # IDs of all contributing elements


def extract(ctx: BusinessContext) -> ExtractedElements:
    """Extract flat business elements from a BusinessContext."""
    project_data_types: list[str] = []
    project_cloud_providers: list[str] = []
    active_vendors: list[str] = []

    for proj in ctx.projects:
        if proj.status in {"in_progress", "planned"}:
            project_data_types.extend(proj.data_types)
            project_cloud_providers.extend(proj.cloud_providers)
            active_vendors.extend(proj.involved_vendors)

    # Deduplicate while preserving order
    project_data_types = _dedup(project_data_types)
    project_cloud_providers = _dedup(project_cloud_providers)
    active_vendors = _dedup(active_vendors)

    # Also collect from supply_chain
    if ctx.supply_chain.cloud_providers:
        for cp in ctx.supply_chain.cloud_providers:
            if cp not in project_cloud_providers:
                project_cloud_providers.append(cp)

    crown_jewel_ids = [cj.id for cj in ctx.crown_jewels]
    crown_jewel_systems = _dedup([cj.system for cj in ctx.crown_jewels if cj.system])
    crown_jewel_impacts = _dedup([cj.business_impact for cj in ctx.crown_jewels])

    active_triggers = _detect_triggers(ctx, project_cloud_providers)

    source_ids = (
        [obj.id for obj in ctx.strategic_objectives]
        + [p.id for p in ctx.projects]
        + crown_jewel_ids
    )

    logger.info(
        "elements_extracted",
        industry=ctx.organization.industry,
        triggers=active_triggers,
        crown_jewels=len(crown_jewel_ids),
    )

    return ExtractedElements(
        org_industry=ctx.organization.industry,
        org_geographies=list(ctx.organization.geography),
        strategic_sensitivity=_dedup([o.sensitivity for o in ctx.strategic_objectives]),
        project_data_types=project_data_types,
        project_cloud_providers=project_cloud_providers,
        crown_jewel_ids=crown_jewel_ids,
        crown_jewel_systems=crown_jewel_systems,
        crown_jewel_impacts=crown_jewel_impacts,
        has_ot_connectivity=ctx.supply_chain.ot_connectivity,
        has_stock_listing=ctx.organization.stock_listed,
        active_vendors=active_vendors,
        active_triggers=active_triggers,
        source_element_ids=source_ids,
    )


def _dedup(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _detect_triggers(ctx: BusinessContext, cloud_providers: list[str]) -> list[str]:
    """Infer active business triggers from context fields."""
    triggers: list[str] = []

    # OT connectivity
    if ctx.supply_chain.ot_connectivity:
        triggers.append("ot_connectivity")

    # Cloud migration: any in-progress project using cloud providers
    in_progress_cloud = any(p.cloud_providers and p.status == "in_progress" for p in ctx.projects)
    if in_progress_cloud or cloud_providers:
        triggers.append("cloud_migration")

    # M&A signal: key_decisions mention M&A / due diligence keywords
    ma_keywords = {"m&a", "merger", "acquisition", "due diligence", "デューデリジェンス", "m&a候補"}
    for obj in ctx.strategic_objectives:
        text = " ".join(obj.key_decisions).lower() + " " + obj.description.lower()
        if any(kw in text for kw in ma_keywords):
            triggers.append("m_and_a")
            break

    # IPO signal: stock_listed + any high/critical objective sensitivity
    if ctx.organization.stock_listed:
        triggers.append("ipo_or_listing")

    # Supply chain expansion: critical vendors + active expansion objectives
    if ctx.supply_chain.critical_vendors:
        expansion_keywords = {"expand", "拡大", "新規", "new", "partner", "パートナー"}
        for obj in ctx.strategic_objectives:
            text = obj.description.lower() + " " + obj.title.lower()
            if any(kw in text for kw in expansion_keywords):
                triggers.append("supply_chain_expansion")
                break

    return _dedup(triggers)
