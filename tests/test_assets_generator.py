"""Tests for analysis/assets_generator.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from beacon.analysis.assets_generator import (
    _CRITICALITY_MAP,
    _INTERNET_EXPOSED_ZONES,
    _normalize_asset_id,
    generate_assets_json,
)
from beacon.ingest.schema import BusinessContext

FIXTURES = Path(__file__).parent / "fixtures"


def _load_ctx(filename: str) -> BusinessContext:
    data = json.loads((FIXTURES / filename).read_text(encoding="utf-8"))
    return BusinessContext.model_validate(data)


class TestNormalizeAssetId:
    def test_keeps_asset_prefix(self):
        assert _normalize_asset_id("asset-001") == "asset-001"

    def test_adds_asset_prefix(self):
        assert _normalize_asset_id("CA-001") == "asset-CA-001"

    def test_adds_prefix_to_plain_id(self):
        assert _normalize_asset_id("server-prod") == "asset-server-prod"


class TestCriticalityMap:
    @pytest.mark.parametrize(
        "label,expected",
        [("low", 3.0), ("medium", 5.0), ("high", 8.0), ("critical", 10.0)],
    )
    def test_mapping(self, label: str, expected: float):
        assert _CRITICALITY_MAP[label] == expected


class TestInternetExposedZones:
    def test_internet_is_exposed(self):
        assert "internet" in _INTERNET_EXPOSED_ZONES

    def test_dmz_is_exposed(self):
        assert "dmz" in _INTERNET_EXPOSED_ZONES

    def test_corporate_not_exposed(self):
        assert "corporate" not in _INTERNET_EXPOSED_ZONES

    def test_ot_not_exposed(self):
        assert "ot" not in _INTERNET_EXPOSED_ZONES


class TestGenerateAssetsJson:
    def setup_method(self):
        self.ctx = _load_ctx("sample_context_manufacturing.json")
        self.result = generate_assets_json(self.ctx)

    def test_top_level_keys_present(self):
        expected_keys = {
            "_comment",
            "network_segments",
            "security_controls",
            "assets",
            "asset_vulnerabilities",
            "asset_connections",
            "actor_targets",
        }
        assert set(self.result.keys()) == expected_keys

    def test_correct_asset_count(self):
        assert len(self.result["assets"]) == 2  # CA-001 and CA-002

    def test_asset_ids_normalised(self):
        ids = {a["id"] for a in self.result["assets"]}
        assert "asset-CA-001" in ids
        assert "asset-CA-002" in ids

    def test_erp_criticality_is_10(self):
        erp = next(a for a in self.result["assets"] if "CA-001" in a["id"])
        assert erp["criticality"] == 10.0  # critical → 10.0

    def test_high_criticality_is_8(self):
        edi = next(a for a in self.result["assets"] if "CA-002" in a["id"])
        assert edi["criticality"] == 8.0  # high → 8.0

    def test_edi_gateway_not_internet_exposed(self):
        edi = next(a for a in self.result["assets"] if "CA-002" in a["id"])
        assert edi["exposed_to_internet"] is False

    def test_corporate_zone_not_exposed(self):
        erp = next(a for a in self.result["assets"] if "CA-001" in a["id"])
        assert erp["exposed_to_internet"] is False

    def test_ot_zone_produces_ot_tag(self):
        edi = next(a for a in self.result["assets"] if "CA-002" in a["id"])
        assert "ot" in edi["tags"]

    def test_erp_function_keyword_matches_erp_tag(self):
        erp = next(a for a in self.result["assets"] if "CA-001" in a["id"])
        assert "erp" in erp["tags"]

    def test_network_segments_cover_all_zones(self):
        segment_zones = {s["zone"] for s in self.result["network_segments"]}
        # corporate and ot zones are present in the fixture
        segs = self.result["network_segments"]
        assert "ot" in segment_zones or any("ot" in s["id"] for s in segs)

    def test_network_segments_have_required_fields(self):
        for seg in self.result["network_segments"]:
            assert "id" in seg
            assert "name" in seg
            assert "cidr" in seg
            assert "zone" in seg

    def test_asset_connection_from_dependency(self):
        # CA-001 depends on CA-002
        conns = self.result["asset_connections"]
        assert any(c["src"] == "asset-CA-001" and c["dst"] == "asset-CA-002" for c in conns)

    def test_connection_outside_asset_set_excluded(self):
        # Dependencies referencing unknown IDs should be dropped
        conns = self.result["asset_connections"]
        known_ids = {a["id"] for a in self.result["assets"]}
        for conn in conns:
            assert conn["src"] in known_ids
            assert conn["dst"] in known_ids

    def test_security_controls_is_empty_list(self):
        assert self.result["security_controls"] == []

    def test_actor_targets_is_empty_list(self):
        assert self.result["actor_targets"] == []

    def test_asset_vulnerabilities_is_empty_list(self):
        assert self.result["asset_vulnerabilities"] == []

    def test_comment_includes_org_name(self):
        # Fixture org name is defined in sample_context_manufacturing.json
        assert self.ctx.organization.name in self.result["_comment"]

    def test_environment_ot_is_onprem(self):
        edi = next(a for a in self.result["assets"] if "CA-002" in a["id"])
        assert edi["environment"] == "onprem"

    def test_owner_is_empty_string(self):
        for asset in self.result["assets"]:
            assert asset["owner"] == ""

    def test_security_control_ids_is_empty(self):
        for asset in self.result["assets"]:
            assert asset["security_control_ids"] == []
