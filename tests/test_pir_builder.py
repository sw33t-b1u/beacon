"""Tests for pir_builder.py."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from beacon.analysis.actor_triage import PrioritizedActor, prioritize_actors
from beacon.analysis.asset_mapper import load_asset_tags, map_asset_tags
from beacon.analysis.element_extractor import extract
from beacon.analysis.risk_scorer import RiskScore, score
from beacon.analysis.threat_mapper import load_taxonomy, map_threats
from beacon.generator.pir_builder import PIROutput, PIROutputDocument, build_pirs
from beacon.ingest.misp_client import MispClient
from beacon.ingest.schema import BusinessContext

FIXTURES = Path(__file__).parent / "fixtures"
SCHEMA_DIR = Path(__file__).parent.parent / "schema"
_TRIAGE_MISP_FIXTURE = FIXTURES / "actor_triage_misp_fixture.json"
_FINANCE_CONTEXT = FIXTURES / "sample_context_finance_banking.json"


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


# ---------------------------------------------------------------------------
# Phase 4 — prioritized_actors integration tests
# ---------------------------------------------------------------------------


class TestPrioritizedActorsField:
    """PIROutput.prioritized_actors is always present (may be empty)."""

    def setup_method(self):
        ctx = BusinessContext.model_validate(
            json.loads(_FINANCE_CONTEXT.read_text(encoding="utf-8"))
        )
        elements = extract(ctx)
        taxonomy = load_taxonomy()
        asset_tags_dict = load_asset_tags()
        asset_tag_list = map_asset_tags(elements, asset_tags_dict)
        threat = map_threats(elements, taxonomy)
        self.risk = score(elements, threat)
        self.elements = elements
        self.threat = threat
        self.asset_tag_list = asset_tag_list
        self.asset_tags_dict = asset_tags_dict

    def _build(self, actors: list[PrioritizedActor] | None = None) -> list[PIROutput]:
        return build_pirs(
            self.elements,
            self.threat,
            self.risk,
            self.asset_tag_list,
            self.asset_tags_dict,
            prioritized_actors=actors,
        )

    def test_prioritized_actors_present_when_not_provided(self):
        pirs = self._build(actors=None)
        assert len(pirs) >= 1
        assert hasattr(pirs[0], "prioritized_actors")
        assert isinstance(pirs[0].prioritized_actors, list)

    def test_prioritized_actors_empty_when_none_passed(self):
        pirs = self._build(actors=None)
        assert pirs[0].prioritized_actors == []

    def test_prioritized_actors_embedded_when_provided(self):
        ctx = BusinessContext.model_validate(
            json.loads(_FINANCE_CONTEXT.read_text(encoding="utf-8"))
        )
        taxonomy = load_taxonomy()
        surface_map = json.loads((SCHEMA_DIR / "surface_ttp_map.json").read_text())
        misp = MispClient(cache_path=_TRIAGE_MISP_FIXTURE)
        actors = prioritize_actors(ctx, taxonomy, surface_map, misp)

        pirs = self._build(actors=actors)
        assert len(pirs) >= 1
        # All PIRs share the same organisation-level actor list
        for pir in pirs:
            assert len(pir.prioritized_actors) == len(actors)

    def test_prioritized_actors_likelihood_raw_float(self):
        """likelihood field is raw [0,1] float, not rescaled to percentage."""
        ctx = BusinessContext.model_validate(
            json.loads(_FINANCE_CONTEXT.read_text(encoding="utf-8"))
        )
        taxonomy = load_taxonomy()
        surface_map = json.loads((SCHEMA_DIR / "surface_ttp_map.json").read_text())
        misp = MispClient(cache_path=_TRIAGE_MISP_FIXTURE)
        actors = prioritize_actors(ctx, taxonomy, surface_map, misp)
        pirs = self._build(actors=actors)

        for actor in pirs[0].prioritized_actors:
            assert 0.0 <= actor.likelihood <= 1.0, (
                f"{actor.name}: likelihood {actor.likelihood} must be raw [0,1] float"
            )

    def test_pir_serializes_with_prioritized_actors(self):
        """model_dump() round-trip preserves prioritized_actors structure."""
        ctx = BusinessContext.model_validate(
            json.loads(_FINANCE_CONTEXT.read_text(encoding="utf-8"))
        )
        taxonomy = load_taxonomy()
        surface_map = json.loads((SCHEMA_DIR / "surface_ttp_map.json").read_text())
        misp = MispClient(cache_path=_TRIAGE_MISP_FIXTURE)
        actors = prioritize_actors(ctx, taxonomy, surface_map, misp)
        pirs = self._build(actors=actors)

        dumped = pirs[0].model_dump()
        assert "prioritized_actors" in dumped
        assert isinstance(dumped["prioritized_actors"], list)
        if dumped["prioritized_actors"]:
            first = dumped["prioritized_actors"][0]
            assert "actor_id" in first
            assert "name" in first
            assert "likelihood" in first
            assert "score_breakdown" in first
            assert "rationale" in first


class TestPrioritizedActorsSchemaValidation:
    """pir_output.schema.json must accept valid PIR output with prioritized_actors."""

    def _load_schema(self) -> dict:
        return json.loads((SCHEMA_DIR / "pir_output.schema.json").read_text())

    def test_prioritized_actors_in_required(self):
        # schema_version 0.16.0+: root is PIROutputDocument; PIROutput lives in $defs
        schema = self._load_schema()
        pir_def = schema["$defs"]["PIROutput"]
        assert "prioritized_actors" in pir_def.get("required", [])

    def test_prioritized_actors_defined_as_array(self):
        schema = self._load_schema()
        pa_prop = schema["$defs"]["PIROutput"]["properties"]["prioritized_actors"]
        assert pa_prop["type"] == "array"

    def test_prioritized_actor_def_has_required_fields(self):
        schema = self._load_schema()
        pa_def = schema["$defs"]["PrioritizedActor"]
        required = pa_def.get("required", [])
        for field in ("actor_id", "name", "likelihood", "score_breakdown", "rationale"):
            assert field in required, f"PrioritizedActor missing required field: {field}"

    def test_likelihood_has_bounds(self):
        schema = self._load_schema()
        lh = schema["$defs"]["PrioritizedActor"]["properties"]["likelihood"]
        assert lh.get("minimum") == 0.0
        assert lh.get("maximum") == 1.0

    def test_capability_component_uses_canonical_field_names(self):
        schema = self._load_schema()
        cap_props = schema["$defs"]["CapabilityComponent"]["properties"]
        assert "ttp_count_norm" in cap_props, "Must use canonical name ttp_count_norm"
        assert "recency_active_campaigns" in cap_props


# ---------------------------------------------------------------------------
# Phase 3 — schema_version field tests (BEACON 1.0.0)
# ---------------------------------------------------------------------------


class TestSchemaVersion:
    """PIROutputDocument.schema_version is always present with default '1.0.0'."""

    def _make_doc(self, pirs=None) -> PIROutputDocument:
        if pirs is None:
            from datetime import date, timedelta

            from beacon.generator.pir_builder import RiskScoreModel

            today = date.today()
            pirs = [
                PIROutput(
                    pir_id="PIR-2026-001",
                    intelligence_level="operational",
                    organizational_scope="Engineering (division)",
                    decision_point="Ransomware impact?",
                    description="Test description.",
                    rationale="High composite score.",
                    recommended_action="Review controls.",
                    threat_actor_tags=["ransomware"],
                    asset_weight_rules=[{"tag": "ot", "criticality_multiplier": 2.0}],
                    collection_focus=["Monitor advisories"],
                    valid_from=today.isoformat(),
                    valid_until=(today + timedelta(days=180)).isoformat(),
                    risk_score=RiskScoreModel(likelihood=4, impact=5, composite=20),
                )
            ]
        return PIROutputDocument(pirs=pirs)

    def test_schema_version_present(self):
        doc = self._make_doc()
        dumped = doc.model_dump()
        assert "schema_version" in dumped

    def test_schema_version_default_value(self):
        doc = self._make_doc()
        assert doc.schema_version == "1.0.0"
        dumped = doc.model_dump()
        assert dumped["schema_version"] == "1.0.0"

    def test_schema_version_is_first_key_in_json(self):
        doc = self._make_doc()
        parsed = json.loads(doc.model_dump_json())
        assert list(parsed.keys())[0] == "schema_version", (
            "schema_version must be the first key in JSON output for human readability"
        )

    def test_schema_version_in_document_required(self):
        schema = json.loads((SCHEMA_DIR / "pir_output.schema.json").read_text())
        assert "schema_version" in schema.get("required", []), (
            "schema_version must appear in top-level required[] of the document schema"
        )

    def test_pirs_in_document_required(self):
        schema = json.loads((SCHEMA_DIR / "pir_output.schema.json").read_text())
        assert "pirs" in schema.get("required", [])

    def test_schema_version_not_overrideable_accident(self):
        doc = PIROutputDocument(schema_version="1.0.0", pirs=[])
        assert doc.schema_version == "1.0.0"
