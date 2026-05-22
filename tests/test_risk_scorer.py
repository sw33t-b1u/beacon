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

    def test_likelihood_boosted_by_any_trigger(self):
        # Manufacturing fixture activates multiple triggers (it_ot_convergence,
        # cloud_dependency, third_party_dependency, sectoral_high_risk,
        # regulated_disclosure_scope) — any one is enough for the +1 boost.
        assert self.threat.active_triggers
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

    def test_any_trigger_escalates_tactical_to_operational(self):
        # Symmetric escalation per NIST SP 800-37 R2 — any trigger lifts level.
        for trigger in [
            "cloud_dependency",
            "it_ot_convergence",
            "third_party_dependency",
            "external_facing_exposure",
            "regulated_disclosure_scope",
            "sectoral_high_risk",
            "ai_adoption_exposure",
        ]:
            r = self._make_risk(2, 3, [trigger])  # composite=6, trigger lifts to operational
            assert r.intelligence_level == "operational", trigger

    def test_no_escalation_when_no_triggers(self):
        r = self._make_risk(2, 3, [])  # composite=6, no triggers → tactical
        assert r.intelligence_level == "tactical"


# ---------------------------------------------------------------------------
# Phase 4 — top_actor_likelihood boost tests
# ---------------------------------------------------------------------------


class TestActorTriageBoost:
    """risk_scorer.score() boosts likelihood by +1 when top_actor_likelihood >= 0.05."""

    def setup_method(self):
        ctx = json.loads(
            (FIXTURES / "sample_context_manufacturing.json").read_text(encoding="utf-8")
        )
        from beacon.ingest.schema import BusinessContext  # noqa: PLC0415

        self.elements = extract(BusinessContext.model_validate(ctx))
        self.threat = map_threats(self.elements, load_taxonomy())

    def test_no_boost_below_threshold(self):
        baseline = score(self.elements, self.threat, top_actor_likelihood=0.0)
        boosted = score(self.elements, self.threat, top_actor_likelihood=0.04)
        assert boosted.likelihood == baseline.likelihood

    def test_boost_at_threshold(self):
        baseline = score(self.elements, self.threat, top_actor_likelihood=0.0)
        boosted = score(self.elements, self.threat, top_actor_likelihood=0.05)
        if baseline.likelihood < 5:
            assert boosted.likelihood == baseline.likelihood + 1
        else:
            assert boosted.likelihood == 5  # capped

    def test_boost_above_threshold(self):
        baseline = score(self.elements, self.threat, top_actor_likelihood=0.0)
        boosted = score(self.elements, self.threat, top_actor_likelihood=0.9)
        assert boosted.likelihood == min(baseline.likelihood + 1, 5)

    def test_boost_capped_at_five(self):
        """Even with a very high actor likelihood, risk likelihood stays ≤ 5."""
        boosted = score(self.elements, self.threat, top_actor_likelihood=1.0)
        assert boosted.likelihood <= 5

    def test_backward_compat_zero_default(self):
        """Calling score() without top_actor_likelihood is backward-compatible."""
        without = score(self.elements, self.threat)
        with_zero = score(self.elements, self.threat, top_actor_likelihood=0.0)
        assert without.likelihood == with_zero.likelihood
