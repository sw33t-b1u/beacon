"""Tests for cmd/refresh_misp_cache.py — idempotent MISP cache refresh."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from tests.conftest import load_cmd_module

_mod = load_cmd_module("refresh_misp_cache")
_PATCH_PREFIX = "_beacon_cmd_refresh_misp_cache"

_SAMPLE_MISP = {
    "name": "threat-actor",
    "category": "threat-actor",
    "values": [
        {"value": "APT1", "uuid": "abc", "meta": {}},
        {"value": "Lazarus Group", "uuid": "def", "meta": {}},
    ],
}


def _make_ok_response(data: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.content = json.dumps(data or _SAMPLE_MISP).encode()
    return resp


def _make_error_response(status_code: int) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = b"Server Error"
    return resp


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_writes_valid_json(self, tmp_path):
        out = tmp_path / "misp-threat-actor.json"
        with patch(f"{_PATCH_PREFIX}.httpx") as mock_httpx:
            mock_httpx.get.return_value = _make_ok_response()
            mock_httpx.TimeoutException = httpx.TimeoutException
            mock_httpx.HTTPError = httpx.HTTPError
            _mod.refresh("http://example.com/threat-actor.json", out, 60, dry_run=False)

        data = json.loads(out.read_text())
        assert data["name"] == "threat-actor"
        assert len(data["values"]) == 2

    def test_metadata_last_auto_sync_bumped(self, tmp_path):
        out = tmp_path / "misp-threat-actor.json"
        with patch(f"{_PATCH_PREFIX}.httpx") as mock_httpx:
            mock_httpx.get.return_value = _make_ok_response()
            mock_httpx.TimeoutException = httpx.TimeoutException
            mock_httpx.HTTPError = httpx.HTTPError
            _mod.refresh("http://example.com/threat-actor.json", out, 60, dry_run=False)

        data = json.loads(out.read_text())
        assert "_metadata" in data
        ts = data["_metadata"]["last_auto_sync"]
        # ISO8601 UTC: "2026-05-23T03:00:00Z"
        assert ts.endswith("Z")
        assert "T" in ts

    def test_metadata_source_url_set(self, tmp_path):
        out = tmp_path / "misp-threat-actor.json"
        url = "http://example.com/threat-actor.json"
        with patch(f"{_PATCH_PREFIX}.httpx") as mock_httpx:
            mock_httpx.get.return_value = _make_ok_response()
            mock_httpx.TimeoutException = httpx.TimeoutException
            mock_httpx.HTTPError = httpx.HTTPError
            _mod.refresh(url, out, 60, dry_run=False)

        data = json.loads(out.read_text())
        assert data["_metadata"]["source_url"] == url

    def test_atomic_write_no_temp_file_remaining(self, tmp_path):
        out = tmp_path / "misp-threat-actor.json"
        with patch(f"{_PATCH_PREFIX}.httpx") as mock_httpx:
            mock_httpx.get.return_value = _make_ok_response()
            mock_httpx.TimeoutException = httpx.TimeoutException
            mock_httpx.HTTPError = httpx.HTTPError
            _mod.refresh("http://example.com/threat-actor.json", out, 60, dry_run=False)

        # No .tmp files should remain in the cache dir
        tmp_files = list(tmp_path.glob(".misp-threat-actor-*.tmp"))
        assert tmp_files == []

    def test_existing_metadata_fields_preserved(self, tmp_path):
        out = tmp_path / "misp-threat-actor.json"
        existing = dict(_SAMPLE_MISP)
        existing["_metadata"] = {"custom_field": "keep_me", "last_auto_sync": "old-ts"}
        out.write_text(json.dumps(existing), encoding="utf-8")

        with patch(f"{_PATCH_PREFIX}.httpx") as mock_httpx:
            mock_httpx.get.return_value = _make_ok_response()
            mock_httpx.TimeoutException = httpx.TimeoutException
            mock_httpx.HTTPError = httpx.HTTPError
            _mod.refresh("http://example.com/threat-actor.json", out, 60, dry_run=False)

        data = json.loads(out.read_text())
        assert data["_metadata"]["custom_field"] == "keep_me"
        assert data["_metadata"]["last_auto_sync"] != "old-ts"

    def test_output_path_override(self, tmp_path):
        custom = tmp_path / "subdir" / "custom-cache.json"
        with patch(f"{_PATCH_PREFIX}.httpx") as mock_httpx:
            mock_httpx.get.return_value = _make_ok_response()
            mock_httpx.TimeoutException = httpx.TimeoutException
            mock_httpx.HTTPError = httpx.HTTPError
            _mod.refresh("http://example.com/threat-actor.json", custom, 60, dry_run=False)

        assert custom.exists()
        data = json.loads(custom.read_text())
        assert "values" in data


# ---------------------------------------------------------------------------
# HTTP error → exit 1, existing cache untouched
# ---------------------------------------------------------------------------


class TestHttpError:
    def test_http_500_exits_1(self, tmp_path):
        out = tmp_path / "misp-threat-actor.json"
        original = json.dumps({"values": [{"value": "original"}]})
        out.write_text(original, encoding="utf-8")
        original_mtime = out.stat().st_mtime

        with patch(f"{_PATCH_PREFIX}.httpx") as mock_httpx:
            mock_httpx.get.return_value = _make_error_response(500)
            mock_httpx.TimeoutException = httpx.TimeoutException
            mock_httpx.HTTPError = httpx.HTTPError
            with pytest.raises(SystemExit) as exc_info:
                _mod.refresh("http://example.com/threat-actor.json", out, 60, dry_run=False)

        assert exc_info.value.code == 1
        # Cache file must be untouched
        assert out.stat().st_mtime == original_mtime
        assert json.loads(out.read_text())["values"][0]["value"] == "original"


# ---------------------------------------------------------------------------
# JSON parse error → exit 2, existing cache untouched
# ---------------------------------------------------------------------------


class TestJsonParseError:
    def test_bad_json_exits_2(self, tmp_path):
        out = tmp_path / "misp-threat-actor.json"
        original = json.dumps({"values": [{"value": "safe"}]})
        out.write_text(original, encoding="utf-8")
        original_mtime = out.stat().st_mtime

        bad_resp = MagicMock()
        bad_resp.status_code = 200
        bad_resp.content = b"not json {"

        with patch(f"{_PATCH_PREFIX}.httpx") as mock_httpx:
            mock_httpx.get.return_value = bad_resp
            mock_httpx.TimeoutException = httpx.TimeoutException
            mock_httpx.HTTPError = httpx.HTTPError
            with pytest.raises(SystemExit) as exc_info:
                _mod.refresh("http://example.com/threat-actor.json", out, 60, dry_run=False)

        assert exc_info.value.code == 2
        assert out.stat().st_mtime == original_mtime
        assert json.loads(out.read_text())["values"][0]["value"] == "safe"


# ---------------------------------------------------------------------------
# Network timeout → exit 1
# ---------------------------------------------------------------------------


class TestNetworkTimeout:
    def test_timeout_exits_1(self, tmp_path):
        out = tmp_path / "misp-threat-actor.json"

        with patch(f"{_PATCH_PREFIX}.httpx") as mock_httpx:
            mock_httpx.TimeoutException = httpx.TimeoutException
            mock_httpx.HTTPError = httpx.HTTPError
            mock_httpx.get.side_effect = httpx.TimeoutException("timed out")
            with pytest.raises(SystemExit) as exc_info:
                _mod.refresh("http://example.com/threat-actor.json", out, 5, dry_run=False)

        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# --dry-run: no file write, exit 0
# ---------------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_no_write(self, tmp_path):
        out = tmp_path / "misp-threat-actor.json"
        assert not out.exists()

        with patch(f"{_PATCH_PREFIX}.httpx") as mock_httpx:
            mock_httpx.get.return_value = _make_ok_response()
            mock_httpx.TimeoutException = httpx.TimeoutException
            mock_httpx.HTTPError = httpx.HTTPError
            _mod.refresh("http://example.com/threat-actor.json", out, 60, dry_run=True)

        assert not out.exists()

    def test_dry_run_exit_0(self, tmp_path):
        out = tmp_path / "misp-threat-actor.json"

        with patch(f"{_PATCH_PREFIX}.httpx") as mock_httpx:
            mock_httpx.get.return_value = _make_ok_response()
            mock_httpx.TimeoutException = httpx.TimeoutException
            mock_httpx.HTTPError = httpx.HTTPError
            # Should not raise SystemExit
            _mod.refresh("http://example.com/threat-actor.json", out, 60, dry_run=True)
