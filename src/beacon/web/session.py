"""Session management: store pipeline results in TMPDIR as JSON files."""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path

_SESSION_PREFIX = "beacon_session_"
_SESSION_TTL = 86400  # 24 hours in seconds
_SESSION_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def _session_dir() -> Path:
    return Path(os.environ.get("TMPDIR", "/tmp"))


def _validate_session_id(session_id: str) -> bool:
    """Return True if session_id is a valid uuid4 hex string (alphanumeric, 32 chars)."""
    return bool(_SESSION_ID_RE.match(session_id))


def _session_path(session_id: str) -> Path | None:
    """Return the session file path, or None if the session_id is invalid."""
    if not _validate_session_id(session_id):
        return None
    return _session_dir() / f"{_SESSION_PREFIX}{session_id}.json"


def create_session(data: dict) -> str:
    """Write session data to a temp file and return the session ID."""
    session_id = uuid.uuid4().hex
    path = _session_dir() / f"{_SESSION_PREFIX}{session_id}.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return session_id


def load_session(session_id: str) -> dict | None:
    """Load session data by ID. Returns None if invalid, not found, or expired."""
    path = _session_path(session_id)
    if path is None or not path.exists():
        return None
    # Check TTL
    age = time.time() - path.stat().st_mtime
    if age > _SESSION_TTL:
        path.unlink(missing_ok=True)
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_session(session_id: str, data: dict) -> None:
    """Overwrite session data. No-op if session_id is invalid."""
    path = _session_path(session_id)
    if path is None:
        return
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def cleanup_old_sessions() -> int:
    """Remove session files older than TTL. Returns count deleted."""
    removed = 0
    for path in _session_dir().glob(f"{_SESSION_PREFIX}*.json"):
        age = time.time() - path.stat().st_mtime
        if age > _SESSION_TTL:
            path.unlink(missing_ok=True)
            removed += 1
    return removed
