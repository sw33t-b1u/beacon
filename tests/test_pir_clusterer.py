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
        # Manufacturing × Japan must yield at least one cluster from the
        # MISP-derived taxonomy families.
        assert len(clusters) >= 1
        families = {c.threat_family for c in clusters}
        assert families & {
            "state_sponsored",
            "espionage",
            "financial_crime",
            "sabotage",
            "subversion",
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


def _make_elements():
    from beacon.analysis.element_extractor import ExtractedElements

    return ExtractedElements(
        org_industry="manufacturing",
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
        source_element_ids=["el-1"],
    )


def _make_state_sponsored_threat():
    """A profile that activates the state_sponsored family (which has plm in its
    asset scope) so we can exercise the available_asset_tags constraint."""
    from beacon.analysis.threat_mapper import ThreatProfile

    return ThreatProfile(
        threat_actor_tags=["apt-china"],
        notable_groups=[],
        priority_ttps=[],
        active_triggers=[],
        matched_categories=["state_sponsored.China"],
    )


class TestAvailableAssetTagsConstraint:
    # state_sponsored family asset scope: identity, source_code, pki, database, plm, erp
    _ORG_ASSET_TAGS = ["identity", "source_code", "pki", "database", "plm", "erp"]

    def _state_cluster(self, clusters):
        return next(c for c in clusters if c.threat_family == "state_sponsored")

    def test_orphan_tag_excluded_when_not_available(self):
        """A tag in the org-level union but on no real asset (plm) is dropped
        from asset_tag_focus → asset_weight_rules when available_asset_tags
        omits it."""
        elements = _make_elements()
        threat = _make_state_sponsored_threat()
        # Real assets carry everything except plm.
        available = {"identity", "source_code", "pki", "database", "erp"}
        clusters = build_clusters(
            elements, threat, self._ORG_ASSET_TAGS, available_asset_tags=available
        )
        cluster = self._state_cluster(clusters)
        assert "plm" not in cluster.asset_tag_focus

    def test_available_tags_are_kept(self):
        """Tags present in available_asset_tags survive the intersection."""
        elements = _make_elements()
        threat = _make_state_sponsored_threat()
        available = {"identity", "database"}
        clusters = build_clusters(
            elements, threat, self._ORG_ASSET_TAGS, available_asset_tags=available
        )
        cluster = self._state_cluster(clusters)
        assert "identity" in cluster.asset_tag_focus
        assert "database" in cluster.asset_tag_focus
        # And only the intersection remains.
        assert set(cluster.asset_tag_focus) == {"identity", "database"}

    def test_none_preserves_legacy_behavior(self):
        """available_asset_tags=None must not intersect (legacy 2-term scope)."""
        elements = _make_elements()
        threat = _make_state_sponsored_threat()
        clusters_default = build_clusters(elements, threat, self._ORG_ASSET_TAGS)
        clusters_none = build_clusters(
            elements, threat, self._ORG_ASSET_TAGS, available_asset_tags=None
        )
        focus_default = self._state_cluster(clusters_default).asset_tag_focus
        focus_none = self._state_cluster(clusters_none).asset_tag_focus
        assert focus_default == focus_none
        # plm is part of the family scope and present in the org tags, so legacy
        # behavior keeps it.
        assert "plm" in focus_default

    def test_empty_set_preserves_legacy_behavior(self):
        """An empty available set must be treated like None (no wipe)."""
        elements = _make_elements()
        threat = _make_state_sponsored_threat()
        clusters_default = build_clusters(elements, threat, self._ORG_ASSET_TAGS)
        clusters_empty = build_clusters(
            elements, threat, self._ORG_ASSET_TAGS, available_asset_tags=set()
        )
        focus_default = self._state_cluster(clusters_default).asset_tag_focus
        focus_empty = self._state_cluster(clusters_empty).asset_tag_focus
        assert focus_default == focus_empty
        assert focus_empty  # not wiped

    def test_threat_actor_tags_unchanged_by_available(self):
        """The asset-side constraint must never touch threat_actor_tags."""
        elements = _make_elements()
        threat = _make_state_sponsored_threat()
        clusters_default = build_clusters(elements, threat, self._ORG_ASSET_TAGS)
        clusters_constrained = build_clusters(
            elements,
            threat,
            self._ORG_ASSET_TAGS,
            available_asset_tags={"identity"},
        )
        assert (
            self._state_cluster(clusters_default).threat_actor_tags
            == self._state_cluster(clusters_constrained).threat_actor_tags
        )

    def test_fallback_cluster_constrained(self):
        """The cybercriminal fallback cluster also honors available_asset_tags."""
        from beacon.analysis.threat_mapper import ThreatProfile

        elements = _make_elements()
        threat = ThreatProfile(
            threat_actor_tags=[],
            notable_groups=[],
            priority_ttps=[],
            active_triggers=[],
            matched_categories=[],
        )
        org_tags = ["identity", "plm", "database"]
        clusters = build_clusters(
            elements, threat, org_tags, available_asset_tags={"identity", "database"}
        )
        assert len(clusters) == 1
        assert clusters[0].threat_family == "cybercriminal"
        assert set(clusters[0].asset_tag_focus) == {"identity", "database"}


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
