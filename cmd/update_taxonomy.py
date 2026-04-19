"""CLI: Regenerate threat_taxonomy.json from MITRE ATT&CK + MISP Galaxy.

The taxonomy is fully machine-generated from two trusted upstream sources:

- MITRE ATT&CK Enterprise STIX bundle (intrusion-sets, attack-patterns, and
  `relationship` objects linking groups to techniques)
- MISP Galaxy threat-actor cluster (country attribution, target industries,
  target geographies, incident-type classification)

No manually curated fields are retained; each run overwrites `actor_categories`
and `geography_threat_map` completely. Hand-curated sections (`industry_threat_map`,
`business_trigger_map`, `supply_chain_threat_map`, `subgroups`) are intentionally
absent from the new schema — they were deleted as part of the credibility refactor.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

import httpx
import structlog

logger = structlog.get_logger(__name__)

_MITRE_STIX_URL = (
    "https://raw.githubusercontent.com/mitre/cti/master/enterprise-attack/enterprise-attack.json"
)
_MISP_THREAT_ACTOR_URL = (
    "https://raw.githubusercontent.com/MISP/misp-galaxy/main/clusters/threat-actor.json"
)
_DEFAULT_TAXONOMY = Path(__file__).parent.parent / "schema" / "threat_taxonomy.json"


# ISO 3166-1 alpha-2 → MISP-style country name (subset; only codes seen in MISP
# threat-actor data are needed). Values mirror `cfr-suspected-state-sponsor`
# spellings so state-sponsor lookup and country-code fallback produce the same
# category keys.
_ISO_COUNTRY_NAME: dict[str, str] = {
    "CN": "China",
    "RU": "Russia",
    "KP": "North Korea",
    "IR": "Iran",
    "IN": "India",
    "KR": "South Korea",
    "US": "United States",
    "GB": "United Kingdom",
    "UA": "Ukraine",
    "IL": "Israel",
    "PK": "Pakistan",
    "TR": "Turkey",
    "VN": "Vietnam",
    "AE": "United Arab Emirates",
    "SY": "Syria",
    "TN": "Tunisia",
    "LB": "Lebanon",
}


# MISP `cfr-type-of-incident` → BEACON non-state category key. Values not
# listed cause the entry to be skipped when no state sponsor is available.
_INCIDENT_TO_CATEGORY: dict[str, str] = {
    "espionage": "espionage",
    "theft": "espionage",
    "intellectual property theft": "espionage",
    "financial crime": "financial_crime",
    "financial theft": "financial_crime",
    "ransomware": "financial_crime",
    "cybercrime": "financial_crime",
    "denial of service": "sabotage",
    "defacement": "sabotage",
    "destructive attack": "sabotage",
    "sabotage": "sabotage",
    "wiper attack": "sabotage",
    "subversion": "subversion",
    "influence operation": "subversion",
    "disinformation": "subversion",
    "hack and leak": "subversion",
}


_NON_STATE_CATEGORY_KEYS = ("espionage", "financial_crime", "sabotage", "subversion")


# MISP `cfr-suspected-state-sponsor` uses multiple spellings for the same
# country. Normalize aliases to a single canonical form so state_sponsored
# buckets do not fragment across variants (e.g. "Russia" vs "Russian
# Federation"). Values not listed pass through unchanged.
_CANONICAL_STATE_NAME: dict[str, str] = {
    "Iran (Islamic Republic of)": "Iran",
    "Korea (Democratic People's Republic of)": "North Korea",
    "Korea, Democratic People's Republic of": "North Korea",
    "Korea (Republic of)": "South Korea",
    "Korea, Republic of": "South Korea",
    "Russian Federation": "Russia",
    "People's Republic of China": "China",
    "China, People's Republic of": "China",
    "Viet Nam": "Vietnam",
    "Syrian Arab Republic": "Syria",
    "US": "United States",
    "USA": "United States",
    "U.S.": "United States",
    "U.S.A.": "United States",
    "UK": "United Kingdom",
}


# State sponsor tokens that carry no useful attribution and should cause the
# entry to be skipped from state_sponsored aggregation.
_NON_ATTRIBUTION_SPONSORS = frozenset({"unknown", "none", "n/a", ""})


# --- Fetchers ---------------------------------------------------------------


def _load_json_source(source: str, label: str) -> dict:
    """Load JSON from an HTTP(S) URL or a local file path."""
    if source.startswith(("http://", "https://")):
        try:
            resp = httpx.get(source, timeout=60, follow_redirects=True)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Failed to fetch {label}: {exc}") from exc

    path = Path(source)
    if not path.exists():
        raise RuntimeError(f"Failed to read {label}: file not found: {source}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Failed to parse {label}: {exc}") from exc


def fetch_stix_bundle(url: str) -> dict:
    """Fetch MITRE ATT&CK STIX bundle from URL or local path."""
    return _load_json_source(url, "STIX bundle")


def fetch_misp_threat_actors(url: str) -> dict:
    """Fetch MISP Galaxy threat-actor cluster from URL or local path."""
    return _load_json_source(url, "MISP threat-actor cluster")


# --- MITRE extraction -------------------------------------------------------


def extract_groups(bundle: dict) -> dict[str, list[str]]:
    """Extract intrusion-set objects → {canonical_name: [all_names_including_aliases]}."""
    groups: dict[str, list[str]] = {}
    for obj in bundle.get("objects", []):
        if obj.get("type") != "intrusion-set":
            continue
        name = obj.get("name", "")
        if not name:
            continue
        aliases = obj.get("aliases", [])
        all_names = list({name} | set(aliases))
        groups[name] = all_names
    return groups


def extract_techniques(bundle: dict) -> list[str]:
    """Extract attack-pattern objects → sorted list of technique IDs (T-numbers)."""
    technique_ids: set[str] = set()
    for obj in bundle.get("objects", []):
        if obj.get("type") != "attack-pattern":
            continue
        for ref in obj.get("external_references", []):
            if ref.get("source_name") == "mitre-attack":
                ext_id = ref.get("external_id", "")
                if ext_id.startswith("T"):
                    technique_ids.add(ext_id)
    return sorted(technique_ids)


def extract_group_ttps(bundle: dict) -> dict[str, list[str]]:
    """Build {group_canonical_name: [ttp_ids]} from STIX `relationship` objects.

    Walks the bundle once to build:
      - intrusion-set id → canonical name
      - attack-pattern id → technique ID (T-number)
      - relationship (type=uses) from intrusion-set → attack-pattern
    """
    intrusion_set_name: dict[str, str] = {}
    attack_pattern_ttp: dict[str, str] = {}

    for obj in bundle.get("objects", []):
        otype = obj.get("type")
        if otype == "intrusion-set":
            obj_id = obj.get("id", "")
            name = obj.get("name", "")
            if obj_id and name:
                intrusion_set_name[obj_id] = name
        elif otype == "attack-pattern":
            obj_id = obj.get("id", "")
            for ref in obj.get("external_references", []):
                if ref.get("source_name") == "mitre-attack":
                    ext_id = ref.get("external_id", "")
                    if ext_id.startswith("T") and obj_id:
                        attack_pattern_ttp[obj_id] = ext_id
                        break

    result: dict[str, set[str]] = {}
    for obj in bundle.get("objects", []):
        if obj.get("type") != "relationship":
            continue
        if obj.get("relationship_type") != "uses":
            continue
        src = obj.get("source_ref", "")
        tgt = obj.get("target_ref", "")
        group_name = intrusion_set_name.get(src)
        ttp_id = attack_pattern_ttp.get(tgt)
        if group_name and ttp_id:
            result.setdefault(group_name, set()).add(ttp_id)

    return {name: sorted(ttps) for name, ttps in result.items()}


# --- MISP normalization -----------------------------------------------------


def _normalize_country(code: str | None) -> str | None:
    """ISO 2-letter → canonical country name used for state_sponsored keys."""
    if not code:
        return None
    return _ISO_COUNTRY_NAME.get(code.upper())


def _classify_non_state(incident: str | list | None) -> str | None:
    """MISP cfr-type-of-incident → non-state category key ('espionage' etc.).

    Accepts either a string or a list of strings (MISP emits both forms).
    Returns the first incident type that maps to a known category.
    """
    if not incident:
        return None
    values = incident if isinstance(incident, list) else [incident]
    for v in values:
        if not isinstance(v, str):
            continue
        mapped = _INCIDENT_TO_CATEGORY.get(v.strip().lower())
        if mapped:
            return mapped
    return None


def _build_alias_to_mitre_canonical(mitre_groups: dict[str, list[str]]) -> dict[str, str]:
    """Lowercase alias/name → MITRE canonical group name."""
    out: dict[str, str] = {}
    for canonical, names in mitre_groups.items():
        for n in names:
            out[n.strip().lower()] = canonical
    return out


def _misp_entry_names(entry: dict) -> list[str]:
    value = entry.get("value", "")
    synonyms = entry.get("meta", {}).get("synonyms", []) or []
    names = [value] + list(synonyms)
    return [n for n in names if n]


def _resolve_mitre_canonical(entry: dict, alias_to_canonical: dict[str, str]) -> str | None:
    """Return the MITRE canonical name if this MISP entry matches a MITRE group."""
    for name in _misp_entry_names(entry):
        canonical = alias_to_canonical.get(name.strip().lower())
        if canonical:
            return canonical
    return None


def _first_str(value: str | list | None) -> str:
    """Return the first non-empty string from a str or list[str], else ''."""
    if not value:
        return ""
    if isinstance(value, list):
        for v in value:
            if isinstance(v, str) and v.strip():
                return v.strip()
        return ""
    if isinstance(value, str):
        return value.strip()
    return ""


def _canonicalize_state(sponsor: str) -> str | None:
    """Normalize country spellings; return None for non-attribution tokens."""
    if sponsor.lower() in _NON_ATTRIBUTION_SPONSORS:
        return None
    return _CANONICAL_STATE_NAME.get(sponsor, sponsor)


def _classify_misp_entry(entry: dict) -> tuple[str, str] | None:
    """Return ('state_sponsored', <country>) or ('<non_state_key>', '') or None."""
    meta = entry.get("meta", {}) or {}
    state_sponsor = _first_str(meta.get("cfr-suspected-state-sponsor"))
    if state_sponsor:
        canonical = _canonicalize_state(state_sponsor)
        if canonical:
            return ("state_sponsored", canonical)
        # Fall through: "Unknown" / "None" sponsors are classified by incident
        # type instead of being dropped entirely.

    country_name = _normalize_country(meta.get("country"))
    if country_name and country_name in {
        "China",
        "Russia",
        "North Korea",
        "Iran",
        "India",
    }:
        # MISP actors with an attacker country code but no explicit sponsor tag
        # are treated as state-sponsored from that country.
        return ("state_sponsored", country_name)

    non_state = _classify_non_state(meta.get("cfr-type-of-incident"))
    if non_state:
        return (non_state, "")

    return None


# --- Taxonomy builder -------------------------------------------------------


def _new_state_entry(country: str) -> dict:
    apt_tag = f"apt-{country.lower().replace(' ', '-')}"
    return {
        "tags": {apt_tag},
        "mitre_groups": set(),
        "priority_ttps": set(),
        "target_industries": set(),
        "target_geographies": set(),
    }


def _new_non_state_entry(category_key: str) -> dict:
    return {
        "tags": {category_key.replace("_", "-")},
        "mitre_groups": set(),
        "priority_ttps": set(),
        "target_industries": set(),
        "target_geographies": set(),
    }


def _freeze_entry(entry: dict) -> dict:
    return {
        "tags": sorted(entry["tags"]),
        "mitre_groups": sorted(entry["mitre_groups"]),
        "priority_ttps": sorted(entry["priority_ttps"]),
        "target_industries": sorted(entry["target_industries"]),
        "target_geographies": sorted(entry["target_geographies"]),
    }


def build_actor_categories(
    mitre_groups: dict[str, list[str]],
    mitre_group_ttps: dict[str, list[str]],
    misp_data: dict,
) -> dict:
    """Build actor_categories by classifying each MISP entry and aggregating.

    Only MISP entries that match a MITRE intrusion-set name or alias contribute
    their TTPs (via MITRE relationships). Entries without a MITRE match still
    contribute tags / industries / geographies but with empty priority_ttps.
    """
    alias_to_canonical = _build_alias_to_mitre_canonical(mitre_groups)

    state_entries: dict[str, dict] = {}
    non_state_entries: dict[str, dict] = {}

    for entry in misp_data.get("values", []):
        classification = _classify_misp_entry(entry)
        if not classification:
            continue
        cat_key, cat_sub = classification

        meta = entry.get("meta", {}) or {}
        target_industries = meta.get("cfr-target-category", []) or []
        target_geographies = meta.get("cfr-suspected-victims", []) or []
        mitre_canonical = _resolve_mitre_canonical(entry, alias_to_canonical)

        if cat_key == "state_sponsored":
            bucket = state_entries.setdefault(cat_sub, _new_state_entry(cat_sub))
        else:
            bucket = non_state_entries.setdefault(cat_key, _new_non_state_entry(cat_key))

        bucket["target_industries"].update(target_industries)
        bucket["target_geographies"].update(target_geographies)
        if mitre_canonical:
            bucket["mitre_groups"].add(mitre_canonical)
            bucket["priority_ttps"].update(mitre_group_ttps.get(mitre_canonical, []))

    out: dict = {}
    if state_entries:
        out["state_sponsored"] = {
            country: _freeze_entry(entry) for country, entry in sorted(state_entries.items())
        }
    for key in _NON_STATE_CATEGORY_KEYS:
        if key in non_state_entries:
            out[key] = _freeze_entry(non_state_entries[key])
    return out


def build_geography_threat_map(
    mitre_groups: dict[str, list[str]],
    misp_data: dict,
) -> dict:
    """Aggregate {geography: {notable_groups, apt_tags}} from MISP victim data."""
    alias_to_canonical = _build_alias_to_mitre_canonical(mitre_groups)

    per_geo: dict[str, dict[str, set[str]]] = {}

    for entry in misp_data.get("values", []):
        meta = entry.get("meta", {}) or {}
        victims = meta.get("cfr-suspected-victims", []) or []
        if not victims:
            continue

        mitre_canonical = _resolve_mitre_canonical(entry, alias_to_canonical)
        classification = _classify_misp_entry(entry)

        apt_tag: str | None = None
        if classification and classification[0] == "state_sponsored":
            apt_tag = f"apt-{classification[1].lower().replace(' ', '-')}"

        for geo in victims:
            bucket = per_geo.setdefault(geo, {"notable_groups": set(), "apt_tags": set()})
            if mitre_canonical:
                bucket["notable_groups"].add(mitre_canonical)
            if apt_tag:
                bucket["apt_tags"].add(apt_tag)

    return {
        geo: {
            "notable_groups": sorted(bucket["notable_groups"]),
            "apt_tags": sorted(bucket["apt_tags"]),
        }
        for geo, bucket in sorted(per_geo.items())
    }


def build_taxonomy(
    mitre_bundle: dict,
    misp_data: dict,
    *,
    now_iso: str,
    mitre_url: str = _MITRE_STIX_URL,
    misp_url: str = _MISP_THREAT_ACTOR_URL,
) -> dict:
    """Produce a complete threat_taxonomy.json dict from upstream sources."""
    mitre_groups = extract_groups(mitre_bundle)
    mitre_group_ttps = extract_group_ttps(mitre_bundle)

    return {
        "_metadata": {
            "sources": {
                "mitre_attack": mitre_url,
                "misp_galaxy_threat_actor": misp_url,
            },
            "last_auto_sync": now_iso,
            "generator": "cmd/update_taxonomy.py",
        },
        "actor_categories": build_actor_categories(mitre_groups, mitre_group_ttps, misp_data),
        "geography_threat_map": build_geography_threat_map(mitre_groups, misp_data),
    }


# --- Diff -------------------------------------------------------------------


def diff_taxonomy(original: dict, updated: dict) -> str:
    """Return a human-readable diff summary between two taxonomy dicts."""
    lines: list[str] = []
    orig_cats = original.get("actor_categories", {})
    upd_cats = updated.get("actor_categories", {})

    orig_keys = set(orig_cats.keys())
    upd_keys = set(upd_cats.keys())
    for added in sorted(upd_keys - orig_keys):
        lines.append(f"[actor_categories] added category: {added}")
    for removed in sorted(orig_keys - upd_keys):
        lines.append(f"[actor_categories] removed category: {removed}")

    for cat_key in sorted(upd_keys & orig_keys):
        orig_cat = orig_cats[cat_key]
        upd_cat = upd_cats[cat_key]
        if cat_key == "state_sponsored" and isinstance(upd_cat, dict):
            for nation in sorted(set(orig_cat.keys()) | set(upd_cat.keys())):
                _diff_entry(
                    f"state_sponsored.{nation}",
                    orig_cat.get(nation, {}) if isinstance(orig_cat, dict) else {},
                    upd_cat.get(nation, {}) if isinstance(upd_cat, dict) else {},
                    lines,
                )
        elif isinstance(upd_cat, dict):
            _diff_entry(cat_key, orig_cat if isinstance(orig_cat, dict) else {}, upd_cat, lines)

    orig_geo = original.get("geography_threat_map", {})
    upd_geo = updated.get("geography_threat_map", {})
    added_geos = sorted(set(upd_geo.keys()) - set(orig_geo.keys()))
    removed_geos = sorted(set(orig_geo.keys()) - set(upd_geo.keys()))
    if added_geos:
        lines.append(f"[geography_threat_map] added: {added_geos}")
    if removed_geos:
        lines.append(f"[geography_threat_map] removed: {removed_geos}")

    if not lines:
        return "No changes detected."
    return "\n".join(lines)


def _diff_entry(label: str, orig: dict, upd: dict, lines: list[str]) -> None:
    orig_grps = set(orig.get("mitre_groups", []))
    upd_grps = set(upd.get("mitre_groups", []))
    added_grps = upd_grps - orig_grps
    removed_grps = orig_grps - upd_grps

    orig_ttps = set(orig.get("priority_ttps", []))
    upd_ttps = set(upd.get("priority_ttps", []))
    added_ttps = upd_ttps - orig_ttps
    removed_ttps = orig_ttps - upd_ttps

    if added_grps:
        lines.append(f"[{label}] mitre_groups added: {sorted(added_grps)}")
    if removed_grps:
        lines.append(f"[{label}] mitre_groups removed: {sorted(removed_grps)}")
    if added_ttps:
        lines.append(f"[{label}] priority_ttps added: {sorted(added_ttps)}")
    if removed_ttps:
        lines.append(f"[{label}] priority_ttps removed: {sorted(removed_ttps)}")


# --- CLI --------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Regenerate threat_taxonomy.json from MITRE ATT&CK + MISP Galaxy."
    )
    parser.add_argument(
        "--output",
        default=str(_DEFAULT_TAXONOMY),
        metavar="FILE",
        help="Path to threat_taxonomy.json to write (default: schema/threat_taxonomy.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print diff to stdout without modifying the file.",
    )
    parser.add_argument(
        "--mitre-url",
        default=_MITRE_STIX_URL,
        metavar="URL",
        help="MITRE ATT&CK STIX bundle URL recorded in _metadata.sources",
    )
    parser.add_argument(
        "--misp-url",
        default=_MISP_THREAT_ACTOR_URL,
        metavar="URL",
        help="MISP Galaxy threat-actor cluster URL recorded in _metadata.sources",
    )
    parser.add_argument(
        "--mitre-cache",
        default=None,
        metavar="PATH_OR_URL",
        help="Optional fetch-source override for MITRE bundle (does not affect _metadata.sources)",
    )
    parser.add_argument(
        "--misp-cache",
        default=None,
        metavar="PATH_OR_URL",
        help="Optional fetch-source override for MISP cluster (does not affect _metadata.sources)",
    )
    args = parser.parse_args(argv)

    taxonomy_path = Path(args.output)
    original: dict = {}
    if taxonomy_path.exists():
        try:
            original = json.loads(taxonomy_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"Error: failed to parse existing taxonomy: {exc}", file=sys.stderr)
            return 1
    elif not args.dry_run:
        print(f"Error: taxonomy file not found: {taxonomy_path}", file=sys.stderr)
        return 1

    mitre_fetch_source = args.mitre_cache or args.mitre_url
    misp_fetch_source = args.misp_cache or args.misp_url

    logger.info("fetching_mitre_stix", source=mitre_fetch_source)
    try:
        mitre_bundle = fetch_stix_bundle(mitre_fetch_source)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    logger.info("fetching_misp_threat_actors", source=misp_fetch_source)
    try:
        misp_data = fetch_misp_threat_actors(misp_fetch_source)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    now_iso = _dt.datetime.now(tz=_dt.UTC).replace(microsecond=0).isoformat()
    updated = build_taxonomy(
        mitre_bundle,
        misp_data,
        now_iso=now_iso,
        mitre_url=args.mitre_url,
        misp_url=args.misp_url,
    )

    diff = diff_taxonomy(original, updated)

    if args.dry_run:
        print("--- dry-run: no file written ---")
        print(diff)
        return 0

    taxonomy_path.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Updated: {taxonomy_path}")
    print(diff)
    return 0


if __name__ == "__main__":
    sys.exit(main())
