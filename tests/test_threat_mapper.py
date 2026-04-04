"""Tests for threat_mapper.py (dictionary-only path)."""

from __future__ import annotations

import json
from pathlib import Path

from beacon.analysis.element_extractor import extract
from beacon.analysis.threat_mapper import load_taxonomy, map_threats
from beacon.ingest.schema import BusinessContext

FIXTURES = Path(__file__).parent / "fixtures"
SCHEMA_DIR = Path(__file__).parent.parent / "schema"


def _load_ctx(filename: str) -> BusinessContext:
    data = json.loads((FIXTURES / filename).read_text(encoding="utf-8"))
    return BusinessContext.model_validate(data)


class TestManufacturingThreatMap:
    def setup_method(self):
        ctx = _load_ctx("sample_context_manufacturing.json")
        self.elements = extract(ctx)
        self.taxonomy = load_taxonomy()
        self.profile = map_threats(self.elements, self.taxonomy)

    def test_china_apt_matched(self):
        # Manufacturing × Japan → China APT should match
        assert "state_sponsored.China" in self.profile.matched_categories

    def test_ransomware_matched(self):
        # Manufacturing → ransomware applicable
        assert "ransomware" in self.profile.matched_categories

    def test_espionage_tag_present(self):
        assert "espionage" in self.profile.threat_actor_tags

    def test_ip_theft_tag_present(self):
        assert "ip-theft" in self.profile.threat_actor_tags

    def test_ot_targeting_tag_present(self):
        # manufacturing industry_map has "ot-targeting"
        assert "ot-targeting" in self.profile.threat_actor_tags

    def test_japan_geo_tags(self):
        assert "targets-japan" in self.profile.threat_actor_tags

    def test_notable_groups_populated(self):
        assert len(self.profile.notable_groups) > 0

    def test_priority_ttps_populated(self):
        assert len(self.profile.priority_ttps) > 0

    def test_no_russia_for_japan_manufacturing(self):
        # Russia targets energy/defense/government — not manufacturing × Japan
        assert "state_sponsored.Russia" not in self.profile.matched_categories


class TestGeographyFilter:
    def test_iran_not_matched_for_japan(self):
        ctx = _load_ctx("sample_context_manufacturing.json")
        elements = extract(ctx)
        taxonomy = load_taxonomy()
        # Iran targets Middle East/USA/Israel — not Japan
        profile = map_threats(elements, taxonomy)
        assert "state_sponsored.Iran" not in profile.matched_categories

    def test_trigger_tags_added(self):
        ctx = _load_ctx("sample_context_manufacturing.json")
        elements = extract(ctx)
        assert "ot_connectivity" in elements.active_triggers
        profile = map_threats(elements, load_taxonomy())
        assert "critical-infrastructure" in profile.threat_actor_tags


class TestTaxonomyLoading:
    def test_default_taxonomy_loads(self):
        taxonomy = load_taxonomy()
        assert "actor_categories" in taxonomy
        assert "industry_threat_map" in taxonomy
        assert "geography_threat_map" in taxonomy
        assert "business_trigger_map" in taxonomy

    def test_custom_taxonomy_path(self):
        taxonomy = load_taxonomy(SCHEMA_DIR / "threat_taxonomy.json")
        assert "actor_categories" in taxonomy
