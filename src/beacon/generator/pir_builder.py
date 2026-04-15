"""Step 5: PIR Generation — build SAGE-compatible PIR JSON.

Emits one PIR per cluster returned by `pir_clusterer.build_clusters`, matching
CTI methodology (one PIR = one focused decision point). See README.md
references.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

import structlog
from pydantic import BaseModel, Field

from beacon.analysis.asset_mapper import get_criticality_multipliers
from beacon.analysis.element_extractor import ExtractedElements
from beacon.analysis.pir_clusterer import PIRCluster, build_clusters
from beacon.analysis.risk_scorer import RiskScore
from beacon.analysis.threat_mapper import ThreatProfile

logger = structlog.get_logger(__name__)

IntelligenceLevel = Literal["strategic", "operational", "tactical"]

_VALIDITY_DAYS: dict[str, int] = {
    "strategic": 365,
    "operational": 180,
    "tactical": 30,
}


class RiskScoreModel(BaseModel):
    likelihood: int
    impact: int
    composite: int


class PIROutput(BaseModel):
    pir_id: str
    intelligence_level: IntelligenceLevel
    organizational_scope: str
    decision_point: str
    description: str
    rationale: str
    recommended_action: str
    threat_actor_tags: list[str]
    notable_groups: list[str] = Field(default_factory=list)
    asset_weight_rules: list[dict]
    collection_focus: list[str]
    valid_from: str
    valid_until: str
    risk_score: RiskScoreModel
    source_elements: list[str] = Field(default_factory=list)


def build_pirs(
    elements: ExtractedElements,
    threat: ThreatProfile,
    risk: RiskScore,
    asset_tags: list[str],
    asset_tags_dict: dict | None = None,
    generated_on: date | None = None,
    pir_id_prefix: str = "PIR",
    *,
    use_llm: bool = False,
    config=None,
) -> list[PIROutput]:
    """Build a list of narrow, per-decision-point PIRs.

    One PIR is emitted per cluster from `pir_clusterer.build_clusters`. Each
    PIR has its own scoped `threat_actor_tags` and `asset_weight_rules`
    (intersection with the cluster's family focus) — never the full profile.

    Only P1 (composite ≥ 20) and P2 (composite ≥ 12) runs emit PIRs; below
    that threshold the run is tracked only in the collection plan.
    """
    today = generated_on or date.today()

    if risk.composite < 12:
        logger.info("pir_skipped_low_score", composite=risk.composite)
        return []

    level = risk.intelligence_level
    valid_until = today + timedelta(days=_VALIDITY_DAYS[level])

    org_scope = (
        f"{elements.org_unit_name} ({elements.org_unit_type})"
        if elements.org_unit_name
        else f"entire company ({elements.org_unit_type})"
    )

    clusters = build_clusters(elements, threat, asset_tags)
    pirs: list[PIROutput] = []

    for idx, cluster in enumerate(clusters, start=1):
        weight_rules = get_criticality_multipliers(cluster.asset_tag_focus, asset_tags_dict)

        draft_description = _build_description(cluster, elements)
        draft_collection_focus = _build_collection_focus(cluster, elements)
        draft_rationale = risk.rationale
        draft_recommended_action = _build_default_action(cluster)

        if use_llm:
            (
                description,
                rationale,
                collection_focus,
                recommended_action,
            ) = _llm_augment_text(
                cluster,
                elements,
                threat,
                risk,
                draft_description,
                draft_rationale,
                draft_collection_focus,
                draft_recommended_action,
                org_scope,
                config,
            )
        else:
            description = draft_description
            rationale = draft_rationale
            collection_focus = draft_collection_focus
            recommended_action = draft_recommended_action

        pir_id = f"{pir_id_prefix}-{today.year}-{idx:03d}"

        pirs.append(
            PIROutput(
                pir_id=pir_id,
                intelligence_level=level,
                organizational_scope=org_scope,
                decision_point=cluster.decision_point,
                description=description,
                rationale=rationale,
                recommended_action=recommended_action,
                threat_actor_tags=cluster.threat_actor_tags,
                notable_groups=cluster.notable_groups,
                asset_weight_rules=weight_rules,
                collection_focus=collection_focus,
                valid_from=today.isoformat(),
                valid_until=valid_until.isoformat(),
                risk_score=RiskScoreModel(
                    likelihood=risk.likelihood,
                    impact=risk.impact,
                    composite=risk.composite,
                ),
                source_elements=cluster.source_element_ids,
            )
        )
        logger.info(
            "pir_built",
            pir_id=pir_id,
            family=cluster.threat_family,
            level=level,
        )

    logger.info("pir_batch_built", count=len(pirs))
    return pirs


def _build_description(cluster: PIRCluster, elements: ExtractedElements) -> str:
    industry = elements.org_industry
    geos = ", ".join(elements.org_geographies[:2]) if elements.org_geographies else "global"
    assets = ", ".join(cluster.asset_tag_focus[:3]) or "in-scope assets"
    tags = ", ".join(cluster.threat_actor_tags[:3]) or cluster.threat_family
    return (
        f"How will {tags} threats against {industry}\u00d7{geos} {assets} "
        f"impact this unit's ability to operate, and what mitigations are required?"
    )


def _build_collection_focus(cluster: PIRCluster, elements: ExtractedElements) -> list[str]:
    focus: list[str] = []
    if cluster.notable_groups:
        groups = " / ".join(cluster.notable_groups[:3])
        focus.append(f"Monitor new TTPs and infrastructure for: {groups}")
    if cluster.asset_tag_focus:
        focus.append(
            "Vulnerability and exploitation reports targeting: "
            + ", ".join(cluster.asset_tag_focus[:4])
        )
    if cluster.threat_family == "supply_chain":
        focus.append("Initial-access-broker listings mentioning this unit's vendors")
    if cluster.threat_family == "cloud" and elements.project_cloud_providers:
        providers = ", ".join(elements.project_cloud_providers[:2])
        focus.append(f"Cloud misconfiguration and compromise cases on: {providers}")
    if cluster.threat_family == "ot_ics" and elements.has_ot_connectivity:
        focus.append("OT/ICS protocol-level advisories and ICS-CERT bulletins")
    if not focus:
        focus.append(f"Continuous collection on {cluster.threat_family} threats for this unit")
    return focus


def _build_default_action(cluster: PIRCluster) -> str:
    assets = ", ".join(cluster.asset_tag_focus[:3]) or "in-scope assets"
    return (
        f"Decide whether current controls on {assets} are sufficient against"
        f" {cluster.threat_family} threats; escalate gaps to the security lead."
    )


def _llm_augment_text(
    cluster: PIRCluster,
    elements: ExtractedElements,
    threat: ThreatProfile,
    risk: RiskScore,
    draft_description: str,
    draft_rationale: str,
    draft_collection_focus: list[str],
    draft_recommended_action: str,
    org_scope: str,
    config=None,
) -> tuple[str, str, list[str], str]:
    """Ask the LLM to sharpen one narrow PIR.

    The cluster scope is passed verbatim — the LLM must not broaden it.
    """
    import json as _json  # noqa: PLC0415

    from beacon.llm.client import call_llm_json, load_prompt  # noqa: PLC0415

    crown_jewels_text = (
        "\n".join(
            f"- {cj.id} ({cj.name}): system={cj.system or 'N/A'}"
            f", impact={cj.business_impact}, exposure={cj.exposure_risk}"
            for cj in elements.crown_jewel_details
        )
        or "none"
    )
    critical_assets_text = (
        "\n".join(
            f"- {ca.id} ({ca.name}): type={ca.type}, zone={ca.network_zone}"
            f", criticality={ca.criticality}"
            + (f", vendor={ca.managing_vendor}" if ca.managing_vendor else "")
            + (f", supply_chain={ca.supply_chain_role}" if ca.supply_chain_role else "")
            for ca in elements.critical_asset_details
        )
        or "none"
    )
    data_types_text = ", ".join(elements.project_data_types) or "none"
    vendors_text = ", ".join(elements.active_vendors[:5]) or "none"

    template = load_prompt("pir_generation.md")
    prompt = (
        template.replace("{{INDUSTRY}}", elements.org_industry)
        .replace("{{ORG_UNIT}}", org_scope)
        .replace("{{GEOGRAPHY}}", ", ".join(elements.org_geographies))
        .replace("{{REGULATORY}}", ", ".join(elements.org_regulatory_context))
        .replace("{{DATA_TYPES}}", data_types_text)
        .replace("{{ACTIVE_VENDORS}}", vendors_text)
        .replace("{{CROWN_JEWELS}}", crown_jewels_text)
        .replace("{{CRITICAL_ASSETS}}", critical_assets_text)
        .replace("{{DECISION_POINT}}", cluster.decision_point)
        .replace("{{CLUSTER_THREAT_FAMILY}}", cluster.threat_family)
        .replace("{{CLUSTER_THREAT_TAGS}}", ", ".join(cluster.threat_actor_tags) or "none")
        .replace("{{CLUSTER_NOTABLE_GROUPS}}", ", ".join(cluster.notable_groups[:6]) or "none")
        .replace("{{CLUSTER_ASSET_TAGS}}", ", ".join(cluster.asset_tag_focus) or "none")
        .replace("{{LIKELIHOOD}}", str(risk.likelihood))
        .replace("{{IMPACT}}", str(risk.impact))
        .replace("{{COMPOSITE}}", str(risk.composite))
        .replace("{{INTELLIGENCE_LEVEL}}", risk.intelligence_level)
        .replace("{{TRIGGERS}}", ", ".join(threat.active_triggers) or "none")
        .replace("{{DRAFT_DESCRIPTION}}", draft_description)
        .replace("{{DRAFT_RATIONALE}}", draft_rationale)
        .replace(
            "{{DRAFT_COLLECTION_FOCUS}}",
            _json.dumps(draft_collection_focus, ensure_ascii=False),
        )
        .replace("{{DRAFT_RECOMMENDED_ACTION}}", draft_recommended_action)
    )

    logger.info("pir_text_llm_augment", family=cluster.threat_family)
    result = call_llm_json("medium", prompt, config=config)

    description = result.get("description") or draft_description
    rationale = result.get("rationale") or draft_rationale
    collection_focus = result.get("collection_focus") or draft_collection_focus
    recommended_action = result.get("recommended_action") or draft_recommended_action

    if not isinstance(collection_focus, list):
        collection_focus = draft_collection_focus

    return description, rationale, collection_focus, recommended_action
