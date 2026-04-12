"""Extract STIX 2.1 objects from CTI report text using LLM.

The LLM (Vertex AI Gemini) reads a CTI report and returns a JSON array of
STIX 2.1 objects (intrusion-set, attack-pattern, malware, tool, vulnerability,
indicator, relationship).  The bundle can then be fed directly to SAGE ETL.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime

import structlog

from beacon.llm.client import TaskType, call_llm, load_prompt

logger = structlog.get_logger(__name__)

# "medium" (gemini-2.5-flash) is the default: fast enough for large CTI articles
# and accurate enough for STIX entity extraction.  Use "complex" only for reports
# with dense, ambiguous, or multi-language content.
_DEFAULT_TASK: TaskType = "medium"

_VALID_STIX_TYPES: frozenset[str] = frozenset(
    {
        "threat-actor",
        "intrusion-set",
        "attack-pattern",
        "malware",
        "tool",
        "vulnerability",
        "indicator",
        "relationship",
    }
)


def _extract_json_from_text(raw: str) -> list | dict | None:
    """Extract a JSON value from a plain-text LLM response.

    The model may wrap the JSON in a Markdown code block (```json ... ```) or
    return it inline.  This function tries, in order:
      1. Parse the full response as-is (already valid JSON)
      2. Extract the content of the first ```json ... ``` block
      3. Find the first '[' or '{' and parse from there
      4. Repair a truncated JSON array by closing after the last complete '}'

    Returns the parsed value, or None if all strategies fail.
    """
    # Strategy 1: verbatim parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Strategy 2: markdown code block  ```json\n...\n```
    block = re.search(r"```(?:json)?\s*\n([\s\S]+?)\n```", raw)
    if block:
        try:
            return json.loads(block.group(1))
        except json.JSONDecodeError:
            pass

    # Strategy 3: find first '[' or '{' and parse from there
    start = min(
        (raw.find("[") if raw.find("[") != -1 else len(raw)),
        (raw.find("{") if raw.find("{") != -1 else len(raw)),
    )
    if start < len(raw):
        try:
            return json.loads(raw[start:])
        except json.JSONDecodeError:
            candidate = raw[start:]

            # Strategy 4: repair truncated array — close after last complete '}'
            last = None
            for m in re.finditer(r"\}", candidate):
                last = m
            if last is not None:
                repaired = re.sub(r",\s*$", "", candidate[: last.end()]) + "\n]"
                try:
                    result = json.loads(repaired)
                    if isinstance(result, list):
                        logger.warning(
                            "truncated_json_repaired",
                            original_chars=len(raw),
                            repaired_objects=len(result),
                        )
                        return result
                except json.JSONDecodeError:
                    pass

    return None


def extract_stix_objects(
    text: str,
    task: TaskType = _DEFAULT_TASK,
    config=None,
) -> list[dict]:
    """Call LLM to extract STIX 2.1 objects from CTI report text.

    Uses plain-text mode (json_mode=False) to avoid Gemini's constrained JSON
    decoding, which can truncate output prematurely for complex STIX structures.
    JSON is extracted from the response with _extract_json_from_text().

    Args:
        text: Plain text of a CTI report (PDF, web article, etc.).
        task: LLM complexity tier. "medium" (gemini-2.5-flash) is the default
              and handles typical CTI blog posts and reports well.
              Use "complex" (gemini-2.5-pro) only for dense or ambiguous content.
        config: BEACON Config. Uses load_config() if None.

    Returns:
        List of STIX 2.1 object dicts filtered to known STIX types.
    """
    template = load_prompt("stix_extraction.md")
    prompt = template.replace("{{REPORT_TEXT}}", text)

    logger.info("extracting_stix_objects", chars=len(text), task=task)
    raw = call_llm(task, prompt, config=config, json_mode=False)

    parsed = _extract_json_from_text(raw)
    if parsed is None:
        logger.warning("llm_json_extract_failed", chars=len(raw))
        return []

    # LLM may return a bare list or a wrapped {"objects": [...]}
    if isinstance(parsed, dict):
        objects: list = parsed.get("objects", [])
    elif isinstance(parsed, list):
        objects = parsed
    else:
        logger.warning("unexpected_llm_response_format", response_type=type(parsed).__name__)
        objects = []

    valid = [o for o in objects if isinstance(o, dict) and o.get("type") in _VALID_STIX_TYPES]
    logger.info("stix_objects_extracted", total=len(objects), valid=len(valid))
    return valid


def build_stix_bundle(objects: list[dict]) -> dict:
    """Wrap extracted STIX objects in a STIX 2.1 bundle.

    Args:
        objects: List of STIX 2.1 object dicts from extract_stix_objects().

    Returns:
        A STIX 2.1 bundle dict ready for JSON serialization or SAGE ETL.
    """
    now = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return {
        "type": "bundle",
        "id": f"bundle--{uuid.uuid4()}",
        "spec_version": "2.1",
        "created": now,
        "objects": objects,
    }
