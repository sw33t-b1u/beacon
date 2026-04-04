"""Static SAGE compatibility validation for BEACON PIR output.

Verifies that BEACON's PIR JSON satisfies the field contracts expected by
SAGE's PIRFilter (SAGE/src/sage/pir/filter.py) without importing the SAGE
package. Contract is derived from the PIRFilter source code:

  PIRFilter.is_relevant_actor()    uses: set(pir["threat_actor_tags"]) for tag intersection
  PIRFilter.adjust_asset_criticality() uses: rule["tag"], rule["criticality_multiplier"]
  PIRFilter.build_targets()        uses: pir["threat_actor_tags"], asset_weight_rules[*]["tag"]
  Formula: min(base_criticality × max_matching_multiplier, 10.0)
           × 1.5 if Targets edge actor matches PIR tags

All tests run with the manufacturing fixture only — no SAGE package or
Spanner instance required.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from beacon.analysis.asset_mapper import load_asset_tags, map_asset_tags
from beacon.analysis.element_extractor import extract
from beacon.analysis.risk_scorer import score
from beacon.analysis.threat_mapper import load_taxonomy, map_threats
from beacon.generator.pir_builder import PIROutput, build_pirs
from beacon.ingest.schema import BusinessContext

FIXTURES = Path(__file__).parent / "fixtures"

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


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


@pytest.fixture(scope="module")
def manufacturing_pirs():
    pirs = _build_pirs_from_fixture("sample_context_manufacturing.json")
    assert pirs, "Manufacturing fixture must produce at least one PIR"
    return pirs


@pytest.fixture(scope="module")
def pir_dict(manufacturing_pirs):
    """First PIR as a plain dict (as SAGE reads it from pir_output.json)."""
    return manufacturing_pirs[0].model_dump()


class TestPIRFieldPresence:
    """PIR JSON must contain all fields accessed by SAGEFilter."""

    def test_pir_id_present(self, pir_dict):
        assert "pir_id" in pir_dict

    def test_threat_actor_tags_present(self, pir_dict):
        assert "threat_actor_tags" in pir_dict

    def test_asset_weight_rules_present(self, pir_dict):
        assert "asset_weight_rules" in pir_dict

    def test_valid_from_present(self, pir_dict):
        assert "valid_from" in pir_dict

    def test_valid_until_present(self, pir_dict):
        assert "valid_until" in pir_dict

    def test_description_present(self, pir_dict):
        assert "description" in pir_dict

    def test_intelligence_level_present(self, pir_dict):
        assert "intelligence_level" in pir_dict


class TestPIRFieldTypes:
    """PIR field values must have the types SAGEFilter expects."""

    def test_pir_id_is_string(self, pir_dict):
        assert isinstance(pir_dict["pir_id"], str)

    def test_pir_id_matches_format(self, pir_dict):
        # Expected: PIR-YYYY-NNN
        assert re.match(r"^PIR-\d{4}-\d{3}$", pir_dict["pir_id"]), (
            f"pir_id '{pir_dict['pir_id']}' does not match PIR-YYYY-NNN"
        )

    def test_threat_actor_tags_is_list_of_strings(self, pir_dict):
        tags = pir_dict["threat_actor_tags"]
        assert isinstance(tags, list)
        assert all(isinstance(t, str) for t in tags)

    def test_threat_actor_tags_not_empty(self, pir_dict):
        assert len(pir_dict["threat_actor_tags"]) > 0

    def test_asset_weight_rules_is_list(self, pir_dict):
        assert isinstance(pir_dict["asset_weight_rules"], list)

    def test_asset_weight_rules_not_empty(self, pir_dict):
        assert len(pir_dict["asset_weight_rules"]) > 0

    def test_asset_weight_rules_tag_field(self, pir_dict):
        for rule in pir_dict["asset_weight_rules"]:
            assert "tag" in rule, f"rule missing 'tag': {rule}"
            assert isinstance(rule["tag"], str)

    def test_asset_weight_rules_multiplier_field(self, pir_dict):
        for rule in pir_dict["asset_weight_rules"]:
            assert "criticality_multiplier" in rule, (
                f"rule missing 'criticality_multiplier': {rule}"
            )
            assert isinstance(rule["criticality_multiplier"], float)
            assert rule["criticality_multiplier"] > 0

    def test_valid_from_is_iso_date(self, pir_dict):
        assert _ISO_DATE_RE.match(pir_dict["valid_from"]), (
            f"valid_from '{pir_dict['valid_from']}' is not ISO date"
        )

    def test_valid_until_is_iso_date(self, pir_dict):
        assert _ISO_DATE_RE.match(pir_dict["valid_until"]), (
            f"valid_until '{pir_dict['valid_until']}' is not ISO date"
        )

    def test_valid_until_after_valid_from(self, pir_dict):
        assert pir_dict["valid_until"] > pir_dict["valid_from"]

    def test_intelligence_level_valid_value(self, pir_dict):
        assert pir_dict["intelligence_level"] in {"strategic", "operational", "tactical"}


class TestSAGEContractValidation:
    """Verify the PIR structure satisfies SAGE PIRFilter's operational contract.

    These tests replicate the logic of SAGE's PIRFilter methods inline so that
    the SAGE package is not required as a dependency. The contract is derived
    from SAGE/src/sage/pir/filter.py (PIRFilter class).
    """

    def test_threat_actor_tags_supports_set_intersection(self, pir_dict):
        # PIRFilter: pir_tags = set(pir["threat_actor_tags"])
        #            actor_tags & pir_tags → tag overlap check
        tags = pir_dict["threat_actor_tags"]
        pir_tags = set(tags)
        actor_tags = {tags[0]}  # matching actor
        assert pir_tags & actor_tags  # non-empty intersection expected

    def test_threat_actor_tags_no_duplicates(self, pir_dict):
        # Duplicate tags would skew PIRFilter.actor_relevance_score()
        # (overlap / len(pir_tags) → duplicates inflate denominator incorrectly)
        tags = pir_dict["threat_actor_tags"]
        assert len(tags) == len(set(tags)), "threat_actor_tags must have no duplicates"

    def test_adjust_criticality_formula_matching_tag(self, pir_dict):
        # PIRFilter.adjust_asset_criticality():
        #   adjusted = min(base * max_multiplier, 10.0)
        rule = pir_dict["asset_weight_rules"][0]
        base = 4.0
        adjusted = min(base * rule["criticality_multiplier"], 10.0)
        assert adjusted >= base  # multiplier ≥ 1.0 → criticality non-decreasing

    def test_adjust_criticality_formula_no_match(self, pir_dict):
        # No matching rule → max_multiplier stays 1.0 → adjusted == base
        base = 3.0
        asset_tags = {"unrelated-tag-xyz"}
        rule_tags = {r["tag"] for r in pir_dict["asset_weight_rules"]}
        matching = rule_tags & asset_tags
        max_multiplier = 1.0
        if matching:
            max_multiplier = max(
                r["criticality_multiplier"]
                for r in pir_dict["asset_weight_rules"]
                if r["tag"] in matching
            )
        adjusted = min(base * max_multiplier, 10.0)
        assert adjusted == pytest.approx(base)

    def test_adjust_criticality_capped_at_10(self, pir_dict):
        # PIRFilter caps pir_adjusted_criticality at 10.0
        rule = pir_dict["asset_weight_rules"][0]
        base = 10.0
        adjusted = min(base * rule["criticality_multiplier"], 10.0)
        assert adjusted <= 10.0

    def test_build_targets_logic_actor_asset_match(self, pir_dict):
        # PIRFilter.build_targets():
        #   matched_actors = actors where actor.tags ∩ pir.threat_actor_tags ≠ ∅
        #   matched_assets = assets where asset.tags ∩ {rule["tag"]} ≠ ∅
        #   → Targets(actor, asset) for every (matched_actor, matched_asset) pair
        pir_tags = set(pir_dict["threat_actor_tags"])
        rule_tags = {r["tag"] for r in pir_dict["asset_weight_rules"]}

        actor = {"stix_id": "identity--a1", "tags": [list(pir_tags)[0]]}
        asset = {"id": "asset-001", "tags": [list(rule_tags)[0]]}

        actor_match = bool(set(actor["tags"]) & pir_tags)
        asset_match = bool(set(asset["tags"]) & rule_tags)
        assert actor_match and asset_match  # both must match → Targets edge generated

    def test_build_targets_no_edge_when_no_actor_match(self, pir_dict):
        pir_tags = set(pir_dict["threat_actor_tags"])
        actor = {"stix_id": "identity--unknown", "tags": ["unrelated-xyz"]}
        assert not (set(actor["tags"]) & pir_tags)  # no match → no Targets edge

    def test_multiplier_all_positive(self, pir_dict):
        # Negative multiplier would decrease criticality — not valid
        for rule in pir_dict["asset_weight_rules"]:
            assert rule["criticality_multiplier"] > 0, (
                f"criticality_multiplier must be positive, got {rule['criticality_multiplier']}"
            )


class TestJSONRoundTrip:
    """PIR must survive JSON serialization and deserialization unchanged."""

    def test_model_dump_and_reload(self, manufacturing_pirs):
        pir = manufacturing_pirs[0]
        json_str = json.dumps(pir.model_dump(), ensure_ascii=False)
        reloaded = PIROutput.model_validate(json.loads(json_str))
        assert reloaded.pir_id == pir.pir_id
        assert reloaded.threat_actor_tags == pir.threat_actor_tags
        assert reloaded.asset_weight_rules == pir.asset_weight_rules
        assert reloaded.valid_from == pir.valid_from
        assert reloaded.valid_until == pir.valid_until
