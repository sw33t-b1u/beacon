"""Tests for threat_mapper.py with the MITRE+MISP-derived taxonomy."""

from __future__ import annotations

import json
from pathlib import Path

from beacon.analysis.element_extractor import extract
from beacon.analysis.threat_mapper import (
    _BEACON_TO_MISP_INDUSTRY,
    load_taxonomy,
    map_threats,
)
from beacon.ingest.schema import BusinessContext

FIXTURES = Path(__file__).parent / "fixtures"
SCHEMA_DIR = Path(__file__).parent.parent / "schema"


def _load_ctx(filename: str) -> BusinessContext:
    data = json.loads((FIXTURES / filename).read_text(encoding="utf-8"))
    return BusinessContext.model_validate(data)


def _synthetic_taxonomy() -> dict:
    """Minimal taxonomy fixture exercising each matching branch."""
    return {
        "_metadata": {"sources": {}, "last_auto_sync": "2026-04-19T00:00:00+00:00"},
        "actor_categories": {
            "state_sponsored": {
                "China": {
                    "tags": ["apt-china"],
                    "mitre_groups": ["APT10", "APT41"],
                    "priority_ttps": ["T1566", "T1078"],
                    "target_industries": ["Private sector", "Government"],
                    "target_geographies": ["Japan", "United States"],
                },
                "Russia": {
                    "tags": ["apt-russia"],
                    "mitre_groups": ["Sandworm"],
                    "priority_ttps": ["T1486"],
                    "target_industries": ["Government", "Military"],
                    "target_geographies": ["Ukraine"],
                },
            },
            "espionage": {
                "tags": ["espionage"],
                "mitre_groups": ["APT10"],
                "priority_ttps": ["T1566"],
                "target_industries": [],
                "target_geographies": [],
            },
            "financial_crime": {
                "tags": ["financial-crime"],
                "mitre_groups": ["FIN7"],
                "priority_ttps": ["T1204"],
                "target_industries": ["Private sector"],
                "target_geographies": ["Global"],
            },
        },
        "geography_threat_map": {
            "Japan": {
                "notable_groups": ["APT10"],
                "apt_tags": ["apt-china", "apt-north-korea"],
            },
        },
    }


class TestManufacturingJapan:
    def setup_method(self):
        ctx = _load_ctx("sample_context_manufacturing.json")
        self.elements = extract(ctx)
        self.taxonomy = _synthetic_taxonomy()
        self.profile = map_threats(self.elements, self.taxonomy)

    def test_china_matched_via_industry_and_geography(self):
        # manufacturing → Private sector; Japan ∈ target_geographies
        assert "state_sponsored.China" in self.profile.matched_categories

    def test_russia_excluded_by_geography(self):
        # Russia targets Ukraine, not Japan
        assert "state_sponsored.Russia" not in self.profile.matched_categories

    def test_espionage_matched_via_empty_filters(self):
        # espionage has empty target_industries/target_geographies → accepts all
        assert "espionage" in self.profile.matched_categories

    def test_financial_crime_matched_via_global(self):
        # Global geography ⇒ accepts any org geography; Private sector matches
        assert "financial_crime" in self.profile.matched_categories

    def test_tags_aggregated(self):
        assert "apt-china" in self.profile.threat_actor_tags
        assert "espionage" in self.profile.threat_actor_tags

    def test_geography_apt_tags_added(self):
        assert "apt-north-korea" in self.profile.threat_actor_tags

    def test_notable_groups_include_geo_and_category_groups(self):
        assert "APT10" in self.profile.notable_groups

    def test_priority_ttps_deduped(self):
        assert "T1566" in self.profile.priority_ttps
        assert "T1078" in self.profile.priority_ttps


class TestDefenseIndustryMapping:
    def test_defense_maps_to_military(self):
        assert _BEACON_TO_MISP_INDUSTRY["defense"] == "Military"

    def test_government_maps_to_government(self):
        assert _BEACON_TO_MISP_INDUSTRY["government"] == "Government"

    def test_education_maps_to_civil_society(self):
        assert _BEACON_TO_MISP_INDUSTRY["education"] == "Civil society"

    def test_other_industries_map_to_private_sector(self):
        for key in (
            "manufacturing",
            "finance",
            "energy",
            "healthcare",
            "technology",
            "logistics",
            "other",
        ):
            assert _BEACON_TO_MISP_INDUSTRY[key] == "Private sector"

    def test_all_beacon_industries_covered(self):
        # Every Literal value in Organization.industry must have a mapping
        from beacon.ingest.schema import Organization

        literal_vals = Organization.model_fields["industry"].annotation.__args__
        for v in literal_vals:
            assert v in _BEACON_TO_MISP_INDUSTRY, f"missing mapping for {v}"


class TestGeographyFiltering:
    def test_empty_target_industries_accept_all(self):
        taxonomy = {
            "actor_categories": {
                "espionage": {
                    "tags": ["espionage"],
                    "mitre_groups": [],
                    "priority_ttps": [],
                    "target_industries": [],
                    "target_geographies": ["Japan"],
                },
            },
            "geography_threat_map": {},
        }
        ctx = _load_ctx("sample_context_manufacturing.json")
        elements = extract(ctx)
        profile = map_threats(elements, taxonomy)
        assert "espionage" in profile.matched_categories

    def test_non_matching_geography_excludes_category(self):
        taxonomy = {
            "actor_categories": {
                "sabotage": {
                    "tags": ["sabotage"],
                    "mitre_groups": [],
                    "priority_ttps": [],
                    "target_industries": ["Private sector"],
                    "target_geographies": ["Saudi Arabia"],
                },
            },
            "geography_threat_map": {},
        }
        ctx = _load_ctx("sample_context_manufacturing.json")
        elements = extract(ctx)
        profile = map_threats(elements, taxonomy)
        assert "sabotage" not in profile.matched_categories


class TestTaxonomyLoading:
    def test_default_taxonomy_loads(self):
        taxonomy = load_taxonomy()
        assert "actor_categories" in taxonomy
        assert "geography_threat_map" in taxonomy
        # Removed fields must not re-appear
        assert "industry_threat_map" not in taxonomy
        assert "business_trigger_map" not in taxonomy
        assert "supply_chain_threat_map" not in taxonomy

    def test_custom_taxonomy_path(self):
        taxonomy = load_taxonomy(SCHEMA_DIR / "threat_taxonomy.json")
        assert "actor_categories" in taxonomy
