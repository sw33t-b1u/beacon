"""Actor prioritization using the SANS I-O-C Threat triad.

Triad source (SANS Internet Storm Center, verbatim):
  "To understand, differentiate, and properly respond to threats, it is
  helpful to divide this concept into a further three components: Intent,
  Opportunity, and Capability (IOC)."

NIST SP 800-30 r1 operationalization (§3.2.1, Table D-3 / D-4):
  "Assess adversary capability (see Table D-3, as tailored by the organization)."
  "Assess adversary intent (see Table D-4, as tailored by the organization)."

MITRE Cyber Prep methodology (Bodeau, Fabius-Greene, Graubart,
"How Do You Assess Your Organization's Cyber Threat Level?"):
  Cyber Prep characterizes the cyber threat in terms of an adversary's
  Capability ("resources, skill or expertise, knowledge, and opportunity"),
  Intent ("goals or outcomes the adversary seeks; consequences the
  adversary seeks to avoid"), and Targeting ("how broadly or narrowly
  and how persistently the adversary targets a specific organization").
  BEACON's `Opportunity` maps to MITRE Cyber Prep's `Targeting`; the
  three-factor decomposition `Likelihood = Intent × Capability ×
  Opportunity` is methodologically aligned with this framework.

IR-observed boost (Initiative G Phase 6, redesigned):
  Binary signal: has this actor ever attacked our organisation within the
  IR lookback window?  1.0 = yes, 0.5 = no (neutral — absence of own
  incidents should not zero out external attribution).  Multiplied into
  Intent as ``ir_observed``: a confirmed past attack is the strongest
  evidence of intent toward this specific organisation.  Fails-soft to
  1.0 when SAGE is unreachable (data_quality.degraded) or skipped
  (data_quality.ir_boost_skipped).

Formula (product form, sign-off 1):
  Likelihood = Intent × Capability × Opportunity
  Intent == 0 hard gate: actor is emitted with likelihood=0.0 and
  rationale "Intent gate failed".

See docs/citations.md for license terms governing each reference.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

import structlog
from pydantic import BaseModel, ConfigDict, Field, model_validator

from beacon.ingest.misp_client import ActorAttributes, MispClient
from beacon.ingest.schema import BusinessContext

if TYPE_CHECKING:
    from beacon.sage.client import SageAPIClient

_log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# STIX 2.1 threat-actor-sophistication-ov → 0..1 linear scale.
# 7 values, evenly spaced.  Only STIX OV literals are valid inputs.
# Per [[feedback_stix_strict_compliance]] — never invent or demote values.
# ---------------------------------------------------------------------------
_SOPHISTICATION_SCALE: dict[str, float] = {
    "none": 0.0,
    "minimal": 1 / 6,
    "intermediate": 2 / 6,
    "advanced": 3 / 6,
    "expert": 4 / 6,
    "innovator": 5 / 6,
    "strategic": 1.0,
}

# Taxonomy sophistication_tier (4-level heuristic) → STIX OV equivalent.
# Used when ActorAttributes.sophistication is None (MISP has no value).
_TIER_TO_STIX_OV: dict[str, str] = {
    "minimal": "minimal",
    "intermediate": "intermediate",
    "advanced": "advanced",
    "expert": "expert",
}

# BEACON Organization.industry → MISP cfr-target-category coarse bucket.
# Mirrors threat_mapper._BEACON_TO_MISP_INDUSTRY (duplicated to keep
# actor_triage.py independent from threat_mapper at this phase).
_BEACON_TO_MISP_SECTOR: dict[str, str] = {
    "manufacturing": "Private sector",
    "finance": "Private sector",
    "energy": "Private sector",
    "healthcare": "Private sector",
    "defense": "Military",
    "technology": "Private sector",
    "logistics": "Private sector",
    "government": "Government",
    "education": "Civil society",
    "other": "Private sector",
}

# STIX threat-actor-motivation-ov values expected per BEACON industry.
# Derived from common adversary motivation profiles; provides a signal
# when actor STIX motivation data is available via MISP.
_INDUSTRY_EXPECTED_MOTIVATIONS: dict[str, list[str]] = {
    "finance": ["personal-gain", "organizational-gain"],
    "manufacturing": ["ideology", "organizational-gain"],
    "energy": ["ideology", "organizational-gain"],
    "healthcare": ["personal-gain", "organizational-gain"],
    "defense": ["ideology", "organizational-gain"],
    "technology": ["organizational-gain", "personal-gain"],
    "logistics": ["personal-gain", "organizational-gain"],
    "government": ["ideology", "organizational-gain"],
    "education": ["ideology", "organizational-gain"],
    "other": ["personal-gain", "organizational-gain"],
}


# ---------------------------------------------------------------------------
# Pydantic models (field names align with BEACON HLD §12.4 / TRACE HLD §14.2)
# ---------------------------------------------------------------------------


class IntentComponent(BaseModel):
    model_config = ConfigDict(extra="allow")
    score: float = Field(ge=0.0, le=1.0)
    motivation_alignment: float = Field(ge=0.0, le=1.0)
    industry_match: float = Field(ge=0.0, le=1.0)
    ir_observed: float = Field(default=1.0, ge=0.0, le=1.0)


class CapabilityComponent(BaseModel):
    model_config = ConfigDict(extra="allow")
    score: float = Field(ge=0.0, le=1.0)
    sophistication_score: float = Field(ge=0.0, le=1.0)
    ttp_count_norm: float = Field(ge=0.0, le=1.0)
    recency_active_campaigns: float = Field(ge=0.0, le=1.0)
    tool_usage: float = Field(default=0.0, ge=0.0, le=1.0)
    targeting_persistence: float = Field(default=0.0, ge=0.0, le=1.0)
    evasion_capability: float = Field(default=0.0, ge=0.0, le=1.0)
    depth: float = Field(default=0.0, ge=0.0, le=1.0)
    breadth: float = Field(default=0.0, ge=0.0, le=1.0)


class OpportunityComponent(BaseModel):
    model_config = ConfigDict(extra="allow")
    score: float = Field(ge=0.0, le=1.0)
    victimology_match: float = Field(ge=0.0, le=1.0)
    geographic_match: float = Field(ge=0.0, le=1.0)
    surface_ttp_coverage: float = Field(ge=0.0, le=1.0)


class DataQualityComponent(BaseModel):
    degraded: bool = False
    missing_sources: list[str] = Field(default_factory=list)
    # Initiative G Phase 6 — set True when the SAGE IR-boost call was skipped
    # (--no-sage CLI flag or SAGE_API_URL unset). Distinct from `degraded`
    # which marks unintended SAGE failure (network/HTTP error).
    ir_boost_skipped: bool = False


class ScoreBreakdown(BaseModel):
    intent: IntentComponent
    capability: CapabilityComponent
    opportunity: OpportunityComponent
    data_quality: DataQualityComponent


class Rationale(BaseModel):
    text: str
    intent_factors: dict[str, float] = Field(default_factory=dict)
    capability_factors: dict[str, float] = Field(default_factory=dict)
    opportunity_factors: dict[str, float] = Field(default_factory=dict)


class PrioritizedActor(BaseModel):
    actor_id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    likelihood: float = Field(ge=0.0, le=1.0)
    score_breakdown: ScoreBreakdown
    rationale: Rationale
    # Analyst annotations (Phase 7 — session-only persistence, no SAGE write-back).
    excluded_by_analyst: bool = False
    exclusion_reason: str | None = None
    manual_likelihood_override: float | None = Field(default=None, ge=0.0, le=1.0)
    analyst_rationale_append: str | None = None

    @model_validator(mode="after")
    def _check_exclusion_reason(self) -> PrioritizedActor:
        if self.excluded_by_analyst and not self.exclusion_reason:
            raise ValueError("exclusion_reason is required when excluded_by_analyst is True")
        return self


# ---------------------------------------------------------------------------
# Component scoring functions — each returns a float in [0.0, 1.0]
# ---------------------------------------------------------------------------


def motivation_alignment(
    actor_motivation: str | None,
    expected_motivations: list[str],
) -> float:
    """Binary match of actor STIX motivation against expected adversary motivations.

    Returns:
      1.0 — actor_motivation is in expected_motivations (positive signal)
      0.5 — actor_motivation is None (no data; neutral penalty, not punitive)
      0.0 — actor_motivation is present but NOT in expected_motivations
    """
    if actor_motivation is None:
        return 0.5
    return 1.0 if actor_motivation in expected_motivations else 0.0


def industry_match(
    actor_industries: list[str],
    business_industries: list[str],
) -> float:
    """Jaccard similarity between actor target industries and business industries.

    Choice: Jaccard (|A∩B| / |A∪B|) — treats partial overlap as an intermediate
    signal rather than binary.  Returns 0.5 when either set is empty (no data;
    neutral, not punitive).
    """
    if not actor_industries or not business_industries:
        return 0.5
    a, b = set(actor_industries), set(business_industries)
    union = a | b
    return len(a & b) / len(union)


def sophistication_score(stix_ov: str | None) -> float:
    """Map STIX 2.1 threat-actor-sophistication-ov to [0, 1].

    Linear normalization over 7-level OV per STIX 2.1 §10.2.
    Only STIX OV literal values are accepted; non-OV inputs return 0.0
    (per [[feedback_stix_strict_compliance]]).
    """
    return _SOPHISTICATION_SCALE.get(stix_ov or "", 0.0)


def ttp_count_norm(technique_count: int) -> float:
    """Normalize actor technique count to [0, 1].

    Upper bound: 100 TTPs — covers the majority of well-characterised actors
    in ATT&CK v16 (APT28 observed at 93 TTPs; 1 actor exceeds 100 at 130).
    Formula: min(technique_count / 100, 1.0).
    """
    return min(technique_count / 100, 1.0)


def recency_active_campaigns(
    campaign_last_seen: str | None,
    *,
    reference: datetime | None = None,
    window_days: int = 90,
) -> float:
    """Time-decay score derived from intrusion_set_profiles.campaign_last_seen.

    Derived from Phase 1 taxonomy field (see Phase 2 residual note #2 — do NOT
    rely on ActorAttributes.active which is hardcoded None at the MISP layer).

    Reference date: datetime.now(UTC) unless overridden (override used
    only in tests for deterministic behaviour).

    window_days controls the "actively campaigning" bucket threshold (env:
    ACTIVITY_WINDOW_DAYS, default 90).

    Buckets:
      ≤ window_days      → 1.0  (actively campaigning)
      ≤ 365 days         → 0.5  (recent activity)
      ≤ 1095 days (3yr)  → 0.25 (historically active)
      older or None      → 0.0
    """
    if not campaign_last_seen:
        return 0.0
    last = _parse_campaign_dt(campaign_last_seen)
    if last is None:
        return 0.0
    ref = reference or datetime.now(UTC)
    days = (ref - last).days
    if days <= window_days:
        return 1.0
    if days <= 365:
        return 0.5
    if days <= 1095:
        return 0.25
    return 0.0


def victimology_match(
    actor_industries: list[str],
    business_industries: list[str],
) -> float:
    """Binary membership: 1.0 if any actor industry is in business industries.

    Complements Intent.industry_match (Jaccard) — any confirmed victimology
    overlap is treated as a full Opportunity signal regardless of set sizes.
    Returns 0.5 when either set is empty (no data; neutral).
    """
    if not actor_industries or not business_industries:
        return 0.5
    return 1.0 if set(actor_industries) & set(business_industries) else 0.0


def geographic_match(
    actor_geos: list[str],
    business_geos: list[str],
) -> float:
    """Jaccard similarity between actor target geographies and business geographies.

    Returns 0.5 when either set is empty (no data; neutral, not punitive).
    """
    if not actor_geos or not business_geos:
        return 0.5
    a, b = set(actor_geos), set(business_geos)
    union = a | b
    return len(a & b) / len(union)


def tool_usage_score(software_count: int) -> float:
    """Normalize software/tool count (from ATT&CK relationships) to [0, 1].

    Upper bound: 50 distinct tools — covers APT29-class actors (~49 observed).
    Formula: min(software_count / 50, 1.0).
    """
    return min(software_count / 50, 1.0)


def targeting_persistence_score(
    campaign_count: int,
    campaign_first_seen: str | None,
    campaign_last_seen: str | None,
) -> float:
    """Combined campaign-count + operational-span indicator, normalized to [0, 1].

    count_norm = min(campaign_count / 5, 1.0)  — 5 attributed campaigns = persistent
    span_norm  = min(span_years / 10, 1.0)     — 10-year span = maximum persistence
    result     = (count_norm + span_norm) / 2  — arithmetic mean (both supply signal)

    Returns 0.0 when campaign_count == 0.
    span_norm is 0.0 when first_seen is unavailable or first_seen >= last_seen.
    """
    if campaign_count == 0:
        return 0.0
    count_norm = min(campaign_count / 5, 1.0)
    span_norm = 0.0
    if campaign_first_seen and campaign_last_seen:
        first = _parse_campaign_dt(campaign_first_seen)
        last = _parse_campaign_dt(campaign_last_seen)
        if first and last and last > first:
            span_years = (last - first).days / 365.25
            span_norm = min(span_years / 10, 1.0)
    return (count_norm + span_norm) / 2


def evasion_capability_score(de_ttp_count: int) -> float:
    """Normalize defense-evasion TTP count to [0, 1].

    Upper bound: 20 distinct DE TTPs — covers well-resourced APT-class actors.
    Includes TTPs mapped to the T1027 obfuscation and T1562 impairment families.
    Formula: min(de_ttp_count / 20, 1.0).
    """
    return min(de_ttp_count / 20, 1.0)


# ---------------------------------------------------------------------------
# Aggregation factor floor (BEACON 4.3.0)
# ---------------------------------------------------------------------------
# Capability and Opportunity are geometric means of three [0, 1] sub-factors.
# A single sub-factor of exactly 0 — which in practice usually means the
# underlying MISP/ATT&CK field was ABSENT rather than the actor genuinely
# scoring zero — would collapse the whole factor (and thus likelihood) to 0 and
# drop an otherwise-capable actor out of the ranking. To keep sparse-data actors
# ranked low but non-zero, each sub-factor is clamped to a small floor *inside
# the geometric mean only*; the raw sub-factor values are still reported
# verbatim in ScoreBreakdown for transparency. Intent is deliberately excluded:
# Intent == 0 remains a hard gate (see prioritize_actors).
_FACTOR_FLOOR = 0.05


def _floored_geomean(*factors: float) -> float:
    """Geometric mean with each factor clamped to ``[_FACTOR_FLOOR, 1.0]``.

    Prevents a single missing/zero sub-factor from zeroing an aggregate score
    while preserving monotonic ranking (BEACON 4.3.0).
    """
    clamped = [min(max(f, _FACTOR_FLOOR), 1.0) for f in factors]
    prod = 1.0
    for c in clamped:
        prod *= c
    return prod ** (1 / len(clamped))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_campaign_dt(s: str) -> datetime | None:
    """Parse ISO-8601 campaign timestamp to UTC datetime.

    Handles trailing 'Z' and optional milliseconds as produced by the ATT&CK
    STIX bundle (e.g. '2024-11-01T04:00:00.000Z').
    """
    try:
        clean = s.rstrip("Z")
        if "." in clean:
            clean = clean.rsplit(".", 1)[0]
        return datetime.fromisoformat(clean).replace(tzinfo=UTC)
    except (ValueError, AttributeError):
        return None


def _resolve_sophistication(attr: ActorAttributes | None, profile: dict) -> str | None:
    """Return STIX OV sophistication value for an actor.

    Priority: MISP ActorAttributes.sophistication (already STIX OV validated)
    > taxonomy sophistication_tier mapped to STIX OV equivalent.
    """
    if attr and attr.sophistication:
        return attr.sophistication
    tier = profile.get("sophistication_tier", "")
    return _TIER_TO_STIX_OV.get(tier)


def _surface_ttp_coverage(actor_ttps: list[str], surface_ttps: set[str]) -> float:
    """Fraction of surface-observed TTPs present in the actor's technique set.

    Measures how well the actor's known TTPs align with the attack patterns
    documented for the organisation's exposed attack surfaces.
    Formula: |actor_ttps ∩ surface_ttps| / |surface_ttps|
    (coverage metric — how much of the surface TTP space does this actor cover?)
    """
    if not surface_ttps:
        return 0.0
    return len(set(actor_ttps) & surface_ttps) / len(surface_ttps)


def _resolve_actor_stix_id(misp_attr: ActorAttributes | None) -> str | None:
    """Return the STIX intrusion-set id for SAGE /api/incidents filter.

    The MISP cluster `uuid` is reused as the intrusion-set UUID — this matches
    OpenCTI-ingested MITRE ATT&CK actors that flow through SAGE. Operators
    using a different ingest pipeline whose actor STIX IDs are not derived
    from MISP UUIDs will see empty IR-boost matches and should override this
    mapping at the deployment layer.
    """
    if misp_attr is None or not misp_attr.actor_uuid:
        return None
    return f"intrusion-set--{misp_attr.actor_uuid}"


def _incident_ttp_ids(incident: dict) -> set[str]:
    """Extract the set of TTP IDs from a SAGE incident payload.

    SAGE Phase 1 response shape includes `ttps[]` and/or `kill_chain_phases[]`.
    Each entry may carry either an ATT&CK external id (`T1190`) under `ttp_id`
    or a STIX attack-pattern id under `x_ttp_stix_id`. This helper extracts
    whatever IDs are present, normalised to plain strings — callers compare
    by intersection so additional irrelevant entries do no harm.
    """
    ids: set[str] = set()
    for entry in incident.get("ttps", []) or []:
        if not isinstance(entry, dict):
            continue
        for key in ("ttp_id", "external_id", "x_ttp_stix_id", "id"):
            val = entry.get(key)
            if isinstance(val, str) and val:
                ids.add(val)
    for entry in incident.get("kill_chain_phases", []) or []:
        if not isinstance(entry, dict):
            continue
        for key in ("ttp_id", "external_id", "x_ttp_stix_id"):
            val = entry.get(key)
            if isinstance(val, str) and val:
                ids.add(val)
    return ids


def _compute_ir_boost(incidents: list[dict]) -> float:
    """Binary IR-observed signal: has this actor attacked our org?

    Returns 1.0 when ≥1 incident exists for this actor in the lookback
    window (caller pre-filters by actor_stix_id), 0.5 otherwise (neutral).
    """
    return 1.0 if incidents else 0.5


def _build_actor_cat_map(taxonomy: dict) -> dict[str, dict]:
    """Build a reverse map: actor_name → category metadata from taxonomy.

    Returns dict with keys: category, target_industries, target_geographies,
    priority_ttps.
    """
    result: dict[str, dict] = {}
    cats = taxonomy.get("actor_categories", {})

    # state_sponsored is nested by sponsor country
    for sponsor, data in cats.get("state_sponsored", {}).items():
        for group in data.get("mitre_groups", []):
            result[group] = {
                "category": f"state_sponsored.{sponsor}",
                "target_industries": data.get("target_industries", []),
                "target_geographies": data.get("target_geographies", []),
                "priority_ttps": data.get("priority_ttps", []),
            }

    # non-state categories (first-seen wins if actor appears in multiple)
    for cat_key, data in cats.items():
        if cat_key == "state_sponsored":
            continue
        for group in data.get("mitre_groups", []):
            if group not in result:
                result[group] = {
                    "category": cat_key,
                    "target_industries": data.get("target_industries", []),
                    "target_geographies": data.get("target_geographies", []),
                    "priority_ttps": data.get("priority_ttps", []),
                }

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def prioritize_actors(
    business_context: BusinessContext,
    taxonomy: dict,
    surface_ttp_map: dict,
    misp_client: MispClient,
    *,
    window_days: int = 90,
    sage_client: SageAPIClient | None = None,
    ir_lookback_days: int = 365,
    ir_boost_skipped: bool = False,
    reference: datetime | None = None,
) -> list[PrioritizedActor]:
    """Score and rank threat actors using the I × C × O likelihood triad.

    Iterates intrusion_set_profiles from taxonomy. For each actor:
      1. Queries MispClient for additional attributes (degraded if None).
      2. Optionally queries SAGE for own-org incidents in the last
         `ir_lookback_days` (Initiative G Phase 6 IR-boost). Skipped when
         `sage_client is None` or `ir_boost_skipped=True`; fails soft (sets
         data_quality.degraded=True + neutral 1.0 IR factors) on network /
         HTTP error.
      3. Computes Intent, Capability, Opportunity scores and their sub-factors.
      4. Sets likelihood = Intent × Capability × Opportunity.
         Intent == 0.0 triggers the hard gate: likelihood stays 0.0 and
         rationale records "Intent gate failed".
         Capability and Opportunity use a floored geometric mean
         (``_floored_geomean``) so a single absent sub-factor does not zero an
         intent-passing but data-sparse actor (BEACON 4.3.0).
    Returns list sorted by likelihood descending.

    `reference` overrides the "now" used for recency / IR-lookback windows
    (defaults to datetime.now(UTC)); supplied only by tests for deterministic
    behaviour, mirroring recency_active_campaigns.
    """
    # Lazy import to avoid a runtime dependency on httpx when sage_client is None.
    import httpx2 as httpx  # noqa: PLC0415

    org = business_context.organization
    business_misp_sector = _BEACON_TO_MISP_SECTOR.get(org.industry, "Private sector")
    business_sectors: list[str] = [business_misp_sector]
    business_geos: list[str] = list(org.geography)
    expected_motivations: list[str] = _INDUSTRY_EXPECTED_MOTIVATIONS.get(
        org.industry, ["personal-gain"]
    )

    actor_cat_map = _build_actor_cat_map(taxonomy)
    all_surface_ttps: set[str] = {
        entry["ttp_id"]
        for entries in surface_ttp_map.get("surface_ttp_map", {}).values()
        for entry in entries
    }

    _now = reference or datetime.now(UTC)
    _today: date = _now.date()
    _ir_since: date = _today - timedelta(days=ir_lookback_days)

    # Track whether SAGE became unreachable mid-loop: a single failure flips
    # `sage_degraded` and short-circuits subsequent per-actor calls so that we
    # do not hammer a dead endpoint N times.
    sage_degraded = False

    results: list[PrioritizedActor] = []

    for actor_name, profile in taxonomy.get("intrusion_set_profiles", {}).items():
        cat = actor_cat_map.get(actor_name, {})
        cat_industries: list[str] = cat.get("target_industries", [])
        cat_geos: list[str] = cat.get("target_geographies", [])
        cat_ttps: list[str] = cat.get("priority_ttps", [])

        # Phase 2 residual note #1 — translate MispClient None → degraded flag
        misp_attr = misp_client.get_actor(actor_name)
        degraded = misp_attr is None
        missing_sources: list[str] = ["misp_galaxy"] if degraded else []

        aliases: list[str] = misp_attr.aliases if misp_attr else []

        # Merge MISP supplemental data into taxonomy base (deduplicated)
        misp_inds = misp_attr.target_industries if misp_attr else []
        misp_geos = misp_attr.target_geographies if misp_attr else []
        actor_industries = list(dict.fromkeys(cat_industries + misp_inds))
        actor_geos = list(dict.fromkeys(cat_geos + misp_geos))

        stix_soph = _resolve_sophistication(misp_attr, profile)

        # ------ Intent ------
        _mot = motivation_alignment(
            misp_attr.primary_motivation if misp_attr else None,
            expected_motivations,
        )
        _ind = industry_match(actor_industries, business_sectors)
        # Plan §3.2: product form — both sub-factors must be non-zero.
        intent_score = min(max(_mot * _ind, 0.0), 1.0)

        # ------ Intent hard gate (Plan §3.2 verbatim) ------
        # "Intent=0 is a hard gate that short-circuits the actor out of
        # prioritized_actors[]" — excluded, not emitted with score 0.
        if intent_score == 0.0:
            _log.debug(
                "actor_triage_intent_gate",
                actor=actor_name,
                motivation_alignment=_mot,
                industry_match=_ind,
            )
            continue

        # ------ IR-boost (Initiative G Phase 6, redesigned) ------
        # Binary signal multiplied into Intent: has this actor attacked us?
        # Fail-soft to 1.0 when SAGE is unreachable or skipped.
        _ir_obs: float = 1.0
        ir_degraded_this_actor = False
        if sage_client is not None and not ir_boost_skipped and not sage_degraded:
            _actor_stix_id = _resolve_actor_stix_id(misp_attr)
            if _actor_stix_id is not None:
                try:
                    _incidents = sage_client.get_recent_incidents(
                        since=_ir_since,
                        until=_today,
                        actor_stix_id=_actor_stix_id,
                    )
                    _ir_obs = _compute_ir_boost(_incidents)
                except (httpx.HTTPError, httpx.TimeoutException) as exc:
                    _log.warning(
                        "actor_triage_sage_unreachable",
                        actor=actor_name,
                        actor_stix_id=_actor_stix_id,
                        error=str(exc),
                    )
                    sage_degraded = True
                    ir_degraded_this_actor = True
                except Exception as exc:  # noqa: BLE001
                    _log.warning(
                        "actor_triage_sage_unexpected_error",
                        actor=actor_name,
                        actor_stix_id=_actor_stix_id,
                        error=str(exc),
                    )
                    sage_degraded = True
                    ir_degraded_this_actor = True

        # ------ Intent (with IR-observed) ------
        intent_score = min(max(_mot * _ind * _ir_obs, 0.0), 1.0)

        # ------ Capability — Depth × Breadth aggregation ------
        # Depth: 3-factor geometric mean of quality factors.
        # Breadth: 3-factor geometric mean of quantity factors.
        # Both use the floored geometric mean so a single absent sub-factor
        # (e.g. no defense-evasion TTPs recorded) does not zero Capability
        # for an otherwise-capable actor (BEACON 4.3.0; see _floored_geomean).
        _soph = sophistication_score(stix_soph)
        _ttp_n = ttp_count_norm(profile.get("technique_count", 0))
        _rec = recency_active_campaigns(
            profile.get("campaign_last_seen"), reference=_now, window_days=window_days
        )
        _tool = tool_usage_score(profile.get("software_count", 0))
        _pers = targeting_persistence_score(
            profile.get("campaign_count", 0),
            profile.get("campaign_first_seen"),
            profile.get("campaign_last_seen"),
        )
        _evas = evasion_capability_score(profile.get("defense_evasion_ttp_count", 0))
        _depth = _floored_geomean(_soph, _tool, _evas)
        _breadth = _floored_geomean(_ttp_n, _pers, _rec)
        capability_score = min(max(_depth * _breadth, 0.0), 1.0)

        # ------ Opportunity — 3-factor floored geometric mean ------
        _vic = victimology_match(actor_industries, business_sectors)
        _geo = geographic_match(actor_geos, business_geos)
        _surf = _surface_ttp_coverage(cat_ttps, all_surface_ttps)
        opportunity_score = min(max(_floored_geomean(_vic, _geo, _surf), 0.0), 1.0)

        likelihood = min(intent_score * capability_score * opportunity_score, 1.0)
        rationale_text = (
            f"Likelihood = Intent({intent_score:.3f}) × "
            f"Capability({capability_score:.3f}) × "
            f"Opportunity({opportunity_score:.3f}) = {likelihood:.4f}"
        )

        actor_id = actor_name.lower().replace(" ", "-").replace(".", "-")

        results.append(
            PrioritizedActor(
                actor_id=actor_id,
                name=actor_name,
                aliases=aliases,
                likelihood=likelihood,
                score_breakdown=ScoreBreakdown(
                    intent=IntentComponent(
                        score=intent_score,
                        motivation_alignment=_mot,
                        industry_match=_ind,
                        ir_observed=_ir_obs,
                    ),
                    capability=CapabilityComponent(
                        score=capability_score,
                        sophistication_score=_soph,
                        ttp_count_norm=_ttp_n,
                        recency_active_campaigns=_rec,
                        tool_usage=_tool,
                        targeting_persistence=_pers,
                        evasion_capability=_evas,
                        depth=_depth,
                        breadth=_breadth,
                    ),
                    opportunity=OpportunityComponent(
                        score=opportunity_score,
                        victimology_match=_vic,
                        geographic_match=_geo,
                        surface_ttp_coverage=_surf,
                    ),
                    data_quality=DataQualityComponent(
                        degraded=degraded or ir_degraded_this_actor or sage_degraded,
                        missing_sources=(
                            [*missing_sources, "sage_incidents"]
                            if (ir_degraded_this_actor or sage_degraded)
                            and "sage_incidents" not in missing_sources
                            else missing_sources
                        ),
                        ir_boost_skipped=ir_boost_skipped,
                    ),
                ),
                rationale=Rationale(
                    text=rationale_text,
                    intent_factors={
                        "motivation_alignment": _mot,
                        "industry_match": _ind,
                        "ir_observed": _ir_obs,
                    },
                    capability_factors={
                        "sophistication_score": _soph,
                        "ttp_count_norm": _ttp_n,
                        "recency_active_campaigns": _rec,
                        "tool_usage": _tool,
                        "targeting_persistence": _pers,
                        "evasion_capability": _evas,
                        "depth": _depth,
                        "breadth": _breadth,
                    },
                    opportunity_factors={
                        "victimology_match": _vic,
                        "geographic_match": _geo,
                        "surface_ttp_coverage": _surf,
                    },
                ),
            )
        )

    results.sort(key=lambda a: a.likelihood, reverse=True)
    return results
