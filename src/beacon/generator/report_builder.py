"""Collection Plan — generate collection_plan.md covering all P1-P4 entries.

Produces a Markdown document with:
  - Priority Intelligence Requirements (P1/P2): generated PIRs with badge,
    intelligence level, collection_focus bullets, and a placeholder
    recommended-sources section (wired in Phase 2).
  - Threat Watch Items (P3/P4): threat categories below the PIR threshold,
    each with a priority badge, intelligence level, collection focus, and
    the same placeholder recommended-sources line.
  - Trigger-Based Collection Actions and a collection frequency table.

Japanese display strings are loaded from schema/content_ja.json to keep source code
language-neutral (Rule 11).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import structlog

from beacon.analysis.element_extractor import ExtractedElements
from beacon.analysis.risk_scorer import RiskScore
from beacon.analysis.source_matcher import geo_to_iso as _geo_to_iso_fn
from beacon.analysis.source_matcher import load_sources, resolve_group_ids, select_sources
from beacon.analysis.source_matcher import pir_source_tiers as _pir_source_tiers_fn
from beacon.analysis.threat_mapper import ThreatProfile
from beacon.generator.pir_builder import PIROutput

logger = structlog.get_logger(__name__)

# Load Japanese display strings from schema/content_ja.json
_CONTENT_PATH = Path(__file__).parents[3] / "schema" / "content_ja.json"
_CONTENT: dict = json.loads(_CONTENT_PATH.read_text(encoding="utf-8"))

# Trigger-specific collection actions
_TRIGGER_ACTIONS: dict[str, str] = _CONTENT["trigger_actions"]

# Suggested collection frequencies
_LEVEL_FREQUENCY: dict[str, str] = _CONTENT["level_frequency"]

# Collection frequency table labels
_TABLE: dict[str, str] = _CONTENT["table"]

# Source candidates loaded once at module import; filtered per-PIR by select_sources().
_SOURCES: list[dict] = load_sources(_CONTENT_PATH)


def _priority_badge(composite: int) -> str:
    """Map a composite risk score to a PIR priority badge P1–P4.

    P1 ≥ 20 (strategic), P2 ≥ 12 (operational),
    P3 ≥ 6 (watch — elevated), P4 < 6 (watch — low).
    """
    if composite >= 20:
        return "P1"
    if composite >= 12:
        return "P2"
    if composite >= 6:
        return "P3"
    return "P4"


def _geo_to_iso(geographies: list[str]) -> str:
    """Return the ISO 3166-1 alpha-2 code for the first recognised geography."""
    return _geo_to_iso_fn(geographies)


def _pir_source_tiers(intelligence_level: str) -> list[str]:
    """Return the source tiers to query for a given PIR intelligence level."""
    return _pir_source_tiers_fn(intelligence_level)


def _format_source_line(src: dict, matched_groups: list[str]) -> str:
    """Format one source entry as a Markdown list item with rationale."""
    name = src["name"]
    tier = src["tier"]
    regions = ", ".join(src.get("region", []))
    industries = ", ".join(src.get("industry_focus", []))
    if src.get("evidence_derivation") == "industry_consensus":
        rationale = f"{industries} sector coverage"
    elif matched_groups:
        groups_str = ", ".join(matched_groups[:4])
        rationale = f"matches {groups_str} via MITRE ATT&CK external_references"
    else:
        rationale = "general coverage"
    return f"- {name} [{tier}, {regions}, {industries}] — {rationale}"


def build_collection_plan(
    elements: ExtractedElements,
    threat: ThreatProfile,
    risk: RiskScore,
    pirs: list[PIROutput] | None = None,
    generated_on: date | None = None,
) -> str:
    """Build a Markdown collection plan document covering all P1-P4 entries.

    Args:
        elements: Extracted business elements.
        threat: Resolved threat profile.
        risk: Computed risk score.
        pirs: PIRs already generated (P1/P2). Each is rendered with its
            priority badge, intelligence level, collection_focus bullets,
            and a placeholder recommended-sources line.
        generated_on: Report date (defaults to today).

    Returns:
        Markdown string for collection_plan.md.
    """
    today = generated_on or date.today()
    pirs = pirs or []

    lines: list[str] = []

    # ── Header ────────────────────────────────────────────────────────────────
    lines.append("# Collection Plan")
    lines.append("")
    lines.append(f"Generated: {today.isoformat()}")
    geos = ", ".join(elements.org_geographies) if elements.org_geographies else "global"
    lines.append(f"Organization: {elements.org_industry} | {geos}")
    lines.append(
        f"Risk Score: Likelihood={risk.likelihood}, Impact={risk.impact}, "
        f"Composite={risk.composite}"
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── Monitoring Status ──────────────────────────────────────────────────────
    lines.append("## Monitoring Status")
    lines.append("")
    if pirs:
        lines.append(
            f"{len(pirs)} PIR(s) generated (P1/P2 threshold met). "
            "This plan covers supplemental collection activities."
        )
    else:
        lines.append(
            f"Composite score {risk.composite} is below PIR threshold (12). "
            "All threat areas are tracked as watch-list items in this plan."
        )
    lines.append("")

    if threat.active_triggers:
        lines.append("**Active Business Triggers:**")
        for t in threat.active_triggers:
            lines.append(f"- `{t}`")
        lines.append("")

    lines.append("---")
    lines.append("")

    # ── Priority Intelligence Requirements (P1/P2 generated PIRs) ─────────────
    if pirs:
        lines.append("## Priority Intelligence Requirements")
        lines.append("")
        lines.append(f"{len(pirs)} PIR(s) generated — active collection required.")
        lines.append("")
        org_region = _geo_to_iso(elements.org_geographies)
        org_industry = elements.org_industry
        for pir in pirs:
            badge = _priority_badge(pir.risk_score.composite)
            lines.append(f"### [{badge}] {pir.pir_id}")
            lines.append("")
            lines.append(f"**Intelligence Level:** {pir.intelligence_level}")
            lines.append(f"**Decision Point:** {pir.decision_point}")
            lines.append(f"**Valid:** {pir.valid_from} → {pir.valid_until}")
            lines.append("")
            if pir.collection_focus:
                lines.append("**Collection Focus:**")
                for item in pir.collection_focus:
                    lines.append(f"- {item}")
                lines.append("")
            pir_sources = select_sources(
                intelligence_levels=_pir_source_tiers(pir.intelligence_level),
                org_region=org_region,
                org_industry=org_industry,
                attack_groups=pir.mitre_attack_groups,
                sources=_SOURCES,
            )
            pir_group_set = set(pir.mitre_attack_groups)
            lines.append("**Recommended Sources:**")
            if pir_sources:
                for src in pir_sources:
                    evidence = src.get("evidence_attack_groups", [])
                    matched = [g for g in evidence if g in pir_group_set]
                    lines.append(_format_source_line(src, matched))
            else:
                lines.append("_(no matching sources for this PIR)_")
            lines.append("")
        lines.append("---")
        lines.append("")

    # ── Threat Watch Items (P3/P4) ─────────────────────────────────────────────
    lines.append("## Threat Watch Items")
    lines.append("")
    if pirs:
        lines.append(
            "> Items below are threat categories identified by the BEACON pipeline. "
            "Categories already covered by a generated PIR are labelled **[PIR COVERED]**."
        )
    else:
        lines.append(
            "> Items below are threat categories identified by the BEACON pipeline. "
            "All items are tracked as watch-list entries."
        )
    lines.append("")

    if threat.matched_categories:
        pir_covered_categories: set[str] = set()
        if pirs:
            pir_covered_categories = set(threat.matched_categories)

        watch_org_region = _geo_to_iso(elements.org_geographies)
        watch_org_industry = elements.org_industry
        watch_groups = resolve_group_ids(threat.notable_groups)
        for cat in threat.matched_categories:
            covered = cat in pir_covered_categories and bool(pirs)
            if covered:
                lines.append(f"### {cat} **[PIR COVERED]**")
                lines.append("")
                lines.append(
                    "_Collection focus documented in Priority Intelligence Requirements above._"
                )
                lines.append("")
            else:
                watch_badge = _priority_badge(risk.composite)
                lines.append(f"### {cat} [{watch_badge}] **[WATCH]**")
                lines.append("")
                lines.append(f"**Intelligence Level:** {risk.intelligence_level}")
                lines.append("")
                watch_sources = select_sources(
                    intelligence_levels=[risk.intelligence_level],
                    org_region=watch_org_region,
                    org_industry=watch_org_industry,
                    attack_groups=watch_groups,
                    sources=_SOURCES,
                )
                watch_group_set = set(watch_groups)
                lines.append("**Recommended Sources:**")
                if watch_sources:
                    for src in watch_sources:
                        evidence = src.get("evidence_attack_groups", [])
                        matched = [g for g in evidence if g in watch_group_set]
                        lines.append(_format_source_line(src, matched))
                else:
                    lines.append(
                        "_(no matching sources for this tier/region/industry combination)_"
                    )
                lines.append("")
    else:
        lines.append("No specific threat categories matched the dictionary for this profile.")
        lines.append("")
        watch_badge = _priority_badge(risk.composite)
        general_org_region = _geo_to_iso(elements.org_geographies)
        general_groups = resolve_group_ids(threat.notable_groups)
        general_sources = select_sources(
            intelligence_levels=[risk.intelligence_level],
            org_region=general_org_region,
            org_industry=elements.org_industry,
            attack_groups=general_groups,
            sources=_SOURCES,
        )
        general_group_set = set(general_groups)
        lines.append(f"**General watch [{watch_badge}] — Recommended Sources:**")
        if general_sources:
            for src in general_sources:
                evidence = src.get("evidence_attack_groups", [])
                matched = [g for g in evidence if g in general_group_set]
                lines.append(_format_source_line(src, matched))
        else:
            lines.append("_(no matching sources for this tier/region/industry combination)_")
        lines.append("")

    # Notable groups
    if threat.notable_groups:
        lines.append("**Notable Groups to Monitor:**")
        lines.append("")
        groups_str = ", ".join(threat.notable_groups)
        lines.append(f"{groups_str}")
        lines.append("")

    lines.append("---")
    lines.append("")

    # ── Trigger-Based Collection ───────────────────────────────────────────────
    if threat.active_triggers:
        lines.append("## Trigger-Based Collection Actions")
        lines.append("")
        lines.append(
            "Business triggers detected in context. "
            "These require targeted collection beyond standard threat monitoring."
        )
        lines.append("")
        for trigger in threat.active_triggers:
            action = _TRIGGER_ACTIONS.get(trigger)
            if action:
                lines.append(f"### {trigger}")
                lines.append("")
                lines.append(f"- {action}")
                lines.append("")
        lines.append("---")
        lines.append("")

    # ── Collection Frequency ──────────────────────────────────────────────────
    lines.append("## Recommended Collection Frequency")
    lines.append("")
    lines.append("| Item | Frequency | Owner |")
    lines.append("|------|-----------|-------|")

    freq = _LEVEL_FREQUENCY.get(risk.intelligence_level, _LEVEL_FREQUENCY["default"])
    lines.append(f"| {_TABLE['feed_collection_item']} | {freq} | {_TABLE['cti_team']} |")

    if "it_ot_convergence" in threat.active_triggers:
        lines.append(f"| {_TABLE['ot_vuln_item']} | {_TABLE['weekly']} | {_TABLE['ot_team']} |")
    if "ransomware" in threat.threat_actor_tags:
        lines.append(
            f"| {_TABLE['ransomware_watch_item']} | {_TABLE['weekly']} | {_TABLE['cti_team']} |"
        )
    if threat.notable_groups:
        groups_summary = ", ".join(threat.notable_groups[:3])
        lines.append(
            f"| {_TABLE['apt_ttp_watch_prefix']} ({groups_summary})"
            f" | {_TABLE['monthly']} | {_TABLE['cti_team']} |"
        )

    lines.append(
        f"| {_TABLE['pir_review_item']} | {_TABLE['quarterly']} | {_TABLE['ciso_office']} |"
    )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "_This document was auto-generated by BEACON. "
        "Review with your CTI team before acting on collection priorities._"
    )

    logger.info(
        "collection_plan_built",
        categories=len(threat.matched_categories),
        triggers=len(threat.active_triggers),
        pir_count=len(pirs),
    )

    return "\n".join(lines)


def write_collection_plan(plan: str, path: Path) -> None:
    """Write collection plan Markdown to a file."""
    path.write_text(plan, encoding="utf-8")
    logger.info("collection_plan_written", path=str(path))
