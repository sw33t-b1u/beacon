"""Tests for generator/report_builder.py."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from beacon.analysis.asset_mapper import load_asset_tags, map_asset_tags
from beacon.analysis.element_extractor import extract
from beacon.analysis.risk_scorer import RiskScore, score
from beacon.analysis.threat_mapper import ThreatProfile, load_taxonomy, map_threats
from beacon.generator.pir_builder import build_pirs
from beacon.generator.report_builder import build_collection_plan, write_collection_plan
from beacon.ingest.schema import BusinessContext

FIXTURES = Path(__file__).parent / "fixtures"
_FIXED_DATE = date(2026, 4, 4)


def _load_ctx(filename: str) -> BusinessContext:
    data = json.loads((FIXTURES / filename).read_text(encoding="utf-8"))
    return BusinessContext.model_validate(data)


def _build_pipeline(filename: str):
    ctx = _load_ctx(filename)
    elements = extract(ctx)
    taxonomy = load_taxonomy()
    asset_tags_dict = load_asset_tags()
    asset_tag_list = map_asset_tags(elements, asset_tags_dict)
    threat = map_threats(elements, taxonomy)
    risk = score(elements, threat)
    pirs = build_pirs(elements, threat, risk, asset_tag_list, asset_tags_dict)
    return elements, threat, risk, pirs


class TestBuildCollectionPlanWithPIRs:
    """Manufacturing fixture produces PIRs; plan should note PIR coverage."""

    def setup_method(self):
        self.elements, self.threat, self.risk, self.pirs = _build_pipeline(
            "sample_context_manufacturing.json"
        )
        self.plan = build_collection_plan(
            self.elements, self.threat, self.risk, self.pirs, generated_on=_FIXED_DATE
        )

    def test_returns_string(self):
        assert isinstance(self.plan, str)

    def test_contains_generated_date(self):
        assert "2026-04-04" in self.plan

    def test_contains_industry(self):
        assert "manufacturing" in self.plan

    def test_contains_monitoring_status(self):
        assert "Monitoring Status" in self.plan

    def test_pir_coverage_noted(self):
        # When PIRs were generated, the plan should mention PIR coverage
        assert "PIR" in self.plan

    def test_contains_watch_items_section(self):
        assert "Watch Items" in self.plan

    def test_contains_collection_frequency_section(self):
        assert "Collection Frequency" in self.plan

    def test_contains_risk_score(self):
        assert f"Likelihood={self.risk.likelihood}" in self.plan
        assert f"Composite={self.risk.composite}" in self.plan


class TestBuildCollectionPlanNoPIRs:
    """Low-score scenario: no PIRs generated."""

    def setup_method(self):
        ctx = _load_ctx("sample_context_manufacturing.json")
        self.elements = extract(ctx)
        taxonomy = load_taxonomy()
        self.threat = map_threats(self.elements, taxonomy)
        # Force composite < 12
        self.risk = RiskScore(
            likelihood=2,
            impact=2,
            composite=4,
            intelligence_level="tactical",
            rationale="test low score",
        )
        self.plan = build_collection_plan(
            self.elements, self.threat, self.risk, pirs=[], generated_on=_FIXED_DATE
        )

    def test_below_threshold_message(self):
        assert "below PIR threshold" in self.plan

    def test_composite_score_shown(self):
        assert "Composite=4" in self.plan

    def test_no_pir_coverage_label(self):
        assert "PIR COVERED" not in self.plan


class TestBuildCollectionPlanTriggers:
    """Trigger-specific collection actions are included when triggers are active."""

    def setup_method(self):
        ctx = _load_ctx("sample_context_manufacturing.json")
        self.elements = extract(ctx)
        taxonomy = load_taxonomy()
        asset_tags_dict = load_asset_tags()
        asset_tag_list = map_asset_tags(self.elements, asset_tags_dict)
        self.threat = map_threats(self.elements, taxonomy)
        self.risk = score(self.elements, self.threat)
        pirs = build_pirs(self.elements, self.threat, self.risk, asset_tag_list, asset_tags_dict)
        self.plan = build_collection_plan(
            self.elements, self.threat, self.risk, pirs, generated_on=_FIXED_DATE
        )

    def test_ot_trigger_in_plan(self):
        # Manufacturing fixture has ot_connectivity=true
        assert "ot_connectivity" in self.plan

    def test_trigger_section_present(self):
        assert "Trigger-Based Collection" in self.plan

    def test_ot_action_included(self):
        assert "ICS-CERT" in self.plan or "JPCERT" in self.plan


class TestBuildCollectionPlanNoTriggers:
    """Plan without triggers should omit trigger section."""

    def test_no_trigger_section_when_no_triggers(self):
        from beacon.analysis.element_extractor import ExtractedElements

        elements = ExtractedElements(
            org_industry="education",
            org_unit_name="",
            org_unit_type="company",
            org_geographies=["USA"],
            org_regulatory_context=[],
            strategic_sensitivity=["medium"],
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
            threat_actor_tags=["hacktivist"],
            notable_groups=[],
            priority_ttps=[],
            active_triggers=[],
            matched_categories=[],
        )
        risk = RiskScore(
            likelihood=2,
            impact=2,
            composite=4,
            intelligence_level="tactical",
            rationale="test",
        )
        plan = build_collection_plan(elements, threat, risk, pirs=[], generated_on=_FIXED_DATE)
        assert "Trigger-Based Collection" not in plan


class TestWriteCollectionPlan:
    def test_writes_file(self, tmp_path):
        plan_text = "# Test Plan\nContent here."
        output_file = tmp_path / "collection_plan.md"
        write_collection_plan(plan_text, output_file)
        assert output_file.exists()
        assert output_file.read_text(encoding="utf-8") == plan_text

    def test_overwrites_existing_file(self, tmp_path):
        output_file = tmp_path / "plan.md"
        output_file.write_text("old content", encoding="utf-8")
        write_collection_plan("new content", output_file)
        assert output_file.read_text(encoding="utf-8") == "new content"
