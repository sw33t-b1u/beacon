"""Tests for schema/content_ja.schema.json and schema/content_ja.json."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

SCHEMA_DIR = Path(__file__).parent.parent / "schema"
CONTENT_JA_PATH = SCHEMA_DIR / "content_ja.json"
SCHEMA_PATH = SCHEMA_DIR / "content_ja.schema.json"


@pytest.fixture(scope="module")
def content_ja() -> dict:
    return json.loads(CONTENT_JA_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


class TestSchemaFileStructure:
    """content_ja.schema.json has required meta-schema fields."""

    def test_schema_keyword_present(self, schema):
        assert "$schema" in schema

    def test_schema_is_draft_2020_12(self, schema):
        assert "2020-12" in schema["$schema"]

    def test_has_intelligence_requirements_def(self, schema):
        assert "IntelligenceRequirement" in schema["$defs"]

    def test_has_source_def(self, schema):
        assert "Source" in schema["$defs"]

    def test_has_eei_def(self, schema):
        assert "EEI" in schema["$defs"]

    def test_required_top_level_keys(self, schema):
        required = set(schema.get("required", []))
        for key in (
            "intelligence_requirements",
            "sources",
            "trigger_actions",
            "level_frequency",
            "table",
        ):
            assert key in required

    def test_gir_id_pattern_present(self, schema):
        ir_props = schema["$defs"]["IntelligenceRequirement"]["properties"]
        assert "pattern" in ir_props["gir_id"]

    def test_tier_enum_values(self, schema):
        enum = schema["$defs"]["Source"]["properties"]["tier"]["enum"]
        assert set(enum) == {"strategic", "operational", "tactical", "technical"}

    def test_tlp_enum_values(self, schema):
        enum = schema["$defs"]["Source"]["properties"]["tlp"]["enum"]
        assert "TLP:CLEAR" in enum
        assert "TLP:AMBER" in enum


class TestContentJaTopLevel:
    """content_ja.json has correct top-level structure."""

    def test_has_intelligence_requirements(self, content_ja):
        assert "intelligence_requirements" in content_ja

    def test_has_sources(self, content_ja):
        assert "sources" in content_ja

    def test_has_trigger_actions(self, content_ja):
        assert "trigger_actions" in content_ja

    def test_has_level_frequency(self, content_ja):
        assert "level_frequency" in content_ja

    def test_has_table(self, content_ja):
        assert "table" in content_ja

    def test_no_old_source_map_key(self, content_ja):
        assert "source_map" not in content_ja

    def test_no_old_default_sources_key(self, content_ja):
        assert "default_sources" not in content_ja

    def test_intelligence_requirements_is_list(self, content_ja):
        assert isinstance(content_ja["intelligence_requirements"], list)

    def test_sources_is_list(self, content_ja):
        assert isinstance(content_ja["sources"], list)


class TestIntelligenceRequirements:
    """Each IR entry has correct structure."""

    def test_at_least_one_entry(self, content_ja):
        assert len(content_ja["intelligence_requirements"]) >= 1

    def test_all_have_gir_id(self, content_ja):
        for ir in content_ja["intelligence_requirements"]:
            assert "gir_id" in ir and ir["gir_id"]

    def test_all_have_name(self, content_ja):
        for ir in content_ja["intelligence_requirements"]:
            assert "name" in ir and ir["name"]

    def test_all_have_eei_5w1h(self, content_ja):
        required_fields = {"who", "what", "when", "where", "why", "how"}
        for ir in content_ja["intelligence_requirements"]:
            assert "eei" in ir
            assert required_fields <= ir["eei"].keys(), f"Missing EEI fields in {ir.get('gir_id')}"

    def test_all_have_mitre_attack_groups(self, content_ja):
        for ir in content_ja["intelligence_requirements"]:
            assert "mitre_attack_groups" in ir
            assert isinstance(ir["mitre_attack_groups"], list)

    def test_gir_id_decimal_format(self, content_ja):
        import re

        pattern = re.compile(r"^[1-9][0-9]*(\.[0-9]+)*(-[A-Z0-9]+(-[A-Z0-9]+)*)?$")
        for ir in content_ja["intelligence_requirements"]:
            assert pattern.match(ir["gir_id"]), f"Invalid gir_id: {ir['gir_id']}"

    def test_attack_groups_gxxxx_format(self, content_ja):
        import re

        gid_pattern = re.compile(r"^G[0-9]{4}$")
        for ir in content_ja["intelligence_requirements"]:
            for gid in ir["mitre_attack_groups"]:
                assert gid_pattern.match(gid), f"Invalid group ID: {gid} in {ir['gir_id']}"

    def test_banking_entry_has_china_nexus_groups(self, content_ja):
        # Phase 1.7 acceptance: banking IR must include MirrorFace (G1054)
        banking_entries = [
            ir for ir in content_ja["intelligence_requirements"] if "6.1.3" in ir.get("gir_id", "")
        ]
        assert banking_entries, "No banking GIR 6.1.3.x entry found"
        all_groups = {g for ir in banking_entries for g in ir["mitre_attack_groups"]}
        assert "G1054" in all_groups, "MirrorFace (G1054) missing from banking IR"


class TestSources:
    """Each source entry has correct structure and valid field values."""

    def test_at_least_one_entry(self, content_ja):
        assert len(content_ja["sources"]) >= 1

    def test_all_have_required_keys(self, content_ja):
        required = {
            "name",
            "tier",
            "region",
            "industry_focus",
            "tlp",
            "requires_membership",
            "evidence_attack_groups",
            "evidence_derivation",
        }
        for src in content_ja["sources"]:
            missing = required - src.keys()
            assert not missing, f"Missing keys {missing} in source {src.get('name')}"

    def test_tiers_valid(self, content_ja):
        valid = {"strategic", "operational", "tactical", "technical"}
        for src in content_ja["sources"]:
            assert src["tier"] in valid, f"Invalid tier in {src['name']}"

    def test_regions_nonempty(self, content_ja):
        for src in content_ja["sources"]:
            assert src["region"], f"Empty region in {src['name']}"

    def test_industry_focus_nonempty(self, content_ja):
        for src in content_ja["sources"]:
            assert src["industry_focus"], f"Empty industry_focus in {src['name']}"

    def test_tlp_values_valid(self, content_ja):
        valid = {"TLP:CLEAR", "TLP:AMBER"}
        for src in content_ja["sources"]:
            assert src["tlp"] in valid, f"Invalid TLP in {src['name']}"

    def test_requires_membership_is_bool(self, content_ja):
        for src in content_ja["sources"]:
            assert isinstance(src["requires_membership"], bool), (
                f"requires_membership not bool in {src['name']}"
            )

    def test_evidence_attack_groups_gxxxx_format(self, content_ja):
        import re

        gid_pattern = re.compile(r"^G[0-9]{4}$")
        for src in content_ja["sources"]:
            for gid in src["evidence_attack_groups"]:
                assert gid_pattern.match(gid), f"Invalid group ID {gid} in {src['name']}"

    def test_industry_consensus_has_empty_groups(self, content_ja):
        for src in content_ja["sources"]:
            if src["evidence_derivation"] == "industry_consensus":
                assert src["evidence_attack_groups"] == [], (
                    f"industry_consensus source {src['name']} "
                    "should have empty evidence_attack_groups"
                )

    def test_jpcert_present(self, content_ja):
        names = [s["name"] for s in content_ja["sources"]]
        assert any("JPCERT" in n for n in names)

    def test_jpcert_has_g1054(self, content_ja):
        # MirrorFace (G1054) is China-nexus and JPCERT-tracked — must be in evidence
        jpcert = next((s for s in content_ja["sources"] if "JPCERT" in s["name"]), None)
        assert jpcert is not None
        assert "G1054" in jpcert["evidence_attack_groups"]

    def test_member_only_sources_have_amber_tlp(self, content_ja):
        for src in content_ja["sources"]:
            if src["requires_membership"]:
                assert src["tlp"] == "TLP:AMBER", (
                    f"Member-only source {src['name']} should be TLP:AMBER"
                )


class TestLevelFrequency:
    """level_frequency preserves all required keys."""

    def test_has_strategic(self, content_ja):
        assert "strategic" in content_ja["level_frequency"]

    def test_has_operational(self, content_ja):
        assert "operational" in content_ja["level_frequency"]

    def test_has_tactical(self, content_ja):
        assert "tactical" in content_ja["level_frequency"]

    def test_has_default(self, content_ja):
        assert "default" in content_ja["level_frequency"]


class TestSchemaValidation:
    """content_ja.json validates against content_ja.schema.json."""

    @pytest.fixture(scope="class")
    def validator(self, schema):
        jsonschema = pytest.importorskip("jsonschema")
        return jsonschema.Draft202012Validator(schema)

    def test_content_ja_is_valid(self, content_ja, validator):
        errors = list(validator.iter_errors(content_ja))
        assert not errors, "Schema validation errors:\n" + "\n".join(str(e) for e in errors)

    def test_invalid_tier_rejected(self, schema):
        jsonschema = pytest.importorskip("jsonschema")
        bad_source = {
            "name": "Bad",
            "tier": "unknown_tier",
            "region": ["JP"],
            "industry_focus": ["cross-sector"],
            "tlp": "TLP:CLEAR",
            "requires_membership": False,
            "evidence_attack_groups": [],
            "evidence_derivation": "industry_consensus",
        }
        bad_doc = {
            "intelligence_requirements": [],
            "sources": [bad_source],
            "trigger_actions": {},
            "level_frequency": {
                "strategic": "月次",
                "operational": "週次",
                "tactical": "日次",
                "default": "月次",
            },
            "table": {},
        }
        validator = jsonschema.Draft202012Validator(schema)
        errors = list(validator.iter_errors(bad_doc))
        assert errors, "Schema should reject unknown tier value"

    def test_invalid_gir_id_rejected(self, schema):
        jsonschema = pytest.importorskip("jsonschema")
        bad_ir = {
            "gir_id": "not-a-decimal",
            "name": "Bad IR",
            "eei": {
                "who": "w",
                "what": "w",
                "when": "w",
                "where": "w",
                "why": "w",
                "how": "w",
            },
            "mitre_attack_groups": [],
        }
        bad_doc = {
            "intelligence_requirements": [bad_ir],
            "sources": [],
            "trigger_actions": {},
            "level_frequency": {
                "strategic": "月次",
                "operational": "週次",
                "tactical": "日次",
                "default": "月次",
            },
            "table": {},
        }
        validator = jsonschema.Draft202012Validator(schema)
        errors = list(validator.iter_errors(bad_doc))
        assert errors, "Schema should reject malformed gir_id"
