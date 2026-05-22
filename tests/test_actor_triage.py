"""Tests for beacon/analysis/actor_triage.py — I×C×O actor prioritization."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from beacon.analysis.actor_triage import (
    DataQualityComponent,
    PrioritizedActor,
    ScoreBreakdown,
    geographic_match,
    industry_match,
    motivation_alignment,
    prioritize_actors,
    recency_active_campaigns_90d,
    sophistication_score,
    ttp_count_norm,
    victimology_match,
)
from beacon.ingest.misp_client import MispClient
from beacon.ingest.schema import BusinessContext

FIXTURES = Path(__file__).parent / "fixtures"
SCHEMA_DIR = Path(__file__).parents[2] / "schema"

_REAL_TAXONOMY_PATH = SCHEMA_DIR / "threat_taxonomy.json"
_REAL_SURFACE_MAP_PATH = SCHEMA_DIR / "surface_ttp_map.json"
_TRIAGE_MISP_FIXTURE = FIXTURES / "actor_triage_misp_fixture.json"
_FINANCE_CONTEXT_FIXTURE = FIXTURES / "sample_context_finance_banking.json"


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _make_mini_taxonomy(
    *,
    actor_name: str = "TestActor",
    target_industries: list[str] | None = None,
    target_geographies: list[str] | None = None,
    priority_ttps: list[str] | None = None,
    technique_count: int = 10,
    sophistication_tier: str = "intermediate",
    campaign_last_seen: str | None = None,
    category: str = "state_sponsored",
    sponsor: str = "Fictional",
) -> dict:
    """Build a minimal taxonomy dict with a single actor for unit tests."""
    profile = {
        "technique_count": technique_count,
        "software_count": 0,
        "sophistication_tier": sophistication_tier,
        "campaign_last_seen": campaign_last_seen,
    }
    cat_data = {
        "mitre_groups": [actor_name],
        "target_industries": target_industries or [],
        "target_geographies": target_geographies or [],
        "priority_ttps": priority_ttps or [],
        "tags": [],
    }
    if category == "state_sponsored":
        cats = {"state_sponsored": {sponsor: cat_data}}
    else:
        cats = {category: cat_data}

    return {
        "actor_categories": cats,
        "intrusion_set_profiles": {actor_name: profile},
    }


def _make_empty_surface_map() -> dict:
    return {"surface_ttp_map": {}}


def _finance_context() -> BusinessContext:
    return BusinessContext.model_validate(_load_json(_FINANCE_CONTEXT_FIXTURE))


# ---------------------------------------------------------------------------
# Unit tests: motivation_alignment
# ---------------------------------------------------------------------------


class TestMotivationAlignment:
    def test_matching_motivation_returns_one(self):
        assert motivation_alignment("personal-gain", ["personal-gain", "ideology"]) == 1.0

    def test_non_matching_motivation_returns_zero(self):
        assert motivation_alignment("coercion", ["personal-gain", "ideology"]) == 0.0

    def test_none_motivation_returns_half(self):
        assert motivation_alignment(None, ["personal-gain"]) == 0.5

    def test_empty_expected_list_non_matching(self):
        assert motivation_alignment("ideology", []) == 0.0

    def test_empty_expected_list_none_actor(self):
        assert motivation_alignment(None, []) == 0.5


# ---------------------------------------------------------------------------
# Unit tests: industry_match
# ---------------------------------------------------------------------------


class TestIndustryMatch:
    def test_identical_sets_return_one(self):
        assert industry_match(["Private sector"], ["Private sector"]) == 1.0

    def test_no_overlap_returns_zero(self):
        assert industry_match(["Military"], ["Private sector"]) == 0.0

    def test_partial_overlap_jaccard(self):
        # |{A,B} ∩ {B,C}| / |{A,B,C}| = 1/3
        score = industry_match(["A", "B"], ["B", "C"])
        assert abs(score - 1 / 3) < 1e-9

    def test_empty_actor_returns_neutral(self):
        assert industry_match([], ["Private sector"]) == 0.5

    def test_empty_business_returns_neutral(self):
        assert industry_match(["Private sector"], []) == 0.5

    def test_both_empty_returns_neutral(self):
        assert industry_match([], []) == 0.5


# ---------------------------------------------------------------------------
# Unit tests: sophistication_score
# ---------------------------------------------------------------------------


class TestSophisticationScore:
    def test_none_returns_zero(self):
        assert sophistication_score(None) == 0.0

    def test_none_string_returns_zero(self):
        assert sophistication_score("none") == 0.0

    def test_minimal_returns_one_sixth(self):
        assert abs(sophistication_score("minimal") - 1 / 6) < 1e-9

    def test_intermediate_returns_two_sixth(self):
        assert abs(sophistication_score("intermediate") - 2 / 6) < 1e-9

    def test_advanced_returns_half(self):
        assert abs(sophistication_score("advanced") - 3 / 6) < 1e-9

    def test_expert_returns_four_sixth(self):
        assert abs(sophistication_score("expert") - 4 / 6) < 1e-9

    def test_innovator_returns_five_sixth(self):
        assert abs(sophistication_score("innovator") - 5 / 6) < 1e-9

    def test_strategic_returns_one(self):
        assert sophistication_score("strategic") == 1.0

    def test_invalid_ov_returns_zero(self):
        assert sophistication_score("godlike") == 0.0

    def test_empty_string_returns_zero(self):
        assert sophistication_score("") == 0.0


# ---------------------------------------------------------------------------
# Unit tests: ttp_count_norm
# ---------------------------------------------------------------------------


class TestTtpCountNorm:
    def test_zero_returns_zero(self):
        assert ttp_count_norm(0) == 0.0

    def test_fifty_returns_half(self):
        assert ttp_count_norm(50) == 0.5

    def test_hundred_returns_one(self):
        assert ttp_count_norm(100) == 1.0

    def test_above_hundred_capped(self):
        assert ttp_count_norm(150) == 1.0
        assert ttp_count_norm(200) == 1.0

    def test_ten_returns_point_one(self):
        assert abs(ttp_count_norm(10) - 0.1) < 1e-9


# ---------------------------------------------------------------------------
# Unit tests: recency_active_campaigns_90d
# ---------------------------------------------------------------------------

_REF = datetime(2026, 5, 22, 12, 0, 0, tzinfo=UTC)


class TestRecencyActiveCampaigns90d:
    def test_none_returns_zero(self):
        assert recency_active_campaigns_90d(None, reference=_REF) == 0.0

    def test_within_90_days_returns_one(self):
        # 30 days before _REF = 2026-04-22
        assert recency_active_campaigns_90d("2026-04-22T00:00:00Z", reference=_REF) == 1.0

    def test_exactly_90_days_returns_one(self):
        # 90 days before _REF = 2026-02-21
        assert recency_active_campaigns_90d("2026-02-21T00:00:00Z", reference=_REF) == 1.0

    def test_within_365_days_returns_half(self):
        # 200 days before _REF = 2025-11-03
        assert recency_active_campaigns_90d("2025-11-03T00:00:00Z", reference=_REF) == 0.5

    def test_within_3_years_returns_quarter(self):
        # ~500 days before _REF = 2025-01-07
        assert recency_active_campaigns_90d("2025-01-07T00:00:00Z", reference=_REF) == 0.25

    def test_older_than_3_years_returns_zero(self):
        # 4 years ago = 2022-05-22
        assert recency_active_campaigns_90d("2022-05-22T00:00:00Z", reference=_REF) == 0.0

    def test_handles_milliseconds_in_timestamp(self):
        # ATT&CK STIX bundle format
        assert recency_active_campaigns_90d("2026-04-22T00:00:00.000Z", reference=_REF) == 1.0

    def test_malformed_timestamp_returns_zero(self):
        assert recency_active_campaigns_90d("not-a-date", reference=_REF) == 0.0


# ---------------------------------------------------------------------------
# Unit tests: victimology_match
# ---------------------------------------------------------------------------


class TestVictimologyMatch:
    def test_overlap_returns_one(self):
        assert victimology_match(["Private sector", "Government"], ["Private sector"]) == 1.0

    def test_no_overlap_returns_zero(self):
        assert victimology_match(["Military"], ["Private sector"]) == 0.0

    def test_empty_actor_returns_neutral(self):
        assert victimology_match([], ["Private sector"]) == 0.5

    def test_empty_business_returns_neutral(self):
        assert victimology_match(["Private sector"], []) == 0.5


# ---------------------------------------------------------------------------
# Unit tests: geographic_match
# ---------------------------------------------------------------------------


class TestGeographicMatch:
    def test_overlap_jaccard(self):
        # {US, JP} ∩ {JP, DE} = {JP} / {US, JP, DE} = 1/3
        score = geographic_match(["United States", "Japan"], ["Japan", "Germany"])
        assert abs(score - 1 / 3) < 1e-9

    def test_no_overlap_returns_zero(self):
        assert geographic_match(["Russia"], ["Japan"]) == 0.0

    def test_empty_actor_returns_neutral(self):
        assert geographic_match([], ["Japan"]) == 0.5

    def test_empty_business_returns_neutral(self):
        assert geographic_match(["Japan"], []) == 0.5

    def test_exact_match_returns_one(self):
        assert geographic_match(["Japan"], ["Japan"]) == 1.0


# ---------------------------------------------------------------------------
# Intent == 0 hard-gate tests — exclusion semantics (Plan §3.2)
# Actor with Intent==0 must be EXCLUDED from prioritized_actors[], not emitted.
# ---------------------------------------------------------------------------

_GHOST_ACTOR_ID = "ghostactor"
_APT29_ACTOR_ID = "apt29"

# Two-actor taxonomy for intent-gate tests: GhostActor (Intent=0) + APT29 (Intent>0).
_TWO_ACTOR_TAXONOMY = {
    "actor_categories": {
        "state_sponsored": {
            "Russia": {
                "mitre_groups": ["APT29"],
                "target_industries": ["Government", "Private sector"],
                "target_geographies": ["United States", "Japan", "Germany"],
                "priority_ttps": [],
                "tags": [],
            },
            "Fictional": {
                "mitre_groups": ["GhostActor"],
                "target_industries": ["Military"],
                "target_geographies": ["North Korea"],
                "priority_ttps": [],
                "tags": [],
            },
        },
    },
    "intrusion_set_profiles": {
        "APT29": {
            "technique_count": 66,
            "software_count": 49,
            "sophistication_tier": "expert",
            "campaign_last_seen": "2021-01-01T06:00:00.000Z",
        },
        "GhostActor": {
            "technique_count": 5,
            "software_count": 0,
            "sophistication_tier": "minimal",
            "campaign_last_seen": None,
        },
    },
}


class TestIntentGateExclusion:
    """Intent==0 actor is excluded from prioritized_actors[] (not emitted with score=0)."""

    def setup_method(self):
        self.misp = MispClient(cache_path=_TRIAGE_MISP_FIXTURE)
        self.surface_map = _make_empty_surface_map()
        self.bctx = _finance_context()

    def test_single_intent_zero_actor_produces_empty_results(self):
        """Single GhostActor (Intent=0): results list is empty."""
        taxonomy = _make_mini_taxonomy(
            actor_name="GhostActor",
            target_industries=["Military"],
            target_geographies=["North Korea"],
            technique_count=5,
            sophistication_tier="minimal",
        )
        results = prioritize_actors(self.bctx, taxonomy, self.surface_map, self.misp)
        assert len(results) == 0

    def test_ghost_actor_not_in_results(self):
        """GhostActor must not appear in results when Intent==0."""
        results = prioritize_actors(self.bctx, _TWO_ACTOR_TAXONOMY, self.surface_map, self.misp)
        assert all(r.actor_id != _GHOST_ACTOR_ID for r in results)

    def test_intent_zero_actor_excluded_from_results(self):
        """Two-actor fixture: Intent==0 actor excluded, Intent>0 actor retained."""
        results = prioritize_actors(self.bctx, _TWO_ACTOR_TAXONOMY, self.surface_map, self.misp)
        # GhostActor: coercion × Military → Intent=0 → excluded
        assert all(r.actor_id != _GHOST_ACTOR_ID for r in results)
        # APT29: None(0.5) × Private sector(0.5) → Intent=0.25 → included
        apt29_entries = [r for r in results if r.actor_id == _APT29_ACTOR_ID]
        assert len(apt29_entries) == 1

    def test_intent_zero_produces_exactly_one_remaining_actor(self):
        """With two actors and one excluded, exactly one result remains."""
        results = prioritize_actors(self.bctx, _TWO_ACTOR_TAXONOMY, self.surface_map, self.misp)
        assert len(results) == 1
        assert results[0].actor_id == _APT29_ACTOR_ID

    def test_remaining_actor_likelihood_in_range(self):
        """Retained actor's likelihood stays in [0, 1]."""
        results = prioritize_actors(self.bctx, _TWO_ACTOR_TAXONOMY, self.surface_map, self.misp)
        assert 0.0 <= results[0].likelihood <= 1.0

    def test_motivation_alignment_zero_for_coercion(self):
        """Direct sub-factor check: 'coercion' not in finance expected motivations."""
        assert motivation_alignment("coercion", ["personal-gain", "organizational-gain"]) == 0.0

    def test_industry_match_zero_for_military_vs_private(self):
        """Direct sub-factor check: Military ∩ Private sector = ∅ → 0.0."""
        assert industry_match(["Military"], ["Private sector"]) == 0.0

    def test_intent_product_is_zero_when_one_factor_is_zero(self):
        """Product form: if either sub-factor is 0, intent = 0."""
        # motivation_alignment = 0.0, industry_match = 0.5
        mot = motivation_alignment("coercion", ["personal-gain"])
        ind = industry_match(["Military"], ["Private sector"])
        assert mot == 0.0
        assert ind == 0.0
        assert min(max(mot * ind, 0.0), 1.0) == 0.0


# ---------------------------------------------------------------------------
# Degraded flag test — when MispClient returns None for an actor
# ---------------------------------------------------------------------------


class TestDegradedFlagWhenMispReturnsNone:
    """Actor not in MISP fixture → degraded=True, result still produced (no exception)."""

    def setup_method(self):
        # MISP fixture has no entry for "APT28" → degraded path.
        # target_industries includes "Private sector" so industry_match > 0 and
        # Intent > 0 with product form (actor stays in results for degraded checks).
        self.misp = MispClient(cache_path=_TRIAGE_MISP_FIXTURE)
        self.taxonomy = _make_mini_taxonomy(
            actor_name="APT28",
            target_industries=["Private sector", "Defense"],
            target_geographies=["Germany", "United States"],
            technique_count=93,
            sophistication_tier="expert",
            campaign_last_seen="2024-11-01T04:00:00.000Z",
        )
        self.surface_map = _make_empty_surface_map()
        self.bctx = _finance_context()

    def test_result_is_produced_not_none(self):
        results = prioritize_actors(self.bctx, self.taxonomy, self.surface_map, self.misp)
        assert results is not None
        assert len(results) == 1

    def test_no_exception_raised(self):
        # This just asserts the call completes without raising
        prioritize_actors(self.bctx, self.taxonomy, self.surface_map, self.misp)

    def test_degraded_flag_is_true(self):
        results = prioritize_actors(self.bctx, self.taxonomy, self.surface_map, self.misp)
        dq: DataQualityComponent = results[0].score_breakdown.data_quality
        assert dq.degraded is True

    def test_missing_sources_contains_misp_galaxy(self):
        results = prioritize_actors(self.bctx, self.taxonomy, self.surface_map, self.misp)
        dq: DataQualityComponent = results[0].score_breakdown.data_quality
        assert "misp_galaxy" in dq.missing_sources

    def test_likelihood_still_in_range(self):
        results = prioritize_actors(self.bctx, self.taxonomy, self.surface_map, self.misp)
        assert 0.0 <= results[0].likelihood <= 1.0


# ---------------------------------------------------------------------------
# Integration test — real taxonomy + real surface_ttp_map
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_prioritize_actors_full_taxonomy():
    """Full prioritize_actors() against real Phase 1 artifacts."""
    if not _REAL_TAXONOMY_PATH.exists():
        pytest.skip(f"Real taxonomy not found at {_REAL_TAXONOMY_PATH}")
    if not _REAL_SURFACE_MAP_PATH.exists():
        pytest.skip(f"Real surface map not found at {_REAL_SURFACE_MAP_PATH}")

    taxonomy = _load_json(_REAL_TAXONOMY_PATH)
    surface_map = _load_json(_REAL_SURFACE_MAP_PATH)
    misp = MispClient(cache_path=_TRIAGE_MISP_FIXTURE)
    bctx = _finance_context()

    results = prioritize_actors(bctx, taxonomy, surface_map, misp)

    assert len(results) > 0, "Expected at least one PrioritizedActor"
    for actor in results:
        assert 0.0 <= actor.likelihood <= 1.0, (
            f"{actor.name}: likelihood {actor.likelihood} out of [0,1]"
        )

    # Verify descending sort
    likelihoods = [a.likelihood for a in results]
    assert likelihoods == sorted(likelihoods, reverse=True), "Results must be sorted descending"

    # At least one actor should have likelihood > 0
    assert any(a.likelihood > 0.0 for a in results), "Expected at least one actor with L > 0"


@pytest.mark.integration
def test_apt29_in_finance_banking_result():
    """APT29 should appear in results when evaluated against a finance-banking org."""
    if not _REAL_TAXONOMY_PATH.exists():
        pytest.skip(f"Real taxonomy not found at {_REAL_TAXONOMY_PATH}")

    taxonomy = _load_json(_REAL_TAXONOMY_PATH)
    if _REAL_SURFACE_MAP_PATH.exists():
        surface_map = _load_json(_REAL_SURFACE_MAP_PATH)
    else:
        surface_map = _make_empty_surface_map()
    misp = MispClient(cache_path=_TRIAGE_MISP_FIXTURE)
    bctx = _finance_context()

    results = prioritize_actors(bctx, taxonomy, surface_map, misp)
    names = {a.name for a in results}
    assert "APT29" in names, "APT29 must appear in triage results"

    apt29 = next(a for a in results if a.name == "APT29")
    assert isinstance(apt29, PrioritizedActor)
    assert isinstance(apt29.score_breakdown, ScoreBreakdown)
    assert 0.0 <= apt29.likelihood <= 1.0

    # APT29 from fixture has sophistication="expert" in MISP cache
    assert apt29.score_breakdown.capability.sophistication_score > 0.0

    # APT29 aliases should be populated from MISP fixture
    assert len(apt29.aliases) > 0
