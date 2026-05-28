"""Tests for cmd/generate_pir.py — companion artifact emission (Phase 2).

Asserts that pir-generate also produces assets.json, identity_assets.json,
and user_accounts.json alongside the PIR output, both via StorageBackend
(default) and explicit --output path mode.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from tests.conftest import load_cmd_module

_FIXTURE = Path(__file__).parent / "fixtures" / "sample_context_manufacturing.json"
_mod = load_cmd_module("generate_pir")


# ---------------------------------------------------------------------------
# Helper: run main() with StorageBackend mocked out
# ---------------------------------------------------------------------------


def _make_storage_mock():
    """Return a MagicMock that records save() calls."""
    mock = MagicMock()
    mock.save = MagicMock()
    return mock


# ---------------------------------------------------------------------------
# StorageBackend path (default: no --output)
# ---------------------------------------------------------------------------


class TestCompanionArtifactsStorageBackend:
    """When --output is not given, companion artifacts go via StorageBackend."""

    def test_assets_saved_to_assets_category(self, monkeypatch):
        monkeypatch.delenv("SAGE_API_URL", raising=False)
        mock_storage = _make_storage_mock()
        with (
            patch("beacon.llm.client.call_llm_json", return_value={}),
            patch("beacon.storage.create_storage_backend", return_value=mock_storage),
        ):
            rc = _mod.main(
                [
                    "--context",
                    str(_FIXTURE),
                    "--collection-plan",
                    "",
                    "--sources-candidate",
                    "",
                ],
            )
        assert rc == 0
        saved_categories = [args[0] for args, _ in mock_storage.save.call_args_list]
        assert "assets" in saved_categories

    def test_assets_json_filename_pattern(self, monkeypatch):
        monkeypatch.delenv("SAGE_API_URL", raising=False)
        mock_storage = _make_storage_mock()
        with (
            patch("beacon.llm.client.call_llm_json", return_value={}),
            patch("beacon.storage.create_storage_backend", return_value=mock_storage),
        ):
            _mod.main(
                [
                    "--context",
                    str(_FIXTURE),
                    "--collection-plan",
                    "",
                    "--sources-candidate",
                    "",
                ],
            )
        # Collect filenames saved under "assets"
        asset_filenames = [
            args[1] for args, _ in mock_storage.save.call_args_list if args[0] == "assets"
        ]
        assert any(f.startswith("assets_") and f.endswith(".json") for f in asset_filenames)

    def test_identity_assets_saved(self, monkeypatch):
        monkeypatch.delenv("SAGE_API_URL", raising=False)
        mock_storage = _make_storage_mock()
        with (
            patch("beacon.llm.client.call_llm_json", return_value={}),
            patch("beacon.storage.create_storage_backend", return_value=mock_storage),
        ):
            _mod.main(
                [
                    "--context",
                    str(_FIXTURE),
                    "--collection-plan",
                    "",
                    "--sources-candidate",
                    "",
                ],
            )
        asset_filenames = [
            args[1] for args, _ in mock_storage.save.call_args_list if args[0] == "assets"
        ]
        assert any(
            f.startswith("identity_assets_") and f.endswith(".json") for f in asset_filenames
        )

    def test_user_accounts_saved(self, monkeypatch):
        monkeypatch.delenv("SAGE_API_URL", raising=False)
        mock_storage = _make_storage_mock()
        with (
            patch("beacon.llm.client.call_llm_json", return_value={}),
            patch("beacon.storage.create_storage_backend", return_value=mock_storage),
        ):
            _mod.main(
                [
                    "--context",
                    str(_FIXTURE),
                    "--collection-plan",
                    "",
                    "--sources-candidate",
                    "",
                ],
            )
        asset_filenames = [
            args[1] for args, _ in mock_storage.save.call_args_list if args[0] == "assets"
        ]
        assert any(f.startswith("user_accounts_") and f.endswith(".json") for f in asset_filenames)

    def test_all_three_artifacts_saved(self, monkeypatch):
        """Single invocation stores all three companion artifacts."""
        monkeypatch.delenv("SAGE_API_URL", raising=False)
        mock_storage = _make_storage_mock()
        with (
            patch("beacon.llm.client.call_llm_json", return_value={}),
            patch("beacon.storage.create_storage_backend", return_value=mock_storage),
        ):
            _mod.main(
                [
                    "--context",
                    str(_FIXTURE),
                    "--collection-plan",
                    "",
                    "--sources-candidate",
                    "",
                ],
            )
        asset_filenames = [
            args[1] for args, _ in mock_storage.save.call_args_list if args[0] == "assets"
        ]
        has_assets = any(f.startswith("assets_") for f in asset_filenames)
        has_identity = any(f.startswith("identity_assets_") for f in asset_filenames)
        has_accounts = any(f.startswith("user_accounts_") for f in asset_filenames)
        assert has_assets and has_identity and has_accounts

    def test_artifacts_content_is_valid_json(self, monkeypatch):
        """Content saved for each companion artifact is valid JSON."""
        monkeypatch.delenv("SAGE_API_URL", raising=False)
        mock_storage = _make_storage_mock()
        with (
            patch("beacon.llm.client.call_llm_json", return_value={}),
            patch("beacon.storage.create_storage_backend", return_value=mock_storage),
        ):
            _mod.main(
                [
                    "--context",
                    str(_FIXTURE),
                    "--collection-plan",
                    "",
                    "--sources-candidate",
                    "",
                ],
            )
        for args, _ in mock_storage.save.call_args_list:
            category, filename, content = args
            if category == "assets":
                parsed = json.loads(content)
                assert isinstance(parsed, dict)


# ---------------------------------------------------------------------------
# Explicit --output path mode
# ---------------------------------------------------------------------------


class TestCompanionArtifactsExplicitOutput:
    """When --output is given, companion artifacts are written next to it."""

    def test_assets_written_next_to_pir_output(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SAGE_API_URL", raising=False)
        out = tmp_path / "pir_output.json"
        with patch("beacon.llm.client.call_llm_json", return_value={}):
            rc = _mod.main(
                [
                    "--context",
                    str(_FIXTURE),
                    "--output",
                    str(out),
                    "--collection-plan",
                    "/dev/null",
                    "--sources-candidate",
                    "/dev/null",
                ],
            )
        assert rc == 0
        assert (tmp_path / "assets.json").exists()

    def test_identity_assets_written_next_to_pir_output(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SAGE_API_URL", raising=False)
        out = tmp_path / "pir_output.json"
        with patch("beacon.llm.client.call_llm_json", return_value={}):
            _mod.main(
                [
                    "--context",
                    str(_FIXTURE),
                    "--output",
                    str(out),
                    "--collection-plan",
                    "/dev/null",
                    "--sources-candidate",
                    "/dev/null",
                ],
            )
        assert (tmp_path / "identity_assets.json").exists()

    def test_user_accounts_written_next_to_pir_output(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SAGE_API_URL", raising=False)
        out = tmp_path / "pir_output.json"
        with patch("beacon.llm.client.call_llm_json", return_value={}):
            _mod.main(
                [
                    "--context",
                    str(_FIXTURE),
                    "--output",
                    str(out),
                    "--collection-plan",
                    "/dev/null",
                    "--sources-candidate",
                    "/dev/null",
                ],
            )
        assert (tmp_path / "user_accounts.json").exists()

    def test_assets_content_has_assets_key(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SAGE_API_URL", raising=False)
        out = tmp_path / "pir_output.json"
        with patch("beacon.llm.client.call_llm_json", return_value={}):
            _mod.main(
                [
                    "--context",
                    str(_FIXTURE),
                    "--output",
                    str(out),
                    "--collection-plan",
                    "/dev/null",
                    "--sources-candidate",
                    "/dev/null",
                ],
            )
        assets_data = json.loads((tmp_path / "assets.json").read_text(encoding="utf-8"))
        assert "assets" in assets_data

    def test_identity_content_has_identities_key(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SAGE_API_URL", raising=False)
        out = tmp_path / "pir_output.json"
        with patch("beacon.llm.client.call_llm_json", return_value={}):
            _mod.main(
                [
                    "--context",
                    str(_FIXTURE),
                    "--output",
                    str(out),
                    "--collection-plan",
                    "/dev/null",
                    "--sources-candidate",
                    "/dev/null",
                ],
            )
        data = json.loads((tmp_path / "identity_assets.json").read_text(encoding="utf-8"))
        assert "identities" in data

    def test_user_accounts_content_has_user_accounts_key(self, tmp_path, monkeypatch):
        monkeypatch.delenv("SAGE_API_URL", raising=False)
        out = tmp_path / "pir_output.json"
        with patch("beacon.llm.client.call_llm_json", return_value={}):
            _mod.main(
                [
                    "--context",
                    str(_FIXTURE),
                    "--output",
                    str(out),
                    "--collection-plan",
                    "/dev/null",
                    "--sources-candidate",
                    "/dev/null",
                ],
            )
        data = json.loads((tmp_path / "user_accounts.json").read_text(encoding="utf-8"))
        assert "user_accounts" in data
