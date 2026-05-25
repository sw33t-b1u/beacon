"""BEACON settings persistence — env > file > default priority."""

from __future__ import annotations

import json
import os
from pathlib import Path

SETTINGS_FILE = ".beacon_settings.json"

# Ordered list of all persisted setting keys (used for iteration/validation).
_SETTING_KEYS: tuple[str, ...] = (
    "storage_backend",
    "storage_base_dir",
    "gcs_bucket",
    "gcs_prefix",
    "sage_api_url",
    "trace_root_path",
)

_DEFAULTS: dict[str, str] = {
    "storage_backend": "local",
    "storage_base_dir": "output",
    "gcs_bucket": "",
    "gcs_prefix": "",
    "sage_api_url": "",
    "trace_root_path": "",
}

# Map env-var name → setting key.
_ENV_MAP: dict[str, str] = {
    "BEACON_STORAGE": "storage_backend",
    "BEACON_STORAGE_BASE_DIR": "storage_base_dir",
    "BEACON_GCS_BUCKET": "gcs_bucket",
    "BEACON_GCS_PREFIX": "gcs_prefix",
    "SAGE_API_URL": "sage_api_url",
    "TRACE_ROOT_PATH": "trace_root_path",
}


class SettingsManager:
    """Load and persist BEACON settings with env > file > default priority."""

    def __init__(self, settings_path: str = SETTINGS_FILE) -> None:
        self._path = Path(settings_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> dict[str, str]:
        """Return merged settings: defaults < file < env vars."""
        file_settings: dict[str, str] = {}
        if self._path.exists():
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    # Only keep known keys; coerce values to str.
                    file_settings = {k: str(v) for k, v in raw.items() if k in _DEFAULTS}
            except (json.JSONDecodeError, OSError):
                pass  # corrupt file → fall back to defaults silently

        merged: dict[str, str] = {**_DEFAULTS, **file_settings}

        # Env-var overrides (highest priority).
        for env_key, setting_key in _ENV_MAP.items():
            env_val = os.environ.get(env_key)
            if env_val is not None:
                merged[setting_key] = env_val

        return merged

    def save(self, settings: dict[str, str]) -> None:
        """Persist *settings* to the JSON file.

        Only known setting keys are written; unknown keys are silently
        dropped.  Values are always stored as strings.
        """
        filtered = {k: str(settings.get(k, _DEFAULTS.get(k, ""))) for k in _SETTING_KEYS}
        self._path.write_text(json.dumps(filtered, indent=2, ensure_ascii=False), encoding="utf-8")

    @property
    def path(self) -> Path:
        """Return the resolved path to the settings file."""
        return self._path
