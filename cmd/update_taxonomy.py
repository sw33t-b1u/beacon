"""CLI: Update threat_taxonomy.json from MITRE ATT&CK STIX bundle (GitHub)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx
import structlog

logger = structlog.get_logger(__name__)

_STIX_URL = (
    "https://raw.githubusercontent.com/mitre/cti/master/enterprise-attack/enterprise-attack.json"
)
_DEFAULT_TAXONOMY = Path(__file__).parent.parent / "schema" / "threat_taxonomy.json"


def fetch_stix_bundle(url: str) -> dict:
    """Fetch STIX bundle from URL. Raises RuntimeError on failure."""
    try:
        resp = httpx.get(url, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Failed to fetch STIX bundle: {exc}") from exc


def extract_groups(bundle: dict) -> dict[str, list[str]]:
    """Extract intrusion-set objects → {name: [aliases]}."""
    groups: dict[str, list[str]] = {}
    for obj in bundle.get("objects", []):
        if obj.get("type") != "intrusion-set":
            continue
        name = obj.get("name", "")
        if not name:
            continue
        aliases = obj.get("aliases", [])
        # Include the name itself in the alias list for matching
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


def update_taxonomy(taxonomy: dict, groups: dict[str, list[str]], techniques: list[str]) -> dict:
    """Merge STIX data into taxonomy without overwriting manually managed fields.

    - actor_categories[*].mitre_groups: update to reflect STIX intrusion-set names
      that match existing groups or aliases.
    - actor_categories[*].priority_ttps: update from STIX technique IDs.
    - geography_threat_map / business_trigger_map / industry_threat_map:
      left untouched (manually managed).
    """
    import copy  # noqa: PLC0415

    updated = copy.deepcopy(taxonomy)
    actor_categories = updated.get("actor_categories", {})

    # Build a lookup: lowercase name/alias → canonical STIX group name
    alias_to_canonical: dict[str, str] = {}
    for canonical, aliases in groups.items():
        for alias in aliases:
            alias_to_canonical[alias.lower()] = canonical

    for _category_key, category_val in actor_categories.items():
        if isinstance(category_val, dict):
            # State-sponsored: nested dict of nations
            for _nation_key, nation_val in category_val.items():
                if not isinstance(nation_val, dict):
                    continue
                _update_actor_entry(nation_val, alias_to_canonical, techniques)
        else:
            # Flat actor category (ransomware, hacktivist)
            _update_actor_entry(category_val, alias_to_canonical, techniques)

    return updated


def _update_actor_entry(
    entry: dict, alias_to_canonical: dict[str, str], all_techniques: list[str]
) -> None:
    """Update mitre_groups and priority_ttps in a single actor entry."""
    existing_groups: list[str] = entry.get("mitre_groups", [])
    updated_groups: list[str] = []
    for grp in existing_groups:
        canonical = alias_to_canonical.get(grp.lower())
        if canonical and canonical not in updated_groups:
            updated_groups.append(canonical)
        elif not canonical:
            # Group not found in STIX — keep original (might be added manually)
            if grp not in updated_groups:
                updated_groups.append(grp)

    # Add any new STIX groups that match our existing group names via alias
    # (already handled above — only update in-place; don't auto-add new groups)

    entry["mitre_groups"] = updated_groups

    # Update priority_ttps: keep only technique IDs present in STIX
    # AND that were in the existing list (don't auto-expand).
    existing_ttps: list[str] = entry.get("priority_ttps", [])
    # Keep TTPs that still exist in STIX; discard removed ones
    all_tech_set = set(all_techniques)
    entry["priority_ttps"] = [t for t in existing_ttps if t in all_tech_set]


def diff_taxonomy(original: dict, updated: dict) -> str:
    """Return a human-readable diff summary."""
    lines: list[str] = []
    orig_cats = original.get("actor_categories", {})
    upd_cats = updated.get("actor_categories", {})

    for cat_key in upd_cats:
        orig_cat = orig_cats.get(cat_key, {})
        upd_cat = upd_cats[cat_key]

        if isinstance(upd_cat, dict) and not isinstance(next(iter(upd_cat.values()), None), dict):
            # Flat category
            _diff_entry(cat_key, orig_cat, upd_cat, lines)
        elif isinstance(upd_cat, dict):
            for nation_key in upd_cat:
                orig_nation = orig_cat.get(nation_key, {})
                upd_nation = upd_cat[nation_key]
                if isinstance(upd_nation, dict):
                    _diff_entry(f"{cat_key}.{nation_key}", orig_nation, upd_nation, lines)

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
    removed_ttps = orig_ttps - upd_ttps

    if added_grps:
        lines.append(f"[{label}] mitre_groups added: {sorted(added_grps)}")
    if removed_grps:
        lines.append(f"[{label}] mitre_groups removed: {sorted(removed_grps)}")
    if removed_ttps:
        lines.append(f"[{label}] priority_ttps removed (no longer in STIX): {sorted(removed_ttps)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Update threat_taxonomy.json from MITRE ATT&CK STIX bundle."
    )
    parser.add_argument(
        "--output",
        default=str(_DEFAULT_TAXONOMY),
        metavar="FILE",
        help="Path to threat_taxonomy.json to update (default: schema/threat_taxonomy.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print diff to stdout without modifying the file.",
    )
    parser.add_argument(
        "--url",
        default=_STIX_URL,
        metavar="URL",
        help="STIX bundle URL (default: MITRE CTI GitHub)",
    )
    args = parser.parse_args(argv)

    taxonomy_path = Path(args.output)
    if not taxonomy_path.exists():
        print(f"Error: taxonomy file not found: {taxonomy_path}", file=sys.stderr)
        return 1

    taxonomy = json.loads(taxonomy_path.read_text(encoding="utf-8"))

    logger.info("fetching_stix_bundle", url=args.url)
    try:
        bundle = fetch_stix_bundle(args.url)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    groups = extract_groups(bundle)
    techniques = extract_techniques(bundle)
    logger.info("stix_parsed", groups=len(groups), techniques=len(techniques))

    updated = update_taxonomy(taxonomy, groups, techniques)
    diff = diff_taxonomy(taxonomy, updated)

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
