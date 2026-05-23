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
_DERIVED_PATH = _SCHEMA_DIR / "source_attack_groups.derived.json"

# Supplement: display names absent from ATT&CK source_name index → known Group IDs.
# Covers groups added to ATT&CK after the current derived snapshot, vendor-specific
# aliases, and Chinese-pinyin names not captured in English index entries.
_GROUP_ID_SUPPLEMENT: dict[str, list[str]] = {
    "MirrorFace": ["G1054"],
    "APT5": ["G1023"],
    "Volt Typhoon": ["G1017"],
    "Salt Typhoon": ["G1045"],
    "HAFNIUM": ["G0125"],
    "Indrik Spider": ["G0119"],
    "TA505": ["G0092"],
    "Wizard Spider": ["G0102"],
    "Star Blizzard": ["G1033"],
    "Aoqin Dragon": ["G1007"],
    "BlackTech": ["G0098"],
    "Contagious Interview": ["G1052"],
    "Daggerfly": ["G1034"],
    "Ember Bear": ["G1003"],
    "FIN13": ["G1016"],
    "VOID MANTICORE": ["G1055"],
    "APT42": ["G1044"],
    "APT-C-23": ["G1028"],
    "APT-C-36": ["G0099"],
    "ZIRCONIUM": ["G0128"],
    "Winter Vivern": ["G1035"],
    "Agrius": ["G1030"],
    "Ajax Security Team": ["G0130"],
    "Cinnamon Tempest": ["G1041"],
    "Earth Lusca": ["G1006"],
    "Ferocious Kitten": ["G0100"],
    "Fox Kitten": ["G0117"],
    "Gelsemium": ["G0115"],
    "HEXANE": ["G1001"],
    "Higaisa": ["G0126"],
    "Mofang": ["G0103"],
    "Moses Staff": ["G1009"],
    "Silent Librarian": ["G0122"],
    "UNC3886": ["G1027"],
}


def load_sources(content_ja_path: Path | None = None) -> list[dict[str, Any]]:
    """Return the sources list from content_ja.json."""
    path = content_ja_path or _CONTENT_JA_PATH
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("sources", [])


def resolve_group_ids(
    names: list[str],
    derived_path: Path | None = None,
) -> list[str]:
    """Resolve threat-actor display names to ATT&CK Group IDs.

    Checks the supplement dict first (aliases not present in ATT&CK source_name
    index), then falls back to source_attack_groups.derived.json for direct
    source_name matches. Returns a deduplicated list preserving discovery order.

    Args:
        names: Threat-actor display names (e.g. ["MirrorFace", "APT41"]).
        derived_path: Override path for source_attack_groups.derived.json.

    Returns:
        List of unique ATT&CK Group IDs (e.g. ["G1054", "G0096"]).
    """
    path = derived_path or _DERIVED_PATH
    try:
        derived: dict[str, dict] = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        derived = {}

    seen: set[str] = set()
    result: list[str] = []

    def _add(gids: list[str]) -> None:
        for gid in gids:
            if gid not in seen:
                seen.add(gid)
                result.append(gid)

    for name in names:
        if name in _GROUP_ID_SUPPLEMENT:
            _add(_GROUP_ID_SUPPLEMENT[name])
        elif name in derived:
            _add(derived[name].get("actor_groups", []))

    return result


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
