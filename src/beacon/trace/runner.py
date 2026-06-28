"""TRACE subprocess wrapper for BEACON web UI (Initiative I Phase 4).

Provides functions to run TRACE crawl commands as subprocesses and read
crawl state. All public functions are fail-soft: they never raise on
subprocess or I/O errors; instead they return a CrawlResult with
success=False and a descriptive stderr message.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import structlog

logger = structlog.get_logger(__name__)

# Subprocess timeout in seconds (5 minutes)
_SUBPROCESS_TIMEOUT = 300


@dataclass
class CrawlResult:
    """Result of a TRACE crawl subprocess invocation."""

    success: bool
    stdout: str
    stderr: str
    return_code: int
    # Parsed metadata extracted from stdout (best-effort, may be empty)
    stix_object_count: int = field(default=0)
    pir_relevance_score: float = field(default=0.0)


@dataclass
class DiscoveryResult:
    """Result of a TRACE discover-pir subprocess invocation."""

    success: bool
    stdout: str
    stderr: str
    return_code: int
    candidates: list[dict] = field(default_factory=list)
    candidate_count: int = 0
    window: dict = field(default_factory=dict)


def _validate_url(url: str) -> bool:
    """Return True only for http/https URLs (basic scheme check).

    Prevents shell injection via URL argument passed to subprocess.
    """
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:  # noqa: BLE001
        return False


def _parse_stdout_metadata(stdout: str) -> tuple[int, float]:
    """Best-effort extraction of STIX object count and PIR relevance score from stdout.

    Returns (stix_object_count, pir_relevance_score). Defaults to (0, 0.0)
    when nothing can be parsed.

    Parsing strategy (in order):
    1. JSON lines: look for keys like ``stix_objects`` / ``stix_count`` and
       ``pir_relevance`` / ``relevance_score``.
    2. Plain-text regex fallback: TRACE crawl_single.py prints lines like
       ``STIX bundle written: output/stix_bundle_*.json (42 objects)``
       and optionally ``Skipped (relevance score 0.45 < threshold 0.50)``.
    """
    stix_count = 0
    relevance = 0.0

    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            if not isinstance(data, dict):
                continue
            # STIX object count — try multiple key names
            for key in ("stix_objects", "stix_count", "object_count"):
                if key in data and isinstance(data[key], int):
                    stix_count = data[key]
                    break
            # PIR relevance score — try multiple key names
            for key in ("pir_relevance", "relevance_score", "relevance"):
                if key in data and isinstance(data[key], (int, float)):
                    relevance = float(data[key])
                    break
        except (json.JSONDecodeError, ValueError):
            # Regex fallback for plain-text TRACE output
            # "STIX bundle written: output/stix_bundle_*.json (42 objects)"
            m = re.search(r"\((\d+)\s+objects?\)", line)
            if m and stix_count == 0:
                stix_count = int(m.group(1))
            # "relevance score 0.45" (from skipped-below-threshold line)
            m2 = re.search(r"relevance score\s+([\d.]+)", line)
            if m2 and relevance == 0.0:
                try:
                    relevance = float(m2.group(1))
                except ValueError:
                    pass

    return stix_count, relevance


def _parse_discovery_payload(stdout: str) -> tuple[list[dict], dict]:
    """Parse candidate JSON emitted by ``trace discover-pir --json``.

    Returns an empty result when stdout is not valid JSON or does not carry the
    expected candidate envelope. The caller still keeps stdout/stderr so the UI
    can show raw diagnostics.
    """
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return [], {}
    if not isinstance(payload, dict):
        return [], {}
    candidates = payload.get("candidates")
    window = payload.get("window")
    if not isinstance(candidates, list):
        candidates = []
    if not isinstance(window, dict):
        window = {}
    return candidates, window


def run_discover_pir(
    pir_path: str,
    trace_root: str,
    *,
    catalog_path: str = "",
    from_date: str = "",
    to_date: str = "",
    since_days: int | None = None,
    max_candidates: int = 50,
    include_recent: bool = False,
) -> DiscoveryResult:
    """Run ``trace discover-pir --json`` in the TRACE directory.

    Args:
        pir_path: Path to BEACON pir_output.json. Absolute paths are safest;
            relative paths are interpreted by TRACE from ``trace_root``.
        trace_root: Path to the TRACE repository root (used as cwd).
        catalog_path: Optional source catalog path.
        from_date: Optional YYYY-MM-DD start date.
        to_date: Optional YYYY-MM-DD end date.
        since_days: Optional relative date window.
        max_candidates: Maximum candidate count requested from TRACE.
        include_recent: Include recent in-window unmatched articles as fallback candidates.

    Returns:
        DiscoveryResult with parsed candidate metadata when stdout is valid
        candidate JSON. The function is fail-soft and never raises for
        subprocess or path errors.
    """
    if not trace_root:
        return DiscoveryResult(
            success=False,
            stdout="",
            stderr="TRACE パスが設定されていません",
            return_code=-1,
        )
    if not pir_path:
        return DiscoveryResult(
            success=False,
            stdout="",
            stderr="PIR path is required",
            return_code=-1,
        )

    trace_path = Path(trace_root)
    if not trace_path.is_dir():
        return DiscoveryResult(
            success=False,
            stdout="",
            stderr=f"TRACE root does not exist: {trace_root}",
            return_code=-1,
        )

    cmd = [
        "uv",
        "run",
        "trace",
        "discover-pir",
        "--pir",
        pir_path,
        "--json",
        "--max-candidates",
        str(max_candidates),
    ]
    if catalog_path:
        cmd.extend(["--catalog", catalog_path])
    if from_date:
        cmd.extend(["--from", from_date])
    if to_date:
        cmd.extend(["--to", to_date])
    if since_days is not None:
        cmd.extend(["--since-days", str(since_days)])
    if include_recent:
        cmd.append("--include-recent")

    logger.info("trace_discover_pir_start", pir_path=pir_path, trace_root=trace_root)
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(trace_path),
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        logger.warning("trace_discover_pir_timeout", pir_path=pir_path, error=str(exc))
        return DiscoveryResult(
            success=False,
            stdout="",
            stderr=f"Subprocess timed out after {_SUBPROCESS_TIMEOUT}s",
            return_code=-1,
        )
    except OSError as exc:
        logger.warning("trace_discover_pir_oserror", pir_path=pir_path, error=str(exc))
        return DiscoveryResult(
            success=False,
            stdout="",
            stderr=f"Failed to start subprocess: {exc}",
            return_code=-1,
        )

    candidates, window = _parse_discovery_payload(proc.stdout)
    success = proc.returncode == 0
    logger.info(
        "trace_discover_pir_done",
        pir_path=pir_path,
        return_code=proc.returncode,
        candidate_count=len(candidates),
    )
    return DiscoveryResult(
        success=success,
        stdout=proc.stdout,
        stderr=proc.stderr,
        return_code=proc.returncode,
        candidates=candidates,
        candidate_count=len(candidates),
        window=window,
    )


def run_crawl_single(url: str, trace_root: str) -> CrawlResult:
    """Run ``uv run python -m cmd.crawl_single --input <url>`` in the TRACE directory.

    Args:
        url: The URL to crawl. Must be http/https.
        trace_root: Path to the TRACE repository root (used as cwd for subprocess).

    Returns:
        CrawlResult with success flag, stdout/stderr, and parsed metadata.
    """
    if not trace_root:
        return CrawlResult(
            success=False,
            stdout="",
            stderr="TRACE パスが設定されていません",
            return_code=-1,
        )

    if not _validate_url(url):
        return CrawlResult(
            success=False,
            stdout="",
            stderr=f"Invalid URL (must be http/https): {url!r}",
            return_code=-1,
        )

    trace_path = Path(trace_root)
    if not trace_path.is_dir():
        return CrawlResult(
            success=False,
            stdout="",
            stderr=f"TRACE root does not exist: {trace_root}",
            return_code=-1,
        )

    cmd = ["uv", "run", "python", "-m", "cmd.crawl_single", "--input", url]
    logger.info("trace_crawl_single_start", url=url, trace_root=trace_root)

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(trace_path),
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        logger.warning("trace_crawl_single_timeout", url=url, error=str(exc))
        return CrawlResult(
            success=False,
            stdout="",
            stderr=f"Subprocess timed out after {_SUBPROCESS_TIMEOUT}s",
            return_code=-1,
        )
    except OSError as exc:
        logger.warning("trace_crawl_single_oserror", url=url, error=str(exc))
        return CrawlResult(
            success=False,
            stdout="",
            stderr=f"Failed to start subprocess: {exc}",
            return_code=-1,
        )

    success = proc.returncode == 0
    stix_count, relevance = _parse_stdout_metadata(proc.stdout)

    logger.info(
        "trace_crawl_single_done",
        url=url,
        return_code=proc.returncode,
        stix_count=stix_count,
    )
    return CrawlResult(
        success=success,
        stdout=proc.stdout,
        stderr=proc.stderr,
        return_code=proc.returncode,
        stix_object_count=stix_count,
        pir_relevance_score=relevance,
    )


def run_crawl_batch(yaml_path: str, trace_root: str, *, pir_path: str = "") -> CrawlResult:
    """Run ``uv run python -m cmd.crawl_batch --sources <yaml_path>`` in the TRACE directory.

    Args:
        yaml_path: Absolute path to the YAML sources file.
        trace_root: Path to the TRACE repository root (used as cwd for subprocess).
        pir_path: Optional BEACON pir_output.json path passed to TRACE for L2/L3/L4 context.

    Returns:
        CrawlResult with success flag, stdout/stderr, and parsed metadata.
    """
    if not trace_root:
        return CrawlResult(
            success=False,
            stdout="",
            stderr="TRACE パスが設定されていません",
            return_code=-1,
        )

    trace_path = Path(trace_root)
    if not trace_path.is_dir():
        return CrawlResult(
            success=False,
            stdout="",
            stderr=f"TRACE root does not exist: {trace_root}",
            return_code=-1,
        )

    cmd = ["uv", "run", "python", "-m", "cmd.crawl_batch", "--sources", yaml_path]
    if pir_path:
        cmd.extend(["--pir", pir_path])
    logger.info(
        "trace_crawl_batch_start",
        yaml_path=yaml_path,
        trace_root=trace_root,
        pir_path=pir_path or None,
    )

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(trace_path),
            capture_output=True,
            text=True,
            timeout=_SUBPROCESS_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        logger.warning("trace_crawl_batch_timeout", yaml_path=yaml_path, error=str(exc))
        return CrawlResult(
            success=False,
            stdout="",
            stderr=f"Subprocess timed out after {_SUBPROCESS_TIMEOUT}s",
            return_code=-1,
        )
    except OSError as exc:
        logger.warning("trace_crawl_batch_oserror", yaml_path=yaml_path, error=str(exc))
        return CrawlResult(
            success=False,
            stdout="",
            stderr=f"Failed to start subprocess: {exc}",
            return_code=-1,
        )

    success = proc.returncode == 0
    stix_count, relevance = _parse_stdout_metadata(proc.stdout)

    logger.info(
        "trace_crawl_batch_done",
        yaml_path=yaml_path,
        return_code=proc.returncode,
        stix_count=stix_count,
    )
    return CrawlResult(
        success=success,
        stdout=proc.stdout,
        stderr=proc.stderr,
        return_code=proc.returncode,
        stix_object_count=stix_count,
        pir_relevance_score=relevance,
    )


def load_crawl_state(trace_root: str) -> list[dict]:
    """Read ``crawl_state.json`` from the TRACE output directory.

    Looks for ``<trace_root>/output/crawl_state.json`` and
    ``<trace_root>/crawl_state.json`` (in that order).

    Returns an empty list when:
    - trace_root is empty or does not exist
    - crawl_state.json is not found
    - the file contains invalid JSON

    Each entry in crawl_state.json should have at minimum:
    ``url``, ``status``, ``timestamp``, ``stix_object_count``.
    """
    if not trace_root:
        return []

    trace_path = Path(trace_root)
    if not trace_path.is_dir():
        return []

    # Check candidate locations
    candidates = [
        trace_path / "output" / "crawl_state.json",
        trace_path / "crawl_state.json",
    ]
    state_path: Path | None = None
    for candidate in candidates:
        if candidate.is_file():
            state_path = candidate
            break

    if state_path is None:
        return []

    try:
        raw = state_path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("trace_crawl_state_read_error", path=str(state_path), error=str(exc))
        return []

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # TRACE CrawlState.save() writes {"version": 1, "entries": {url: {...}, ...}}
        # where entries is a dict keyed by URL. Extract values as a list.
        for key in ("entries", "crawls", "results"):
            if key not in data:
                continue
            value = data[key]
            if isinstance(value, dict):
                # Authentic TRACE format: dict keyed by URL
                return list(value.values())
            if isinstance(value, list):
                # Future-proofing: already a list
                return value
    return []
