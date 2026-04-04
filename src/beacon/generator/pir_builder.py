"""Step 5: PIR Generation — build SAGE-compatible PIR JSON."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Literal

import structlog
from pydantic import BaseModel, Field

from beacon.analysis.asset_mapper import get_criticality_multipliers
from beacon.analysis.element_extractor import ExtractedElements
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
    description: str
    rationale: str
    threat_actor_tags: list[str]
    asset_weight_rules: list[dict]
    collection_focus: list[str]
    valid_from: str  # ISO date string
    valid_until: str  # ISO date string
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
    """Build PIR output list from pipeline results.

    Only P1 (composite ≥ 20) and P2 (composite ≥ 12) are output as SAGE PIR JSON.
    P3/P4 are tracked only in report/collection_plan (Phase 3).

    When use_llm=True, description/rationale/collection_focus are augmented
    by Vertex AI (gemini-2.5-flash) using the dictionary results as context.
    """
    today = generated_on or date.today()

    if risk.composite < 12:
        logger.info("pir_skipped_low_score", composite=risk.composite)
        return []

    pir_id = f"{pir_id_prefix}-{today.year}-001"
    level = risk.intelligence_level
    valid_until = today + timedelta(days=_VALIDITY_DAYS[level])
    weight_rules = get_criticality_multipliers(asset_tags, asset_tags_dict)

    # Build dictionary-based drafts first
    description = _build_description(elements, threat)
    collection_focus = _build_collection_focus(threat, elements)
    rationale = risk.rationale

    # LLM augmentation: improve text fields using dictionary results as context
    if use_llm:
        description, rationale, collection_focus = _llm_augment_text(
            elements, threat, risk, description, rationale, collection_focus, config
        )

    pir = PIROutput(
        pir_id=pir_id,
        intelligence_level=level,
        description=description,
        rationale=rationale,
        threat_actor_tags=threat.threat_actor_tags,
        asset_weight_rules=weight_rules,
        collection_focus=collection_focus,
        valid_from=today.isoformat(),
        valid_until=valid_until.isoformat(),
        risk_score=RiskScoreModel(
            likelihood=risk.likelihood,
            impact=risk.impact,
            composite=risk.composite,
        ),
        source_elements=elements.source_element_ids,
    )

    logger.info(
        "pir_built",
        pir_id=pir_id,
        level=level,
        composite=risk.composite,
        valid_until=valid_until.isoformat(),
    )

    return [pir]


def _build_description(elements: ExtractedElements, threat: ThreatProfile) -> str:
    cj_count = len(elements.crown_jewel_ids)
    industry = elements.org_industry
    geos = ", ".join(elements.org_geographies[:2]) if elements.org_geographies else "global"

    if cj_count > 0:
        systems = (
            ", ".join(elements.crown_jewel_systems[:2]) if elements.crown_jewel_systems else ""
        )
        system_part = f"（{systems}）" if systems else ""
        return (
            f"{industry}×{geos} 環境のクラウンジュエル{system_part}を狙う脅威アクターへの耐性強化"
        )

    tags_summary = (
        ", ".join(threat.threat_actor_tags[:3]) if threat.threat_actor_tags else "unknown"
    )
    return f"{industry}×{geos} における脅威（{tags_summary}）の監視"


def _build_collection_focus(threat: ThreatProfile, elements: ExtractedElements) -> list[str]:
    focus: list[str] = []

    if threat.notable_groups:
        groups = " / ".join(threat.notable_groups[:3])
        focus.append(f"{groups} の新規TTP・インフラ変化の観測")

    if "ip-theft" in threat.threat_actor_tags or "espionage" in threat.threat_actor_tags:
        focus.append("スピアフィッシング・サプライチェーン経由の侵入試行")

    if "ransomware" in threat.threat_actor_tags:
        focus.append("ランサムウェアグループによる業種標的型キャンペーン")

    if elements.has_ot_connectivity:
        focus.append("OT/ICS環境を標的とする脆弱性悪用情報")

    if elements.project_cloud_providers:
        providers = ", ".join(elements.project_cloud_providers[:2])
        focus.append(f"{providers} 環境を狙ったクラウド設定ミス・侵害事例")

    if not focus:
        focus.append("業種関連の脅威インテリジェンスの継続収集")

    return focus


def _llm_augment_text(
    elements: ExtractedElements,
    threat: ThreatProfile,
    risk: RiskScore,
    draft_description: str,
    draft_rationale: str,
    draft_collection_focus: list[str],
    config=None,
) -> tuple[str, str, list[str]]:
    """Augment PIR text fields using Vertex AI (gemini-2.5-flash).

    The dictionary-based drafts are passed as context so the LLM improves
    rather than invents content.
    """
    import json as _json  # noqa: PLC0415

    from beacon.llm.client import call_llm_json, load_prompt  # noqa: PLC0415

    crown_jewels_text = (
        "\n".join(
            f"- {cj_id}: system={sys_}"
            for cj_id, sys_ in zip(elements.crown_jewel_ids, elements.crown_jewel_systems or [""])
        )
        or "none"
    )

    template = load_prompt("pir_generation.md")
    prompt = (
        template.replace("{{INDUSTRY}}", elements.org_industry)
        .replace("{{GEOGRAPHY}}", ", ".join(elements.org_geographies))
        .replace("{{REGULATORY}}", ", ".join(getattr(elements, "regulatory_context", [])))
        .replace("{{CROWN_JEWELS}}", crown_jewels_text)
        .replace("{{MATCHED_CATEGORIES}}", ", ".join(threat.matched_categories) or "none")
        .replace("{{NOTABLE_GROUPS}}", ", ".join(threat.notable_groups[:6]) or "none")
        .replace("{{THREAT_TAGS}}", ", ".join(threat.threat_actor_tags[:8]) or "none")
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
    )

    logger.info("pir_text_llm_augment")
    result = call_llm_json("medium", prompt, config=config)

    description = result.get("description") or draft_description
    rationale = result.get("rationale") or draft_rationale
    collection_focus = result.get("collection_focus") or draft_collection_focus

    if not isinstance(collection_focus, list):
        collection_focus = draft_collection_focus

    logger.info("pir_text_augmented")
    return description, rationale, collection_focus
