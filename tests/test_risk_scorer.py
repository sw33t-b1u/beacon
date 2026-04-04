"""Tests for risk_scorer.py."""

from __future__ import annotations

import json
from pathlib import Path

from beacon.analysis.element_extractor import extract
from beacon.analysis.risk_scorer import RiskScore, score
from beacon.analysis.threat_mapper import load_taxonomy, map_threats
from beacon.ingest.schema import BusinessContext

FIXTURES = Path(__file__).parent / "fixtures"


def _load_ctx(filename: str) -> BusinessContext:
    data = json.loads((FIXTURES / filename).read_text(encoding="utf-8"))
    return BusinessContext.model_validate(data)


class TestManufacturingRiskScore:
    def setup_method(self):
        ctx = _load_ctx("sample_context_manufacturing.json")
        self.elements = extract(ctx)
        self.threat = map_threats(self.elements, load_taxonomy())
        self.risk = score(self.elements, self.threat)

    def test_composite_is_likelihood_times_impact(self):
        assert self.risk.composite == self.risk.likelihood * self.risk.impact

    def test_composite_in_valid_range(self):
        assert 1 <= self.risk.composite <= 25

    def test_likelihood_boosted_by_trigger(self):
        # ot_connectivity is a high-risk trigger → likelihood boosted
        assert self.risk.likelihood >= 3

    def test_impact_reflects_critical_crown_jewel(self):
        # CJ-001 has business_impact=critical → impact should be 5
        assert self.risk.impact == 5

    def test_intelligence_level_is_string(self):
        assert self.risk.intelligence_level in {"strategic", "operational", "tactical"}

    def test_high_score_yields_strategic_level(self):
        # Manufacturing × Japan × critical CJ → likely strategic
        if self.risk.composite >= 20:
            assert self.risk.intelligence_level == "strategic"

    def test_rationale_not_empty(self):
        assert len(self.risk.rationale) > 0


class TestIntelligenceLevelRecommendation:
    def _make_risk(self, likelihood: int, impact: int, triggers: list[str]) -> RiskScore:
        from beacon.analysis.risk_scorer import _recommend_level

        composite = likelihood * impact
        level = _recommend_level(composite, triggers)
        return RiskScore(
            likelihood=likelihood,
            impact=impact,
            composite=composite,
            intelligence_level=level,
            rationale="test",
        )

    def test_strategic_at_20_plus(self):
        r = self._make_risk(4, 5, [])
        assert r.intelligence_level == "strategic"

    def test_operational_at_12_to_19(self):
        r = self._make_risk(3, 5, [])  # composite=15
        assert r.intelligence_level == "operational"

    def test_tactical_below_12(self):
        r = self._make_risk(2, 4, [])  # composite=8
        assert r.intelligence_level == "tactical"

    def test_trigger_escalates_tactical_to_operational(self):
        r = self._make_risk(2, 3, ["ot_connectivity"])  # composite=6, but trigger escalates
        assert r.intelligence_level == "operational"

    def test_no_escalation_without_high_risk_trigger(self):
        r = self._make_risk(2, 3, ["cloud_migration"])  # composite=6, cloud_migration ≠ escalation
        assert r.intelligence_level == "tactical"
