"""Tests for pir_builder.py."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from beacon.analysis.asset_mapper import load_asset_tags, map_asset_tags
from beacon.analysis.element_extractor import extract
from beacon.analysis.risk_scorer import RiskScore, score
from beacon.analysis.threat_mapper import load_taxonomy, map_threats
from beacon.generator.pir_builder import PIROutput, build_pirs
from beacon.ingest.schema import BusinessContext

FIXTURES = Path(__file__).parent / "fixtures"


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
    return pirs, risk


class TestManufacturingPIR:
    def setup_method(self):
        self.pirs, self.risk = _build_pipeline("sample_context_manufacturing.json")

    def test_pir_generated_for_high_score(self):
        # Manufacturing × Japan × OT is expected to score ≥ 12
        assert len(self.pirs) >= 1

    def test_pir_id_format(self):
        pir = self.pirs[0]
        assert pir.pir_id.startswith("PIR-")

    def test_valid_from_today(self):
        pir = self.pirs[0]
        today = date.today().isoformat()
        assert pir.valid_from == today

    def test_valid_until_strategic(self):
        pir = self.pirs[0]
        if pir.intelligence_level == "strategic":
            expected = (date.today() + timedelta(days=365)).isoformat()
            assert pir.valid_until == expected

    def test_valid_until_operational(self):
        pir = self.pirs[0]
        if pir.intelligence_level == "operational":
            expected = (date.today() + timedelta(days=180)).isoformat()
            assert pir.valid_until == expected

    def test_threat_actor_tags_populated(self):
        pir = self.pirs[0]
        assert len(pir.threat_actor_tags) > 0

    def test_asset_weight_rules_populated(self):
        pir = self.pirs[0]
        assert len(pir.asset_weight_rules) > 0

    def test_asset_weight_rules_have_required_fields(self):
        pir = self.pirs[0]
        for rule in pir.asset_weight_rules:
            assert "tag" in rule
            assert "criticality_multiplier" in rule
            assert isinstance(rule["criticality_multiplier"], float)

    def test_collection_focus_not_empty(self):
        pir = self.pirs[0]
        assert len(pir.collection_focus) > 0

    def test_source_elements_include_cj(self):
        pir = self.pirs[0]
        assert "CJ-001" in pir.source_elements

    def test_pir_is_sage_compatible(self):
        # Round-trip through model_dump → model_validate
        pir = self.pirs[0]
        dumped = pir.model_dump()
        reloaded = PIROutput.model_validate(dumped)
        assert reloaded.pir_id == pir.pir_id

    def test_risk_score_composite(self):
        pir = self.pirs[0]
        assert pir.risk_score.composite == pir.risk_score.likelihood * pir.risk_score.impact


class TestLowScoreSkipped:
    def test_composite_below_12_returns_empty(self):
        ctx = _load_ctx("sample_context_manufacturing.json")
        elements = extract(ctx)
        # Force a low risk score
        low_risk = RiskScore(
            likelihood=2,
            impact=2,
            composite=4,
            intelligence_level="tactical",
            rationale="test",
        )
        asset_tags_dict = load_asset_tags()
        threat = map_threats(elements, load_taxonomy())
        pirs = build_pirs(elements, threat, low_risk, [], asset_tags_dict)
        assert pirs == []


class TestValidUntilCalculation:
    def test_strategic_365_days(self):
        from beacon.generator.pir_builder import _VALIDITY_DAYS

        assert _VALIDITY_DAYS["strategic"] == 365

    def test_operational_180_days(self):
        from beacon.generator.pir_builder import _VALIDITY_DAYS

        assert _VALIDITY_DAYS["operational"] == 180

    def test_tactical_30_days(self):
        from beacon.generator.pir_builder import _VALIDITY_DAYS

        assert _VALIDITY_DAYS["tactical"] == 30
