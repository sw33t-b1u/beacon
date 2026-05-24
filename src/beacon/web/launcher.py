"""Background launcher for the BEACON review web UI (Initiative H Phase 6).

``launch_web()`` spawns ``cmd/web_app.py`` (uvicorn-backed FastAPI) as a
detached child process bound to a free local port, polls the root URL
until it returns ``200``, prints the URL to stdout, and returns
without blocking the caller. The server stays running until the
operator terminates it; the parent CLI invocation completes.

The chosen output directory is published to the child via the
``BEACON_OUTPUT_DIR`` environment variable so the multi-artifact
landing page (``GET /``) can scan it.

Designed for ``beacon pir-generate`` auto-launch (Decision 14): the
operator finishes a PIR run and immediately sees a clickable URL for
review.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import structlog

logger = structlog.get_logger(__name__)

_DEFAULT_HOST = "127.0.0.1"
_READINESS_TIMEOUT_SECONDS = 10.0
_READINESS_POLL_INTERVAL_SECONDS = 0.2


def _find_free_port() -> int:
    """Bind a transient socket to discover a free port, then release it.

    Race-window risk is tolerated: between ``close()`` and uvicorn
    binding, another process could grab the port. Acceptable for a
    single-operator local development server.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((_DEFAULT_HOST, 0))
        return int(sock.getsockname()[1])


def _wait_for_ready(url: str, timeout: float) -> bool:
    """Poll ``url`` until it returns 2xx/3xx or ``timeout`` elapses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(url, timeout=1.0)
            if resp.status_code < 500:
                return True
        except (httpx.HTTPError, OSError):
            pass
        time.sleep(_READINESS_POLL_INTERVAL_SECONDS)
    return False


def launch_web(
    output_dir: Path | str,
    *,
    host: str = _DEFAULT_HOST,
    port: int | None = None,
    timeout: float = _READINESS_TIMEOUT_SECONDS,
) -> str:
    """Start the BEACON web UI as a detached background subprocess.

    Args:
        output_dir: Directory the landing page will scan for artifacts.
        host: Bind host (default 127.0.0.1).
        port: Explicit port; ``None`` picks a free one automatically.
        timeout: Seconds to wait for readiness probe before returning the
            URL anyway (the operator can refresh).

    Returns:
        The URL the operator should open (e.g. ``http://127.0.0.1:54321/``).
    """
    chosen_port = port if port is not None else _find_free_port()
    url = f"http://{host}:{chosen_port}/"

    env = dict(os.environ)
    env["BEACON_OUTPUT_DIR"] = str(Path(output_dir).resolve())

    repo_root = Path(__file__).resolve().parents[3]
    cmd = [
        sys.executable,
        str(repo_root / "cmd" / "web_app.py"),
        "--host",
        host,
        "--port",
        str(chosen_port),
    ]

    # Detach so the parent CLI can exit cleanly while uvicorn keeps running.
    popen_kwargs: dict = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
        "env": env,
    }
    if os.name == "posix":
        popen_kwargs["start_new_session"] = True

    proc = subprocess.Popen(cmd, **popen_kwargs)
    logger.info("beacon_web_launched", pid=proc.pid, url=url, output_dir=str(output_dir))

    if not _wait_for_ready(url, timeout):
        logger.warning("beacon_web_readiness_timeout", url=url, timeout=timeout)

    return url
