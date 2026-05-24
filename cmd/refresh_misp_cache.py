"""Idempotent MISP threat-actor cache refresh script.

Downloads the MISP Galaxy threat-actor cluster JSON from upstream and writes it
atomically to the local cache file used by MispClient.  Safe to run from cron —
on any failure the existing cache is left untouched.

Usage:
    uv run python -m cmd.refresh_misp_cache
    uv run python -m cmd.refresh_misp_cache --output /custom/path/misp-threat-actor.json
    uv run python -m cmd.refresh_misp_cache --dry-run

Exit codes:
    0 — success (or dry-run)
    1 — HTTP / network error
    2 — JSON parse error

.. deprecated:: 1.0.0
    Invoke as ``beacon misp-cache-refresh`` instead. The
    ``python -m cmd.refresh_misp_cache`` form is preserved for 1.x backward
    compatibility and will be removed in BEACON 2.0.0.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import tempfile
from pathlib import Path

import httpx
import structlog

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]
)
logger = structlog.get_logger(__name__)

_DEFAULT_OUTPUT = Path(__file__).parent.parent / "cache" / "misp-threat-actor.json"
_DEFAULT_SOURCE = (
    "https://raw.githubusercontent.com/MISP/misp-galaxy/main/clusters/threat-actor.json"
)
_DEFAULT_TIMEOUT = 60
_MAX_RETRIES = 1


def _fetch_with_retry(url: str, timeout: int) -> bytes:
    """Download URL, retrying once on transient failures. Returns raw bytes."""
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = httpx.get(url, timeout=timeout, follow_redirects=True)
            if resp.status_code != 200:
                logger.error(
                    "misp_cache_refresh.http_error",
                    status_code=resp.status_code,
                    url=url,
                    attempt=attempt,
                )
                sys.exit(1)
            return resp.content
        except httpx.TimeoutException as exc:
            last_exc = exc
            logger.warning(
                "misp_cache_refresh.timeout",
                url=url,
                attempt=attempt,
                error=str(exc),
            )
        except httpx.HTTPError as exc:
            last_exc = exc
            logger.warning(
                "misp_cache_refresh.network_error",
                url=url,
                attempt=attempt,
                error=str(exc),
            )

    logger.error(
        "misp_cache_refresh.fetch_failed",
        url=url,
        max_retries=_MAX_RETRIES,
        error=str(last_exc),
    )
    sys.exit(1)


def _load_existing_metadata(output_path: Path) -> dict:
    """Return _metadata dict from existing cache file, or {} if absent/unreadable."""
    if not output_path.exists():
        return {}
    try:
        data = json.loads(output_path.read_bytes())
        return dict(data.get("_metadata", {}))
    except Exception:
        return {}


def refresh(source_url: str, output_path: Path, timeout: int, dry_run: bool) -> None:
    logger.info(
        "misp_cache_refresh.start",
        source_url=source_url,
        output_path=str(output_path),
        dry_run=dry_run,
    )

    raw = _fetch_with_retry(source_url, timeout)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error(
            "misp_cache_refresh.json_parse_error",
            error=str(exc),
            source_url=source_url,
        )
        sys.exit(2)

    if dry_run:
        logger.info(
            "misp_cache_refresh.dry_run_ok",
            values_count=len(data.get("values", [])),
        )
        return

    existing_meta = _load_existing_metadata(output_path)
    existing_meta["last_auto_sync"] = _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    existing_meta["source_url"] = source_url
    data["_metadata"] = existing_meta

    output_path.parent.mkdir(parents=True, exist_ok=True)

    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=output_path.parent,
        prefix=".misp-threat-actor-",
        suffix=".tmp",
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp_path, output_path)
    except Exception as exc:
        logger.error(
            "misp_cache_refresh.write_error",
            tmp_path=tmp_path,
            output_path=str(output_path),
            error=str(exc),
        )
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        sys.exit(1)

    logger.info(
        "misp_cache_refresh.done",
        output_path=str(output_path),
        last_auto_sync=existing_meta["last_auto_sync"],
        values_count=len(data.get("values", [])),
    )


def main(argv: list[str] | None = None, *, _from_beacon_cli: bool = False) -> None:
    if not _from_beacon_cli:
        print(
            "DeprecationWarning: `python -m cmd.refresh_misp_cache` is deprecated; "
            "use `beacon misp-cache-refresh` instead (removal scheduled for 2.0.0).",
            file=sys.stderr,
        )
    parser = argparse.ArgumentParser(
        description="Refresh BEACON MISP threat-actor cache from upstream."
    )
    parser.add_argument(
        "--output",
        default=str(_DEFAULT_OUTPUT),
        help=f"Destination path for cache file (default: {_DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--source",
        default=_DEFAULT_SOURCE,
        help="URL of MISP Galaxy threat-actor cluster JSON",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=_DEFAULT_TIMEOUT,
        help="HTTP request timeout in seconds (default: 60)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Download and validate JSON but do not write to disk",
    )
    args = parser.parse_args(argv)

    refresh(
        source_url=args.source,
        output_path=Path(args.output),
        timeout=args.timeout,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
