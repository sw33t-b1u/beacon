"""BEACON configuration — environment-variable based."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class Config:
    # GCP / Vertex AI
    gcp_project_id: str = field(default_factory=lambda: os.environ.get("GCP_PROJECT_ID", ""))
    vertex_location: str = field(
        default_factory=lambda: os.environ.get("VERTEX_LOCATION", "us-central1")
    )

    # LLM model selection (overridable per environment)
    llm_model_simple: str = field(
        default_factory=lambda: os.environ.get("BEACON_LLM_SIMPLE", "gemini-2.5-flash-lite")
    )
    llm_model_medium: str = field(
        default_factory=lambda: os.environ.get("BEACON_LLM_MEDIUM", "gemini-2.5-flash")
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
    # BEACON_GCS_BUCKET: GCS bucket name (required when BEACON_STORAGE=gcs).
    gcs_bucket: str = field(default_factory=lambda: os.environ.get("BEACON_GCS_BUCKET", ""))
    # BEACON_GCS_PREFIX: optional key prefix for all GCS objects.
    gcs_prefix: str = field(default_factory=lambda: os.environ.get("BEACON_GCS_PREFIX", ""))

    # TRACE integration (Initiative I Phase 4).
    # TRACE_ROOT_PATH: absolute path to the TRACE repository root.
    # When empty the Collection tab shows a "TRACE パスが設定されていません" message.
    trace_root_path: str = field(default_factory=lambda: os.environ.get("TRACE_ROOT_PATH", ""))


def load_config() -> Config:
    return Config()
