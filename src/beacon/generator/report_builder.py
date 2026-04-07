"""Phase 3: Collection Plan — generate collection_plan.md for P3/P4 priority items.

Produces a Markdown document listing threat watch items and trigger-based collection
actions for areas that did not meet the P1/P2 PIR threshold (composite < 12), or
as supplemental monitoring guidance alongside generated PIRs.

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
from beacon.analysis.threat_mapper import ThreatProfile
from beacon.generator.pir_builder import PIROutput

logger = structlog.get_logger(__name__)

# Load Japanese display strings from schema/content_ja.json
_CONTENT_PATH = Path(__file__).parents[3] / "schema" / "content_ja.json"
_CONTENT: dict = json.loads(_CONTENT_PATH.read_text(encoding="utf-8"))

# Recommended collection sources per threat category
_SOURCE_MAP: dict[str, list[str]] = _CONTENT["source_map"]
_DEFAULT_SOURCES: list[str] = _CONTENT["default_sources"]

# Trigger-specific collection actions
_TRIGGER_ACTIONS: dict[str, str] = _CONTENT["trigger_actions"]

# Suggested collection frequencies
_LEVEL_FREQUENCY: dict[str, str] = _CONTENT["level_frequency"]

# Collection frequency table labels
_TABLE: dict[str, str] = _CONTENT["table"]


def build_collection_plan(
    elements: ExtractedElements,
    threat: ThreatProfile,
    risk: RiskScore,
    pirs: list[PIROutput] | None = None,
    generated_on: date | None = None,
) -> str:
    """Build a Markdown collection plan document.

    Args:
        elements: Extracted business elements.
        threat: Resolved threat profile.
        risk: Computed risk score.
        pirs: PIRs already generated (P1/P2). Used to label covered categories.
        generated_on: Report date (defaults to today).

    Returns:
        Markdown string for collection_plan.md.
    """
    today = generated_on or date.today()
    pirs = pirs or []

    lines: list[str] = []
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

    # Monitoring status
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

    # Active business triggers
    if threat.active_triggers:
        lines.append("**Active Business Triggers:**")
        for t in threat.active_triggers:
            lines.append(f"- `{t}`")
        lines.append("")

    lines.append("---")
    lines.append("")

    # Threat watch items
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
            # Any category that contributed to a generated PIR is "covered"
            pir_covered_categories = set(threat.matched_categories)

        for cat in threat.matched_categories:
            covered = cat in pir_covered_categories and bool(pirs)
            label = " **[PIR COVERED]**" if covered else " **[WATCH]**"
            lines.append(f"### {cat}{label}")
            lines.append("")

            sources = _SOURCE_MAP.get(cat, _DEFAULT_SOURCES)
            # Threat tags for this category
            lines.append("**Recommended collection sources:**")
            for src in sources:
                lines.append(f"- {src}")
            lines.append("")
    else:
        lines.append("No specific threat categories matched the dictionary for this profile.")
        lines.append("")
        lines.append("**General watch — Recommended sources:**")
        for src in _DEFAULT_SOURCES:
            lines.append(f"- {src}")
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

    # Trigger-based collection
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

    # Collection frequency
    lines.append("## Recommended Collection Frequency")
    lines.append("")
    lines.append("| Item | Frequency | Owner |")
    lines.append("|------|-----------|-------|")

    # Determine frequency based on intelligence level
    freq = _LEVEL_FREQUENCY.get(risk.intelligence_level, _LEVEL_FREQUENCY["default"])
    lines.append(f"| {_TABLE['feed_collection_item']} | {freq} | {_TABLE['cti_team']} |")

    if "ot_connectivity" in threat.active_triggers:
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
