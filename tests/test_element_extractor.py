"""Tests for element_extractor.py."""

from __future__ import annotations

import json
from pathlib import Path

from beacon.analysis.element_extractor import extract
from beacon.ingest.schema import BusinessContext

FIXTURES = Path(__file__).parent / "fixtures"


def _load_ctx(filename: str) -> BusinessContext:
    data = json.loads((FIXTURES / filename).read_text(encoding="utf-8"))
    return BusinessContext.model_validate(data)


class TestExtractManufacturing:
    def setup_method(self):
        self.ctx = _load_ctx("sample_context_manufacturing.json")
        self.elements = extract(self.ctx)

    def test_industry(self):
        assert self.elements.org_industry == "manufacturing"

    def test_geographies(self):
        assert "Japan" in self.elements.org_geographies
        assert "Southeast Asia" in self.elements.org_geographies

    def test_ot_connectivity(self):
        assert self.elements.has_ot_connectivity is True

    def test_stock_listed(self):
        assert self.elements.has_stock_listing is True

    def test_crown_jewels_extracted(self):
        assert "CJ-001" in self.elements.crown_jewel_ids
        assert "PLM system" in self.elements.crown_jewel_systems
        assert "critical" in self.elements.crown_jewel_impacts

    def test_project_data_types(self):
        assert "financial" in self.elements.project_data_types
        assert "manufacturing" in self.elements.project_data_types

    def test_project_cloud_providers(self):
        assert "GCP" in self.elements.project_cloud_providers

    def test_active_vendors(self):
        assert "SAP" in self.elements.active_vendors
        assert "Accenture" in self.elements.active_vendors

    def test_source_element_ids(self):
        assert "OBJ-001" in self.elements.source_element_ids
        assert "PROJ-001" in self.elements.source_element_ids
        assert "CJ-001" in self.elements.source_element_ids


class TestTriggerDetection:
    def setup_method(self):
        self.ctx = _load_ctx("sample_context_manufacturing.json")

    def test_ot_trigger(self):
        elements = extract(self.ctx)
        assert "ot_connectivity" in elements.active_triggers

    def test_cloud_migration_trigger(self):
        elements = extract(self.ctx)
        assert "cloud_migration" in elements.active_triggers

    def test_ma_trigger_detected(self):
        # OBJ-001 mentions "M&A候補デューデリジェンス"
        elements = extract(self.ctx)
        assert "m_and_a" in elements.active_triggers

    def test_stock_listing_trigger(self):
        elements = extract(self.ctx)
        assert "ipo_or_listing" in elements.active_triggers

    def test_no_duplicate_triggers(self):
        elements = extract(self.ctx)
        assert len(elements.active_triggers) == len(set(elements.active_triggers))


class TestDedup:
    def test_completed_project_excluded(self):
        ctx = _load_ctx("sample_context_manufacturing.json")
        # Add a completed project with different vendors
        from beacon.ingest.schema import Project

        ctx.projects.append(
            Project(
                id="PROJ-999",
                name="Old System",
                status="completed",
                involved_vendors=["OldVendor"],
                cloud_providers=["AWS"],
                data_types=["hr"],
            )
        )
        elements = extract(ctx)
        assert "OldVendor" not in elements.active_vendors
