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
from beacon.generator.report_builder import (
    _priority_badge,
    build_collection_plan,
    write_collection_plan,
)
from beacon.ingest.schema import BusinessContext

FIXTURES = Path(__file__).parent / "fixtures"
_FIXED_DATE = date(2026, 4, 4)


def _assert_golden(plan: str, golden_name: str) -> None:
    """Assert plan matches a golden fixture file, creating it on first run."""
    golden_path = FIXTURES / golden_name
    if not golden_path.exists():
        golden_path.write_text(plan, encoding="utf-8")
        return
    expected = golden_path.read_text(encoding="utf-8")
    assert plan == expected, (
        f"Golden fixture mismatch for {golden_name}.\n"
        "Delete the fixture file and re-run to regenerate, or fix the implementation."
    )


def _load_ctx(filename: str) -> BusinessContext:
    data = json.loads((FIXTURES / filename).read_text(encoding="utf-8"))
    return BusinessContext.model_validate(data)


def _build_pipeline(filename: str, generated_on: date | None = None):
    ctx = _load_ctx(filename)
    elements = extract(ctx)
    taxonomy = load_taxonomy()
    asset_tags_dict = load_asset_tags()
    asset_tag_list = map_asset_tags(elements, asset_tags_dict)
    threat = map_threats(elements, taxonomy)
    risk = score(elements, threat)
    pirs = build_pirs(
        elements, threat, risk, asset_tag_list, asset_tags_dict, generated_on=generated_on
    )
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

    def test_it_ot_convergence_trigger_in_plan(self):
        # Manufacturing fixture has supply_chain.ot_connectivity=true → it_ot_convergence
        assert "it_ot_convergence" in self.plan

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


class TestPriorityBadgeFunction:
    """Unit tests for the _priority_badge helper."""

    def test_p1_at_20(self):
        assert _priority_badge(20) == "P1"

    def test_p1_at_25(self):
        assert _priority_badge(25) == "P1"

    def test_p2_at_12(self):
        assert _priority_badge(12) == "P2"

    def test_p2_at_19(self):
        assert _priority_badge(19) == "P2"

    def test_p3_at_6(self):
        assert _priority_badge(6) == "P3"

    def test_p3_at_11(self):
        assert _priority_badge(11) == "P3"

    def test_p4_at_1(self):
        assert _priority_badge(1) == "P4"

    def test_p4_at_5(self):
        assert _priority_badge(5) == "P4"

    def test_p4_at_zero(self):
        assert _priority_badge(0) == "P4"


class TestPriorityIntelligenceRequirementsSection:
    """New section: generated PIRs appear with badge, level, focus, placeholder."""

    def setup_method(self):
        self.elements, self.threat, self.risk, self.pirs = _build_pipeline(
            "sample_context_manufacturing.json"
        )
        self.plan = build_collection_plan(
            self.elements, self.threat, self.risk, self.pirs, generated_on=_FIXED_DATE
        )

    def test_pir_section_heading_present(self):
        assert "Priority Intelligence Requirements" in self.plan

    def test_p1_badge_in_plan(self):
        # manufacturing composite=25 → P1
        assert "[P1]" in self.plan

    def test_pir_id_present(self):
        assert "PIR-2026-001" in self.plan

    def test_intelligence_level_label_present(self):
        assert "**Intelligence Level:**" in self.plan

    def test_decision_point_label_present(self):
        assert "**Decision Point:**" in self.plan

    def test_valid_range_arrow_present(self):
        assert "**Valid:**" in self.plan
        assert "→" in self.plan

    def test_collection_focus_label_present(self):
        assert "**Collection Focus:**" in self.plan

    def test_placeholder_sources_present(self):
        assert "_pending Phase 2 wiring_" in self.plan

    def test_recommended_sources_label_present(self):
        assert "**Recommended Sources:**" in self.plan

    def test_no_pir_section_when_no_pirs(self):
        plan_no_pirs = build_collection_plan(
            self.elements, self.threat, self.risk, pirs=[], generated_on=_FIXED_DATE
        )
        assert "Priority Intelligence Requirements" not in plan_no_pirs


class TestPriorityIntelligenceRequirementsSectionFinance:
    """Finance banking fixture — exercises P1 badge, collection_focus, placeholder."""

    def setup_method(self):
        self.elements, self.threat, self.risk, self.pirs = _build_pipeline(
            "sample_context_finance_banking.json"
        )
        self.plan = build_collection_plan(
            self.elements, self.threat, self.risk, self.pirs, generated_on=_FIXED_DATE
        )

    def test_pir_section_present_for_finance(self):
        assert "Priority Intelligence Requirements" in self.plan

    def test_priority_badge_present(self):
        # Finance has critical crown jewel + multiple triggers → composite ≥ 12
        assert "[P1]" in self.plan or "[P2]" in self.plan

    def test_collection_focus_bullets(self):
        assert "**Collection Focus:**" in self.plan

    def test_placeholder_present(self):
        assert "_pending Phase 2 wiring_" in self.plan

    def test_pir_ids_present(self):
        assert "PIR-2026-" in self.plan

    def test_finance_industry_in_plan(self):
        assert "finance" in self.plan

    def test_watch_items_section_still_present(self):
        assert "Watch Items" in self.plan


class TestWatchItemsPriorityBadge:
    """When composite < 12 (no PIRs), watch items carry P3 or P4 badge."""

    def _make_plan(self, composite: int, matched_categories: list[str]) -> str:
        from beacon.analysis.element_extractor import ExtractedElements

        elements = ExtractedElements(
            org_industry="education",
            org_unit_name="",
            org_unit_type="company",
            org_geographies=["USA"],
            org_regulatory_context=[],
            strategic_sensitivity=["low"],
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
            matched_categories=matched_categories,
        )
        risk = RiskScore(
            likelihood=2,
            impact=composite // 2 if composite > 0 else 1,
            composite=composite,
            intelligence_level="tactical",
            rationale="test",
        )
        return build_collection_plan(elements, threat, risk, pirs=[], generated_on=_FIXED_DATE)

    def test_p3_badge_shown_for_composite_6(self):
        plan = self._make_plan(6, ["ransomware"])
        assert "[P3]" in plan

    def test_p4_badge_shown_for_composite_4(self):
        plan = self._make_plan(4, ["hacktivist"])
        assert "[P4]" in plan

    def test_intelligence_level_in_watch_item(self):
        plan = self._make_plan(4, ["hacktivist"])
        assert "**Intelligence Level:**" in plan

    def test_collection_focus_label_in_watch_item(self):
        plan = self._make_plan(4, ["hacktivist"])
        assert "**Collection Focus:**" in plan

    def test_placeholder_in_watch_item(self):
        plan = self._make_plan(4, ["hacktivist"])
        assert "_pending Phase 2 wiring_" in plan

    def test_no_pir_covered_label_for_watch_items(self):
        plan = self._make_plan(4, ["hacktivist"])
        assert "PIR COVERED" not in plan

    def test_general_watch_badge_when_no_categories(self):
        plan = self._make_plan(4, [])
        assert "[P4]" in plan
        assert "General watch" in plan


class TestGoldenCollectionPlanManufacturing:
    """Golden round-trip: manufacturing fixture produces stable Markdown output."""

    def test_golden_round_trip(self):
        elements, threat, risk, pirs = _build_pipeline(
            "sample_context_manufacturing.json", generated_on=_FIXED_DATE
        )
        plan = build_collection_plan(elements, threat, risk, pirs, generated_on=_FIXED_DATE)
        _assert_golden(plan, "golden_collection_plan_manufacturing.md")


class TestGoldenCollectionPlanFinance:
    """Golden round-trip: finance banking fixture produces stable Markdown output."""

    def test_golden_round_trip(self):
        elements, threat, risk, pirs = _build_pipeline(
            "sample_context_finance_banking.json", generated_on=_FIXED_DATE
        )
        plan = build_collection_plan(elements, threat, risk, pirs, generated_on=_FIXED_DATE)
        _assert_golden(plan, "golden_collection_plan_finance.md")
