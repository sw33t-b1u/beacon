"""CLI: Launch BEACON Web UI (FastAPI + uvicorn).

.. deprecated:: 1.0.0
    Invoke as ``beacon web`` instead. The ``python -m cmd.web_app`` form is
    preserved for 1.x backward compatibility and will be removed in BEACON
    2.0.0.
"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None, *, _from_beacon_cli: bool = False) -> int:
    if not _from_beacon_cli:
        print(
            "DeprecationWarning: `python -m cmd.web_app` is deprecated; "
            "use `beacon web` instead (removal scheduled for 2.0.0).",
            file=sys.stderr,
        )
    parser = argparse.ArgumentParser(description="Start BEACON Web UI.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="Bind port (default: 8080)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload (dev mode)")
    args = parser.parse_args(argv)

    import uvicorn  # noqa: PLC0415

    uvicorn.run(
        "beacon.web.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
