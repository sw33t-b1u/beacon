"""In-process PIR round-trip test: BEACON PIROutput → TRACE PIRItem contract.

Validates that PIROutput (BEACON producer) serialises into a shape that
PIRItem (TRACE consumer) can parse without error.  This test intentionally
does NOT depend on TRACE being checked out: it either imports PIRItem from
the installed trace_engine package or falls back to a minimal inline
model that mirrors the required fields from §2.2 of the plan.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from beacon.analysis.asset_mapper import load_asset_tags, map_asset_tags
from beacon.analysis.element_extractor import extract
from beacon.analysis.risk_scorer import score
from beacon.analysis.threat_mapper import load_taxonomy, map_threats
from beacon.generator.pir_builder import PIROutput, PIROutputDocument, build_pirs
from beacon.ingest.schema import BusinessContext

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Try to import the real PIRItem; fall back to a minimal inline replica.
# ---------------------------------------------------------------------------
try:
    from trace_engine.validate.schema.models import PIRItem as _TracePIRItem  # type: ignore[import]

    _TRACE_AVAILABLE = True
    PIRItem = _TracePIRItem
except ImportError:
    _TRACE_AVAILABLE = False

    # Minimal replica of TRACE's PIRItem that covers the required fields
    # (§2.2 / §2.3 of the plan).  Extra fields are accepted via extra="allow".
    from pydantic import BaseModel, ConfigDict, Field, model_validator

    class _AssetWeightRule(BaseModel):
        model_config = ConfigDict(extra="allow")
        tag: str
        criticality_multiplier: float

    class PIRItem(BaseModel):  # type: ignore[no-redef]
        model_config = ConfigDict(extra="allow")

        pir_id: str
        threat_actor_tags: list[str] = Field(default_factory=list)
        asset_weight_rules: list[_AssetWeightRule] = Field(default_factory=list)
        valid_from: date
        valid_until: date
        organizational_scope: str | None = None
        description: str | None = None
        intelligence_level: str | None = None

        @model_validator(mode="after")
        def _check_window(self) -> PIRItem:
            if self.valid_from >= self.valid_until:
                raise ValueError("valid_from must be earlier than valid_until")
            return self


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_pirs_from_fixture(filename: str) -> list[PIROutput]:
    data = json.loads((FIXTURES / filename).read_text(encoding="utf-8"))
    ctx = BusinessContext.model_validate(data)
    elements = extract(ctx)
    taxonomy = load_taxonomy()
    asset_tags_dict = load_asset_tags()
    asset_tag_list = map_asset_tags(elements, asset_tags_dict)
    threat = map_threats(elements, taxonomy)
    risk = score(elements, threat)
    return build_pirs(elements, threat, risk, asset_tag_list, asset_tags_dict)


def _build_minimal_pir() -> PIROutput:
    """Construct a PIROutput directly without going through the full pipeline."""
    from beacon.generator.pir_builder import RiskScoreModel

    today = date.today()
    return PIROutput(
        pir_id="PIR-2026-001",
        intelligence_level="operational",
        organizational_scope="Engineering (division)",
        decision_point="How will ransomware threats impact core systems?",
        description="Ransomware risk to engineering assets.",
        rationale="High composite score due to OT exposure.",
        recommended_action="Review segmentation controls.",
        threat_actor_tags=["ransomware", "state_sponsored.Russia"],
        notable_groups=["LockBit", "Black Basta"],
        asset_weight_rules=[{"tag": "ot", "criticality_multiplier": 2.0}],
        collection_focus=["Monitor ICS-CERT advisories"],
        valid_from=today.isoformat(),
        valid_until=(today + timedelta(days=180)).isoformat(),
        risk_score=RiskScoreModel(likelihood=4, impact=5, composite=20),
        source_elements=["CJ-001"],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPIRRoundtripMinimal:
    """Round-trip a directly-constructed PIROutput through PIRItem."""

    def test_minimal_pir_validates(self):
        pir = _build_minimal_pir()
        payload = json.loads(pir.model_dump_json())
        item = PIRItem.model_validate(payload)
        assert item.pir_id == pir.pir_id

    def test_valid_from_coerced_to_date(self):
        pir = _build_minimal_pir()
        payload = json.loads(pir.model_dump_json())
        item = PIRItem.model_validate(payload)
        assert isinstance(item.valid_from, date)

    def test_valid_until_coerced_to_date(self):
        pir = _build_minimal_pir()
        payload = json.loads(pir.model_dump_json())
        item = PIRItem.model_validate(payload)
        assert isinstance(item.valid_until, date)

    def test_validity_window_positive(self):
        pir = _build_minimal_pir()
        payload = json.loads(pir.model_dump_json())
        item = PIRItem.model_validate(payload)
        assert item.valid_until > item.valid_from

    def test_asset_weight_rules_parsed(self):
        pir = _build_minimal_pir()
        payload = json.loads(pir.model_dump_json())
        item = PIRItem.model_validate(payload)
        assert len(item.asset_weight_rules) == 1
        rule = item.asset_weight_rules[0]
        assert rule.tag == "ot"
        assert rule.criticality_multiplier == 2.0

    def test_intelligence_level_preserved(self):
        pir = _build_minimal_pir()
        payload = json.loads(pir.model_dump_json())
        item = PIRItem.model_validate(payload)
        assert item.intelligence_level == "operational"

    def test_trace_import_indicator(self):
        """Document whether the real TRACE PIRItem was used or the inline replica."""
        if _TRACE_AVAILABLE:
            assert PIRItem.__module__.startswith("trace_engine")
        else:
            pytest.skip("trace_engine not installed — inline replica used (expected in CI)")


class TestPIRRoundtripFromFixture:
    """Round-trip manufacturing-fixture PIRs through PIRItem."""

    def setup_method(self):
        self.pirs = _build_pirs_from_fixture("sample_context_manufacturing.json")

    def test_at_least_one_pir_generated(self):
        assert len(self.pirs) >= 1

    def test_all_pirs_validate_as_pir_item(self):
        for pir in self.pirs:
            payload = json.loads(pir.model_dump_json())
            item = PIRItem.model_validate(payload)
            assert item.pir_id == pir.pir_id

    def test_all_pirs_have_valid_date_window(self):
        for pir in self.pirs:
            payload = json.loads(pir.model_dump_json())
            item = PIRItem.model_validate(payload)
            assert item.valid_until > item.valid_from


# ---------------------------------------------------------------------------
# Phase 3 — PIROutputDocument schema_version roundtrip
# ---------------------------------------------------------------------------


class TestPIRDocumentSchemaVersionRoundtrip:
    """schema_version survives emit -> reparse -> equality."""

    def _make_doc(self) -> PIROutputDocument:
        return PIROutputDocument(pirs=_build_pirs_from_fixture("sample_context_manufacturing.json"))

    def test_schema_version_present_after_roundtrip(self):
        doc = self._make_doc()
        serialised = doc.model_dump_json()
        reparsed = PIROutputDocument.model_validate_json(serialised)
        assert reparsed.schema_version == doc.schema_version

    def test_schema_version_value_after_roundtrip(self):
        doc = self._make_doc()
        reparsed = PIROutputDocument.model_validate_json(doc.model_dump_json())
        assert reparsed.schema_version == "0.18.0"

    def test_pirs_count_preserved_after_roundtrip(self):
        doc = self._make_doc()
        reparsed = PIROutputDocument.model_validate_json(doc.model_dump_json())
        assert len(reparsed.pirs) == len(doc.pirs)

    def test_pir_ids_preserved_after_roundtrip(self):
        doc = self._make_doc()
        reparsed = PIROutputDocument.model_validate_json(doc.model_dump_json())
        for orig, parsed in zip(doc.pirs, reparsed.pirs):
            assert parsed.pir_id == orig.pir_id
