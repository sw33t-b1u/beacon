"""Tests for load_config() unifying SettingsManager with Config.

load_config() must honor the same `defaults < file < env` priority that the
web Settings UI uses, so a backend chosen in the UI (persisted to
`.beacon_settings.json`) is respected by every data/storage code path even
when no matching env var is set.

Each test runs inside an isolated tmp_path (via monkeypatch.chdir) so that
SettingsManager()'s default relative path `.beacon_settings.json` resolves
inside the temp dir, and scrubs the six settings-managed env vars so the
file/default layers are observable.
"""

from __future__ import annotations

import json

import pytest

_SETTINGS_ENV_KEYS = (
    "BEACON_STORAGE",
    "BEACON_STORAGE_BASE_DIR",
    "BEACON_STORAGE_BUCKET",
    "BEACON_STORAGE_PREFIX",
    "SAGE_API_URL",
    "TRACE_ROOT_PATH",
)


@pytest.fixture
def _isolated_settings(tmp_path, monkeypatch):
    """Isolate SettingsManager: chdir into tmp_path, scrub settings env vars."""
    monkeypatch.chdir(tmp_path)
    for key in _SETTINGS_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    return tmp_path


def _write_settings(tmp_path, values):
    (tmp_path / ".beacon_settings.json").write_text(json.dumps(values), encoding="utf-8")


def test_no_file_no_env_uses_defaults(_isolated_settings):
    """With no settings file and no env, the six fields fall back to defaults."""
    from beacon.config import load_config

    cfg = load_config()
    assert cfg.storage_backend == "local"
    assert cfg.storage_base_dir == "output"
    assert cfg.storage_bucket == ""
    assert cfg.storage_prefix == ""
    assert cfg.sage_api_url == ""
    assert cfg.trace_root_path == ""


def test_settings_file_selects_gcs(_isolated_settings):
    """A settings file choosing gcs is reflected in Config without any env var.

    This is the bug-repro/fix-confirm test: before the fix load_config()
    ignored .beacon_settings.json entirely.
    """
    from beacon.config import load_config

    _write_settings(
        _isolated_settings,
        {"storage_backend": "gcs", "storage_bucket": "my-bucket"},
    )
    cfg = load_config()
    assert cfg.storage_backend == "gcs"
    assert cfg.storage_bucket == "my-bucket"
    # Non-overridden keys remain at defaults.
    assert cfg.storage_base_dir == "output"


def test_env_overrides_file(_isolated_settings, monkeypatch):
    """Env var wins over the settings file (highest priority)."""
    from beacon.config import load_config

    _write_settings(_isolated_settings, {"storage_backend": "gcs"})
    monkeypatch.setenv("BEACON_STORAGE", "local")

    cfg = load_config()
    assert cfg.storage_backend == "local"


def test_file_sets_sage_url_and_trace_path(_isolated_settings):
    """sage_api_url and trace_root_path from the file are reflected in Config."""
    from beacon.config import load_config

    _write_settings(
        _isolated_settings,
        {
            "sage_api_url": "http://sage:8001",
            "trace_root_path": "/opt/trace",
        },
    )
    cfg = load_config()
    assert cfg.sage_api_url == "http://sage:8001"
    assert cfg.trace_root_path == "/opt/trace"
