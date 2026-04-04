"""Parse business context input (JSON or Markdown) into BusinessContext."""

from __future__ import annotations

import json
from pathlib import Path

import structlog

from beacon.ingest.schema import BusinessContext

logger = structlog.get_logger(__name__)


def parse_json(source: str | Path) -> BusinessContext:
    """Load a JSON file or JSON string and return a validated BusinessContext."""
    if isinstance(source, Path) or (isinstance(source, str) and Path(source).exists()):
        text = Path(source).read_text(encoding="utf-8")
    else:
        text = source  # treat as raw JSON string

    data = json.loads(text)
    ctx = BusinessContext.model_validate(data)
    logger.info("business_context_loaded", org=ctx.organization.name)
    return ctx


def parse_markdown(
    source: str | Path,
    config=None,
) -> BusinessContext:
    """Parse a Markdown strategy document into BusinessContext (one-shot LLM).

    Uses gemini-2.5-flash-lite via Vertex AI to convert the document to
    BusinessContext JSON in a single call.
    """
    from beacon.llm.client import call_llm_json, load_prompt  # noqa: PLC0415

    text = Path(source).read_text(encoding="utf-8") if Path(str(source)).exists() else str(source)
    template = load_prompt("context_structuring.md")
    prompt = template.replace("{{DOCUMENT}}", text)

    logger.info("parsing_markdown_with_llm", chars=len(text))
    data = call_llm_json("simple", prompt, config=config)
    ctx = BusinessContext.model_validate(data)
    logger.info("business_context_from_markdown", org=ctx.organization.name)
    return ctx


def parse(source: str | Path, no_llm: bool = False) -> BusinessContext:
    """Dispatch to the appropriate parser based on file extension and flags."""
    path = Path(source) if not isinstance(source, Path) else source

    if path.suffix.lower() in {".md", ".markdown"}:
        if no_llm:
            raise NotImplementedError(
                "Markdown input requires LLM processing (Phase 2). "
                "Use a JSON file with --no-llm, or omit --no-llm to enable LLM support."
            )
        return parse_markdown(path)

    return parse_json(path)
