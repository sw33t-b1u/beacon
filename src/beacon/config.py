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

    # GitHub / GHE review workflow
    ghe_token: str = field(default_factory=lambda: os.environ.get("GHE_TOKEN", ""))
    ghe_repo: str = field(default_factory=lambda: os.environ.get("GHE_REPO", ""))
    ghe_api_base: str = field(
        default_factory=lambda: os.environ.get("GHE_API_BASE", "https://api.github.com")
    )

    # SAGE Analysis API
    sage_api_url: str = field(default_factory=lambda: os.environ.get("SAGE_API_URL", ""))


def load_config() -> Config:
    return Config()
