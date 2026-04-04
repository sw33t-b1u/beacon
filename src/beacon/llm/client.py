"""Vertex AI Gemini LLM client for BEACON.

Exposes a single `call_llm(task, prompt)` function that is easy to mock in tests.
Vertex AI is initialized lazily on first call.
"""

from __future__ import annotations

import json
from typing import Literal

import structlog

from beacon.config import Config, load_config

# Top-level import with fallback so tests can patch beacon.llm.client.vertexai
# and beacon.llm.client.GenerativeModel without vertexai being installed.
try:
    import vertexai
    from vertexai.generative_models import GenerationConfig, GenerativeModel
except ImportError:  # pragma: no cover
    vertexai = None  # type: ignore[assignment]
    GenerativeModel = None  # type: ignore[assignment,misc]
    GenerationConfig = None  # type: ignore[assignment,misc]

logger = structlog.get_logger(__name__)

TaskType = Literal["simple", "medium", "complex"]

_initialized = False
_config: Config | None = None


def _ensure_initialized(config: Config) -> None:
    global _initialized, _config
    if _initialized and _config is config:
        return
    if vertexai is None:
        raise RuntimeError("google-cloud-aiplatform is required for LLM mode. Run: uv sync")
    vertexai.init(project=config.gcp_project_id, location=config.vertex_location)
    _initialized = True
    _config = config
    logger.info(
        "vertexai_initialized",
        project=config.gcp_project_id,
        location=config.vertex_location,
    )


def call_llm(
    task: TaskType,
    prompt: str,
    *,
    config: Config | None = None,
    json_mode: bool = True,
) -> str:
    """Call Vertex AI Gemini and return the text response.

    Args:
        task: Complexity level — selects the model ("simple", "medium", "complex").
        prompt: Full prompt text to send to the model.
        config: Config instance. Uses load_config() if None.
        json_mode: If True, sets response_mime_type="application/json".

    Returns:
        The model's text response (JSON string if json_mode=True).
    """
    cfg = config or load_config()
    _ensure_initialized(cfg)

    model_name = _model_for_task(task, cfg)

    model = GenerativeModel(model_name)
    generation_config = GenerationConfig(
        response_mime_type="application/json" if json_mode else "text/plain",
        temperature=0.2,
    )

    logger.info("llm_call_start", task=task, model=model_name)
    response = model.generate_content(prompt, generation_config=generation_config)
    text = response.text
    logger.info("llm_call_done", task=task, model=model_name, chars=len(text))
    return text


def call_llm_json(
    task: TaskType,
    prompt: str,
    *,
    config: Config | None = None,
) -> dict | list:
    """Call Vertex AI Gemini and parse the JSON response.

    Raises:
        ValueError: If the response cannot be parsed as JSON.
    """
    raw = call_llm(task, prompt, config=config, json_mode=True)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM returned non-JSON response: {raw[:200]}") from exc


def _model_for_task(task: TaskType, config: Config) -> str:
    mapping = {
        "simple": config.llm_model_simple,
        "medium": config.llm_model_medium,
        "complex": config.llm_model_complex,
    }
    return mapping[task]


def load_prompt(name: str) -> str:
    """Load a prompt template from src/beacon/llm/prompts/<name>.md."""
    from pathlib import Path  # noqa: PLC0415

    path = Path(__file__).parent / "prompts" / name
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text(encoding="utf-8")
