"""Step 4b: PIR Clustering — split the aggregated ThreatProfile into narrow
per-decision-point clusters.

Each cluster becomes one PIR. This matches CTI methodology (FIRST CTI-SIG, SANS
/ Red Hat / Intel471): a PIR is one focused decision point, not a kitchen-sink
aggregate. See references in README.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from beacon.analysis.element_extractor import ExtractedElements
from beacon.analysis.threat_mapper import ThreatProfile

logger = structlog.get_logger(__name__)


# Threat-family → canonical tags that belong to it. A tag may appear in at most
# one family; if a family has any overlap with the profile tags it is active.
# Keys intentionally mirror the first segment of `matched_categories` paths
# (e.g. "state_sponsored.China" → family "state_sponsored").
_FAMILY_TAGS: dict[str, set[str]] = {
    "financial_crime": {"financial-crime"},
    "state_sponsored": {
        "apt-china",
        "apt-russia",
        "apt-north-korea",
        "apt-iran",
        "apt-india",
        "apt-south-korea",
        "apt-vietnam",
        "apt-pakistan",
        "apt-belarus",
        "apt-israel",
        "apt-palestine",
        "apt-lebanon",
        "apt-spain",
        "apt-france",
        "apt-united-states",
        "apt-united-kingdom",
        "apt-united-arab-emirates",
        "apt-turkey",
        "apt-ukraine",
        "apt-tunisia",
        "apt-syria",
    },
    "espionage": {"espionage"},
    "sabotage": {"sabotage"},
    "subversion": {"subversion"},
    "cybercriminal": {  # fallback bucket — only used if nothing else matched
        "cybercriminal",
    },
}

# Asset tags each family cares about. Used to scope asset_weight_rules per PIR.
_FAMILY_ASSET_TAGS: dict[str, set[str]] = {
    "financial_crime": {"financial", "identity", "database", "payment"},
    "state_sponsored": {"identity", "source_code", "pki", "database", "plm", "erp"},
    "espionage": {"identity", "source_code", "database", "plm"},
    "sabotage": {"ot", "external-facing"},
    "subversion": {"external-facing", "web", "identity"},
    "cybercriminal": set(),  # unscoped fallback
}

# Human-readable short labels for the decision point.
_FAMILY_LABELS: dict[str, str] = {
    "financial_crime": "Financial fraud and cybercrime against in-scope services",
    "state_sponsored": "State-sponsored actor activity targeting this unit",
    "espionage": "Generic espionage-motivated intrusion",
    "sabotage": "Destructive / sabotage-motivated intrusion",
    "subversion": "Influence operation / subversion activity",
    "cybercriminal": "General cybercriminal threat to this unit",
}

# Upper bound on PIRs per run. "Less is more" (FIRST CTI-SIG guidance).
_MAX_CLUSTERS = 5


@dataclass
class PIRCluster:
    """One narrow decision point that will become one PIR."""

    cluster_id: str
    threat_family: str
    decision_point: str
    threat_actor_tags: list[str]
    notable_groups: list[str]
    asset_tag_focus: list[str]
    source_element_ids: list[str] = field(default_factory=list)


def build_clusters(
    elements: ExtractedElements,
    threat: ThreatProfile,
    asset_tag_list: list[str],
) -> list[PIRCluster]:
    """Split a ThreatProfile into up to ~5 narrow clusters, one per
    (threat family × asset focus) pair.

    Returns at least one cluster unless the profile is empty. When no family
    matches, emits a single fallback cluster using the full profile so
    downstream behavior degrades gracefully (matches legacy single-PIR output).
    """
    profile_tags = set(threat.threat_actor_tags)
    profile_groups = set(threat.notable_groups)
    asset_tags = set(asset_tag_list)

    # Extract which families are "declared" in matched_categories (strong signal).
    declared_families: set[str] = set()
    for cat_path in threat.matched_categories:
        family = cat_path.split(".", 1)[0]
        if family in _FAMILY_TAGS:
            declared_families.add(family)

    clusters: list[PIRCluster] = []
    used_tags: set[str] = set()

    # Iterate families in stable order (declared first, then dict order).
    family_order = [f for f in _FAMILY_TAGS if f in declared_families] + [
        f for f in _FAMILY_TAGS if f not in declared_families
    ]

    for family in family_order:
        if family == "cybercriminal":
            continue  # reserved for the fallback path below
        family_tag_set = _FAMILY_TAGS[family]
        matched_tags = profile_tags & family_tag_set
        if not matched_tags and family not in declared_families:
            continue

        scoped_asset_tags = sorted(asset_tags & _FAMILY_ASSET_TAGS[family])
        scoped_tags = sorted(matched_tags)

        # Skip if the family produces an empty scope (no actor tags AND no
        # asset anchor); nothing to say.
        if not scoped_tags and not scoped_asset_tags:
            continue

        clusters.append(
            PIRCluster(
                cluster_id=f"{family}",
                threat_family=family,
                decision_point=_FAMILY_LABELS[family],
                threat_actor_tags=scoped_tags,
                notable_groups=_scope_notable_groups(profile_groups, family),
                asset_tag_focus=scoped_asset_tags,
                source_element_ids=list(elements.source_element_ids),
            )
        )
        used_tags.update(matched_tags)

        if len(clusters) >= _MAX_CLUSTERS:
            break

    # Fallback: if no family matched, emit one cluster covering everything so
    # the run still produces a PIR (legacy-compatible behavior).
    if not clusters:
        clusters.append(
            PIRCluster(
                cluster_id="general",
                threat_family="cybercriminal",
                decision_point=_FAMILY_LABELS["cybercriminal"],
                threat_actor_tags=sorted(profile_tags),
                notable_groups=sorted(profile_groups),
                asset_tag_focus=sorted(asset_tags),
                source_element_ids=list(elements.source_element_ids),
            )
        )

    logger.info(
        "pir_clusters_built",
        count=len(clusters),
        families=[c.threat_family for c in clusters],
    )
    return clusters


def _scope_notable_groups(all_groups: set[str], family: str) -> list[str]:
    """Best-effort filter of notable groups to those typically associated with
    the family. Dictionary-free heuristic: cheap substring check against a
    family keyword list. Unknown groups fall through so we never drop data.
    """
    keywords = _FAMILY_GROUP_KEYWORDS.get(family, set())
    if not keywords:
        return sorted(all_groups)
    kept = [g for g in all_groups if any(k.lower() in g.lower() for k in keywords)]
    # If filtering leaves nothing, keep the full list — better than empty.
    return sorted(kept) if kept else sorted(all_groups)


# Lightweight keyword hints per family for `_scope_notable_groups`. Not
# authoritative — intentionally biased toward recall.
_FAMILY_GROUP_KEYWORDS: dict[str, set[str]] = {
    "financial_crime": {"fin", "carbanak", "anunak", "evil corp"},
    "state_sponsored": {
        "apt",
        "lazarus",
        "kimsuky",
        "sandworm",
        "turla",
        "mirrorface",
        "earth",
        "typhoon",
        "blizzard",
    },
    "espionage": {"apt", "earth", "mirrorface", "turla"},
    "sabotage": {"sandworm", "xenotime", "shamoon"},
    "subversion": {"killnet", "noname", "anonymous"},
}
