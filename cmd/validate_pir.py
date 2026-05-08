"""Deprecation stub — PIR validation has moved to TRACE.

BEACON 0.9.0 retained a schema-only ``validate_pir.py``; from this release
forward the canonical implementation is TRACE's richer validator, which adds
referential checks (taxonomy presence, asset-tag matching, validity window).

This stub remains for one BEACON release so muscle memory and any pinned
documentation has time to redirect, then will be deleted entirely.
"""

from __future__ import annotations

import sys

_MESSAGE = (
    "validate_pir has moved to TRACE/cmd/validate_pir.py.\n"
    "Run instead:\n"
    "    cd ../TRACE && uv run python cmd/validate_pir.py --pir <PATH> [--assets <PATH>]\n"
    "TRACE's validator adds referential checks beyond schema (taxonomy "
    "presence, asset-tag match, validity window).\n"
    "See TRACE/docs/beacon_handoff.md for details."
)


def main() -> None:
    print(_MESSAGE, file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
