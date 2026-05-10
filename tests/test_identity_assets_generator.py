"""Tests for analysis/identity_assets_generator.py (Initiative A)."""

from __future__ import annotations

from beacon.analysis.identity_assets_generator import generate_identity_assets_json
from beacon.ingest.schema import (
    BusinessContext,
    HasAccess,
    Identity,
    Organization,
)


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
                    name="電子マネーシステム部 運用保守エンジニアチーム",
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
        assert ident["name"].startswith("電子マネーシステム部")

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
                    role="Edy Core Processing 運用保守",
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
        assert edge["role"] == "Edy Core Processing 運用保守"
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
