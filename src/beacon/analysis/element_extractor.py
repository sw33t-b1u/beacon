"""Step 1: Element Extraction — extract business elements from BusinessContext."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import structlog

from beacon.ingest.schema import BusinessContext

# Load trigger detection keywords from schema/trigger_keywords.json.
# Keywords are only used for ai_adoption_exposure and regulated_disclosure_scope —
# every other trigger is detected from BusinessContext structural fields.
# Bilingual (EN + JA) to match input documents written in either language.
_KEYWORDS_PATH = Path(__file__).parents[3] / "schema" / "trigger_keywords.json"
_TRIGGER_KEYWORDS: dict = json.loads(_KEYWORDS_PATH.read_text(encoding="utf-8"))
_AI_ADOPTION_KEYWORDS: frozenset[str] = frozenset(
    kw.lower() for kw in _TRIGGER_KEYWORDS.get("ai_adoption_keywords", [])
)
_DISCLOSURE_REGULATION_KEYWORDS: frozenset[str] = frozenset(
    kw.lower() for kw in _TRIGGER_KEYWORDS.get("disclosure_regulation_keywords", [])
)

# Sectors observed as disproportionately targeted across ENISA Threat Landscape 2025,
# Verizon DBIR 2025, and CrowdStrike Global Threat Report 2025. See docs/triggers.md.
_HIGH_RISK_SECTORS: frozenset[str] = frozenset(
    {
        "finance",
        "healthcare",
        "energy",
        "manufacturing",
        "government",
        "defense",
        "logistics",
        "technology",
    }
)

# ISO 3166-1 alpha-2 codes for the geopolitical exposure trigger (BEACON 0.14.0).
# Sourced from the empirical intersection of active conflict zones and
# state-sponsored cyber activity in the 2025-2026 reporting window:
# CrowdStrike GTR 2025 (China-nexus +150%, key sectors +200-300%);
# Cloudflare 2026 Threat Report (state-sponsored pre-positioning chapter);
# IOCTA 2026 (Russian-speaking cybercrime ecosystems); INTERPOL ASP 2025/2026
# (Taiwan / regional ASP exposure); M-Trends 2026 Regional Breakouts chapter.
# See docs/triggers.md §8 for the per-citation breakdown. This set is a
# judgement-laden constant — extension requires explicit re-review against
# the ref/ corpus.
HIGH_RISK_GEOPOLITICAL_ZONES: frozenset[str] = frozenset(
    {
        "UA",  # Ukraine — active conflict zone, Russia-nexus targeting
        "RU",  # Russia — sanctions exposure, cybercriminal ecosystem nexus
        "IL",  # Israel — active conflict, state-nexus targeting
        "PS",  # Palestinian Territories — active conflict
        "TW",  # Taiwan — China-nexus pre-positioning (Cloudflare 2026)
        "CN",  # China — CCP-nexus state activity hub
        "IR",  # Iran — state-sponsored activity / sanctions exposure
        "KP",  # North Korea — DPRK-nexus state activity
        "SY",  # Syria — conflict zone
        "YE",  # Yemen — conflict zone
    }
)

logger = structlog.get_logger(__name__)


@dataclass
class CrownJewelDetail:
    """Per-CJ structured data for prompt building."""

    id: str
    name: str
    system: str
    business_impact: str
    exposure_risk: str


@dataclass
class CriticalAssetDetail:
    """Per-CriticalAsset structured data for asset mapping and prompt building."""

    id: str
    name: str
    type: str
    function: str
    network_zone: str
    criticality: str
    data_types: list[str]
    managing_vendor: str
    supply_chain_role: str
    exposure_risk: str


@dataclass
class ExtractedElements:
    """Flat list of business elements relevant for threat mapping."""

    org_industry: str
    org_unit_name: str  # department / team name, empty string if company-level
    org_unit_type: str  # "company" | "division" | "department" | "team"
    org_geographies: list[str]
    org_regulatory_context: list[str]  # regulatory frameworks (APPI, ISO27001, GDPR, etc.)
    strategic_sensitivity: list[str]  # sensitivity levels from strategic objectives
    project_data_types: list[str]  # deduplicated data types across projects
    project_cloud_providers: list[str]
    crown_jewel_ids: list[str]
    crown_jewel_systems: list[str]
    crown_jewel_impacts: list[str]  # business_impact values (deduped)
    crown_jewel_details: list[CrownJewelDetail]  # per-CJ structured data
    critical_asset_ids: list[str]
    critical_asset_details: list[CriticalAssetDetail]  # per-CA structured data for mapping
    has_ot_connectivity: bool
    has_stock_listing: bool
    active_vendors: list[str]  # vendors from in_progress projects + critical asset vendors
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
    crown_jewel_details = [
        CrownJewelDetail(
            id=cj.id,
            name=cj.name,
            system=cj.system or "",
            business_impact=cj.business_impact,
            exposure_risk=cj.exposure_risk,
        )
        for cj in ctx.crown_jewels
    ]

    # Critical assets — surface vendors and supply-chain roles into active_vendors
    critical_asset_ids = [ca.id for ca in ctx.critical_assets]
    critical_asset_details = [
        CriticalAssetDetail(
            id=ca.id,
            name=ca.name,
            type=ca.type,
            function=ca.function,
            network_zone=ca.network_zone,
            criticality=ca.criticality,
            data_types=list(ca.data_types),
            managing_vendor=ca.managing_vendor,
            supply_chain_role=ca.supply_chain_role,
            exposure_risk=ca.exposure_risk,
        )
        for ca in ctx.critical_assets
    ]
    for ca in ctx.critical_assets:
        if ca.managing_vendor and ca.managing_vendor not in active_vendors:
            active_vendors.append(ca.managing_vendor)

    active_triggers = _detect_triggers(ctx, project_cloud_providers)

    source_ids = (
        [obj.id for obj in ctx.strategic_objectives]
        + [p.id for p in ctx.projects]
        + crown_jewel_ids
        + critical_asset_ids
    )

    logger.info(
        "elements_extracted",
        industry=ctx.organization.industry,
        unit_name=ctx.organization.unit_name,
        unit_type=ctx.organization.unit_type,
        triggers=active_triggers,
        crown_jewels=len(crown_jewel_ids),
        critical_assets=len(critical_asset_ids),
    )

    return ExtractedElements(
        org_industry=ctx.organization.industry,
        org_unit_name=ctx.organization.unit_name,
        org_unit_type=ctx.organization.unit_type,
        org_geographies=list(ctx.organization.geography),
        org_regulatory_context=list(ctx.organization.regulatory_context),
        strategic_sensitivity=_dedup([o.sensitivity for o in ctx.strategic_objectives]),
        project_data_types=project_data_types,
        project_cloud_providers=project_cloud_providers,
        crown_jewel_ids=crown_jewel_ids,
        crown_jewel_systems=crown_jewel_systems,
        crown_jewel_impacts=crown_jewel_impacts,
        crown_jewel_details=crown_jewel_details,
        critical_asset_ids=critical_asset_ids,
        critical_asset_details=critical_asset_details,
        has_ot_connectivity=ctx.supply_chain.ot_connectivity
        or any(ca.network_zone == "ot" for ca in ctx.critical_assets),
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
    """Detect active business triggers from BusinessContext structural fields.

    Each trigger is derived from a recognised external framework (NIST SP
    800-37 R2 event-driven trigger concept) and corroborated by past-12-month
    incident-response evidence. See ``BEACON/docs/triggers.md`` for the
    per-trigger citation table.

    Triggers are reported as a flat list of stable string identifiers; weights
    are applied uniformly downstream (see ``risk_scorer.py``). Detection
    favours structural Pydantic fields over keyword matching wherever
    possible — keyword fallback is restricted to ``ai_adoption_exposure``
    and ``regulated_disclosure_scope``.
    """
    triggers: list[str] = []

    # 1. cloud_dependency — public cloud presence (migrating, operating, or
    #    structurally dependent). NIST SP 800-37 R2 environment change;
    #    CrowdStrike GTR 2025 +26% cloud intrusions; M-Trends 2026 IAM theme.
    if (
        cloud_providers
        or any(p.cloud_providers for p in ctx.projects)
        or any(ca.network_zone == "cloud" for ca in ctx.critical_assets)
    ):
        triggers.append("cloud_dependency")

    # 2. it_ot_convergence — IT/OT integration point. NIST SP 800-82 R3 §1.2;
    #    ENISA ETL 2025 (OT 18.2% of threat categories); IEC 62443.
    if ctx.supply_chain.ot_connectivity or any(
        ca.network_zone == "ot" for ca in ctx.critical_assets
    ):
        triggers.append("it_ot_convergence")

    # 3. third_party_dependency — structural reliance on outside vendors.
    #    NIST SP 800-161 R1; Verizon DBIR 2025 third-party 30%; IBM CoDB 2025
    #    (9-month detection time for third-party breaches); EO 14028.
    if ctx.supply_chain.critical_vendors or any(ca.managing_vendor for ca in ctx.critical_assets):
        triggers.append("third_party_dependency")

    # 4. external_facing_exposure — internet-reachable critical assets.
    #    M-Trends 2026 (#1 initial-access vector at 32%, sixth year running);
    #    Verizon DBIR 2025 (edge exploitation 8x); CISA KEV catalog.
    if any(ca.network_zone in {"internet", "dmz"} for ca in ctx.critical_assets) or any(
        cj.exposure_risk in {"high", "critical"} for cj in ctx.crown_jewels
    ):
        triggers.append("external_facing_exposure")

    # 5. regulated_disclosure_scope — subject to material cyber disclosure
    #    obligations. SEC Final Rule 33-11216 Item 106 (US public companies);
    #    EU NIS2 Directive Art. 23; HIPAA Breach Notification Rule.
    if ctx.organization.stock_listed or _matches_any_keyword(
        ctx.organization.regulatory_context, _DISCLOSURE_REGULATION_KEYWORDS
    ):
        triggers.append("regulated_disclosure_scope")

    # 6. sectoral_high_risk — industry empirically targeted disproportionately.
    #    ENISA Threat Landscape 2025 sectoral analysis; Verizon DBIR 2025;
    #    CrowdStrike GTR 2025; ENISA Sectoral TLs.
    if ctx.organization.industry in _HIGH_RISK_SECTORS:
        triggers.append("sectoral_high_risk")

    # 7. ai_adoption_exposure — AI/ML adoption signal in objectives, projects,
    #    or data types. IBM CoDB 2025 ($670K shadow-AI cost premium, 63%
    #    lacked governance); CrowdStrike GTR 2025 (AI-driven vishing +442%);
    #    ENISA ETL 2025 (>80% of social engineering AI-supported).
    if _detect_ai_adoption(ctx):
        triggers.append("ai_adoption_exposure")

    # 8. geopolitical_exposure — operates in / supplies / sells into a
    #    high-risk geopolitical zone. CrowdStrike GTR 2025 (China-nexus
    #    +150%); Cloudflare 2026 (state-sponsored pre-positioning); IOCTA
    #    2026 (Russian-speaking ecosystems); INTERPOL ASP 2025/2026;
    #    M-Trends 2026 Regional Breakouts. See docs/triggers.md §8.
    if _detect_geopolitical_exposure(ctx):
        triggers.append("geopolitical_exposure")

    # 9. ransomware_resilience_gap — backup / IR / recovery-test posture is
    #    absent or incomplete. ENISA ETL 2025 (ransomware 83.9% of
    #    cybercrime); M-Trends 2026 ("Ransomware is Now a Resilience
    #    Problem"); IBM CoDB 2025 ($5.08M ransomware breach cost); Dragos
    #    2026 (119 ransomware groups, 3,300+ industrial victims).
    #    See docs/triggers.md §9. Absent block = conservative gap=True.
    if _detect_ransomware_resilience_gap(ctx):
        triggers.append("ransomware_resilience_gap")

    # 10. identity_credential_exposure — MFA / PIM-PAM / helpdesk-auth
    #     maturity gap. CrowdStrike GTR 2025 (valid account abuse 35%,
    #     vishing +442%); M-Trends 2026 (vishing 23% cloud initial access);
    #     IOCTA 2026 (IAB ecosystem); APWG Q4 2025 (BEC).
    #     See docs/triggers.md §10. Absent block = conservative gap=True.
    if _detect_identity_credential_exposure(ctx):
        triggers.append("identity_credential_exposure")

    return _dedup(triggers)


def _matches_any_keyword(values: list[str], keywords: frozenset[str]) -> bool:
    for v in values:
        text = v.lower()
        if any(kw in text for kw in keywords):
            return True
    return False


def _detect_ai_adoption(ctx: BusinessContext) -> bool:
    haystacks: list[str] = []
    for obj in ctx.strategic_objectives:
        haystacks.append(obj.title)
        haystacks.append(obj.description)
        haystacks.extend(obj.key_decisions)
    for proj in ctx.projects:
        haystacks.append(proj.name)
        haystacks.extend(proj.data_types)
    return _matches_any_keyword(haystacks, _AI_ADOPTION_KEYWORDS)


def _detect_geopolitical_exposure(ctx: BusinessContext) -> bool:
    """Fire when any declared geographic touch-point intersects
    HIGH_RISK_GEOPOLITICAL_ZONES. Returns False when the optional block
    is absent (no information = no signal; conservative for this trigger
    because false positives based on absence are not actionable).
    """
    geo = ctx.geopolitical_exposure
    if geo is None:
        return False
    all_regions: set[str] = set()
    if geo.headquartered_country:
        all_regions.add(geo.headquartered_country)
    all_regions.update(c for c in geo.operational_countries if c)
    all_regions.update(c for c in geo.primary_customer_regions if c)
    all_regions.update(c for c in geo.supply_chain_origin_regions if c)
    return bool(all_regions & HIGH_RISK_GEOPOLITICAL_ZONES)


def _detect_ransomware_resilience_gap(ctx: BusinessContext) -> bool:
    """Fire when the org cannot demonstrate ransomware recovery readiness.
    Absent block = gap (conservative — undocumented posture is treated
    as elevated risk per M-Trends 2026 ``Ransomware is Now a Resilience
    Problem``). Threshold: recovery test cadence within the last 180 days.
    """
    bc = ctx.business_continuity
    if bc is None:
        return True
    cadence = bc.recovery_test_cadence_days
    cadence_ok = cadence is not None and 0 < cadence <= 180
    return not (
        bc.backup_strategy_documented
        and bc.backup_offsite_or_immutable
        and bc.incident_response_plan_documented
        and cadence_ok
    )


def _detect_identity_credential_exposure(ctx: BusinessContext) -> bool:
    """Fire when MFA coverage <95% OR PIM/PAM absent OR helpdesk
    authentication undocumented. Absent block = gap (conservative —
    undocumented IAM posture is the empirical baseline for credential
    abuse / vishing / IAB-driven initial access per CrowdStrike GTR 2025).
    """
    im = ctx.identity_management
    if im is None:
        return True
    mfa = im.mfa_coverage_percent
    mfa_gap = mfa is None or mfa < 95
    return mfa_gap or not im.pim_or_pam_deployed or not im.helpdesk_authentication_documented
