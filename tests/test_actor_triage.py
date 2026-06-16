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
    evasion_capability_score,
    geographic_match,
    industry_match,
    motivation_alignment,
    prioritize_actors,
    recency_active_campaigns,
    sophistication_score,
    targeting_persistence_score,
    tool_usage_score,
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
# Unit tests: recency_active_campaigns (window_days default=90)
# ---------------------------------------------------------------------------

_REF = datetime(2026, 5, 22, 12, 0, 0, tzinfo=UTC)


class TestRecencyActiveCampaigns:
    def test_none_returns_zero(self):
        assert recency_active_campaigns(None, reference=_REF) == 0.0

    def test_within_90_days_returns_one(self):
        # 30 days before _REF = 2026-04-22
        assert recency_active_campaigns("2026-04-22T00:00:00Z", reference=_REF) == 1.0

    def test_exactly_90_days_returns_one(self):
        # 90 days before _REF = 2026-02-21
        assert recency_active_campaigns("2026-02-21T00:00:00Z", reference=_REF) == 1.0

    def test_within_365_days_returns_half(self):
        # 200 days before _REF = 2025-11-03
        assert recency_active_campaigns("2025-11-03T00:00:00Z", reference=_REF) == 0.5

    def test_within_3_years_returns_quarter(self):
        # ~500 days before _REF = 2025-01-07
        assert recency_active_campaigns("2025-01-07T00:00:00Z", reference=_REF) == 0.25

    def test_older_than_3_years_returns_zero(self):
        # 4 years ago = 2022-05-22
        assert recency_active_campaigns("2022-05-22T00:00:00Z", reference=_REF) == 0.0

    def test_handles_milliseconds_in_timestamp(self):
        # ATT&CK STIX bundle format
        assert recency_active_campaigns("2026-04-22T00:00:00.000Z", reference=_REF) == 1.0

    def test_malformed_timestamp_returns_zero(self):
        assert recency_active_campaigns("not-a-date", reference=_REF) == 0.0

    # Window=180 tests — 2025-12-15 is 158 days before _REF (between 90 and 180)
    def test_window_180_activates_for_158_day_old_campaign(self):
        # 158d < 180 → 1.0 with window=180; 0.5 with default window=90
        assert (
            recency_active_campaigns("2025-12-15T00:00:00Z", reference=_REF, window_days=180) == 1.0
        )

    def test_window_90_returns_half_for_158_day_old_campaign(self):
        # Same date, default window=90 → 0.5
        assert recency_active_campaigns("2025-12-15T00:00:00Z", reference=_REF) == 0.5

    def test_window_180_boundary_at_180_days(self):
        # Exactly 180 days before _REF = 2025-11-23 (180d boundary → 1.0)
        assert (
            recency_active_campaigns("2025-11-23T00:00:00Z", reference=_REF, window_days=180) == 1.0
        )

    def test_window_180_beyond_boundary_returns_half(self):
        # 200d before ref = 2025-11-03 → > 180 window → 0.5
        assert (
            recency_active_campaigns("2025-11-03T00:00:00Z", reference=_REF, window_days=180) == 0.5
        )


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


# ---------------------------------------------------------------------------
# New scoring function unit tests — Phase 1 (Initiative E)
# ---------------------------------------------------------------------------


class TestToolSophisticationScore:
    def test_zero_software(self):
        assert tool_usage_score(0) == 0.0

    def test_fifty_software_is_max(self):
        assert tool_usage_score(50) == 1.0

    def test_above_fifty_capped(self):
        assert tool_usage_score(100) == 1.0

    def test_twenty_five_software(self):
        assert tool_usage_score(25) == pytest.approx(0.5)

    def test_ten_software(self):
        assert tool_usage_score(10) == pytest.approx(0.2)


class TestTargetingPersistenceScore:
    def test_zero_campaigns_returns_zero(self):
        assert targeting_persistence_score(0, None, None) == 0.0

    def test_single_campaign_no_span(self):
        # count_norm=0.2, span_norm=0 → (0.2+0)/2=0.1
        assert targeting_persistence_score(1, None, "2025-01-01T00:00:00Z") == pytest.approx(0.1)

    def test_single_campaign_with_span(self):
        # count_norm=0.2, span=5y → span_norm=0.5 → (0.2+0.5)/2=0.35
        assert targeting_persistence_score(
            1, "2020-01-01T00:00:00Z", "2025-01-01T00:00:00Z"
        ) == pytest.approx(0.35, abs=1e-3)

    def test_five_campaigns_is_max_count(self):
        # count_norm=1.0, span=0 → (1.0+0)/2=0.5
        assert targeting_persistence_score(5, None, "2025-01-01T00:00:00Z") == pytest.approx(0.5)

    def test_ten_year_span_is_max_span(self):
        # count_norm=0.2, span_norm=1.0 → (0.2+1.0)/2=0.6
        assert targeting_persistence_score(
            1, "2010-01-01T00:00:00Z", "2020-01-01T00:00:00Z"
        ) == pytest.approx(0.6, abs=1e-3)

    def test_first_seen_after_last_seen_treated_as_no_span(self):
        # Malformed data: first > last → span_norm=0
        assert targeting_persistence_score(
            1, "2025-06-01T00:00:00Z", "2025-01-01T00:00:00Z"
        ) == pytest.approx(0.1)


class TestEvasionCapabilityScore:
    def test_zero_de_ttps(self):
        assert evasion_capability_score(0) == 0.0

    def test_twenty_de_ttps_is_max(self):
        assert evasion_capability_score(20) == 1.0

    def test_above_twenty_capped(self):
        assert evasion_capability_score(30) == 1.0

    def test_ten_de_ttps(self):
        assert evasion_capability_score(10) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Golden regression tests — APT28, APT41, Mustang Panda
# Derived from regenerated threat_taxonomy.json (Phase 1 artifacts).
# Reference date: 2026-05-23 00:00:00 UTC (fixed for determinism).
# All expected values computed from the production scoring functions against
# the actual profiles in schema/threat_taxonomy.json.
# ---------------------------------------------------------------------------

# beacon/schema/threat_taxonomy.json (parents[1] = beacon/ project root)
_BEACON_TAXONOMY_PATH = Path(__file__).parents[1] / "schema" / "threat_taxonomy.json"

_REF_DATE = datetime(2026, 5, 23, tzinfo=UTC)

# STIX OV scale value for "expert" tier (= 4/6)
_EXPERT_SOPH = 4 / 6


class TestCapabilityGoldenAPT28:
    """APT28: tc=93, sw=29, de=18, campaigns=1, first=2022-02-01, last=2024-11-01."""

    def setup_method(self):
        if not _BEACON_TAXONOMY_PATH.exists():
            pytest.skip("Real taxonomy not found")
        tx = json.loads(_BEACON_TAXONOMY_PATH.read_text())
        self.p = tx["intrusion_set_profiles"]["APT28"]

    def test_sophistication_score(self):
        # expert tier → 4/6
        assert sophistication_score("expert") == pytest.approx(_EXPERT_SOPH)

    def test_ttp_count_norm(self):
        assert ttp_count_norm(self.p["technique_count"]) == pytest.approx(0.93)

    def test_recency(self):
        assert recency_active_campaigns(
            self.p["campaign_last_seen"], reference=_REF_DATE
        ) == pytest.approx(0.25)

    def test_tool_usage(self):
        # sw=29 → 29/50=0.58
        assert tool_usage_score(self.p["software_count"]) == pytest.approx(0.58)

    def test_targeting_persistence(self):
        # count=1, span≈2.746y → (0.2+0.2746)/2≈0.2373
        assert targeting_persistence_score(
            self.p["campaign_count"],
            self.p["campaign_first_seen"],
            self.p["campaign_last_seen"],
        ) == pytest.approx(0.2373, abs=1e-3)

    def test_evasion_capability(self):
        # de=18 → 18/20=0.9
        assert evasion_capability_score(self.p["defense_evasion_ttp_count"]) == pytest.approx(0.9)

    def test_depth(self):
        # 3-factor geometric mean (soph × tool × evasion).
        _soph = sophistication_score("expert")
        _tool = tool_usage_score(self.p["software_count"])
        _evas = evasion_capability_score(self.p["defense_evasion_ttp_count"])
        depth = (_soph * _tool * _evas) ** (1 / 3)
        assert depth == pytest.approx(0.7034, abs=1e-3)

    def test_breadth(self):
        _ttp_n = ttp_count_norm(self.p["technique_count"])
        _pers = targeting_persistence_score(
            self.p["campaign_count"],
            self.p["campaign_first_seen"],
            self.p["campaign_last_seen"],
        )
        _rec = recency_active_campaigns(self.p["campaign_last_seen"], reference=_REF_DATE)
        breadth = (_ttp_n * _pers * _rec) ** (1 / 3)
        assert breadth == pytest.approx(0.3807, abs=1e-3)

    def test_capability_score(self):
        _soph = sophistication_score("expert")
        _tool = tool_usage_score(self.p["software_count"])
        _evas = evasion_capability_score(self.p["defense_evasion_ttp_count"])
        _ttp_n = ttp_count_norm(self.p["technique_count"])
        _pers = targeting_persistence_score(
            self.p["campaign_count"],
            self.p["campaign_first_seen"],
            self.p["campaign_last_seen"],
        )
        _rec = recency_active_campaigns(self.p["campaign_last_seen"], reference=_REF_DATE)
        depth = (_soph * _tool * _evas) ** (1 / 3)
        breadth = (_ttp_n * _pers * _rec) ** (1 / 3)
        assert depth * breadth == pytest.approx(0.2678, abs=1e-3)


class TestCapabilityGoldenAPT41:
    """APT41: tc=82, sw=32, de=23, campaigns=2, first=2021-05-01, last=2024-06-30."""

    def setup_method(self):
        if not _BEACON_TAXONOMY_PATH.exists():
            pytest.skip("Real taxonomy not found")
        tx = json.loads(_BEACON_TAXONOMY_PATH.read_text())
        self.p = tx["intrusion_set_profiles"]["APT41"]

    def test_ttp_count_norm(self):
        assert ttp_count_norm(self.p["technique_count"]) == pytest.approx(0.82)

    def test_tool_usage(self):
        # sw=32 → 32/50=0.64
        assert tool_usage_score(self.p["software_count"]) == pytest.approx(0.64)

    def test_evasion_capability(self):
        # de=23 → min(23/20,1.0)=1.0
        assert evasion_capability_score(self.p["defense_evasion_ttp_count"]) == pytest.approx(1.0)

    def test_targeting_persistence(self):
        # count=2, span≈3.17y → (0.4+0.317)/2≈0.358
        assert targeting_persistence_score(
            self.p["campaign_count"],
            self.p["campaign_first_seen"],
            self.p["campaign_last_seen"],
        ) == pytest.approx(0.3582, abs=1e-3)

    def test_recency(self):
        # last=2024-06-30 → ~692d → 0.25
        assert recency_active_campaigns(
            self.p["campaign_last_seen"], reference=_REF_DATE
        ) == pytest.approx(0.25)

    def test_depth(self):
        # 3-factor geometric mean (soph × tool × evasion).
        _soph = sophistication_score("expert")
        _tool = tool_usage_score(self.p["software_count"])
        _evas = evasion_capability_score(self.p["defense_evasion_ttp_count"])
        depth = (_soph * _tool * _evas) ** (1 / 3)
        assert depth == pytest.approx(0.7528, abs=1e-3)

    def test_capability_score(self):
        _soph = sophistication_score("expert")
        _tool = tool_usage_score(self.p["software_count"])
        _evas = evasion_capability_score(self.p["defense_evasion_ttp_count"])
        _ttp_n = ttp_count_norm(self.p["technique_count"])
        _pers = targeting_persistence_score(
            self.p["campaign_count"],
            self.p["campaign_first_seen"],
            self.p["campaign_last_seen"],
        )
        _rec = recency_active_campaigns(self.p["campaign_last_seen"], reference=_REF_DATE)
        depth = (_soph * _tool * _evas) ** (1 / 3)
        breadth = (_ttp_n * _pers * _rec) ** (1 / 3)
        assert depth * breadth == pytest.approx(0.3153, abs=1e-3)


class TestCapabilityGoldenMustangPanda:
    """Mustang Panda: tc=85, sw=23, de=20, campaigns=1, first=2023-07-01, last=2024-12-01."""

    def setup_method(self):
        if not _BEACON_TAXONOMY_PATH.exists():
            pytest.skip("Real taxonomy not found")
        tx = json.loads(_BEACON_TAXONOMY_PATH.read_text())
        self.p = tx["intrusion_set_profiles"]["Mustang Panda"]

    def test_ttp_count_norm(self):
        assert ttp_count_norm(self.p["technique_count"]) == pytest.approx(0.85)

    def test_tool_usage(self):
        # sw=23 → 23/50=0.46
        assert tool_usage_score(self.p["software_count"]) == pytest.approx(0.46)

    def test_evasion_capability(self):
        # de=20 → 20/20=1.0
        assert evasion_capability_score(self.p["defense_evasion_ttp_count"]) == pytest.approx(1.0)

    def test_targeting_persistence(self):
        # count=1, span≈1.42y → (0.2+0.142)/2≈0.171
        assert targeting_persistence_score(
            self.p["campaign_count"],
            self.p["campaign_first_seen"],
            self.p["campaign_last_seen"],
        ) == pytest.approx(0.1710, abs=1e-3)

    def test_recency(self):
        # last=2024-12-01 → ~538d → 0.25
        assert recency_active_campaigns(
            self.p["campaign_last_seen"], reference=_REF_DATE
        ) == pytest.approx(0.25)

    def test_depth(self):
        # 3-factor geometric mean (soph × tool × evasion).
        _soph = sophistication_score("expert")
        _tool = tool_usage_score(self.p["software_count"])
        _evas = evasion_capability_score(self.p["defense_evasion_ttp_count"])
        depth = (_soph * _tool * _evas) ** (1 / 3)
        assert depth == pytest.approx(0.6744, abs=1e-3)

    def test_capability_score(self):
        _soph = sophistication_score("expert")
        _tool = tool_usage_score(self.p["software_count"])
        _evas = evasion_capability_score(self.p["defense_evasion_ttp_count"])
        _ttp_n = ttp_count_norm(self.p["technique_count"])
        _pers = targeting_persistence_score(
            self.p["campaign_count"],
            self.p["campaign_first_seen"],
            self.p["campaign_last_seen"],
        )
        _rec = recency_active_campaigns(self.p["campaign_last_seen"], reference=_REF_DATE)
        depth = (_soph * _tool * _evas) ** (1 / 3)
        breadth = (_ttp_n * _pers * _rec) ** (1 / 3)
        assert depth * breadth == pytest.approx(0.2234, abs=1e-3)


# ---------------------------------------------------------------------------
# window_days=180 golden tests — synthetic actor with campaign 158 days ago
# Reference date: _REF_DATE = 2026-05-23 UTC
# 2025-12-16T00:00:00Z is 158 days before ref → between 90 and 180.
# With window=90: recency=0.5; with window=180: recency=1.0.
# tc=50, sw=10, de=10, campaigns=2, first=2023-01-01, last=2025-12-16.
# ---------------------------------------------------------------------------

_WINDOW_ACTOR_PROFILE = {
    "technique_count": 50,
    "software_count": 10,
    "defense_evasion_ttp_count": 10,
    "campaign_count": 2,
    "campaign_first_seen": "2023-01-01T00:00:00Z",
    "campaign_last_seen": "2025-12-16T00:00:00Z",
}
# 2025-12-16 → 158 days before 2026-05-23


class TestCapabilityGoldenWindow180:
    """Synthetic actor with campaign 158 days before ref — shows window=90 vs 180 split."""

    def test_recency_window90_returns_half(self):
        assert recency_active_campaigns(
            _WINDOW_ACTOR_PROFILE["campaign_last_seen"], reference=_REF_DATE
        ) == pytest.approx(0.5)

    def test_recency_window180_returns_one(self):
        assert recency_active_campaigns(
            _WINDOW_ACTOR_PROFILE["campaign_last_seen"],
            reference=_REF_DATE,
            window_days=180,
        ) == pytest.approx(1.0)

    def test_breadth_window90(self):
        # _rec=0.5, _ttp_n=0.5, _pers=(0.4+span_norm)/2 ≈ 0.3478
        # breadth = (0.5*0.3478*0.5)^(1/3) ≈ 0.443
        _ttp_n = ttp_count_norm(50)
        _pers = targeting_persistence_score(
            _WINDOW_ACTOR_PROFILE["campaign_count"],
            _WINDOW_ACTOR_PROFILE["campaign_first_seen"],
            _WINDOW_ACTOR_PROFILE["campaign_last_seen"],
        )
        _rec = recency_active_campaigns(
            _WINDOW_ACTOR_PROFILE["campaign_last_seen"], reference=_REF_DATE
        )
        breadth = (_ttp_n * _pers * _rec) ** (1 / 3)
        assert breadth == pytest.approx(0.4430, abs=1e-3)

    def test_breadth_window180(self):
        # Same as above but _rec=1.0 instead of 0.5 → breadth ≈ 0.558
        _ttp_n = ttp_count_norm(50)
        _pers = targeting_persistence_score(
            _WINDOW_ACTOR_PROFILE["campaign_count"],
            _WINDOW_ACTOR_PROFILE["campaign_first_seen"],
            _WINDOW_ACTOR_PROFILE["campaign_last_seen"],
        )
        _rec = recency_active_campaigns(
            _WINDOW_ACTOR_PROFILE["campaign_last_seen"],
            reference=_REF_DATE,
            window_days=180,
        )
        breadth = (_ttp_n * _pers * _rec) ** (1 / 3)
        assert breadth == pytest.approx(0.5582, abs=1e-3)

    def test_breadth_window180_exceeds_window90(self):
        _ttp_n = ttp_count_norm(50)
        _pers = targeting_persistence_score(
            _WINDOW_ACTOR_PROFILE["campaign_count"],
            _WINDOW_ACTOR_PROFILE["campaign_first_seen"],
            _WINDOW_ACTOR_PROFILE["campaign_last_seen"],
        )
        breadth90 = (
            _ttp_n
            * _pers
            * recency_active_campaigns(
                _WINDOW_ACTOR_PROFILE["campaign_last_seen"], reference=_REF_DATE
            )
        ) ** (1 / 3)
        breadth180 = (
            _ttp_n
            * _pers
            * recency_active_campaigns(
                _WINDOW_ACTOR_PROFILE["campaign_last_seen"],
                reference=_REF_DATE,
                window_days=180,
            )
        ) ** (1 / 3)
        assert breadth180 > breadth90


# ---------------------------------------------------------------------------
# Config: activity_window_days reads ACTIVITY_WINDOW_DAYS env var
# ---------------------------------------------------------------------------


class TestActivityWindowDaysConfig:
    def test_default_is_90(self, monkeypatch):
        monkeypatch.delenv("ACTIVITY_WINDOW_DAYS", raising=False)
        from beacon.config import load_config

        cfg = load_config()
        assert cfg.activity_window_days == 90

    def test_env_var_overrides_to_180(self, monkeypatch):
        monkeypatch.setenv("ACTIVITY_WINDOW_DAYS", "180")
        from beacon.config import load_config

        cfg = load_config()
        assert cfg.activity_window_days == 180

    def test_prioritize_actors_uses_window_days_param(self):
        # Synthetic one-actor taxonomy: campaign_last_seen 158 days before the
        # fixed reference (_REF_DATE = 2026-05-23). A pinned reference keeps this
        # deterministic — without it the wall clock drifts the gap past 180 days
        # and both windows collapse to the same recency bucket.
        # window=90 → recency=0.5; window=180 → recency=1.0 → capability differs.
        misp = MispClient(cache_path=_TRIAGE_MISP_FIXTURE)
        taxonomy = _make_mini_taxonomy(
            actor_name="WindowTestActor",
            target_industries=["Private sector"],
            target_geographies=["Japan"],
            technique_count=50,
            sophistication_tier="intermediate",
            campaign_last_seen="2025-12-16T00:00:00Z",
        )
        # Add remaining fields so Capability > 0 (campaign_count > 0 required for _pers > 0)
        taxonomy["intrusion_set_profiles"]["WindowTestActor"].update(
            {
                "software_count": 10,
                "defense_evasion_ttp_count": 10,
                "campaign_count": 2,
                "campaign_first_seen": "2023-01-01T00:00:00Z",
            }
        )
        surface_map = _make_empty_surface_map()
        bctx = _finance_context()

        results90 = prioritize_actors(
            bctx, taxonomy, surface_map, misp, window_days=90, reference=_REF_DATE
        )
        results180 = prioritize_actors(
            bctx, taxonomy, surface_map, misp, window_days=180, reference=_REF_DATE
        )

        assert len(results90) == 1
        assert len(results180) == 1
        # window=180 should yield higher recency → higher breadth → higher capability
        cap90 = results90[0].score_breakdown.capability.score
        cap180 = results180[0].score_breakdown.capability.score
        assert cap180 > cap90, f"Expected cap180 ({cap180}) > cap90 ({cap90})"


# ---------------------------------------------------------------------------
# Initiative G Phase 6 — IR-boost integration tests
# ---------------------------------------------------------------------------


class _StubSageClient:
    """Configurable mock matching SageAPIClient.get_recent_incidents.

    Use `incidents_by_actor` to map actor_stix_id → incident list. Set
    `raise_exc` to simulate network failure on every call.
    """

    def __init__(
        self,
        incidents_by_actor: dict[str, list[dict]] | None = None,
        raise_exc: Exception | None = None,
    ) -> None:
        self.incidents_by_actor = incidents_by_actor or {}
        self.raise_exc = raise_exc
        self.calls: list[dict] = []

    def get_recent_incidents(
        self,
        since,
        until,
        actor_stix_id=None,
        limit: int = 50,
    ) -> list[dict]:
        self.calls.append(
            {
                "since": since,
                "until": until,
                "actor_stix_id": actor_stix_id,
                "limit": limit,
            }
        )
        if self.raise_exc:
            raise self.raise_exc
        if actor_stix_id is None:
            return [inc for incs in self.incidents_by_actor.values() for inc in incs]
        return self.incidents_by_actor.get(actor_stix_id, [])


def _apt29_window_taxonomy() -> dict:
    """Single-actor taxonomy keyed by APT29 (matches MISP fixture).

    Geographies / priority_ttps populated so the actor passes Intent gate
    and has at least one known TTP for the capability boost test.
    """
    return {
        "actor_categories": {
            "state_sponsored": {
                "Russia": {
                    "mitre_groups": ["APT29"],
                    "target_industries": ["Private sector"],
                    "target_geographies": ["Japan"],
                    "priority_ttps": ["T1190", "T1078"],
                    "tags": [],
                }
            }
        },
        "intrusion_set_profiles": {
            "APT29": {
                "technique_count": 50,
                "software_count": 10,
                "sophistication_tier": "expert",
                "campaign_last_seen": "2025-12-16T00:00:00Z",
                "campaign_first_seen": "2023-01-01T00:00:00Z",
                "campaign_count": 2,
                "defense_evasion_ttp_count": 10,
            }
        },
    }


_APT29_STIX_ID = "intrusion-set--test-apt29-triage"


class TestIRBoostFactorsPresentByDefault:
    """Without a SAGE client, ir_observed defaults to 1.0 and ir_boost_skipped=False."""

    def setup_method(self):
        self.misp = MispClient(cache_path=_TRIAGE_MISP_FIXTURE)
        self.taxonomy = _apt29_window_taxonomy()
        self.bctx = _finance_context()

    def test_no_sage_client_yields_neutral_ir_observed(self):
        actors = prioritize_actors(
            self.bctx,
            self.taxonomy,
            _make_empty_surface_map(),
            self.misp,
            sage_client=None,
        )
        assert len(actors) == 1
        assert actors[0].score_breakdown.intent.ir_observed == 1.0

    def test_no_sage_client_does_not_set_ir_boost_skipped(self):
        actors = prioritize_actors(
            self.bctx,
            self.taxonomy,
            _make_empty_surface_map(),
            self.misp,
            sage_client=None,
        )
        assert actors[0].score_breakdown.data_quality.ir_boost_skipped is False


class TestIRBoostFactorsWithMockedSage:
    """Mocked SAGE responses: binary ir_observed (1.0 if incidents, 0.5 if none)."""

    def setup_method(self):
        self.misp = MispClient(cache_path=_TRIAGE_MISP_FIXTURE)
        self.taxonomy = _apt29_window_taxonomy()
        self.bctx = _finance_context()

    def test_no_incidents_yields_half(self):
        sage = _StubSageClient(incidents_by_actor={})
        actors = prioritize_actors(
            self.bctx,
            self.taxonomy,
            _make_empty_surface_map(),
            self.misp,
            sage_client=sage,
        )
        assert actors[0].score_breakdown.intent.ir_observed == 0.5

    def test_incident_present_yields_full(self):
        sage = _StubSageClient(
            incidents_by_actor={
                _APT29_STIX_ID: [
                    {
                        "incident_stix_id": "incident--abc-1",
                        "ttps": [{"ttp_id": "T1190"}],
                    }
                ]
            }
        )
        actors = prioritize_actors(
            self.bctx,
            self.taxonomy,
            _make_empty_surface_map(),
            self.misp,
            sage_client=sage,
        )
        assert actors[0].score_breakdown.intent.ir_observed == 1.0

    def test_incident_no_ttp_overlap_still_yields_full(self):
        sage = _StubSageClient(
            incidents_by_actor={
                _APT29_STIX_ID: [
                    {
                        "incident_stix_id": "incident--abc-2",
                        "ttps": [{"ttp_id": "T9999"}],
                    }
                ]
            }
        )
        actors = prioritize_actors(
            self.bctx,
            self.taxonomy,
            _make_empty_surface_map(),
            self.misp,
            sage_client=sage,
        )
        assert actors[0].score_breakdown.intent.ir_observed == 1.0

    def test_sage_call_uses_lookback_window(self):
        sage = _StubSageClient(incidents_by_actor={})
        prioritize_actors(
            self.bctx,
            self.taxonomy,
            _make_empty_surface_map(),
            self.misp,
            sage_client=sage,
            ir_lookback_days=180,
        )
        assert len(sage.calls) == 1
        call = sage.calls[0]
        assert (call["until"] - call["since"]).days == 180
        assert call["actor_stix_id"] == _APT29_STIX_ID

    def test_ir_boost_skipped_flag_skips_sage_call(self):
        sage = _StubSageClient(
            incidents_by_actor={
                _APT29_STIX_ID: [{"incident_stix_id": "incident--x", "ttps": [{"ttp_id": "T1190"}]}]
            }
        )
        actors = prioritize_actors(
            self.bctx,
            self.taxonomy,
            _make_empty_surface_map(),
            self.misp,
            sage_client=sage,
            ir_boost_skipped=True,
        )
        assert sage.calls == []
        assert actors[0].score_breakdown.intent.ir_observed == 1.0
        assert actors[0].score_breakdown.data_quality.ir_boost_skipped is True


class TestIRBoostFailSoft:
    """Network failures degrade gracefully — neutral factors + data_quality.degraded."""

    def setup_method(self):
        self.misp = MispClient(cache_path=_TRIAGE_MISP_FIXTURE)
        self.taxonomy = _apt29_window_taxonomy()
        self.bctx = _finance_context()

    def test_httpx_timeout_sets_degraded_and_neutral_factors(self):
        import httpx  # noqa: PLC0415

        sage = _StubSageClient(raise_exc=httpx.TimeoutException("simulated"))
        actors = prioritize_actors(
            self.bctx,
            self.taxonomy,
            _make_empty_surface_map(),
            self.misp,
            sage_client=sage,
        )
        dq = actors[0].score_breakdown.data_quality
        assert actors[0].score_breakdown.intent.ir_observed == 1.0
        assert dq.degraded is True
        assert "sage_incidents" in dq.missing_sources

    def test_httpx_http_error_sets_degraded_and_neutral_factors(self):
        from unittest.mock import MagicMock  # noqa: PLC0415

        import httpx  # noqa: PLC0415

        sage = _StubSageClient(
            raise_exc=httpx.HTTPStatusError("500", request=MagicMock(), response=MagicMock())
        )
        actors = prioritize_actors(
            self.bctx,
            self.taxonomy,
            _make_empty_surface_map(),
            self.misp,
            sage_client=sage,
        )
        dq = actors[0].score_breakdown.data_quality
        assert dq.degraded is True
        assert "sage_incidents" in dq.missing_sources


# ---------------------------------------------------------------------------
# Config: ir_lookback_days reads BEACON_IR_LOOKBACK_DAYS env var
# ---------------------------------------------------------------------------


class TestIRLookbackDaysConfig:
    def test_default_is_365(self, monkeypatch):
        monkeypatch.delenv("BEACON_IR_LOOKBACK_DAYS", raising=False)
        from beacon.config import load_config  # noqa: PLC0415

        cfg = load_config()
        assert cfg.ir_lookback_days == 365

    def test_env_var_overrides_to_30(self, monkeypatch):
        monkeypatch.setenv("BEACON_IR_LOOKBACK_DAYS", "30")
        from beacon.config import load_config  # noqa: PLC0415

        cfg = load_config()
        assert cfg.ir_lookback_days == 30


# ---------------------------------------------------------------------------
# Schema version bump — 0.18.0 → 1.0.0 (Initiative H Phase 4 — pre-1.0 stabilization)
# ---------------------------------------------------------------------------


class TestSchemaVersionBumped:
    def test_pir_output_document_default_is_2_0_0(self):
        from beacon.generator.pir_builder import PIROutputDocument  # noqa: PLC0415

        doc = PIROutputDocument(pirs=[])
        assert doc.schema_version == "2.0.0"
