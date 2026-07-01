"""BEACON configuration — environment-variable based."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# Selectable Gemini models for the PIR web UI dropdowns and per-request
# overrides. Kept in one place so the web UI stays in sync with the tier
# defaults below instead of hard-coding the list in a template. Every entry
# must be available in VERTEX_LOCATION (us-central1); Gemini 3.x preview models
# (e.g. gemini-3.1-pro-preview) require the global endpoint and are therefore
# intentionally excluded.
AVAILABLE_LLM_MODELS: tuple[str, ...] = (
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
    "gemini-2.5-pro",
)


@dataclass
class Config:
    # GCP / Vertex AI
    gcp_project_id: str = field(default_factory=lambda: os.environ.get("GCP_PROJECT_ID", ""))
    vertex_location: str = field(
        default_factory=lambda: os.environ.get("VERTEX_LOCATION", "us-central1")
    )

    # LLM model selection (overridable per environment)
    llm_model_simple: str = field(
        default_factory=lambda: os.environ.get("BEACON_LLM_SIMPLE", "gemini-3.1-flash-lite")
    )
    llm_model_medium: str = field(
        default_factory=lambda: os.environ.get("BEACON_LLM_MEDIUM", "gemini-3.5-flash")
    )
    llm_model_complex: str = field(
        default_factory=lambda: os.environ.get("BEACON_LLM_COMPLEX", "gemini-2.5-pro")
    )

    # LLM output token budgets per tier. Defaults sized for the largest single
    # call we currently make: context_structuring on a long ja-JP context.md.
    # ~7k chars of JP markdown emits ~6k tokens of structured JSON, comfortably
    # below 32768 with headroom; medium / complex tiers retain a similar budget
    # for STIX / PIR generation. Overridable via env vars.
    llm_max_output_tokens_simple: int = field(
        default_factory=lambda: int(os.environ.get("BEACON_LLM_MAX_OUTPUT_SIMPLE", "32768"))
    )
    llm_max_output_tokens_medium: int = field(
        default_factory=lambda: int(os.environ.get("BEACON_LLM_MAX_OUTPUT_MEDIUM", "32768"))
    )
    llm_max_output_tokens_complex: int = field(
        default_factory=lambda: int(os.environ.get("BEACON_LLM_MAX_OUTPUT_COMPLEX", "32768"))
    )

    # GitHub / GHE review workflow
    ghe_token: str = field(default_factory=lambda: os.environ.get("GHE_TOKEN", ""))
    ghe_repo: str = field(default_factory=lambda: os.environ.get("GHE_REPO", ""))
    ghe_api_base: str = field(
        default_factory=lambda: os.environ.get("GHE_API_BASE", "https://api.github.com")
    )

    # SAGE Analysis API
    sage_api_url: str = field(default_factory=lambda: os.environ.get("SAGE_API_URL", ""))

    # Activity window for Capability recency scoring (env: ACTIVITY_WINDOW_DAYS, default 90).
    # Controls the "actively campaigning" bucket threshold in recency_active_campaigns().
    # SAGE uses its own SAGE_ACTIVITY_WINDOW_DAYS (falls back to this value).
    activity_window_days: int = field(
        default_factory=lambda: int(os.environ.get("ACTIVITY_WINDOW_DAYS", "90"))
    )

    # IR lookback window for actor_triage IR-boost (env: BEACON_IR_LOOKBACK_DAYS,
    # default 365). Controls the (today - N) .. today window over which BEACON
    # queries SAGE /api/incidents to compute ir_observed per actor
    # (Initiative G Phase 6).
    ir_lookback_days: int = field(
        default_factory=lambda: int(os.environ.get("BEACON_IR_LOOKBACK_DAYS", "365"))
    )

    # Storage backend selection (Initiative I Phase 1).
    # BEACON_STORAGE: "local" (default) or "gcs".
    storage_backend: str = field(default_factory=lambda: os.environ.get("BEACON_STORAGE", "local"))
    # BEACON_STORAGE_BASE_DIR: root directory for LocalStorage (default: "output").
    storage_base_dir: str = field(
        default_factory=lambda: os.environ.get("BEACON_STORAGE_BASE_DIR", "output")
    )
    # BEACON_STORAGE_BUCKET: GCS bucket name (required when BEACON_STORAGE=gcs).
    storage_bucket: str = field(default_factory=lambda: os.environ.get("BEACON_STORAGE_BUCKET", ""))
    # BEACON_STORAGE_PREFIX: optional key prefix for all GCS objects.
    storage_prefix: str = field(default_factory=lambda: os.environ.get("BEACON_STORAGE_PREFIX", ""))

    # TRACE integration (Initiative I Phase 4).
    # TRACE_ROOT_PATH: absolute path to the TRACE repository root.
    # When empty the Collection tab shows a "TRACE パスが設定されていません" message.
    trace_root_path: str = field(default_factory=lambda: os.environ.get("TRACE_ROOT_PATH", ""))


def load_config() -> Config:
    """Build a Config honoring the unified `defaults < file < env` precedence.

    BEACON has two config surfaces that must agree: the web Settings UI
    persists six keys to `.beacon_settings.json` via SettingsManager, while
    every storage/data code path reads its Config from here. If load_config()
    only consulted environment variables, a backend chosen in the web UI (e.g.
    "gcs") would be silently ignored unless the matching env var was also set,
    so PIR/assets persisted to GCS would never be loaded.

    To keep both surfaces unified, the six settings-managed fields
    (storage_backend, storage_base_dir, storage_bucket, storage_prefix,
    sage_api_url, trace_root_path) are sourced from SettingsManager().load(),
    which already applies the `defaults < file < env` priority. All other
    Config fields (gcp/llm/ghe/etc.) keep their existing env-based defaults via
    their default_factory. SettingsManager imports only stdlib, so the local
    import below is cycle-free.
    """
    from beacon.settings import SettingsManager  # local import, cycle-safe

    s = SettingsManager().load()
    return Config(
        storage_backend=s["storage_backend"],
        storage_base_dir=s["storage_base_dir"],
        storage_bucket=s["storage_bucket"],
        storage_prefix=s["storage_prefix"],
        sage_api_url=s["sage_api_url"],
        trace_root_path=s["trace_root_path"],
    )
