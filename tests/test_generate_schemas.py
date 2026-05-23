"""Tests for cmd/generate_schemas.py — schema idempotency and constraint coverage.

Verifies that generate_schemas.py is a thin, idempotent dumper: running it
twice produces byte-identical output, and all Pydantic Field constraints are
natively present in the generated schema without any hand-augmentation.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.conftest import load_cmd_module

SCHEMA_DIR = Path(__file__).parent.parent / "schema"
_mod = load_cmd_module("generate_schemas")


class TestGenerateSchemasIdempotent:
    """Running generate_schemas.py twice must produce byte-identical files."""

    def test_pir_schema_idempotent(self, tmp_path):
        """Second invocation of main() yields identical pir_output.schema.json."""
        pir_path = SCHEMA_DIR / "pir_output.schema.json"

        _mod.main()
        first_content = pir_path.read_bytes()

        _mod.main()
        second_content = pir_path.read_bytes()

        assert first_content == second_content, (
            "generate_schemas.py is not idempotent: two consecutive runs "
            "produced different pir_output.schema.json bytes"
        )

    def test_business_context_schema_idempotent(self):
        """Second invocation yields identical business_context.schema.json."""
        bc_path = SCHEMA_DIR / "business_context.schema.json"

        _mod.main()
        first_content = bc_path.read_bytes()

        _mod.main()
        second_content = bc_path.read_bytes()

        assert first_content == second_content


class TestPirSchemaConstraints:
    """pir_output.schema.json carries all Field constraints natively."""

    def setup_method(self):
        self.schema = json.loads((SCHEMA_DIR / "pir_output.schema.json").read_text())

    def test_schema_version_in_document_required(self):
        """schema_version must be in top-level required[] of PIROutputDocument."""
        assert "schema_version" in self.schema.get("required", [])

    def test_pirs_in_document_required(self):
        """pirs must be in top-level required[] of PIROutputDocument."""
        assert "pirs" in self.schema.get("required", [])

    def test_prioritized_actors_in_pir_output_required(self):
        """prioritized_actors must be in PIROutput.$defs required[] natively."""
        pir_def = self.schema["$defs"]["PIROutput"]
        assert "prioritized_actors" in pir_def.get("required", [])

    def test_likelihood_has_min_max(self):
        """PrioritizedActor.likelihood carries ge=0.0 / le=1.0 natively."""
        lh = self.schema["$defs"]["PrioritizedActor"]["properties"]["likelihood"]
        assert lh.get("minimum") == 0.0
        assert lh.get("maximum") == 1.0

    def test_intent_score_bounded(self):
        """IntentComponent.score carries Field(ge=0.0, le=1.0)."""
        score = self.schema["$defs"]["IntentComponent"]["properties"]["score"]
        assert score.get("minimum") == 0.0
        assert score.get("maximum") == 1.0

    def test_intent_sub_factors_bounded(self):
        """motivation_alignment and industry_match carry [0,1] bounds."""
        props = self.schema["$defs"]["IntentComponent"]["properties"]
        for field in ("motivation_alignment", "industry_match"):
            assert props[field].get("minimum") == 0.0, f"{field} missing minimum"
            assert props[field].get("maximum") == 1.0, f"{field} missing maximum"

    def test_capability_score_bounded(self):
        """CapabilityComponent.score carries Field(ge=0.0, le=1.0)."""
        score = self.schema["$defs"]["CapabilityComponent"]["properties"]["score"]
        assert score.get("minimum") == 0.0
        assert score.get("maximum") == 1.0

    def test_capability_sub_factors_bounded(self):
        """All CapabilityComponent sub-factors carry [0,1] bounds."""
        props = self.schema["$defs"]["CapabilityComponent"]["properties"]
        for field in ("sophistication_score", "ttp_count_norm", "recency_active_campaigns"):
            assert props[field].get("minimum") == 0.0, f"{field} missing minimum"
            assert props[field].get("maximum") == 1.0, f"{field} missing maximum"

    def test_opportunity_score_bounded(self):
        """OpportunityComponent.score carries Field(ge=0.0, le=1.0)."""
        score = self.schema["$defs"]["OpportunityComponent"]["properties"]["score"]
        assert score.get("minimum") == 0.0
        assert score.get("maximum") == 1.0

    def test_opportunity_sub_factors_bounded(self):
        """All OpportunityComponent sub-factors carry [0,1] bounds."""
        props = self.schema["$defs"]["OpportunityComponent"]["properties"]
        for field in ("victimology_match", "geographic_match", "surface_ttp_coverage"):
            assert props[field].get("minimum") == 0.0, f"{field} missing minimum"
            assert props[field].get("maximum") == 1.0, f"{field} missing maximum"

    def test_canonical_field_names_present(self):
        """Canonical Phase 3 field names (ttp_count_norm, etc.) are in schema."""
        cap_props = self.schema["$defs"]["CapabilityComponent"]["properties"]
        assert "ttp_count_norm" in cap_props
        assert "recency_active_campaigns" in cap_props
        assert "sophistication_score" in cap_props

    def test_generate_schemas_has_no_post_processing(self):
        """generate_schemas.py source must not contain dict-patching after model_json_schema()."""
        src = Path(__file__).parent.parent / "cmd" / "generate_schemas.py"
        content = src.read_text()
        # These would indicate hand-augmentation of the schema dict outside Pydantic
        forbidden_patterns = [
            'schema["required"]',
            "schema['required']",
            'schema["minimum"]',
            'schema["maximum"]',
            ".append(",
        ]
        for pattern in forbidden_patterns:
            assert pattern not in content, (
                f"generate_schemas.py contains post-processing pattern: {pattern!r}"
            )
