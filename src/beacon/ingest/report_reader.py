"""Convert CTI reports (PDF, URL, text) to Markdown text for STIX extraction.

Uses markitdown (Microsoft) to convert inputs to clean Markdown.  Compared to
plain-text extraction, Markdown output:
- Discards navigation bars, footers, ads, and sidebars (lower noise)
- Preserves document structure: headings, tables, lists
- Produces 3–5× fewer characters for the same article content

Supported sources:
- https?:// URL   — markitdown fetches and converts the article
- .pdf file       — markitdown extracts text via pdfminer.six
- Any other file  — read as plain text (no conversion needed)
"""

from __future__ import annotations

from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

# Target character limit for the LLM prompt (~2.5 k tokens).
# markitdown's clean Markdown output typically fits a full CTI blog post within
# this limit.  Use read_report(source, max_chars=...) to override.
_MAX_CHARS = 10_000


def _markitdown_convert(source: str) -> str:
    """Convert a URL or file path to Markdown using markitdown.

    Raises:
        RuntimeError: If markitdown is not installed.
    """
    try:
        from markitdown import MarkItDown  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError("markitdown is required for PDF/URL input. Run: uv sync") from exc

    md = MarkItDown()
    result = md.convert(source)
    return result.text_content or ""


def read_report(source: str | Path, max_chars: int = _MAX_CHARS) -> str:
    """Convert a CTI report to Markdown text and truncate to max_chars.

    Detects source type:
    - https?:// URL     → markitdown fetches and converts the article
    - .pdf file         → markitdown extracts and converts via pdfminer.six
    - any other file    → read as plain text (no conversion needed)

    Args:
        source: URL string, PDF path, or plain-text/Markdown file path.
        max_chars: Maximum characters returned (default: _MAX_CHARS = 10,000).
                   Increase for lengthy technical reports.

    Returns:
        Extracted text, truncated to max_chars.

    Raises:
        FileNotFoundError: If a local file does not exist.
        RuntimeError: If markitdown is not installed.
    """
    s = str(source)

    if s.lower().startswith(("http://", "https://")):
        text = _markitdown_convert(s)
        logger.info("url_converted", url=s, chars=len(text))
        return text[:max_chars]

    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"Report file not found: {path}")

    if path.suffix.lower() == ".pdf":
        text = _markitdown_convert(str(path))
        logger.info("pdf_converted", path=str(path), chars=len(text))
        return text[:max_chars]

    # Plain text / Markdown — no conversion needed
    text = path.read_text(encoding="utf-8")
    logger.info("text_read", path=str(path), chars=len(text))
    return text[:max_chars]
