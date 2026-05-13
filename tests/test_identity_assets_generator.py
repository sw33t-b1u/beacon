"""Tests for analysis/identity_assets_generator.py (Initiative A)."""

from __future__ import annotations

import json
from pathlib import Path

from beacon.analysis.identity_assets_generator import generate_identity_assets_json
from beacon.ingest.schema import (
    BusinessContext,
    HasAccess,
    Identity,
    Organization,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _ctx(*, identities=None, has_access=None) -> BusinessContext:
    return BusinessContext(
        organization=Organization(name="TestOrg", industry="finance"),
        identities=identities or [],
        has_access=has_access or [],
    )


class TestEmptyContext:
    def test_empty_lists_yield_empty_arrays_not_missing_keys(self):
        result = generate_identity_assets_json(_ctx())
        assert result["identities"] == []
        assert result["has_access"] == []
        assert result["version"] == 1
        assert "_comment" in result
        assert "TestOrg" in result["_comment"]


class TestSingleIdentity:
    def setup_method(self):
        self.ctx = _ctx(
            identities=[
                Identity(
                    id="id-finance-team",
                    name="情報システム部 運用保守エンジニアチーム",
                    identity_class="group",
                    sectors=["financial-services"],
                    roles=["operations", "maintenance"],
                )
            ]
        )
        self.result = generate_identity_assets_json(self.ctx)

    def test_identity_emitted(self):
        assert len(self.result["identities"]) == 1

    def test_japanese_name_preserved(self):
        ident = self.result["identities"][0]
        assert ident["name"].startswith("情報システム部")

    def test_identity_class_passed_through(self):
        assert self.result["identities"][0]["identity_class"] == "group"

    def test_sectors_and_roles_emitted_as_lists(self):
        ident = self.result["identities"][0]
        assert ident["sectors"] == ["financial-services"]
        assert ident["roles"] == ["operations", "maintenance"]


class TestSingleHasAccessEdge:
    def setup_method(self):
        self.ctx = _ctx(
            identities=[Identity(id="id-finance-team", name="Finance Team")],
            has_access=[
                HasAccess(
                    identity_id="id-finance-team",
                    asset_id="asset-CA-001",
                    access_level="admin",
                    role="Core Processing 運用保守",
                    granted_at="2024-04-01",
                )
            ],
        )
        self.result = generate_identity_assets_json(self.ctx)

    def test_edge_emitted(self):
        assert len(self.result["has_access"]) == 1

    def test_edge_fields_passed_through(self):
        edge = self.result["has_access"][0]
        assert edge["identity_id"] == "id-finance-team"
        assert edge["asset_id"] == "asset-CA-001"
        assert edge["access_level"] == "admin"
        assert edge["role"] == "Core Processing 運用保守"
        assert edge["granted_at"] == "2024-04-01"
        assert edge["revoked_at"] == ""


class TestNoCrossRefValidation:
    """The generator does NOT enforce cross-reference between identities
    and has_access (Initiative A §6.1: that responsibility lives in
    TRACE's validate_identity_assets). Verify the generator passes
    through unresolved references without raising — the validator catches
    them later.
    """

    def test_dangling_identity_id_passes_through(self):
        ctx = _ctx(
            identities=[],
            has_access=[
                HasAccess(identity_id="id-ghost", asset_id="asset-CA-001"),
            ],
        )
        # Should not raise; cross-ref is TRACE's job.
        result = generate_identity_assets_json(ctx)
        assert result["has_access"][0]["identity_id"] == "id-ghost"


class TestDefaults:
    def test_optional_fields_default_to_empty(self):
        ctx = _ctx(
            identities=[Identity(id="id-x", name="X")],
            has_access=[
                HasAccess(identity_id="id-x", asset_id="asset-1"),
            ],
        )
        result = generate_identity_assets_json(ctx)
        ident = result["identities"][0]
        assert ident["sectors"] == []
        assert ident["roles"] == []
        assert ident["description"] == ""
        edge = result["has_access"][0]
        assert edge["access_level"] == "read"  # schema default
        assert edge["role"] == ""
        assert edge["granted_at"] == ""
        assert edge["revoked_at"] == ""


class TestImpersonationFlagPassThrough:
    """Initiative C Phase 2 (0.13.0): the producer must propagate
    ``is_high_value_impersonation_target`` and ``impersonation_risk_factors``
    from BusinessContext into identity_assets.json so SAGE 0.9.0 and TRACE
    1.6.0 can consume them. Flag default is False, list default is [].
    """

    def test_flag_true_with_risk_factors_round_trips(self):
        ctx = _ctx(
            identities=[
                Identity(
                    id="id-cfo",
                    name="Chief Financial Officer",
                    identity_class="individual",
                    roles=["executive"],
                    is_high_value_impersonation_target=True,
                    impersonation_risk_factors=["executive", "public-facing-brand"],
                )
            ]
        )
        result = generate_identity_assets_json(ctx)
        ident = result["identities"][0]
        assert ident["is_high_value_impersonation_target"] is True
        assert ident["impersonation_risk_factors"] == ["executive", "public-facing-brand"]

    def test_flag_default_false_and_empty_risk_factors(self):
        ctx = _ctx(
            identities=[Identity(id="id-team", name="Generic Team")],
        )
        result = generate_identity_assets_json(ctx)
        ident = result["identities"][0]
        assert ident["is_high_value_impersonation_target"] is False
        assert ident["impersonation_risk_factors"] == []

    def test_pydantic_rejects_non_bool_flag(self):
        import pytest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            Identity(
                id="id-x",
                name="X",
                is_high_value_impersonation_target="not-a-bool",  # type: ignore[arg-type]
            )

    def test_round_trip_through_business_context_validation(self):
        ctx = _ctx(
            identities=[
                Identity(
                    id="id-brand",
                    name="Public Brand",
                    identity_class="organization",
                    is_high_value_impersonation_target=True,
                    impersonation_risk_factors=["public-facing-brand", "trusted-supplier"],
                )
            ]
        )
        dumped = ctx.model_dump()
        reloaded = BusinessContext.model_validate(dumped)
        assert reloaded.identities[0].is_high_value_impersonation_target is True
        assert reloaded.identities[0].impersonation_risk_factors == [
            "public-facing-brand",
            "trusted-supplier",
        ]

    def test_legacy_identity_without_flag_remains_valid(self):
        """Existing 0.12.x identity_assets payloads omit the flag entirely.
        Schema must accept them (default False, default [])."""
        legacy_payload = {
            "id": "id-legacy",
            "name": "Legacy Team",
            "identity_class": "group",
            "sectors": [],
            "roles": [],
            "description": "",
        }
        ident = Identity.model_validate(legacy_payload)
        assert ident.is_high_value_impersonation_target is False
        assert ident.impersonation_risk_factors == []

    def test_phase2_fixture_round_trips_through_generator(self):
        """End-to-end: load the Phase 2 fixture, validate as BusinessContext,
        run through generate_identity_assets_json, verify both flag-true
        and flag-false identities are preserved in the output."""
        data = json.loads((FIXTURES / "sample_identities_phase2.json").read_text(encoding="utf-8"))
        # Drop the comment field (not part of BusinessContext schema)
        data.pop("_comment", None)
        ctx = BusinessContext.model_validate(data)
        result = generate_identity_assets_json(ctx)
        by_id = {ident["id"]: ident for ident in result["identities"]}

        assert by_id["id-cfo"]["is_high_value_impersonation_target"] is True
        assert "executive" in by_id["id-cfo"]["impersonation_risk_factors"]
        assert by_id["id-ops-team"]["is_high_value_impersonation_target"] is False
        assert by_id["id-ops-team"]["impersonation_risk_factors"] == []


class TestAssetIdNormalization:
    """0.11.1: ``has_access[*].asset_id`` must share the
    `asset-` prefix convention with ``assets.json``. Without this, the
    TRACE validator's cross-reference check rejects every edge as a
    dangling reference because LLM-extracted ids (``CA-001``) and
    assets_generator-emitted ids (``asset-CA-001``) don't match.
    """

    def test_raw_ca_id_gets_asset_prefix(self):
        ctx = _ctx(
            identities=[Identity(id="id-x", name="X")],
            has_access=[HasAccess(identity_id="id-x", asset_id="CA-001")],
        )
        result = generate_identity_assets_json(ctx)
        assert result["has_access"][0]["asset_id"] == "asset-CA-001"

    def test_already_prefixed_id_passes_through(self):
        ctx = _ctx(
            identities=[Identity(id="id-x", name="X")],
            has_access=[HasAccess(identity_id="id-x", asset_id="asset-CA-001")],
        )
        result = generate_identity_assets_json(ctx)
        assert result["has_access"][0]["asset_id"] == "asset-CA-001"

    def test_idempotent_double_normalization(self):
        # Belt-and-braces: SAGE's load_identity_assets also normalizes,
        # so this artifact must be safe under repeat normalization.
        ctx = _ctx(
            identities=[Identity(id="id-x", name="X")],
            has_access=[HasAccess(identity_id="id-x", asset_id="CA-007")],
        )
        result = generate_identity_assets_json(ctx)
        from beacon.analysis.assets_generator import _normalize_asset_id

        once = result["has_access"][0]["asset_id"]
        twice = _normalize_asset_id(once)
        assert once == twice == "asset-CA-007"
