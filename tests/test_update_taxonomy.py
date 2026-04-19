"""Tests for cmd/update_taxonomy.py — MITRE + MISP regeneration."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import load_cmd_module

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_BUNDLE = json.loads((FIXTURES / "sample_stix_bundle.json").read_text())
SAMPLE_MISP = json.loads((FIXTURES / "sample_misp_galaxy.json").read_text())

_mod = load_cmd_module("update_taxonomy")
_PATCH_PREFIX = "_beacon_cmd_update_taxonomy"


class TestFetchStixBundle:
    def test_success_via_http(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = SAMPLE_BUNDLE
        mock_resp.raise_for_status.return_value = None

        with patch(f"{_PATCH_PREFIX}.httpx") as mock_httpx:
            mock_httpx.get.return_value = mock_resp
            result = _mod.fetch_stix_bundle("http://example.com/bundle.json")

        assert result == SAMPLE_BUNDLE

    def test_success_via_local_path(self, tmp_path):
        path = tmp_path / "bundle.json"
        path.write_text(json.dumps(SAMPLE_BUNDLE), encoding="utf-8")
        assert _mod.fetch_stix_bundle(str(path)) == SAMPLE_BUNDLE

    def test_http_error_raises_runtime_error(self):
        import httpx  # noqa: PLC0415

        with patch(f"{_PATCH_PREFIX}.httpx") as mock_httpx:
            mock_httpx.HTTPError = httpx.HTTPError
            mock_httpx.get.side_effect = httpx.HTTPError("connection failed")
            with pytest.raises(RuntimeError, match="Failed to fetch STIX bundle"):
                _mod.fetch_stix_bundle("http://example.com/bundle.json")

    def test_missing_local_file_raises(self, tmp_path):
        with pytest.raises(RuntimeError, match="file not found"):
            _mod.fetch_stix_bundle(str(tmp_path / "nope.json"))


class TestExtractGroups:
    def test_extracts_intrusion_sets(self):
        groups = _mod.extract_groups(SAMPLE_BUNDLE)
        assert "APT10" in groups
        assert "APT41" in groups
        assert "Lazarus Group" in groups

    def test_includes_aliases(self):
        groups = _mod.extract_groups(SAMPLE_BUNDLE)
        assert "menuPass" in groups["APT10"] or "Stone Panda" in groups["APT10"]

    def test_empty_bundle(self):
        assert _mod.extract_groups({"objects": []}) == {}


class TestExtractGroupTtps:
    def test_maps_group_to_ttps(self):
        ttps = _mod.extract_group_ttps(SAMPLE_BUNDLE)
        assert "T1566" in ttps["APT10"]
        assert "T1078" in ttps["APT10"]
        assert "T1190" in ttps["APT41"]
        assert "T1486" in ttps["Lazarus Group"]

    def test_ignores_non_uses_relationships(self):
        ttps = _mod.extract_group_ttps(SAMPLE_BUNDLE)
        # The "attributed-to" relationship (T1083) must NOT appear
        assert "T1083" not in ttps.get("APT10", [])


class TestNormalizeHelpers:
    def test_normalize_country_known(self):
        assert _mod._normalize_country("CN") == "China"
        assert _mod._normalize_country("kp") == "North Korea"

    def test_normalize_country_unknown_returns_none(self):
        assert _mod._normalize_country("XX") is None
        assert _mod._normalize_country(None) is None

    def test_classify_non_state_string(self):
        assert _mod._classify_non_state("Financial Crime") == "financial_crime"
        assert _mod._classify_non_state("defacement") == "sabotage"

    def test_classify_non_state_list(self):
        assert _mod._classify_non_state(["Espionage"]) == "espionage"

    def test_classify_non_state_unknown(self):
        assert _mod._classify_non_state("Unknown Motive") is None
        assert _mod._classify_non_state(None) is None

    def test_canonicalize_state_alias(self):
        assert _mod._canonicalize_state("Russian Federation") == "Russia"
        assert _mod._canonicalize_state("US") == "United States"

    def test_canonicalize_state_pass_through(self):
        assert _mod._canonicalize_state("China") == "China"

    def test_canonicalize_state_rejects_unknown_sponsor(self):
        assert _mod._canonicalize_state("Unknown") is None
        assert _mod._canonicalize_state("") is None


class TestBuildActorCategories:
    def setup_method(self):
        self.groups = _mod.extract_groups(SAMPLE_BUNDLE)
        self.ttps = _mod.extract_group_ttps(SAMPLE_BUNDLE)
        self.cats = _mod.build_actor_categories(self.groups, self.ttps, SAMPLE_MISP)

    def test_state_sponsored_china_bucket(self):
        china = self.cats["state_sponsored"]["China"]
        assert "APT10" in china["mitre_groups"]
        assert "APT41" in china["mitre_groups"]
        assert "apt-china" in china["tags"]
        # Inherited TTPs from MITRE relationships
        assert "T1566" in china["priority_ttps"]
        assert "T1190" in china["priority_ttps"]

    def test_state_sponsored_north_korea_bucket(self):
        nk = self.cats["state_sponsored"]["North Korea"]
        assert "Lazarus Group" in nk["mitre_groups"]
        assert "T1486" in nk["priority_ttps"]

    def test_non_state_financial_crime(self):
        assert "financial_crime" in self.cats
        fc = self.cats["financial_crime"]
        assert "United States" in fc["target_geographies"]

    def test_non_state_sabotage_iran_goes_to_state(self):
        # Shamoon has cfr-suspected-state-sponsor=Iran, so must land in state bucket,
        # NOT in the sabotage non-state bucket.
        iran = self.cats["state_sponsored"]["Iran"]
        assert "Saudi Arabia" in iran["target_geographies"]

    def test_hacktivist_defacement_goes_to_sabotage(self):
        # Rebel Jackal has no state sponsor, incident=Defacement → sabotage
        assert "sabotage" in self.cats
        sabotage = self.cats["sabotage"]
        assert sabotage["tags"] == ["sabotage"]

    def test_unclassifiable_entry_skipped(self):
        # UnknownGroup has no country/sponsor/incident — must not appear anywhere
        all_groups: set[str] = set()
        for cat in self.cats.values():
            if "mitre_groups" in cat:  # non-state leaf
                all_groups.update(cat["mitre_groups"])
            elif isinstance(cat, dict):  # state_sponsored nested
                for sub in cat.values():
                    all_groups.update(sub.get("mitre_groups", []))
        assert "UnknownGroup" not in all_groups

    def test_target_industries_from_misp(self):
        china = self.cats["state_sponsored"]["China"]
        assert "Private sector" in china["target_industries"]


class TestBuildGeographyThreatMap:
    def test_japan_populated_from_victim_data(self):
        groups = _mod.extract_groups(SAMPLE_BUNDLE)
        geo = _mod.build_geography_threat_map(groups, SAMPLE_MISP)
        assert "Japan" in geo
        japan = geo["Japan"]
        assert "APT10" in japan["notable_groups"]
        assert "apt-china" in japan["apt_tags"]


class TestBuildTaxonomy:
    def test_metadata_populated(self):
        result = _mod.build_taxonomy(
            SAMPLE_BUNDLE, SAMPLE_MISP, now_iso="2026-04-19T00:00:00+00:00"
        )
        meta = result["_metadata"]
        assert meta["last_auto_sync"] == "2026-04-19T00:00:00+00:00"
        assert "mitre_attack" in meta["sources"]
        assert "misp_galaxy_threat_actor" in meta["sources"]
        assert meta["generator"] == "cmd/update_taxonomy.py"

    def test_removed_fields_absent(self):
        result = _mod.build_taxonomy(
            SAMPLE_BUNDLE, SAMPLE_MISP, now_iso="2026-04-19T00:00:00+00:00"
        )
        assert "industry_threat_map" not in result
        assert "business_trigger_map" not in result
        assert "supply_chain_threat_map" not in result

    def test_metadata_uses_provided_urls(self):
        result = _mod.build_taxonomy(
            SAMPLE_BUNDLE,
            SAMPLE_MISP,
            now_iso="2026-04-19T00:00:00+00:00",
            mitre_url="https://example.com/mitre.json",
            misp_url="https://example.com/misp.json",
        )
        assert result["_metadata"]["sources"]["mitre_attack"] == "https://example.com/mitre.json"
        assert (
            result["_metadata"]["sources"]["misp_galaxy_threat_actor"]
            == "https://example.com/misp.json"
        )


class TestDiffTaxonomy:
    def test_no_diff_same_input(self):
        sample = _mod.build_taxonomy(
            SAMPLE_BUNDLE, SAMPLE_MISP, now_iso="2026-04-19T00:00:00+00:00"
        )
        result = _mod.diff_taxonomy(sample, sample)
        assert result == "No changes detected."

    def test_diff_shows_added_category(self):
        import copy  # noqa: PLC0415

        original = _mod.build_taxonomy(
            SAMPLE_BUNDLE, SAMPLE_MISP, now_iso="2026-04-19T00:00:00+00:00"
        )
        updated = copy.deepcopy(original)
        updated["actor_categories"]["subversion"] = {
            "tags": ["subversion"],
            "mitre_groups": [],
            "priority_ttps": [],
            "target_industries": [],
            "target_geographies": [],
        }
        result = _mod.diff_taxonomy(original, updated)
        assert "added category: subversion" in result


class TestMainCLI:
    def _mock_httpx(self, mock_httpx, *, bundles: list):
        """Configure mock_httpx.get to return distinct JSON payloads per call."""
        responses = []
        for payload in bundles:
            resp = MagicMock()
            resp.json.return_value = payload
            resp.raise_for_status.return_value = None
            responses.append(resp)
        mock_httpx.get.side_effect = responses
        mock_httpx.HTTPError = Exception

    def test_dry_run_does_not_modify_file(self, tmp_path):
        taxonomy_file = tmp_path / "taxonomy.json"
        taxonomy_file.write_text(json.dumps({"actor_categories": {}}), encoding="utf-8")
        original = taxonomy_file.read_text()

        with patch(f"{_PATCH_PREFIX}.httpx") as mock_httpx:
            self._mock_httpx(mock_httpx, bundles=[SAMPLE_BUNDLE, SAMPLE_MISP])
            rc = _mod.main(["--output", str(taxonomy_file), "--dry-run"])

        assert rc == 0
        assert taxonomy_file.read_text() == original

    def test_updates_file_without_dry_run(self, tmp_path):
        taxonomy_file = tmp_path / "taxonomy.json"
        taxonomy_file.write_text(json.dumps({"actor_categories": {}}), encoding="utf-8")

        with patch(f"{_PATCH_PREFIX}.httpx") as mock_httpx:
            self._mock_httpx(mock_httpx, bundles=[SAMPLE_BUNDLE, SAMPLE_MISP])
            rc = _mod.main(["--output", str(taxonomy_file)])

        assert rc == 0
        updated = json.loads(taxonomy_file.read_text())
        assert "actor_categories" in updated
        assert "state_sponsored" in updated["actor_categories"]
        assert "China" in updated["actor_categories"]["state_sponsored"]

    def test_missing_file_returns_error(self, tmp_path):
        rc = _mod.main(["--output", str(tmp_path / "nonexistent.json")])
        assert rc == 1

    def test_mitre_fetch_error_returns_1(self, tmp_path):
        import httpx  # noqa: PLC0415

        taxonomy_file = tmp_path / "taxonomy.json"
        taxonomy_file.write_text(json.dumps({"actor_categories": {}}), encoding="utf-8")

        with patch(f"{_PATCH_PREFIX}.httpx") as mock_httpx:
            mock_httpx.HTTPError = httpx.HTTPError
            mock_httpx.get.side_effect = httpx.HTTPError("timeout")
            rc = _mod.main(["--output", str(taxonomy_file)])

        assert rc == 1

    def test_cache_overrides_preserve_metadata_urls(self, tmp_path):
        """--mitre-cache / --misp-cache override fetch but not _metadata.sources."""
        taxonomy_file = tmp_path / "taxonomy.json"
        taxonomy_file.write_text(json.dumps({"actor_categories": {}}), encoding="utf-8")

        mitre_cache = tmp_path / "mitre.json"
        misp_cache = tmp_path / "misp.json"
        mitre_cache.write_text(json.dumps(SAMPLE_BUNDLE), encoding="utf-8")
        misp_cache.write_text(json.dumps(SAMPLE_MISP), encoding="utf-8")

        rc = _mod.main(
            [
                "--output",
                str(taxonomy_file),
                "--mitre-cache",
                str(mitre_cache),
                "--misp-cache",
                str(misp_cache),
            ]
        )
        assert rc == 0

        updated = json.loads(taxonomy_file.read_text())
        assert updated["_metadata"]["sources"]["mitre_attack"].startswith("https://")
        assert updated["_metadata"]["sources"]["misp_galaxy_threat_actor"].startswith("https://")
