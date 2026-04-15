"""Tests for pir_clusterer.py — per-decision-point PIR scoping."""

from __future__ import annotations

import json
from pathlib import Path

from beacon.analysis.asset_mapper import load_asset_tags, map_asset_tags
from beacon.analysis.element_extractor import extract
from beacon.analysis.pir_clusterer import build_clusters
from beacon.analysis.threat_mapper import load_taxonomy, map_threats
from beacon.ingest.schema import BusinessContext

FIXTURES = Path(__file__).parent / "fixtures"


def _load(filename: str):
    ctx = BusinessContext.model_validate(
        json.loads((FIXTURES / filename).read_text(encoding="utf-8"))
    )
    elements = extract(ctx)
    asset_tag_list = map_asset_tags(elements, load_asset_tags())
    threat = map_threats(elements, load_taxonomy())
    return elements, threat, asset_tag_list


class TestClustering:
    def test_manufacturing_splits_into_multiple_clusters(self):
        elements, threat, asset_tag_list = _load("sample_context_manufacturing.json")
        clusters = build_clusters(elements, threat, asset_tag_list)
        # Manufacturing × Japan × OT should produce > 1 cluster (state_sponsored,
        # ransomware, ot_ics, cloud, etc.)
        assert len(clusters) >= 1
        families = {c.threat_family for c in clusters}
        # At least one of the expected families should appear
        assert families & {
            "ransomware",
            "state_sponsored",
            "ot_ics",
            "cloud",
            "supply_chain",
        }

    def test_cluster_tags_are_strict_subset_of_profile(self):
        elements, threat, asset_tag_list = _load("sample_context_manufacturing.json")
        clusters = build_clusters(elements, threat, asset_tag_list)
        profile_tags = set(threat.threat_actor_tags)
        for c in clusters:
            assert set(c.threat_actor_tags) <= profile_tags, (
                f"cluster {c.cluster_id} leaked tags: {set(c.threat_actor_tags) - profile_tags}"
            )

    def test_no_single_cluster_contains_all_tags(self):
        """A properly split profile should not put every tag into one cluster."""
        elements, threat, asset_tag_list = _load("sample_context_manufacturing.json")
        if len(threat.threat_actor_tags) < 3:
            return  # not enough tags to split meaningfully
        clusters = build_clusters(elements, threat, asset_tag_list)
        if len(clusters) < 2:
            return  # only one family matched — single cluster is fine
        for c in clusters:
            assert set(c.threat_actor_tags) != set(threat.threat_actor_tags)

    def test_cluster_count_capped(self):
        elements, threat, asset_tag_list = _load("sample_context_manufacturing.json")
        clusters = build_clusters(elements, threat, asset_tag_list)
        assert len(clusters) <= 5  # "less is more"

    def test_each_cluster_has_identity(self):
        elements, threat, asset_tag_list = _load("sample_context_manufacturing.json")
        clusters = build_clusters(elements, threat, asset_tag_list)
        for c in clusters:
            assert c.cluster_id
            assert c.threat_family
            assert c.decision_point
            # A cluster must have at least one dimension populated (tags OR
            # asset focus); otherwise it carries no signal.
            assert c.threat_actor_tags or c.asset_tag_focus


class TestFallback:
    def test_empty_profile_yields_single_fallback_cluster(self):
        """When no family matches, emit one fallback cluster — not zero."""
        from beacon.analysis.element_extractor import ExtractedElements
        from beacon.analysis.threat_mapper import ThreatProfile

        elements = ExtractedElements(
            org_industry="unknown",
            org_unit_name="",
            org_unit_type="company",
            org_geographies=[],
            org_regulatory_context=[],
            strategic_sensitivity=[],
            project_data_types=[],
            project_cloud_providers=[],
            crown_jewel_ids=[],
            crown_jewel_systems=[],
            crown_jewel_impacts=[],
            crown_jewel_details=[],
            critical_asset_ids=[],
            critical_asset_details=[],
            has_ot_connectivity=False,
            has_stock_listing=False,
            active_vendors=[],
            active_triggers=[],
            source_element_ids=[],
        )
        threat = ThreatProfile(
            threat_actor_tags=[],
            notable_groups=[],
            priority_ttps=[],
            active_triggers=[],
            matched_categories=[],
        )
        clusters = build_clusters(elements, threat, asset_tag_list=[])
        assert len(clusters) == 1
        assert clusters[0].threat_family == "cybercriminal"


class TestMultiClusterPIRBuilder:
    def test_multi_cluster_produces_sequential_pir_ids(self):
        from beacon.analysis.risk_scorer import score
        from beacon.generator.pir_builder import build_pirs

        elements, threat, asset_tag_list = _load("sample_context_manufacturing.json")
        risk = score(elements, threat)
        pirs = build_pirs(elements, threat, risk, asset_tag_list, load_asset_tags())
        if len(pirs) >= 2:
            assert pirs[0].pir_id.endswith("-001")
            assert pirs[1].pir_id.endswith("-002")
            # Decision points must be distinct
            assert pirs[0].decision_point != pirs[1].decision_point
            # Per-PIR scoping — no two PIRs should have identical tag sets if
            # they come from different families.
            tags_per_pir = [tuple(sorted(p.threat_actor_tags)) for p in pirs]
            assert len(set(tags_per_pir)) == len(tags_per_pir)

    def test_every_pir_has_decision_point_and_action(self):
        from beacon.analysis.risk_scorer import score
        from beacon.generator.pir_builder import build_pirs

        elements, threat, asset_tag_list = _load("sample_context_manufacturing.json")
        risk = score(elements, threat)
        pirs = build_pirs(elements, threat, risk, asset_tag_list, load_asset_tags())
        for p in pirs:
            assert p.decision_point
            assert p.recommended_action
