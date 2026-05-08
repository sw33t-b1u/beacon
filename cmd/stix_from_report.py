"""Deprecated — moved to TRACE.

URL/PDF → STIX 2.1 extraction has been transferred to the sibling project
TRACE (Threat Report Analyzer & Crawling Engine) at
`/Users/test/Projects/claude_pj/TRACE/`.

Use TRACE's `cmd/crawl_single.py` instead:

    cd ../TRACE
    uv run python cmd/crawl_single.py --input <PATH_OR_URL>

This stub remains for one release (BEACON 0.9.x) and will be removed in 0.10.0.
"""

from __future__ import annotations

import sys

_MESSAGE = (
    "stix_from_report has moved to TRACE/cmd/crawl_single.py.\n"
    "Run instead:\n"
    "    cd ../TRACE && uv run python cmd/crawl_single.py --input <PATH_OR_URL>\n"
    "See TRACE/docs/beacon_handoff.md for the full migration note."
)


def main() -> None:
    print(_MESSAGE, file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
