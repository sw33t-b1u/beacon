"""Tests for generator/sources_yaml_builder.py."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import yaml
from jsonschema import validate as jvalidate

from beacon.analysis.asset_mapper import load_asset_tags, map_asset_tags
from beacon.analysis.element_extractor import ExtractedElements, extract
from beacon.analysis.risk_scorer import score
from beacon.analysis.threat_mapper import load_taxonomy, map_threats
from beacon.generator.pir_builder import build_pirs
from beacon.generator.sources_yaml_builder import (
    build_sources_candidate_yaml,
    write_sources_candidate,
)
from beacon.ingest.schema import BusinessContext

FIXTURES = Path(__file__).parent / "fixtures"
_FIXED_DATE = date(2026, 4, 4)
_FIXED_DT = datetime(2026, 4, 4, 0, 0, 0)

_TRACE_SCHEMA_PATH = (
    Path(__file__).parent.parent.parent / "TRACE" / "schema" / "sources.schema.json"
)
_TRACE_SCHEMA: dict = json.loads(_TRACE_SCHEMA_PATH.read_text(encoding="utf-8"))


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
    pirs = build_pirs(
        elements, threat, risk, asset_tag_list, asset_tags_dict, generated_on=_FIXED_DATE
    )
    return elements, pirs


class TestFinanceSources:
    """Finance/Japan fixture — exercises strategic+operational+tactical tiers."""

    def setup_method(self):
        self.elements, self.pirs = _build_pipeline("sample_context_finance_banking.json")
        self.yaml_str = build_sources_candidate_yaml(
            self.pirs, self.elements, generated_at=_FIXED_DT
        )
        self.parsed = yaml.safe_load(self.yaml_str)

    def test_schema_valid(self):
        jvalidate(instance=self.parsed, schema=_TRACE_SCHEMA)

    def test_version_is_1(self):
        assert self.parsed["version"] == 1

    def test_sources_list_nonempty(self):
        assert len(self.parsed["sources"]) > 0

    def test_all_pir_ids_covered(self):
        all_pir_ids_in_yaml: set[str] = set()
        for entry in self.parsed["sources"]:
            all_pir_ids_in_yaml.update(entry.get("pir_ids", []))
        expected = {p.pir_id for p in self.pirs}
        assert expected <= all_pir_ids_in_yaml

    def test_all_urls_are_todo(self):
        for entry in self.parsed["sources"]:
            assert "<TODO: fill from candidate>" in entry["url"]

    def test_jpcert_present(self):
        labels = [s["label"] for s in self.parsed["sources"]]
        assert "JPCERT/CC Blog" in labels

    def test_ipa_present(self):
        labels = [s["label"] for s in self.parsed["sources"]]
        assert "IPA Security Alerts" in labels

    def test_fs_isac_present(self):
        labels = [s["label"] for s in self.parsed["sources"]]
        assert "FS-ISAC Threat Intelligence" in labels

    def test_kinyu_isac_present(self):
        labels = [s["label"] for s in self.parsed["sources"]]
        assert "金融ISAC (Japan Financial ISAC)" in labels

    def test_task_field_is_medium(self):
        for entry in self.parsed["sources"]:
            assert entry.get("task") == "medium"

    def test_pir_ids_field_present_on_every_entry(self):
        for entry in self.parsed["sources"]:
            assert "pir_ids" in entry

    def test_byte_deterministic(self):
        yaml_str2 = build_sources_candidate_yaml(self.pirs, self.elements, generated_at=_FIXED_DT)
        assert self.yaml_str == yaml_str2


class TestManufacturingSources:
    """Manufacturing fixture — exercises OT tier and supply_chain cluster."""

    def setup_method(self):
        self.elements, self.pirs = _build_pipeline("sample_context_manufacturing.json")
        self.yaml_str = build_sources_candidate_yaml(
            self.pirs, self.elements, generated_at=_FIXED_DT
        )
        self.parsed = yaml.safe_load(self.yaml_str)

    def test_schema_valid(self):
        jvalidate(instance=self.parsed, schema=_TRACE_SCHEMA)

    def test_all_pir_ids_covered(self):
        all_pir_ids_in_yaml: set[str] = set()
        for entry in self.parsed["sources"]:
            all_pir_ids_in_yaml.update(entry.get("pir_ids", []))
        expected = {p.pir_id for p in self.pirs}
        assert expected <= all_pir_ids_in_yaml

    def test_pir_001_present(self):
        all_pir_ids_in_yaml: set[str] = set()
        for entry in self.parsed["sources"]:
            all_pir_ids_in_yaml.update(entry.get("pir_ids", []))
        assert "PIR-2026-001" in all_pir_ids_in_yaml

    def test_all_urls_are_todo(self):
        for entry in self.parsed["sources"]:
            assert "<TODO: fill from candidate>" in entry["url"]

    def test_byte_deterministic(self):
        yaml_str2 = build_sources_candidate_yaml(self.pirs, self.elements, generated_at=_FIXED_DT)
        assert self.yaml_str == yaml_str2


class TestHeaderContent:
    """Top-of-file header lines and per-entry comment annotations."""

    def setup_method(self):
        self.elements, self.pirs = _build_pipeline("sample_context_finance_banking.json")
        self.yaml_str = build_sources_candidate_yaml(
            self.pirs, self.elements, schema_version="1.0.0", generated_at=_FIXED_DT
        )

    def test_activity_window_warning_present(self):
        assert "ACTIVITY_WINDOW_DAYS" in self.yaml_str

    def test_window_baseline_note(self):
        assert "BEACON 1.0.0 default-window (90-day) baseline" in self.yaml_str

    def test_operator_action_note(self):
        assert "OPERATOR ACTION" in self.yaml_str

    def test_do_not_overwrite_note(self):
        assert "Do NOT overwrite" in self.yaml_str

    def test_cu_gir_citation_present(self):
        assert "CU-GIR" in self.yaml_str

    def test_citations_md_reference(self):
        assert "docs/citations.md" in self.yaml_str

    def test_schema_version_in_header(self):
        assert "schema_version: 1.0.0" in self.yaml_str

    def test_generated_timestamp_in_header(self):
        assert "2026-04-04T00:00:00Z" in self.yaml_str

    def test_tier_annotation_in_comments(self):
        assert "tier:" in self.yaml_str

    def test_region_annotation_in_comments(self):
        assert "region:" in self.yaml_str

    def test_industry_annotation_in_comments(self):
        assert "industry:" in self.yaml_str

    def test_evidence_attack_groups_annotation(self):
        assert "evidence_attack_groups:" in self.yaml_str

    def test_gir_id_hint_annotation(self):
        assert "gir_id_hint:" in self.yaml_str

    def test_feed_url_hint_annotation(self):
        assert "feed_url_hint:" in self.yaml_str


class TestNoPIRs:
    """When no PIRs exist (composite < 12), still emit general candidates."""

    def setup_method(self):
        elements = ExtractedElements(
            org_industry="finance",
            org_unit_name="",
            org_unit_type="company",
            org_geographies=["Japan"],
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
        self.yaml_str = build_sources_candidate_yaml(
            pirs=[], elements=elements, generated_at=_FIXED_DT
        )
        self.parsed = yaml.safe_load(self.yaml_str)

    def test_schema_valid(self):
        jvalidate(instance=self.parsed, schema=_TRACE_SCHEMA)

    def test_sources_nonempty(self):
        assert len(self.parsed["sources"]) > 0

    def test_all_pir_ids_empty(self):
        for entry in self.parsed["sources"]:
            assert entry.get("pir_ids", []) == []

    def test_all_urls_are_todo(self):
        for entry in self.parsed["sources"]:
            assert "<TODO: fill from candidate>" in entry["url"]


class TestSourcesSortedAlphabetically:
    """Entries are sorted by label for byte-determinism."""

    def test_labels_sorted(self):
        elements, pirs = _build_pipeline("sample_context_finance_banking.json")
        yaml_str = build_sources_candidate_yaml(pirs, elements, generated_at=_FIXED_DT)
        parsed = yaml.safe_load(yaml_str)
        labels = [s["label"] for s in parsed["sources"]]
        assert labels == sorted(labels)


class TestWriteSourcesCandidate:
    """write_sources_candidate creates the file at the given path."""

    def test_writes_file(self, tmp_path):
        yaml_content = "version: 1\nsources: []\n"
        out = tmp_path / "sources_candidate.yaml"
        write_sources_candidate(yaml_content, out)
        assert out.exists()
        assert out.read_text(encoding="utf-8") == yaml_content

    def test_creates_parent_dir(self, tmp_path):
        yaml_content = "version: 1\nsources: []\n"
        out = tmp_path / "output" / "sources_candidate.yaml"
        write_sources_candidate(yaml_content, out)
        assert out.exists()

    def test_overwrites_existing(self, tmp_path):
        out = tmp_path / "sources_candidate.yaml"
        out.write_text("old", encoding="utf-8")
        write_sources_candidate("new", out)
        assert out.read_text(encoding="utf-8") == "new"
