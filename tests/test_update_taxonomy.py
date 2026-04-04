"""Tests for cmd/update_taxonomy.py."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import load_cmd_module

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_BUNDLE = json.loads((FIXTURES / "sample_stix_bundle.json").read_text())
SAMPLE_TAXONOMY = json.loads(
    (Path(__file__).parent.parent / "schema" / "threat_taxonomy.json").read_text()
)

_mod = load_cmd_module("update_taxonomy")
_PATCH_PREFIX = "_beacon_cmd_update_taxonomy"


class TestFetchStixBundle:
    def test_success(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = SAMPLE_BUNDLE
        mock_resp.raise_for_status.return_value = None

        with patch(f"{_PATCH_PREFIX}.httpx") as mock_httpx:
            mock_httpx.get.return_value = mock_resp
            result = _mod.fetch_stix_bundle("http://example.com/bundle.json")

        assert result == SAMPLE_BUNDLE

    def test_http_error_raises_runtime_error(self):
        import httpx  # noqa: PLC0415

        with patch(f"{_PATCH_PREFIX}.httpx") as mock_httpx:
            mock_httpx.HTTPError = httpx.HTTPError
            mock_httpx.get.side_effect = httpx.HTTPError("connection failed")

            with pytest.raises(RuntimeError, match="Failed to fetch STIX bundle"):
                _mod.fetch_stix_bundle("http://example.com/bundle.json")


class TestExtractGroups:
    def test_extracts_intrusion_sets(self):
        groups = _mod.extract_groups(SAMPLE_BUNDLE)
        assert "APT10" in groups
        assert "APT41" in groups
        assert "Lazarus Group" in groups

    def test_includes_aliases(self):
        groups = _mod.extract_groups(SAMPLE_BUNDLE)
        apt10_aliases = groups["APT10"]
        assert "Stone Panda" in apt10_aliases or "menuPass" in apt10_aliases

    def test_ignores_non_intrusion_set(self):
        groups = _mod.extract_groups(SAMPLE_BUNDLE)
        # Keys should be intrusion-set names, not technique IDs (e.g., no "T1190")
        for key in groups:
            assert not key.startswith("T") or not key[1:].isdigit()

    def test_empty_bundle(self):
        assert _mod.extract_groups({"objects": []}) == {}


class TestExtractTechniques:
    def test_extracts_t_numbers(self):
        techniques = _mod.extract_techniques(SAMPLE_BUNDLE)
        assert "T1190" in techniques
        assert "T1566" in techniques
        assert "T1566.001" in techniques

    def test_sorted(self):
        techniques = _mod.extract_techniques(SAMPLE_BUNDLE)
        assert techniques == sorted(techniques)

    def test_ignores_non_mitre_refs(self):
        bundle = {
            "objects": [
                {
                    "type": "attack-pattern",
                    "external_references": [{"source_name": "capec", "external_id": "CAPEC-123"}],
                }
            ]
        }
        assert _mod.extract_techniques(bundle) == []


class TestUpdateTaxonomy:
    def test_mitre_groups_updated(self):
        groups = _mod.extract_groups(SAMPLE_BUNDLE)
        techniques = _mod.extract_techniques(SAMPLE_BUNDLE)
        updated = _mod.update_taxonomy(SAMPLE_TAXONOMY, groups, techniques)

        china = updated["actor_categories"]["state_sponsored"]["China"]
        assert "APT10" in china["mitre_groups"]

    def test_manual_tags_preserved(self):
        groups = _mod.extract_groups(SAMPLE_BUNDLE)
        techniques = _mod.extract_techniques(SAMPLE_BUNDLE)
        updated = _mod.update_taxonomy(SAMPLE_TAXONOMY, groups, techniques)

        orig_china = SAMPLE_TAXONOMY["actor_categories"]["state_sponsored"]["China"]
        upd_china = updated["actor_categories"]["state_sponsored"]["China"]

        assert upd_china["tags"] == orig_china["tags"]
        assert upd_china["target_industries"] == orig_china["target_industries"]
        assert upd_china["target_geographies"] == orig_china["target_geographies"]

    def test_priority_ttps_retained_if_in_stix(self):
        groups = _mod.extract_groups(SAMPLE_BUNDLE)
        techniques = _mod.extract_techniques(SAMPLE_BUNDLE)
        updated = _mod.update_taxonomy(SAMPLE_TAXONOMY, groups, techniques)

        china = updated["actor_categories"]["state_sponsored"]["China"]
        assert "T1190" in china["priority_ttps"]

    def test_geography_threat_map_unchanged(self):
        groups = _mod.extract_groups(SAMPLE_BUNDLE)
        techniques = _mod.extract_techniques(SAMPLE_BUNDLE)
        updated = _mod.update_taxonomy(SAMPLE_TAXONOMY, groups, techniques)
        assert updated["geography_threat_map"] == SAMPLE_TAXONOMY["geography_threat_map"]

    def test_industry_threat_map_unchanged(self):
        groups = _mod.extract_groups(SAMPLE_BUNDLE)
        techniques = _mod.extract_techniques(SAMPLE_BUNDLE)
        updated = _mod.update_taxonomy(SAMPLE_TAXONOMY, groups, techniques)
        assert updated["industry_threat_map"] == SAMPLE_TAXONOMY["industry_threat_map"]

    def test_business_trigger_map_unchanged(self):
        groups = _mod.extract_groups(SAMPLE_BUNDLE)
        techniques = _mod.extract_techniques(SAMPLE_BUNDLE)
        updated = _mod.update_taxonomy(SAMPLE_TAXONOMY, groups, techniques)
        assert updated["business_trigger_map"] == SAMPLE_TAXONOMY["business_trigger_map"]

    def test_original_not_mutated(self):
        import copy  # noqa: PLC0415

        original_copy = copy.deepcopy(SAMPLE_TAXONOMY)
        groups = _mod.extract_groups(SAMPLE_BUNDLE)
        techniques = _mod.extract_techniques(SAMPLE_BUNDLE)
        _mod.update_taxonomy(SAMPLE_TAXONOMY, groups, techniques)
        assert SAMPLE_TAXONOMY == original_copy


class TestDiffTaxonomy:
    def test_no_diff_same_input(self):
        result = _mod.diff_taxonomy(SAMPLE_TAXONOMY, SAMPLE_TAXONOMY)
        assert result == "No changes detected."

    def test_diff_shows_removed_group(self):
        import copy  # noqa: PLC0415

        updated = copy.deepcopy(SAMPLE_TAXONOMY)
        updated["actor_categories"]["state_sponsored"]["China"]["mitre_groups"] = ["APT10"]
        result = _mod.diff_taxonomy(SAMPLE_TAXONOMY, updated)
        assert "mitre_groups removed" in result


class TestMainCLI:
    def test_dry_run_does_not_modify_file(self, tmp_path):
        taxonomy_file = tmp_path / "taxonomy.json"
        taxonomy_file.write_text(json.dumps(SAMPLE_TAXONOMY), encoding="utf-8")
        original_content = taxonomy_file.read_text()

        mock_resp = MagicMock()
        mock_resp.json.return_value = SAMPLE_BUNDLE
        mock_resp.raise_for_status.return_value = None

        with patch(f"{_PATCH_PREFIX}.httpx") as mock_httpx:
            mock_httpx.get.return_value = mock_resp
            mock_httpx.HTTPError = Exception
            rc = _mod.main(["--output", str(taxonomy_file), "--dry-run"])

        assert rc == 0
        assert taxonomy_file.read_text() == original_content

    def test_updates_file_without_dry_run(self, tmp_path):
        taxonomy_file = tmp_path / "taxonomy.json"
        taxonomy_file.write_text(json.dumps(SAMPLE_TAXONOMY), encoding="utf-8")

        mock_resp = MagicMock()
        mock_resp.json.return_value = SAMPLE_BUNDLE
        mock_resp.raise_for_status.return_value = None

        with patch(f"{_PATCH_PREFIX}.httpx") as mock_httpx:
            mock_httpx.get.return_value = mock_resp
            mock_httpx.HTTPError = Exception
            rc = _mod.main(["--output", str(taxonomy_file)])

        assert rc == 0
        updated = json.loads(taxonomy_file.read_text())
        assert "actor_categories" in updated

    def test_missing_file_returns_error(self, tmp_path):
        rc = _mod.main(["--output", str(tmp_path / "nonexistent.json")])
        assert rc == 1

    def test_http_error_returns_error(self, tmp_path):
        import httpx  # noqa: PLC0415

        taxonomy_file = tmp_path / "taxonomy.json"
        taxonomy_file.write_text(json.dumps(SAMPLE_TAXONOMY), encoding="utf-8")

        with patch(f"{_PATCH_PREFIX}.httpx") as mock_httpx:
            mock_httpx.HTTPError = httpx.HTTPError
            mock_httpx.get.side_effect = httpx.HTTPError("timeout")
            rc = _mod.main(["--output", str(taxonomy_file)])

        assert rc == 1
