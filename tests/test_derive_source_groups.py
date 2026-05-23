"""Tests for scripts/derive_source_groups.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.conftest import load_scripts_module

dsg = load_scripts_module("derive_source_groups")

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_BUNDLE = FIXTURES / "sample_attack_bundle.json"

# Expected output for the sample fixture bundle.
# Fixture has:
#   APT41 (G0096) → Mandiant APT41 Feb 2020, CISA AA20-258A, BARIUM
#   Lazarus Group (G0032) → JPCERT/CC Lazarus 2022, Mandiant APT38 Sept 2018, Hidden Cobra
#   APT28 (G0007) → CISA APT28 June 2020, Mandiant APT28 Jan 2017
#   NoGIDGroup → skipped (no mitre-attack ref)
#   attack-pattern → skipped (not intrusion-set)
_EXPECTED_SOURCES = {
    "BARIUM": {"actor_groups": ["G0096"], "reference_count": 1},
    "CISA AA20-258A": {"actor_groups": ["G0096"], "reference_count": 1},
    "CISA APT28 June 2020": {"actor_groups": ["G0007"], "reference_count": 1},
    "Hidden Cobra": {"actor_groups": ["G0032"], "reference_count": 1},
    "JPCERT/CC Lazarus 2022": {"actor_groups": ["G0032"], "reference_count": 1},
    "Mandiant APT28 Jan 2017": {"actor_groups": ["G0007"], "reference_count": 1},
    "Mandiant APT38 Sept 2018": {"actor_groups": ["G0032"], "reference_count": 1},
    "Mandiant APT41 Feb 2020": {"actor_groups": ["G0096"], "reference_count": 1},
}


class TestDeriveSourceGroups:
    """Unit tests for derive_source_groups()."""

    def setup_method(self):
        self.mapping = dsg.derive_source_groups(SAMPLE_BUNDLE)

    def test_comment_key_present(self):
        assert "_comment" in self.mapping

    def test_comment_mentions_mitre(self):
        assert "MITRE ATT&CK" in self.mapping["_comment"]

    def test_comment_mentions_terms_of_use(self):
        assert "Terms of Use" in self.mapping["_comment"]

    def test_comment_mentions_attribution(self):
        assert "MITRE Corporation" in self.mapping["_comment"]

    def test_all_expected_sources_present(self):
        for sn in _EXPECTED_SOURCES:
            assert sn in self.mapping, f"Missing source: {sn}"

    def test_actor_groups_correct(self):
        for sn, expected in _EXPECTED_SOURCES.items():
            assert self.mapping[sn]["actor_groups"] == expected["actor_groups"], (
                f"actor_groups mismatch for {sn}"
            )

    def test_reference_count_correct(self):
        for sn, expected in _EXPECTED_SOURCES.items():
            assert self.mapping[sn]["reference_count"] == expected["reference_count"], (
                f"reference_count mismatch for {sn}"
            )

    def test_mitre_attack_source_excluded(self):
        # The 'mitre-attack' source_name must never appear as a key
        assert "mitre-attack" not in self.mapping

    def test_no_gid_group_skipped(self):
        # intrusion-set without mitre-attack external_id must be silently skipped
        assert "Some Report 2023" not in self.mapping

    def test_non_intrusion_set_skipped(self):
        # attack-pattern objects must not contribute to the mapping
        assert "T1566" not in self.mapping

    def test_source_count(self):
        # 8 sources + _comment key = 9 keys
        assert len(self.mapping) == 9

    def test_sources_sorted(self):
        keys = [k for k in self.mapping if k != "_comment"]
        assert keys == sorted(keys)

    def test_actor_groups_sorted(self):
        for sn, entry in self.mapping.items():
            if sn == "_comment":
                continue
            groups = entry["actor_groups"]
            assert groups == sorted(groups), f"actor_groups not sorted for {sn}"

    def test_jpcert_entry_present(self):
        jpcert_keys = [k for k in self.mapping if "JPCERT" in k]
        assert jpcert_keys, "Expected at least one JPCERT/CC entry"

    def test_cisa_entry_present(self):
        cisa_keys = [k for k in self.mapping if k.startswith("CISA")]
        assert len(cisa_keys) == 2  # CISA AA20-258A and CISA APT28 June 2020

    def test_mandiant_entry_present(self):
        mandiant_keys = [k for k in self.mapping if k.startswith("Mandiant")]
        assert len(mandiant_keys) == 3


class TestDumpJson:
    """Unit tests for dump_json() serialisation."""

    def test_returns_string(self):
        assert isinstance(dsg.dump_json({"a": 1}), str)

    def test_trailing_newline(self):
        result = dsg.dump_json({"a": 1})
        assert result.endswith("\n")

    def test_two_space_indent(self):
        result = dsg.dump_json({"key": {"nested": 1}})
        assert '  "key"' in result

    def test_valid_json(self):
        mapping = dsg.derive_source_groups(SAMPLE_BUNDLE)
        text = dsg.dump_json(mapping)
        parsed = json.loads(text)
        assert parsed["_comment"] == mapping["_comment"]


class TestDeterminism:
    """Re-run produces byte-identical output."""

    def test_two_runs_identical(self):
        run1 = dsg.dump_json(dsg.derive_source_groups(SAMPLE_BUNDLE))
        run2 = dsg.dump_json(dsg.derive_source_groups(SAMPLE_BUNDLE))
        assert run1 == run2

    def test_group_sharing_two_sources(self, tmp_path):
        # A single source_name referenced by two actors → reference_count=2
        bundle = {
            "type": "bundle",
            "id": "bundle--test-sharing",
            "objects": [
                {
                    "type": "intrusion-set",
                    "name": "ActorA",
                    "external_references": [
                        {"source_name": "mitre-attack", "external_id": "G0001"},
                        {"source_name": "Shared Report 2024"},
                    ],
                },
                {
                    "type": "intrusion-set",
                    "name": "ActorB",
                    "external_references": [
                        {"source_name": "mitre-attack", "external_id": "G0002"},
                        {"source_name": "Shared Report 2024"},
                    ],
                },
            ],
        }
        p = tmp_path / "bundle.json"
        p.write_text(json.dumps(bundle), encoding="utf-8")
        mapping = dsg.derive_source_groups(p)
        assert mapping["Shared Report 2024"]["actor_groups"] == ["G0001", "G0002"]
        assert mapping["Shared Report 2024"]["reference_count"] == 2


class TestCLI:
    """CLI --input / --output flags."""

    def test_output_written(self, tmp_path):
        out = tmp_path / "out.json"
        dsg.main(["--input", str(SAMPLE_BUNDLE), "--output", str(out)])
        assert out.exists()

    def test_output_valid_json(self, tmp_path):
        out = tmp_path / "out.json"
        dsg.main(["--input", str(SAMPLE_BUNDLE), "--output", str(out)])
        data = json.loads(out.read_text(encoding="utf-8"))
        assert "_comment" in data

    def test_output_has_trailing_newline(self, tmp_path):
        out = tmp_path / "out.json"
        dsg.main(["--input", str(SAMPLE_BUNDLE), "--output", str(out)])
        assert out.read_bytes().endswith(b"\n")

    def test_missing_input_exits_nonzero(self, tmp_path):
        out = tmp_path / "out.json"
        with pytest.raises(SystemExit) as exc:
            dsg.main(["--input", str(tmp_path / "missing.json"), "--output", str(out)])
        assert exc.value.code != 0

    def test_idempotent_two_runs(self, tmp_path):
        out1 = tmp_path / "run1.json"
        out2 = tmp_path / "run2.json"
        dsg.main(["--input", str(SAMPLE_BUNDLE), "--output", str(out1)])
        dsg.main(["--input", str(SAMPLE_BUNDLE), "--output", str(out2)])
        assert out1.read_bytes() == out2.read_bytes()

    def test_output_directory_created(self, tmp_path):
        out = tmp_path / "nested" / "dir" / "out.json"
        dsg.main(["--input", str(SAMPLE_BUNDLE), "--output", str(out)])
        assert out.exists()
