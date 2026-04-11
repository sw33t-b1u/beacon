"""Extract STIX 2.1 objects from CTI report text using LLM.

The LLM (Vertex AI Gemini) reads a CTI report and returns a JSON array of
STIX 2.1 objects (intrusion-set, attack-pattern, malware, tool, vulnerability,
indicator, relationship).  The bundle can then be fed directly to SAGE ETL.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog

from beacon.llm.client import TaskType, call_llm_json, load_prompt

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


def extract_stix_objects(
    text: str,
    task: TaskType = _DEFAULT_TASK,
    config=None,
) -> list[dict]:
    """Call LLM to extract STIX 2.1 objects from CTI report text.

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
    raw = call_llm_json(task, prompt, config=config)

    # LLM may return a bare list or a wrapped {"objects": [...]}
    if isinstance(raw, dict):
        objects: list = raw.get("objects", [])
    elif isinstance(raw, list):
        objects = raw
    else:
        logger.warning("unexpected_llm_response_format", response_type=type(raw).__name__)
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
