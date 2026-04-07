"""Step 4: Risk Scoring — compute Likelihood × Impact composite score."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import structlog

from beacon.analysis.element_extractor import ExtractedElements
from beacon.analysis.threat_mapper import ThreatProfile

logger = structlog.get_logger(__name__)

IntelligenceLevel = Literal["strategic", "operational", "tactical"]

_IMPACT_WEIGHTS = {
    "critical": 5,
    "high": 4,
    "medium": 3,
    "low": 2,
}

_LIKELIHOOD_BASE = {
    # matched_category count → base likelihood
    0: 1,
    1: 2,
    2: 3,
    3: 4,
}


@dataclass
class RiskScore:
    likelihood: int  # 1–5
    impact: int  # 1–5
    composite: int  # likelihood × impact (max 25)
    intelligence_level: IntelligenceLevel
    rationale: str


def score(
    elements: ExtractedElements,
    threat: ThreatProfile,
    *,
    use_llm: bool = False,
    config=None,
    use_sage: bool = False,
    sage_client=None,
) -> RiskScore:
    """Compute risk score from extracted elements and threat profile.

    Likelihood is derived from the number of matched threat categories
    and presence of active business triggers.
    Impact is derived from the highest crown jewel business_impact.

    When use_llm=True and matched_categories is empty (dictionary had no basis),
    calls Vertex AI (gemini-2.5-pro) to assist with likelihood reasoning.

    When use_sage=True and sage_client is provided, observation count from SAGE
    is fetched and likelihood is boosted by +1 (capped at 5) if count >= 1.
    """
    likelihood = _compute_likelihood(elements, threat)
    impact = _compute_impact(elements)

    # LLM scoring assist: only when dictionary provided no matched categories
    if use_llm and not threat.matched_categories:
        likelihood = _llm_assist_likelihood(elements, threat, likelihood, config)

    # SAGE observation boost
    sage_observation_count = 0
    if use_sage and sage_client is not None:
        sage_observation_count = sage_client.get_actor_observation_count(threat.threat_actor_tags)
        if sage_observation_count >= 1:
            likelihood = min(likelihood + 1, 5)

    composite = likelihood * impact
    level = _recommend_level(composite, threat.active_triggers)
    rationale = _build_rationale(elements, threat, likelihood, impact, sage_observation_count)

    logger.info(
        "risk_scored",
        likelihood=likelihood,
        impact=impact,
        composite=composite,
        level=level,
    )

    return RiskScore(
        likelihood=likelihood,
        impact=impact,
        composite=composite,
        intelligence_level=level,
        rationale=rationale,
    )


def _compute_likelihood(elements: ExtractedElements, threat: ThreatProfile) -> int:
    n_categories = len(threat.matched_categories)
    base = _LIKELIHOOD_BASE.get(min(n_categories, 3), 4)

    # Boost for active business triggers
    high_risk_triggers = {"ot_connectivity", "m_and_a", "ipo_or_listing"}
    trigger_boost = 1 if any(t in high_risk_triggers for t in threat.active_triggers) else 0

    return min(base + trigger_boost, 5)


def _compute_impact(elements: ExtractedElements) -> int:
    if not elements.crown_jewel_impacts:
        return 2  # default: low-medium

    max_impact = max(_IMPACT_WEIGHTS.get(imp, 2) for imp in elements.crown_jewel_impacts)
    return max_impact


def _recommend_level(composite: int, active_triggers: list[str]) -> IntelligenceLevel:
    """Recommend intelligence level based on composite score and triggers.

    composite 20–25 → strategic
    composite 12–19 → operational
    composite  1–11 → tactical

    Business triggers can escalate to operational or higher.
    """
    trigger_escalation = {"m_and_a", "ot_connectivity", "ipo_or_listing"}

    if composite >= 20:
        return "strategic"
    if composite >= 12:
        return "operational"
    # Below 12 but high-risk trigger → escalate to operational
    if any(t in trigger_escalation for t in active_triggers):
        return "operational"
    return "tactical"


def _build_rationale(
    elements: ExtractedElements,
    threat: ThreatProfile,
    likelihood: int,
    impact: int,
    sage_observation_count: int = 0,
) -> str:
    parts = []

    if threat.matched_categories:
        cats = ", ".join(threat.matched_categories)
        parts.append(f"Industry/geography match: {cats}")

    if elements.has_ot_connectivity:
        parts.append("OT connectivity — lateral movement risk")

    if elements.crown_jewel_ids:
        max_impact = max(
            (elements.crown_jewel_impacts or ["low"]),
            key=lambda x: _IMPACT_WEIGHTS.get(x, 2),
        )
        parts.append(f"Crown jewels: {len(elements.crown_jewel_ids)} (max impact: {max_impact})")

    if threat.notable_groups:
        groups = ", ".join(threat.notable_groups[:4])
        parts.append(f"Matched groups: {groups}")

    if threat.active_triggers:
        parts.append(f"Business triggers: {', '.join(threat.active_triggers)}")

    if sage_observation_count >= 1:
        parts.append(f"SAGE observations: {sage_observation_count}")

    base = f"Likelihood={likelihood}, Impact={impact}"
    if parts:
        return base + " — " + " / ".join(parts)
    return base


def _llm_assist_likelihood(
    elements: ExtractedElements,
    threat: ThreatProfile,
    current_likelihood: int,
    config=None,
) -> int:
    """Call Vertex AI (gemini-2.5-pro) to reason about likelihood when dictionary has no basis.

    Returns a likelihood score (1–5). Falls back to current_likelihood on any error.
    """
    from beacon.llm.client import call_llm_json  # noqa: PLC0415

    _impact_map = {"low": 1, "medium": 2, "high": 3, "critical": 4}
    max_cj_impact = max(
        elements.crown_jewel_impacts or ["low"], key=lambda x: _impact_map.get(x, 1)
    )
    prompt = (
        "You are a threat intelligence analyst. Estimate the likelihood score (1-5) that "
        "the following organization would be targeted by a significant cyberattack.\n\n"
        "Likelihood scale:\n"
        "5 = APT matching industry+geography has attacked similar orgs in past 12 months\n"
        "4 = Active generic threat (ransomware) targeting this industry\n"
        "3 = Industry OR geography match only\n"
        "2 = Indirect exposure (supply chain)\n"
        "1 = Weak evidence\n\n"
        "Organization:\n"
        f"- Industry: {elements.org_industry}\n"
        f"- Geography: {', '.join(elements.org_geographies)}\n"
        f"- Business triggers: {', '.join(threat.active_triggers) or 'none'}\n"
        f"- Crown jewels: {len(elements.crown_jewel_ids)} asset(s), "
        f"max impact: {max_cj_impact}\n"
        f"- Threat tags from partial dictionary match: "
        f"{', '.join(threat.threat_actor_tags) or 'none'}\n\n"
        'Return ONLY JSON: {"likelihood": <int 1-5>, "reasoning": "<brief explanation>"}'
    )

    logger.info("likelihood_llm_assist", industry=elements.org_industry)
    try:
        result = call_llm_json("complex", prompt, config=config)
        llm_score = int(result.get("likelihood", current_likelihood))
        llm_score = max(1, min(5, llm_score))
        logger.info("likelihood_llm_result", score=llm_score, reasoning=result.get("reasoning"))
        return llm_score
    except Exception as exc:  # noqa: BLE001
        logger.warning("likelihood_llm_failed", error=str(exc))
        return current_likelihood
