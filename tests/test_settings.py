"""Tests for SettingsManager and Settings tab routes (Initiative I Phase 6)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from beacon.web.app import app

client = TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# SettingsManager unit tests
# ---------------------------------------------------------------------------


class TestSettingsManagerLoad:
    def test_returns_defaults_when_no_file(self, tmp_path):
        from beacon.settings import _DEFAULTS, SettingsManager

        mgr = SettingsManager(str(tmp_path / ".beacon_settings.json"))
        loaded = mgr.load()
        for k, v in _DEFAULTS.items():
            assert loaded[k] == v

    def test_file_values_override_defaults(self, tmp_path):
        from beacon.settings import SettingsManager

        settings_file = tmp_path / ".beacon_settings.json"
        settings_file.write_text(
            json.dumps({"storage_backend": "gcs", "gcs_bucket": "my-bucket"}),
            encoding="utf-8",
        )
        mgr = SettingsManager(str(settings_file))
        loaded = mgr.load()
        assert loaded["storage_backend"] == "gcs"
        assert loaded["gcs_bucket"] == "my-bucket"
        # Non-overridden defaults remain
        assert loaded["storage_base_dir"] == "output"

    def test_env_vars_override_file(self, tmp_path, monkeypatch):
        from beacon.settings import SettingsManager

        settings_file = tmp_path / ".beacon_settings.json"
        settings_file.write_text(
            json.dumps({"storage_backend": "gcs", "gcs_bucket": "file-bucket"}),
            encoding="utf-8",
        )
        monkeypatch.setenv("BEACON_GCS_BUCKET", "env-bucket")
        monkeypatch.setenv("BEACON_STORAGE", "local")

        mgr = SettingsManager(str(settings_file))
        loaded = mgr.load()
        # env > file
        assert loaded["gcs_bucket"] == "env-bucket"
        assert loaded["storage_backend"] == "local"

    def test_env_vars_override_defaults_when_no_file(self, tmp_path, monkeypatch):
        from beacon.settings import SettingsManager

        monkeypatch.setenv("SAGE_API_URL", "http://localhost:9999")
        monkeypatch.setenv("TRACE_ROOT_PATH", "/tmp/trace")

        mgr = SettingsManager(str(tmp_path / ".beacon_settings.json"))
        loaded = mgr.load()
        assert loaded["sage_api_url"] == "http://localhost:9999"
        assert loaded["trace_root_path"] == "/tmp/trace"

    def test_corrupt_file_falls_back_to_defaults(self, tmp_path):
        from beacon.settings import _DEFAULTS, SettingsManager

        settings_file = tmp_path / ".beacon_settings.json"
        settings_file.write_text("not valid json", encoding="utf-8")

        mgr = SettingsManager(str(settings_file))
        loaded = mgr.load()
        for k, v in _DEFAULTS.items():
            assert loaded[k] == v

    def test_all_env_map_keys(self, tmp_path, monkeypatch):
        """Every env var in _ENV_MAP is applied correctly."""
        from beacon.settings import _ENV_MAP, SettingsManager

        for env_key, setting_key in _ENV_MAP.items():
            monkeypatch.setenv(env_key, f"test-{setting_key}")

        mgr = SettingsManager(str(tmp_path / ".beacon_settings.json"))
        loaded = mgr.load()

        for env_key, setting_key in _ENV_MAP.items():
            assert loaded[setting_key] == f"test-{setting_key}"


class TestSettingsManagerSave:
    def test_creates_file_with_known_keys(self, tmp_path):
        from beacon.settings import _SETTING_KEYS, SettingsManager

        settings_file = tmp_path / ".beacon_settings.json"
        mgr = SettingsManager(str(settings_file))
        mgr.save({"storage_backend": "gcs", "gcs_bucket": "my-bucket"})

        assert settings_file.exists()
        data = json.loads(settings_file.read_text(encoding="utf-8"))
        assert data["storage_backend"] == "gcs"
        assert data["gcs_bucket"] == "my-bucket"
        # All known keys must be present
        for k in _SETTING_KEYS:
            assert k in data

    def test_unknown_keys_dropped(self, tmp_path):
        from beacon.settings import SettingsManager

        settings_file = tmp_path / ".beacon_settings.json"
        mgr = SettingsManager(str(settings_file))
        mgr.save({"unknown_key": "should-not-appear", "storage_backend": "local"})

        data = json.loads(settings_file.read_text(encoding="utf-8"))
        assert "unknown_key" not in data

    def test_save_roundtrip(self, tmp_path):
        from beacon.settings import SettingsManager

        settings_file = tmp_path / ".beacon_settings.json"
        mgr = SettingsManager(str(settings_file))

        original = {
            "storage_backend": "gcs",
            "storage_base_dir": "artifacts",
            "gcs_bucket": "my-bucket",
            "gcs_prefix": "beacon/",
            "sage_api_url": "http://sage:8001",
            "trace_root_path": "/opt/trace",
        }
        mgr.save(original)

        # Clear env to ensure load reads file, not env
        loaded = mgr.load()
        for k, v in original.items():
            assert loaded[k] == v

    def test_overwrite_existing_file(self, tmp_path):
        from beacon.settings import SettingsManager

        settings_file = tmp_path / ".beacon_settings.json"
        mgr = SettingsManager(str(settings_file))
        mgr.save({"storage_backend": "gcs"})
        mgr.save({"storage_backend": "local"})

        data = json.loads(settings_file.read_text(encoding="utf-8"))
        assert data["storage_backend"] == "local"

    def test_path_property(self, tmp_path):
        from pathlib import Path

        from beacon.settings import SettingsManager

        settings_file = tmp_path / ".beacon_settings.json"
        mgr = SettingsManager(str(settings_file))
        assert mgr.path == Path(str(settings_file))


# ---------------------------------------------------------------------------
# GET /settings
# ---------------------------------------------------------------------------


class TestSettingsPage:
    def test_returns_200(self):
        resp = client.get("/settings")
        assert resp.status_code == 200

    def test_active_tab_is_settings(self):
        resp = client.get("/settings")
        assert resp.status_code == 200
        assert "settings" in resp.text

    def test_shows_storage_fields(self):
        resp = client.get("/settings")
        assert "storage_backend" in resp.text
        assert "storage_base_dir" in resp.text

    def test_shows_sage_url_field(self):
        resp = client.get("/settings")
        assert "sage_api_url" in resp.text

    def test_shows_trace_root_path_field(self):
        resp = client.get("/settings")
        assert "trace_root_path" in resp.text

    def test_shows_system_info(self):
        resp = client.get("/settings")
        assert "BEACON version" in resp.text
        assert "Python version" in resp.text

    def test_shows_saved_message_when_flag_set(self):
        resp = client.get("/settings?saved=1")
        assert resp.status_code == 200
        assert "Settings saved" in resp.text

    def test_no_saved_message_without_flag(self):
        resp = client.get("/settings")
        assert "Settings saved" not in resp.text

    def test_displays_env_overridden_values(self, monkeypatch):
        monkeypatch.setenv("SAGE_API_URL", "http://my-sage:8001")
        resp = client.get("/settings")
        assert resp.status_code == 200
        assert "http://my-sage:8001" in resp.text


# ---------------------------------------------------------------------------
# POST /settings/save
# ---------------------------------------------------------------------------


class TestSettingsSave:
    def _csrf_token(self):
        resp = client.get("/settings")
        return resp.cookies.get("beacon_csrf", "")

    def test_redirects_to_settings_on_success(self, tmp_path, monkeypatch):
        """POST /settings/save should redirect to /settings?saved=1."""
        monkeypatch.chdir(tmp_path)
        csrf = self._csrf_token()
        resp = client.post(
            "/settings/save",
            data={
                "storage_backend": "local",
                "storage_base_dir": "output",
                "gcs_bucket": "",
                "gcs_prefix": "",
                "sage_api_url": "",
                "trace_root_path": "",
                "csrf_token": csrf,
            },
            cookies={"beacon_csrf": csrf},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"].endswith("/settings?saved=1")

    def test_persists_settings_to_file(self, tmp_path, monkeypatch):
        """Saved settings appear in .beacon_settings.json."""
        monkeypatch.chdir(tmp_path)
        csrf = self._csrf_token()
        client.post(
            "/settings/save",
            data={
                "storage_backend": "gcs",
                "storage_base_dir": "output",
                "gcs_bucket": "my-test-bucket",
                "gcs_prefix": "beacon/",
                "sage_api_url": "http://sage:8001",
                "trace_root_path": "/opt/trace",
                "csrf_token": csrf,
            },
            cookies={"beacon_csrf": csrf},
            follow_redirects=False,
        )
        settings_file = tmp_path / ".beacon_settings.json"
        assert settings_file.exists()
        data = json.loads(settings_file.read_text(encoding="utf-8"))
        assert data["storage_backend"] == "gcs"
        assert data["gcs_bucket"] == "my-test-bucket"
        assert data["sage_api_url"] == "http://sage:8001"

    def test_csrf_mismatch_returns_403(self):
        resp = client.post(
            "/settings/save",
            data={
                "storage_backend": "local",
                "csrf_token": "wrong-token",
            },
            cookies={"beacon_csrf": "cookie-token"},
        )
        assert resp.status_code == 403

    def test_missing_csrf_returns_403(self):
        resp = client.post(
            "/settings/save",
            data={"storage_backend": "local"},
            cookies={},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /settings/test-sage
# ---------------------------------------------------------------------------


class TestSettingsTestSage:
    def test_no_url_returns_error(self):
        resp = client.get("/settings/test-sage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"

    def test_empty_url_returns_error(self):
        resp = client.get("/settings/test-sage?sage_url=")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"

    def test_successful_connection(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200

        async def mock_get(url, **kwargs):
            return mock_resp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = mock_get

        with patch("httpx.AsyncClient", return_value=mock_client):
            resp = client.get("/settings/test-sage?sage_url=http://localhost:8001")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_server_error_returns_error_status(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 500

        async def mock_get(url, **kwargs):
            return mock_resp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = mock_get

        with patch("httpx.AsyncClient", return_value=mock_client):
            resp = client.get("/settings/test-sage?sage_url=http://localhost:8001")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"
        assert "500" in data["detail"]

    def test_connection_error_returns_error_status(self):
        import httpx as _httpx

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(side_effect=_httpx.ConnectError("Connection refused"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            resp = client.get("/settings/test-sage?sage_url=http://nonexistent:9999")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "error"
        assert data["detail"]

    def test_4xx_considered_ok(self):
        """A 4xx response (e.g. 404 from misconfigured route) is still 'ok' — server responded."""
        mock_resp = MagicMock()
        mock_resp.status_code = 404

        async def mock_get(url, **kwargs):
            return mock_resp

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = mock_get

        with patch("httpx.AsyncClient", return_value=mock_client):
            resp = client.get("/settings/test-sage?sage_url=http://localhost:8001")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
