"""Derive source → actor group mapping from MITRE ATT&CK Enterprise STIX bundle.

Reads intrusion-set objects from a MITRE ATT&CK STIX 2.1 JSON bundle and
produces a deterministic JSON mapping of external-reference source_names to
the ATT&CK Group IDs (Gxxxx) that cite each source.

For each intrusion-set the canonical 'mitre-attack' external reference
supplies the Group ID (e.g. G0032); all other source_names found in that
object's external_references are then mapped to that Group ID.

Attribution: MITRE ATT&CK is licensed under the MITRE ATT&CK Terms of Use.
This script and its derived output preserve attribution to MITRE Corporation.
See also: docs/citations.md in the BEACON repository.

Usage:
    python scripts/derive_source_groups.py [--input PATH] [--output PATH]

Environment:
    ATTACK_BUNDLE_PATH  default input path if --input is omitted
                        (fallback: ref/enterprise-attack-19.1.json relative
                        to the repository root)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parents[1]
_DEFAULT_BUNDLE_PATH = _REPO_ROOT / "ref" / "enterprise-attack-19.1.json"
_DEFAULT_OUTPUT_PATH = _REPO_ROOT / "schema" / "source_attack_groups.derived.json"

_COMMENT = (
    "Auto-derived from MITRE ATT&CK Enterprise via scripts/derive_source_groups.py. "
    "MITRE ATT&CK is licensed under the MITRE ATT&CK Terms of Use; "
    "this derived artifact preserves attribution to MITRE Corporation."
)


def derive_source_groups(bundle_path: Path) -> dict[str, object]:
    """Parse MITRE ATT&CK STIX bundle and derive source_name → actor groups mapping.

    Args:
        bundle_path: Path to a MITRE ATT&CK Enterprise STIX 2.1 JSON bundle.

    Returns:
        Ordered dict: '_comment' key first, then source_name keys in
        lexicographic order. Each source entry contains:
          actor_groups  — sorted list of ATT&CK Group IDs that cite this source
          reference_count — len(actor_groups)
    """
    data = json.loads(bundle_path.read_text(encoding="utf-8"))

    source_to_groups: dict[str, set[str]] = {}

    for obj in data.get("objects", []):
        if obj.get("type") != "intrusion-set":
            continue

        refs = obj.get("external_references", [])

        # Extract canonical ATT&CK Group ID (e.g. G0032) from the mitre-attack ref
        group_id = next(
            (r["external_id"] for r in refs if r.get("source_name") == "mitre-attack"),
            None,
        )
        if not group_id:
            continue

        for ref in refs:
            sn = ref.get("source_name", "")
            if not sn or sn == "mitre-attack":
                continue
            source_to_groups.setdefault(sn, set()).add(group_id)

    # Build output: _comment first, then sources in sorted key order.
    # Python 3.7+ dicts preserve insertion order; no sort_keys needed.
    result: dict[str, object] = {"_comment": _COMMENT}
    for sn in sorted(source_to_groups):
        groups = sorted(source_to_groups[sn])
        result[sn] = {"actor_groups": groups, "reference_count": len(groups)}

    return result


def dump_json(mapping: dict[str, object]) -> str:
    """Serialise mapping to byte-deterministic JSON (2-space indent, trailing newline)."""
    return json.dumps(mapping, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Derive source → ATT&CK group mapping from a STIX bundle."
    )
    parser.add_argument(
        "--input",
        default=os.environ.get("ATTACK_BUNDLE_PATH", str(_DEFAULT_BUNDLE_PATH)),
        help=(
            "Path to MITRE ATT&CK Enterprise STIX bundle "
            "(default: $ATTACK_BUNDLE_PATH or ref/enterprise-attack-19.1.json)"
        ),
    )
    parser.add_argument(
        "--output",
        default=str(_DEFAULT_OUTPUT_PATH),
        help="Output path for derived JSON (default: schema/source_attack_groups.derived.json)",
    )
    args = parser.parse_args(argv)

    bundle_path = Path(args.input)
    output_path = Path(args.output)

    if not bundle_path.exists():
        print(f"Error: input bundle not found: {bundle_path}", file=sys.stderr)
        sys.exit(1)

    mapping = derive_source_groups(bundle_path)
    json_text = dump_json(mapping)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json_text, encoding="utf-8")

    n_sources = len(mapping) - 1  # subtract _comment key
    print(f"Derived {n_sources} source entries → {output_path}")


if __name__ == "__main__":
    main()
