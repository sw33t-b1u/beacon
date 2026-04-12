"""Convert a PDF or web article to a STIX 2.1 bundle via LLM extraction.

Uses Vertex AI Gemini (via BEACON's LLM client) to extract threat actors, TTPs,
malware, tools, vulnerabilities, indicators, and relationships from a CTI report.

Usage:
    # From a PDF report
    uv run python cmd/stix_from_report.py --input report.pdf

    # From a web article (quote the URL to prevent shell glob expansion)
    uv run python cmd/stix_from_report.py --input 'https://example.com/apt-report?id=1'

    # Specify output path
    uv run python cmd/stix_from_report.py --input report.pdf --output output/bundle.json

    # Use the more powerful (but slower) model for dense reports
    uv run python cmd/stix_from_report.py --input report.pdf --task complex

    # Increase input size for long technical reports (default: 20000 chars)
    uv run python cmd/stix_from_report.py --input report.pdf --max-chars 30000

The resulting STIX bundle can be fed directly to SAGE ETL:
    uv run python cmd/run_etl.py --manual-bundle output/stix_bundle.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import structlog

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from beacon.ingest.report_reader import _MAX_CHARS, read_report
from beacon.ingest.stix_extractor import build_stix_bundle, extract_stix_objects

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]
)
logger = structlog.get_logger(__name__)

_OUTPUT_DIR = Path(__file__).parent.parent / "output"


def _default_output(bundle_id: str) -> Path:
    """Return output/stix_bundle_<last-12-chars-of-bundle-id>.json."""
    suffix = bundle_id.replace("bundle--", "")[-12:]
    return _OUTPUT_DIR / f"stix_bundle_{suffix}.json"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract STIX 2.1 bundle from a PDF or web article"
    )
    parser.add_argument(
        "--input",
        required=True,
        metavar="PATH_OR_URL",
        help=(
            "Path to a PDF/text file, or a https:// URL of a CTI article. "
            "Wrap URLs in single quotes in zsh/bash to prevent glob expansion."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Output path for the STIX bundle JSON "
            "(default: output/stix_bundle_<bundle-id-last-12>.json)"
        ),
    )
    parser.add_argument(
        "--task",
        choices=["simple", "medium", "complex"],
        default="medium",
        help=(
            "LLM complexity tier (default: medium = gemini-2.5-flash). "
            "Use 'complex' (gemini-2.5-pro) for dense or multi-language reports — "
            "expect 2–5 minutes per call."
        ),
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=_MAX_CHARS,
        metavar="N",
        help=f"Maximum characters of report text to send to the LLM (default: {_MAX_CHARS})",
    )
    args = parser.parse_args()

    try:
        text = read_report(args.input, max_chars=args.max_chars)
    except FileNotFoundError as exc:
        logger.error("input_not_found", error=str(exc))
        sys.exit(1)

    if not text.strip():
        logger.error("empty_report_text", input=args.input)
        sys.exit(1)

    objects = extract_stix_objects(text, task=args.task)
    bundle = build_stix_bundle(objects)

    out = args.output if args.output is not None else _default_output(bundle["id"])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(bundle, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info("stix_bundle_written", path=str(out), object_count=len(objects))
    print(
        f"STIX bundle written: {out} ({len(objects)} objects)\n"
        f"Feed to SAGE ETL:\n"
        f"  uv run python cmd/run_etl.py --manual-bundle {out}"
    )


if __name__ == "__main__":
    main()
