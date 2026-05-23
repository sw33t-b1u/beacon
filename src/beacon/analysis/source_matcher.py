"""PIR → source candidate matching for BEACON collection plan generation.

Implements the tier / region / industry_focus / evidence_attack_groups
intersection logic defined in Initiative F Phase 1.7.

Matching criteria (all must hold):
  1. source.tier in intelligence_levels
  2. org_region in source.region  OR  "GLOBAL" in source.region
  3. org_industry in source.industry_focus  OR  "cross-sector" in source.industry_focus
  4. source.evidence_attack_groups ∩ attack_groups ≠ ∅
     OR  source.evidence_derivation == "industry_consensus"
     OR  attack_groups is empty  (cross-actor IR — no group filter applied)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_SCHEMA_DIR = Path(__file__).parents[3] / "schema"
_CONTENT_JA_PATH = _SCHEMA_DIR / "content_ja.json"


def load_sources(content_ja_path: Path | None = None) -> list[dict[str, Any]]:
    """Return the sources list from content_ja.json."""
    path = content_ja_path or _CONTENT_JA_PATH
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("sources", [])


def select_sources(
    *,
    intelligence_levels: list[str],
    org_region: str,
    org_industry: str,
    attack_groups: list[str],
    sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Select candidate sources matching the given PIR requirements.

    Args:
        intelligence_levels: Acceptable tier values (e.g. ["strategic"] or
            ["strategic", "operational"]).
        org_region: ISO 3166-1 alpha-2 code for the organisation (e.g. "JP").
        org_industry: Industry vertical string (e.g. "finance", "OT").
        attack_groups: ATT&CK Group IDs from the PIR (e.g. ["G0096", "G1054"]).
            Empty list disables the group-intersection filter.
        sources: Source entries from content_ja.json (each a dict with tier,
            region, industry_focus, evidence_attack_groups, evidence_derivation).

    Returns:
        Filtered list of source dicts in original order.
    """
    tier_set = set(intelligence_levels)
    attack_set = set(attack_groups)

    results: list[dict[str, Any]] = []
    for src in sources:
        if not _matches_tier(src, tier_set):
            continue
        if not _matches_region(src, org_region):
            continue
        if not _matches_industry(src, org_industry):
            continue
        if not _matches_groups(src, attack_set):
            continue
        results.append(src)
    return results


def _matches_tier(src: dict[str, Any], tier_set: set[str]) -> bool:
    return src.get("tier") in tier_set


def _matches_region(src: dict[str, Any], org_region: str) -> bool:
    regions = set(src.get("region", []))
    return org_region in regions or "GLOBAL" in regions


def _matches_industry(src: dict[str, Any], org_industry: str) -> bool:
    industries = set(src.get("industry_focus", []))
    return org_industry in industries or "cross-sector" in industries


def _matches_groups(src: dict[str, Any], attack_set: set[str]) -> bool:
    if not attack_set:
        return True
    if src.get("evidence_derivation") == "industry_consensus":
        return True
    evidence = set(src.get("evidence_attack_groups", []))
    return bool(evidence & attack_set)
