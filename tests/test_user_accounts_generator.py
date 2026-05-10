"""Tests for analysis/user_accounts_generator.py (Initiative B)."""

from __future__ import annotations

from beacon.analysis.user_accounts_generator import generate_user_accounts_json
from beacon.ingest.schema import (
    AccountOnAsset,
    BusinessContext,
    Organization,
    UserAccount,
)


def _ctx(*, user_accounts=None, account_on_asset=None) -> BusinessContext:
    return BusinessContext(
        organization=Organization(name="TestOrg", industry="finance"),
        user_accounts=user_accounts or [],
        account_on_asset=account_on_asset or [],
    )


class TestEmptyContext:
    def test_empty_lists_yield_empty_arrays_not_missing_keys(self):
        result = generate_user_accounts_json(_ctx())
        assert result["user_accounts"] == []
        assert result["account_on_asset"] == []
        assert result["version"] == 1
        assert "_comment" in result
        assert "TestOrg" in result["_comment"]


class TestSingleUserAccount:
    def setup_method(self):
        self.ctx = _ctx(
            user_accounts=[
                UserAccount(
                    id="ua-alice-corp",
                    account_login="alice@corp.example.com",
                    display_name="Alice Yamamoto",
                    account_type="windows-domain",
                    is_privileged=False,
                    is_service_account=False,
                    identity_id="id-finance-team",
                    description="Domain user account for Alice",
                )
            ]
        )
        self.result = generate_user_accounts_json(self.ctx)

    def test_account_emitted(self):
        assert len(self.result["user_accounts"]) == 1

    def test_fields_passed_through(self):
        ua = self.result["user_accounts"][0]
        assert ua["id"] == "ua-alice-corp"
        assert ua["account_login"] == "alice@corp.example.com"
        assert ua["display_name"] == "Alice Yamamoto"
        assert ua["account_type"] == "windows-domain"
        assert ua["is_privileged"] is False
        assert ua["is_service_account"] is False
        assert ua["identity_id"] == "id-finance-team"


class TestServiceAccount:
    def test_service_account_flags(self):
        ctx = _ctx(
            user_accounts=[
                UserAccount(
                    id="ua-svc-jenkins",
                    account_login="svc-jenkins",
                    account_type="",  # 0.12.1: no STIX OV value matches generic service
                    is_privileged=True,
                    is_service_account=True,
                )
            ]
        )
        result = generate_user_accounts_json(ctx)
        ua = result["user_accounts"][0]
        assert ua["is_privileged"] is True
        assert ua["is_service_account"] is True
        assert ua["identity_id"] == ""  # no human owner


class TestAccountOnAssetEdge:
    def setup_method(self):
        self.ctx = _ctx(
            user_accounts=[UserAccount(id="ua-alice", account_login="alice")],
            account_on_asset=[
                AccountOnAsset(
                    user_account_id="ua-alice",
                    asset_id="CA-005",
                    first_seen="2024-04-01",
                )
            ],
        )
        self.result = generate_user_accounts_json(self.ctx)

    def test_edge_emitted(self):
        assert len(self.result["account_on_asset"]) == 1

    def test_asset_id_normalized_to_asset_prefix(self):
        # Initiative A 0.11.1 lesson: same _normalize_asset_id used by
        # assets_generator must apply here. CA-005 → asset-CA-005 so
        # cross-ref against assets.json works.
        edge = self.result["account_on_asset"][0]
        assert edge["asset_id"] == "asset-CA-005"

    def test_already_prefixed_passes_through(self):
        ctx = _ctx(
            user_accounts=[UserAccount(id="ua-x", account_login="x")],
            account_on_asset=[AccountOnAsset(user_account_id="ua-x", asset_id="asset-CA-001")],
        )
        result = generate_user_accounts_json(ctx)
        assert result["account_on_asset"][0]["asset_id"] == "asset-CA-001"

    def test_edge_first_seen_passed_through(self):
        assert self.result["account_on_asset"][0]["first_seen"] == "2024-04-01"
        assert self.result["account_on_asset"][0]["last_seen"] == ""


class TestSameLoginMultipleHosts:
    def test_two_edges_for_same_account_on_two_hosts(self):
        ctx = _ctx(
            user_accounts=[
                UserAccount(
                    id="ua-root",
                    account_login="root",
                    account_type="unix",
                )
            ],
            account_on_asset=[
                AccountOnAsset(user_account_id="ua-root", asset_id="CA-001"),
                AccountOnAsset(user_account_id="ua-root", asset_id="CA-002"),
            ],
        )
        result = generate_user_accounts_json(ctx)
        assert len(result["account_on_asset"]) == 2
        assert {e["asset_id"] for e in result["account_on_asset"]} == {
            "asset-CA-001",
            "asset-CA-002",
        }


class TestNoCrossRefValidation:
    """Generator does not enforce cross-references between
    user_accounts[*].id ↔ account_on_asset[*].user_account_id, or
    user_accounts[*].identity_id ↔ identities[*].id. That responsibility
    lives in TRACE's validate_user_accounts (Initiative B §6.1).
    """

    def test_dangling_user_account_id_passes_through(self):
        ctx = _ctx(
            user_accounts=[],
            account_on_asset=[
                AccountOnAsset(user_account_id="ua-ghost", asset_id="CA-001"),
            ],
        )
        result = generate_user_accounts_json(ctx)
        assert result["account_on_asset"][0]["user_account_id"] == "ua-ghost"


class TestDefaults:
    def test_optional_fields_default_to_empty(self):
        ctx = _ctx(
            user_accounts=[UserAccount(id="ua-x", account_login="x")],
        )
        result = generate_user_accounts_json(ctx)
        ua = result["user_accounts"][0]
        assert ua["display_name"] == ""
        assert ua["account_type"] == ""  # 0.12.1 strict STIX OV: empty default
        assert ua["is_privileged"] is False
        assert ua["is_service_account"] is False
        assert ua["identity_id"] == ""
        assert ua["description"] == ""
