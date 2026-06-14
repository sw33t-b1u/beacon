"""FastAPI web application for BEACON PIR generation and review."""

from __future__ import annotations

import datetime as _dt
import html as _html
import json
import os
import re
import secrets
import sys
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import Cookie, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from beacon.generator.pir_builder import wrap_envelope
from beacon.web.session import cleanup_old_sessions, create_session, load_session, save_session

logger = structlog.get_logger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


# ---------------------------------------------------------------------------
# Stdlib-only Markdown → HTML filter (no PyPI dep; sandbox-compatible)
# ---------------------------------------------------------------------------


def _inline(escaped: str) -> str:
    """Apply inline Markdown to already-HTML-escaped text."""
    # Bold **x**
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    # Inline code `x`
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    return escaped


def _render_collection_plan_md(text: str) -> str:
    """Render a known subset of Markdown for collection_plan as HTML.

    Handles: H1-H6, unordered (- or *) and ordered (1.) lists, **bold**,
    ``inline code``, horizontal rules (---), > blockquote. Anything else
    falls through as an escaped paragraph.

    H2 headings are wrapped in ``<details class="collection-plan-section">``
    (default closed). H1 and H3+ headings are rendered as plain heading tags.
    Content before the first H2 (preamble) is rendered without wrapping.

    Stdlib-only (only ``re`` and ``html`` modules) — no PyPI dep.
    """
    if not text:
        return ""
    lines = text.split("\n")
    out: list[str] = []
    in_ul = False
    in_ol = False
    in_section = False  # True when inside a <details> H2 section

    def _close_lists() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False

    def _close_section() -> None:
        nonlocal in_section
        if in_section:
            out.append("</div></details>")
            in_section = False

    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            _close_lists()
            out.append("")
            continue
        # Horizontal rule
        if re.fullmatch(r"-{3,}", line.strip()):
            _close_lists()
            out.append("<hr>")
            continue
        # Headings
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            _close_lists()
            level = len(m.group(1))
            title_escaped = _html.escape(m.group(2))
            if level == 1:
                # H1: close any open section, render as plain <h1>
                _close_section()
                out.append(f"<h{level}>{_inline(title_escaped)}</h{level}>")
            elif level == 2:
                # H2: close previous section, open new <details> section
                _close_section()
                summary = (
                    f'<summary><span class="section-title">'
                    f"{_inline(title_escaped)}"
                    f"</span></summary>"
                )
                out.append(
                    f'<details class="collection-plan-section">{summary}<div class="section-body">'
                )
                in_section = True
            else:
                # H3+: render as plain heading inside (or outside) section
                out.append(f"<h{level}>{_inline(title_escaped)}</h{level}>")
            continue
        # Blockquote
        if line.lstrip().startswith("> "):
            _close_lists()
            content = _inline(_html.escape(line.lstrip()[2:]))
            out.append(f"<blockquote>{content}</blockquote>")
            continue
        # Unordered list
        m = re.match(r"^\s*[-*]\s+(.*)$", line)
        if m:
            if in_ol:
                out.append("</ol>")
                in_ol = False
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"  <li>{_inline(_html.escape(m.group(1)))}</li>")
            continue
        # Ordered list
        m = re.match(r"^\s*\d+\.\s+(.*)$", line)
        if m:
            if in_ul:
                out.append("</ul>")
                in_ul = False
            if not in_ol:
                out.append("<ol>")
                in_ol = True
            out.append(f"  <li>{_inline(_html.escape(m.group(1)))}</li>")
            continue
        # Plain paragraph
        _close_lists()
        out.append(f"<p>{_inline(_html.escape(line))}</p>")
    _close_lists()
    _close_section()
    return "\n".join(out)


templates.env.filters["md_to_html"] = _render_collection_plan_md

# Maximum upload size: 10 MB
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024

# Multi-artifact landing-page configuration (Initiative H Phase 6).
# Artifact filenames are aligned with `docs/api-stability.md` §3.8 and the
# default outputs of `beacon pir-generate`. JSON / Markdown / YAML are the
# only three viewer media types — anything else is rejected by name.
_ARTIFACT_FILENAMES: tuple[str, ...] = (
    "pir_output.json",
    "assets.json",
    "identity_assets.json",
    "user_accounts.json",
    "collection_plan.md",
    "sources_candidate.yaml",
)


def _resolve_output_dir() -> Path:
    """Return the directory the landing page scans for generated artifacts.

    Defaults to ``./output`` (matches the legacy CLI default). When
    ``beacon pir-generate`` auto-launches the web UI it sets
    ``BEACON_OUTPUT_DIR`` so the operator sees that run's artifacts.
    """
    env_value = os.environ.get("BEACON_OUTPUT_DIR")
    if env_value:
        return Path(env_value)
    return Path("output")


def _scan_artifacts(output_dir: Path) -> list[dict]:
    """Return descriptors for every present artifact in ``output_dir``.

    Each descriptor carries the filename, size in bytes, ISO-8601 mtime,
    and a viewer URL. PIR outputs link to ``/review/pir/{pir_id}`` for the
    first PIR they contain (multi-PIR documents still resolve here because
    that route fans out from the file); other artifacts go to the
    readonly ``/review/artifacts/{filename}`` viewer.
    """
    descriptors: list[dict] = []
    for name in _ARTIFACT_FILENAMES:
        path = output_dir / name
        if not path.exists() or not path.is_file():
            continue
        stat = path.stat()
        descriptors.append(
            {
                "filename": name,
                "size_bytes": stat.st_size,
                "mtime_iso": _dt.datetime.fromtimestamp(stat.st_mtime).isoformat(
                    timespec="seconds"
                ),
                "view_url": f"/review/artifacts/{name}",
            }
        )
    return descriptors


@asynccontextmanager
async def _lifespan(app: FastAPI):
    cleanup_old_sessions()
    yield


app = FastAPI(title="BEACON PIR Generator", lifespan=_lifespan)


# ---------------------------------------------------------------------------
# CSRF protection
# ---------------------------------------------------------------------------

_CSRF_COOKIE = "beacon_csrf"
_CSRF_FIELD = "csrf_token"


def _generate_csrf_token() -> str:
    return secrets.token_hex(32)


def _set_csrf_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        _CSRF_COOKIE,
        token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=86400,
    )


def _verify_csrf(request_cookie: str, form_token: str) -> None:
    """Raise HTTPException if CSRF tokens do not match."""
    if not request_cookie or not form_token:
        raise HTTPException(status_code=403, detail="Missing CSRF token")
    if not secrets.compare_digest(request_cookie, form_token):
        raise HTTPException(status_code=403, detail="CSRF token mismatch")


# ---------------------------------------------------------------------------
# Upload size guard
# ---------------------------------------------------------------------------


async def _read_upload(file: UploadFile, max_bytes: int = _MAX_UPLOAD_BYTES) -> bytes:
    """Read upload content with size limit."""
    content = await file.read()
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large (max {max_bytes // 1024 // 1024} MB)",
        )
    return content


# ---------------------------------------------------------------------------
# HTML routes (Jinja2)
# ---------------------------------------------------------------------------


@app.get("/")
async def root_redirect():
    """Redirect root to /dashboard (Initiative I Phase 2)."""
    return RedirectResponse(url="/dashboard", status_code=302)


@app.get("/dashboard")
async def dashboard(request: Request):
    """Pipeline-wide summary dashboard (Initiative I Phase 5)."""
    import datetime as _datetime  # noqa: PLC0415

    from beacon.config import load_config  # noqa: PLC0415
    from beacon.storage import create_storage_backend  # noqa: PLC0415
    from beacon.trace.runner import load_crawl_state  # noqa: PLC0415

    cfg = load_config()

    # --- StorageBackend: PIR + STIX counts ---
    pir_files: list[str] = []
    stix_files: list[str] = []
    try:
        storage = create_storage_backend(cfg)
        pir_files = storage.list_files("pir")
        pir_files = [f for f in pir_files if f.endswith(".json")]
        stix_files = storage.list_files("stix")
    except Exception:  # noqa: BLE001
        pass

    pir_count = len(pir_files)
    latest_pir_filename = pir_files[-1] if pir_files else ""
    stix_bundle_count = len(stix_files)

    # --- Approval status (best-effort from metadata, not yet implemented) ---
    approval_approved = 0
    approval_total = 0

    # --- Crawl state ---
    crawl_history: list[dict] = []
    if cfg.trace_root_path:
        try:
            crawl_history = load_crawl_state(cfg.trace_root_path)
        except Exception:  # noqa: BLE001
            crawl_history = []

    crawl_total = len(crawl_history)

    # Count entries with a timestamp within the last 24 hours
    now = _datetime.datetime.now(_datetime.UTC)
    crawl_last_24h = 0
    for entry in crawl_history:
        ts_raw = entry.get("timestamp") or entry.get("crawled_at") or ""
        if not ts_raw:
            continue
        try:
            ts = _datetime.datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
            if (now - ts).total_seconds() < 86400:
                crawl_last_24h += 1
        except (ValueError, TypeError):
            pass

    # --- SAGE API (best-effort, all fail-soft) ---
    sage_offline = True
    # actor/ttp/cve counts are not available via SAGE's current API endpoints;
    # they are displayed as "—" unless a proxy value can be derived (e.g. actor_count
    # may be updated from choke-points targeting_actor_count).
    actor_count: int | str = "—"
    ttp_count: int | str = "—"
    cve_count: int | str = "—"
    choke_points: list[str] = []
    recent_incidents: list[dict] = []

    if cfg.sage_api_url:
        try:
            import httpx as _httpx  # noqa: PLC0415

            _base = cfg.sage_api_url.rstrip("/")

            # Actor count: SAGE has no global actor-count endpoint; shown as "—"
            # (actor_count stays "N/A"; targeting_actor_count is extracted from choke-points below)

            # TTP count: no global /ttps endpoint in SAGE; shown as "—"
            # (ttp_count stays "N/A")

            # CVE count: no /vulnerabilities endpoint in SAGE; shown as "—"
            # (cve_count stays "N/A")

            # Choke-points top-5
            # SAGE returns a bare list, not {"choke_points": [...]}
            try:
                r = _httpx.get(f"{_base}/choke-points", params={"top_n": 5}, timeout=5)
                r.raise_for_status()
                raw_cp = r.json()  # already a list
                if isinstance(raw_cp, list):
                    choke_points = []
                    targeting_actor_total = 0
                    for item in raw_cp[:5]:
                        if isinstance(item, dict):
                            label = item.get("asset_name") or item.get("asset_id") or str(item)
                            score_val = item.get("choke_score")
                            if score_val is not None:
                                label = f"{label} (score: {score_val})"
                            targeting_actor_total += item.get("targeting_actor_count", 0)
                        else:
                            label = str(item)
                        choke_points.append(label)
                    # Use targeting actor count from choke-points as a proxy for actor_count
                    if targeting_actor_total > 0:
                        actor_count = targeting_actor_total
                sage_offline = False
            except Exception:  # noqa: BLE001
                pass

            # Recent incidents (limit 5)
            try:
                r = _httpx.get(f"{_base}/api/incidents", params={"limit": 5}, timeout=5)
                r.raise_for_status()
                d = r.json()
                if isinstance(d, dict):
                    recent_incidents = d.get("incidents", [])
                elif isinstance(d, list):
                    recent_incidents = d
                sage_offline = False
            except Exception:  # noqa: BLE001
                pass

        except Exception:  # noqa: BLE001
            pass

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "active_tab": "dashboard",
            "pir_count": pir_count,
            "latest_pir_filename": latest_pir_filename,
            "stix_bundle_count": stix_bundle_count,
            "approval_approved": approval_approved,
            "approval_total": approval_total,
            "crawl_total": crawl_total,
            "crawl_last_24h": crawl_last_24h,
            "sage_offline": sage_offline,
            "actor_count": actor_count,
            "ttp_count": ttp_count,
            "cve_count": cve_count,
            "choke_points": choke_points,
            "recent_incidents": recent_incidents,
        },
    )


@app.get("/collection")
async def collection(request: Request):
    """Collection tab — TRACE crawl runner + history (Initiative I Phase 4)."""
    from beacon.config import load_config  # noqa: PLC0415
    from beacon.trace.runner import load_crawl_state  # noqa: PLC0415

    cfg = load_config()
    trace_configured = bool(cfg.trace_root_path)
    crawl_history: list[dict] = []
    if trace_configured:
        try:
            crawl_history = load_crawl_state(cfg.trace_root_path)
        except Exception:  # noqa: BLE001
            crawl_history = []

    csrf_token = _generate_csrf_token()
    response = templates.TemplateResponse(
        request=request,
        name="collection.html",
        context={
            "active_tab": "collection",
            "trace_configured": trace_configured,
            "crawl_history": crawl_history,
            "csrf_token": csrf_token,
            "crawl_result": None,
        },
    )
    _set_csrf_cookie(response, csrf_token)
    return response


@app.post("/collection/crawl-single")
async def collection_crawl_single(
    request: Request,
    url: str = Form(...),
    csrf_token: str = Form(default=""),
    beacon_csrf: str = Cookie(default=""),
):
    """Run TRACE crawl-single for a single URL."""
    _verify_csrf(beacon_csrf, csrf_token)

    from beacon.config import load_config  # noqa: PLC0415
    from beacon.trace.runner import load_crawl_state, run_crawl_single  # noqa: PLC0415

    cfg = load_config()
    result = run_crawl_single(url, cfg.trace_root_path)

    trace_configured = bool(cfg.trace_root_path)
    crawl_history: list[dict] = []
    if trace_configured:
        try:
            crawl_history = load_crawl_state(cfg.trace_root_path)
        except Exception:  # noqa: BLE001
            crawl_history = []

    new_csrf = _generate_csrf_token()
    response = templates.TemplateResponse(
        request=request,
        name="collection.html",
        context={
            "active_tab": "collection",
            "trace_configured": trace_configured,
            "crawl_history": crawl_history,
            "csrf_token": new_csrf,
            "crawl_result": {
                "mode": "single",
                "url": url,
                "success": result.success,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "return_code": result.return_code,
                "stix_object_count": result.stix_object_count,
                "pir_relevance_score": result.pir_relevance_score,
            },
        },
    )
    _set_csrf_cookie(response, new_csrf)
    return response


@app.post("/collection/crawl-batch")
async def collection_crawl_batch(
    request: Request,
    sources_file: UploadFile = File(...),
    csrf_token: str = Form(default=""),
    beacon_csrf: str = Cookie(default=""),
):
    """Accept a YAML sources file and run TRACE crawl-batch."""
    _verify_csrf(beacon_csrf, csrf_token)

    import tempfile  # noqa: PLC0415 (already imported at module level but safe to re-import)

    from beacon.config import load_config  # noqa: PLC0415
    from beacon.trace.runner import load_crawl_state, run_crawl_batch  # noqa: PLC0415

    cfg = load_config()

    content = await _read_upload(sources_file)
    # Save to a temp file; the path is passed to crawl_batch
    suffix = Path(sources_file.filename or "sources.yaml").suffix or ".yaml"
    tmp_yaml_path: str = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(content)
            tmp_yaml_path = tmp.name

        result = run_crawl_batch(tmp_yaml_path, cfg.trace_root_path)
    finally:
        if tmp_yaml_path:
            Path(tmp_yaml_path).unlink(missing_ok=True)

    trace_configured = bool(cfg.trace_root_path)
    crawl_history: list[dict] = []
    if trace_configured:
        try:
            crawl_history = load_crawl_state(cfg.trace_root_path)
        except Exception:  # noqa: BLE001
            crawl_history = []

    new_csrf = _generate_csrf_token()
    response = templates.TemplateResponse(
        request=request,
        name="collection.html",
        context={
            "active_tab": "collection",
            "trace_configured": trace_configured,
            "crawl_history": crawl_history,
            "csrf_token": new_csrf,
            "crawl_result": {
                "mode": "batch",
                "filename": sources_file.filename or "sources.yaml",
                "success": result.success,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "return_code": result.return_code,
                "stix_object_count": result.stix_object_count,
                "pir_relevance_score": result.pir_relevance_score,
            },
        },
    )
    _set_csrf_cookie(response, new_csrf)
    return response


@app.get("/collection/api/crawl-state")
async def collection_api_crawl_state():
    """JSON endpoint returning the TRACE crawl history from crawl_state.json."""
    from beacon.config import load_config  # noqa: PLC0415
    from beacon.trace.runner import load_crawl_state  # noqa: PLC0415

    cfg = load_config()
    if not cfg.trace_root_path:
        return JSONResponse({"entries": [], "error": "TRACE パスが設定されていません"})

    try:
        entries = load_crawl_state(cfg.trace_root_path)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"entries": [], "error": str(exc)})

    return JSONResponse({"entries": entries})


@app.get("/threats")
async def threats(request: Request):
    """Threats tab — actor / asset views with SAGE API proxy."""
    from beacon.config import load_config  # noqa: PLC0415

    cfg = load_config()
    sage_configured = bool(cfg.sage_api_url)
    return templates.TemplateResponse(
        request=request,
        name="threats.html",
        context={
            "active_tab": "threats",
            "sage_api_url": cfg.sage_api_url,
            "sage_configured": sage_configured,
        },
    )


@app.get("/threats/api/actors")
async def threats_api_actors(name: str = ""):
    """JSON proxy: search SAGE for threat actors matching *name*."""
    from beacon.config import load_config  # noqa: PLC0415
    from beacon.sage.client import SageAPIClient  # noqa: PLC0415

    cfg = load_config()
    if not cfg.sage_api_url:
        return JSONResponse({"actors": [], "error": "SAGE not configured"})

    client = SageAPIClient(cfg.sage_api_url)
    actors = client.search_actors(name)
    return JSONResponse({"actors": actors})


@app.get("/threats/api/actor-ttps")
async def threats_api_actor_ttps(
    actor_id: str = "",
    since: str = "",
    until: str = "",
):
    """JSON proxy: fetch TTPs for a specific actor from SAGE."""
    from beacon.config import load_config  # noqa: PLC0415
    from beacon.sage.client import SageAPIClient  # noqa: PLC0415

    cfg = load_config()
    if not cfg.sage_api_url:
        return JSONResponse({"ttps": [], "error": "SAGE not configured"})

    client = SageAPIClient(cfg.sage_api_url)
    ttps = client.get_actor_ttps(
        actor_id,
        since=since or None,
        until=until or None,
    )
    return JSONResponse({"ttps": ttps})


@app.get("/threats/api/threat-summary")
async def threats_api_threat_summary(
    asset: str = "",
    since: str = "",
    until: str = "",
):
    """JSON proxy: fetch threat summary for an asset from SAGE."""
    from beacon.config import load_config  # noqa: PLC0415
    from beacon.sage.client import SageAPIClient  # noqa: PLC0415

    cfg = load_config()
    if not cfg.sage_api_url:
        return JSONResponse({"error": "SAGE not configured"})

    client = SageAPIClient(cfg.sage_api_url)
    summary = client.get_threat_summary(
        asset,
        since=since or None,
        until=until or None,
    )
    return JSONResponse(summary)


@app.get("/settings")
async def settings(request: Request, saved: str = ""):
    """Settings tab — display current configuration values."""
    from beacon.settings import SettingsManager  # noqa: PLC0415

    mgr = SettingsManager()
    current_settings = mgr.load()

    # Retrieve BEACON version from package metadata.
    try:
        from importlib.metadata import version as _pkg_version  # noqa: PLC0415

        beacon_version = _pkg_version("beacon")
    except Exception:  # noqa: BLE001
        beacon_version = "unknown"

    python_version = sys.version.split()[0]

    csrf_token = _generate_csrf_token()
    response = templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "active_tab": "settings",
            "settings": current_settings,
            "beacon_version": beacon_version,
            "python_version": python_version,
            "settings_file": str(mgr.path),
            "csrf_token": csrf_token,
            "saved": saved == "1",
            "save_error": None,
        },
    )
    _set_csrf_cookie(response, csrf_token)
    return response


@app.post("/settings/save")
async def settings_save(
    request: Request,
    storage_backend: str = Form(default="local"),
    storage_base_dir: str = Form(default="output"),
    storage_bucket: str = Form(default=""),
    storage_prefix: str = Form(default=""),
    sage_api_url: str = Form(default=""),
    trace_root_path: str = Form(default=""),
    csrf_token: str = Form(default=""),
    beacon_csrf: str = Cookie(default=""),
):
    """Persist settings to .beacon_settings.json."""
    _verify_csrf(beacon_csrf, csrf_token)

    from beacon.settings import SettingsManager  # noqa: PLC0415

    mgr = SettingsManager()
    new_settings = {
        "storage_backend": storage_backend.strip() or "local",
        "storage_base_dir": storage_base_dir.strip() or "output",
        "storage_bucket": storage_bucket.strip(),
        "storage_prefix": storage_prefix.strip(),
        "sage_api_url": sage_api_url.strip(),
        "trace_root_path": trace_root_path.strip(),
    }
    try:
        mgr.save(new_settings)
    except OSError as exc:
        # Re-render the settings page with an error message.
        from importlib.metadata import version as _pkg_version  # noqa: PLC0415

        try:
            beacon_version = _pkg_version("beacon")
        except Exception:  # noqa: BLE001
            beacon_version = "unknown"

        python_version = sys.version.split()[0]
        new_csrf = _generate_csrf_token()
        response = templates.TemplateResponse(
            request=request,
            name="settings.html",
            context={
                "active_tab": "settings",
                "settings": new_settings,
                "beacon_version": beacon_version,
                "python_version": python_version,
                "settings_file": str(mgr.path),
                "csrf_token": new_csrf,
                "saved": False,
                "save_error": str(exc),
            },
        )
        _set_csrf_cookie(response, new_csrf)
        return response

    return RedirectResponse(url="/settings?saved=1", status_code=303)


@app.get("/settings/test-sage")
async def settings_test_sage(sage_url: str = ""):
    """Test connectivity to the SAGE API.

    Sends a lightweight request (GET /choke-points?top_n=1) to the
    provided URL and returns ``{"status": "ok"}`` or
    ``{"status": "error", "detail": "..."}``.
    """
    if not sage_url:
        return JSONResponse({"status": "error", "detail": "No URL provided"})

    try:
        import httpx  # noqa: PLC0415

        async with httpx.AsyncClient(timeout=5.0) as client_h:
            url = sage_url.rstrip("/") + "/choke-points?top_n=1"
            resp = await client_h.get(url)
        if resp.status_code < 500:
            return JSONResponse({"status": "ok"})
        return JSONResponse({"status": "error", "detail": f"HTTP {resp.status_code}"})
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"status": "error", "detail": str(exc)})


@app.get("/pir")
async def pir_page(request: Request, beacon_session: str = Cookie(default="")):
    """Unified PIR page: generate + stored PIRs list + review."""
    from beacon.config import load_config  # noqa: PLC0415
    from beacon.storage import create_storage_backend  # noqa: PLC0415

    # Load stored PIR filenames from StorageBackend
    try:
        cfg = load_config()
        storage = create_storage_backend(cfg)
        stored_pir_files = storage.list_files("pir")
        stored_pir_files = [f for f in stored_pir_files if f.endswith(".json")]
    except Exception:
        stored_pir_files = []

    session = load_session(beacon_session) if beacon_session else None
    pirs = session["pirs"] if session else []
    collection_plan = session.get("collection_plan", "") if session else ""

    csrf_token = _generate_csrf_token()
    response = templates.TemplateResponse(
        request=request,
        name="pir.html",
        context={
            "active_tab": "pir",
            "csrf_token": csrf_token,
            "stored_pir_files": stored_pir_files,
            "pirs": pirs,
            "collection_plan": collection_plan,
        },
    )
    _set_csrf_cookie(response, csrf_token)
    return response


@app.post("/pir/generate")
async def pir_generate(
    request: Request,
    context_file: UploadFile = File(...),
    model_simple: str = Form(default=""),
    model_medium: str = Form(default=""),
    model_complex: str = Form(default=""),
    csrf_token: str = Form(default=""),
    beacon_csrf: str = Cookie(default=""),
):
    """Run PIR pipeline on uploaded business context file, store results in session."""
    _verify_csrf(beacon_csrf, csrf_token)

    cfg = _build_config(model_simple, model_medium, model_complex)

    content = await _read_upload(context_file)
    suffix = Path(context_file.filename or "ctx.json").suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        pirs, collection_plan_md = _run_pipeline(tmp_path, config=cfg)
    finally:
        tmp_path.unlink(missing_ok=True)

    # Persist PIR to StorageBackend (matches assets/identity/user_accounts pattern)
    from beacon.storage import create_storage_backend  # noqa: PLC0415

    try:
        storage = create_storage_backend(cfg)
        ts = _dt.datetime.now().strftime("%Y%m%d%H%M")
        storage.save(
            "pir",
            f"pir_output_{ts}.json",
            json.dumps(wrap_envelope(pirs), ensure_ascii=False, indent=2),
        )
        if collection_plan_md:
            storage.save("pir", f"collection_plan_{ts}.md", collection_plan_md)
    except Exception as exc:  # noqa: BLE001
        logger.warning("pir_save_storage_failed", error=str(exc))

    session_data = {
        "pirs": pirs,
        "collection_plan": collection_plan_md,
    }
    session_id = create_session(session_data)

    new_csrf = _generate_csrf_token()
    response = RedirectResponse(url="/pir", status_code=303)
    response.set_cookie(
        "beacon_session", session_id, httponly=True, secure=True, samesite="lax", max_age=86400
    )
    _set_csrf_cookie(response, new_csrf)
    return response


@app.post("/pir/load")
async def pir_load(
    request: Request,
    pir_file: UploadFile = File(...),
    collection_plan_file: UploadFile | None = File(default=None),
    csrf_token: str = Form(default=""),
    beacon_csrf: str = Cookie(default=""),
):
    """Load an existing pir_output.json into a session for review."""
    _verify_csrf(beacon_csrf, csrf_token)

    content = await _read_upload(pir_file)
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc

    if isinstance(data, dict):
        # Accept both {"pirs": [...]} and bare list
        pirs = data.get("pirs", [data]) if "pirs" in data else [data]
    elif isinstance(data, list):
        pirs = data
    else:
        raise HTTPException(
            status_code=400, detail="pir_output.json must be a JSON array or object"
        )

    collection_plan_md = ""
    if collection_plan_file is not None and collection_plan_file.filename:
        try:
            cp_content = await _read_upload(collection_plan_file)
            collection_plan_md = cp_content.decode("utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.warning("collection_plan_upload_failed", error=str(exc))
            collection_plan_md = ""

    session_data = {"pirs": pirs, "collection_plan": collection_plan_md}
    session_id = create_session(session_data)

    new_csrf = _generate_csrf_token()
    response = RedirectResponse(url="/pir", status_code=303)
    response.set_cookie(
        "beacon_session", session_id, httponly=True, secure=True, samesite="lax", max_age=86400
    )
    _set_csrf_cookie(response, new_csrf)
    return response


@app.post("/pir/load-stored/{filename}")
async def pir_load_stored(
    request: Request,
    filename: str,
    csrf_token: str = Form(default=""),
    beacon_csrf: str = Cookie(default=""),
):
    """Load a stored PIR from StorageBackend into a session for review."""
    _verify_csrf(beacon_csrf, csrf_token)

    from beacon.config import load_config  # noqa: PLC0415
    from beacon.storage import create_storage_backend  # noqa: PLC0415

    try:
        cfg = load_config()
        storage = create_storage_backend(cfg)
        raw = storage.load("pir", filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Stored PIR not found: {filename}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON in stored PIR: {exc}") from exc

    if isinstance(data, dict):
        pirs = data.get("pirs", [data]) if "pirs" in data else [data]
    elif isinstance(data, list):
        pirs = data
    else:
        raise HTTPException(status_code=400, detail="Stored PIR must be a JSON array or object")

    # Pair-load matching collection_plan_<ts>.md from the same "pir" category.
    # Plan 1 saves both pir_output_<ts>.json and collection_plan_<ts>.md with
    # the same timestamp; load both so reload restores the full review view.
    collection_plan_md = ""
    ts_match = re.match(r"^pir_output_(\d+)\.json$", filename)
    if ts_match:
        ts = ts_match.group(1)
        try:
            collection_plan_md = storage.load("pir", f"collection_plan_{ts}.md")
        except FileNotFoundError:
            collection_plan_md = ""
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "collection_plan_pair_load_failed", error=str(exc), pir_filename=filename
            )
            collection_plan_md = ""

    session_data = {"pirs": pirs, "collection_plan": collection_plan_md}
    session_id = create_session(session_data)

    new_csrf = _generate_csrf_token()
    response = RedirectResponse(url="/pir", status_code=303)
    response.set_cookie(
        "beacon_session", session_id, httponly=True, secure=True, samesite="lax", max_age=86400
    )
    _set_csrf_cookie(response, new_csrf)
    return response


@app.post("/pir/save")
async def pir_save(
    request: Request,
    beacon_session: str = Cookie(default=""),
    beacon_csrf: str = Cookie(default=""),
    pir_index: int = Form(...),
    description: str = Form(default=""),
    rationale: str = Form(default=""),
    collection_focus: str = Form(default=""),
    csrf_token: str = Form(default=""),
    actor_index: str = Form(default=""),
    actor_excluded: str = Form(default=""),
    actor_exclusion_reason: str = Form(default=""),
    actor_manual_likelihood: str = Form(default=""),
    actor_rationale_append: str = Form(default=""),
):
    """Update editable fields for a PIR or a prioritized actor in the session."""
    _verify_csrf(beacon_csrf, csrf_token)

    if not beacon_session:
        raise HTTPException(status_code=400, detail="No session")
    session = load_session(beacon_session)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    pirs = session.get("pirs", [])
    if pir_index < 0 or pir_index >= len(pirs):
        raise HTTPException(status_code=400, detail="Invalid PIR index")

    if actor_index != "":
        # Actor-level edit
        try:
            actor_idx = int(actor_index)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid actor index")

        actors = pirs[pir_index].get("prioritized_actors", [])
        if actor_idx < 0 or actor_idx >= len(actors):
            raise HTTPException(status_code=400, detail="Invalid actor index")

        excluded = actor_excluded in ("1", "true", "on")
        reason = actor_exclusion_reason.strip() or None

        manual_likelihood = None
        if actor_manual_likelihood.strip():
            try:
                val = float(actor_manual_likelihood)
            except ValueError:
                raise HTTPException(
                    status_code=400, detail="actor_manual_likelihood must be a number"
                )
            if not (0.0 <= val <= 1.0):
                raise HTTPException(
                    status_code=400,
                    detail="actor_manual_likelihood must be between 0.0 and 1.0",
                )
            manual_likelihood = val

        rationale_app = actor_rationale_append.strip() or None

        updated = dict(actors[actor_idx])
        updated["excluded_by_analyst"] = excluded
        updated["exclusion_reason"] = reason
        updated["manual_likelihood_override"] = manual_likelihood
        updated["analyst_rationale_append"] = rationale_app

        from pydantic import ValidationError  # noqa: PLC0415

        from beacon.analysis.actor_triage import PrioritizedActor  # noqa: PLC0415

        try:
            PrioritizedActor.model_validate(updated)
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        actors[actor_idx] = updated
        pirs[pir_index]["prioritized_actors"] = actors
    else:
        # PIR-level edit (existing behavior, unchanged)
        pirs[pir_index]["description"] = description
        pirs[pir_index]["rationale"] = rationale
        # collection_focus is stored as a list; split on newlines
        pirs[pir_index]["collection_focus"] = [
            line.strip() for line in collection_focus.splitlines() if line.strip()
        ]

    session["pirs"] = pirs
    save_session(beacon_session, session)

    return RedirectResponse(url="/pir", status_code=303)


@app.post("/pir/approve")
async def pir_approve(
    request: Request,
    beacon_session: str = Cookie(default=""),
    beacon_csrf: str = Cookie(default=""),
    csrf_token: str = Form(default=""),
):
    """Create GHE Issues for all PIRs in the current session."""
    _verify_csrf(beacon_csrf, csrf_token)

    if not beacon_session:
        raise HTTPException(status_code=400, detail="No session")
    session = load_session(beacon_session)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    from beacon.config import load_config  # noqa: PLC0415
    from beacon.review.github import GHEClient, submit_pirs_for_review  # noqa: PLC0415

    cfg = load_config()
    try:
        client = GHEClient(token=cfg.ghe_token, repo=cfg.ghe_repo, api_base=cfg.ghe_api_base)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    pirs = session.get("pirs", [])
    collection_plan_text = session.get("collection_plan", "") or None
    results = submit_pirs_for_review(pirs, client, collection_plan_text)

    created = [
        {"pir_id": r.pir_id, "issue_number": r.issue_number, "url": r.html_url} for r in results
    ]
    return JSONResponse({"created": created})


@app.get("/pir/export")
async def pir_export(beacon_session: str = Cookie(default="")):
    """Download pir_output.json from the current session."""
    if not beacon_session:
        raise HTTPException(status_code=400, detail="No session")
    session = load_session(beacon_session)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    pirs = session.get("pirs", [])
    content = json.dumps(wrap_envelope(pirs), ensure_ascii=False, indent=2).encode("utf-8")
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=pir_output.json"},
    )


@app.get("/pir/{pir_id}")
async def pir_single(request: Request, pir_id: str):
    """Render the prioritized_actors review view for a single PIR.

    Loads ``<output_dir>/pir_output.json`` from the launcher-scoped
    directory, locates the PIR with the matching ``pir_id``, seeds a
    review session containing only that PIR, and renders the PIR template.
    """
    output_dir = _resolve_output_dir()
    pir_path = output_dir / "pir_output.json"
    if not pir_path.exists():
        raise HTTPException(status_code=404, detail=f"pir_output.json not found in {output_dir}")
    try:
        data = json.loads(pir_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid PIR JSON: {exc}") from exc

    if isinstance(data, dict) and "pirs" in data:
        all_pirs = data["pirs"]
    elif isinstance(data, list):
        all_pirs = data
    elif isinstance(data, dict):
        all_pirs = [data]
    else:
        raise HTTPException(status_code=400, detail="pir_output.json must be an object or list")

    matching = [p for p in all_pirs if p.get("pir_id") == pir_id]
    if not matching:
        raise HTTPException(status_code=404, detail=f"PIR not found: {pir_id}")

    session_id = create_session({"pirs": matching, "collection_plan": ""})
    csrf_token = _generate_csrf_token()

    from beacon.config import load_config  # noqa: PLC0415
    from beacon.storage import create_storage_backend  # noqa: PLC0415

    try:
        cfg = load_config()
        storage = create_storage_backend(cfg)
        stored_pir_files = storage.list_files("pir")
        stored_pir_files = [f for f in stored_pir_files if f.endswith(".json")]
    except Exception:
        stored_pir_files = []

    response = templates.TemplateResponse(
        request=request,
        name="pir.html",
        context={
            "active_tab": "pir",
            "pirs": matching,
            "collection_plan": "",
            "csrf_token": csrf_token,
            "stored_pir_files": stored_pir_files,
        },
    )
    response.set_cookie(
        "beacon_session", session_id, httponly=True, secure=True, samesite="lax", max_age=86400
    )
    _set_csrf_cookie(response, csrf_token)
    return response


# ---------------------------------------------------------------------------
# Assets tab routes
# ---------------------------------------------------------------------------

# CVE identifier validation pattern (mirrors TRACE _CVE_ID_PATTERN; MUST stay in sync).
# "MUST match TRACE _CVE_ID_PATTERN" (Rule 26: no shared importable package).
_CVE_ID_PATTERN = re.compile(r"^CVE-\d{4}-\d{4,}$")


def _validate_cve_id(cve_id: str) -> bool:
    """Return True if *cve_id* matches the canonical CVE format."""
    return bool(_CVE_ID_PATTERN.match(cve_id))


@app.get("/assets")
async def assets_page(request: Request, beacon_session: str = Cookie(default="")):
    """Assets tab: list stored drafts + edit org-known fields when a doc is loaded."""
    from beacon.config import load_config  # noqa: PLC0415
    from beacon.storage import create_storage_backend  # noqa: PLC0415

    # Collect stored assets_*.json drafts from StorageBackend
    try:
        cfg = load_config()
        storage = create_storage_backend(cfg)
        all_assets_files = storage.list_files("assets")
        stored_assets_files = [f for f in all_assets_files if f.startswith("assets_")]
    except Exception:  # noqa: BLE001
        stored_assets_files = []

    # Load the currently-active assets doc from session (if any)
    session = load_session(beacon_session) if beacon_session else None
    assets_doc = session.get("assets_doc") if session else None

    csrf_token = _generate_csrf_token()
    response = templates.TemplateResponse(
        request=request,
        name="assets.html",
        context={
            "active_tab": "assets",
            "csrf_token": csrf_token,
            "stored_assets_files": stored_assets_files,
            "assets_doc": assets_doc,
            "saved_filename": None,
        },
    )
    _set_csrf_cookie(response, csrf_token)
    return response


@app.post("/assets/load-stored/{filename}")
async def assets_load_stored(
    request: Request,
    filename: str,
    csrf_token: str = Form(default=""),
    beacon_csrf: str = Cookie(default=""),
    beacon_session: str = Cookie(default=""),
):
    """Load a stored assets_*.json draft from StorageBackend into session."""
    _verify_csrf(beacon_csrf, csrf_token)

    from beacon.config import load_config  # noqa: PLC0415
    from beacon.storage import create_storage_backend  # noqa: PLC0415

    try:
        cfg = load_config()
        storage = create_storage_backend(cfg)
        raw = storage.load("assets", filename)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail=f"Stored assets draft not found: {filename}"
        ) from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400, detail=f"Invalid JSON in stored assets: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="assets.json must be a JSON object")

    # Merge into existing session (preserves PIR data) or create a new one
    session: dict = {}
    if beacon_session:
        existing = load_session(beacon_session)
        if existing:
            session = existing
    session["assets_doc"] = data

    if beacon_session and load_session(beacon_session) is not None:
        save_session(beacon_session, session)
        session_id = beacon_session
    else:
        session_id = create_session(session)

    new_csrf = _generate_csrf_token()
    response = RedirectResponse(url="/assets", status_code=303)
    response.set_cookie(
        "beacon_session", session_id, httponly=True, secure=True, samesite="lax", max_age=86400
    )
    _set_csrf_cookie(response, new_csrf)
    return response


@app.post("/assets/save")
async def assets_save(
    request: Request,
    beacon_session: str = Cookie(default=""),
    beacon_csrf: str = Cookie(default=""),
    csrf_token: str = Form(default=""),
    asset_count: int = Form(default=0),
    security_controls_json: str = Form(default=""),
    asset_vulnerabilities_json: str = Form(default=""),
):
    """Persist edited assets fields (owner, security_control_ids, security_controls,
    asset_vulnerabilities) back into the session doc and write a new timestamped
    assets_<ts>.json to StorageBackend.
    """
    _verify_csrf(beacon_csrf, csrf_token)

    if not beacon_session:
        raise HTTPException(status_code=400, detail="No session")
    session = load_session(beacon_session)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    assets_doc = session.get("assets_doc")
    if assets_doc is None:
        raise HTTPException(status_code=400, detail="No assets doc loaded in session")

    # --- Parse form data for per-asset edits ---
    # FastAPI provides raw form data via request.form()
    form_data = await request.form()

    assets_list: list[dict] = assets_doc.get("assets", [])
    for idx in range(asset_count):
        asset_id_key = f"asset_id_{idx}"
        owner_key = f"asset_owner_{idx}"
        sc_ids_key = f"asset_sc_ids_{idx}"

        asset_id = form_data.get(asset_id_key, "")
        if not asset_id:
            continue

        # Find the matching asset in the list
        for asset in assets_list:
            if asset.get("id") == asset_id:
                asset["owner"] = str(form_data.get(owner_key, "") or "").strip()
                raw_sc = str(form_data.get(sc_ids_key, "") or "").strip()
                asset["security_control_ids"] = (
                    [s.strip() for s in raw_sc.split(",") if s.strip()] if raw_sc else []
                )
                break

    assets_doc["assets"] = assets_list

    # --- Parse security_controls JSON (optional) ---
    sc_raw = security_controls_json.strip()
    if sc_raw:
        try:
            sc_parsed = json.loads(sc_raw)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=400, detail=f"Invalid JSON in security_controls: {exc}"
            ) from exc
        if not isinstance(sc_parsed, list):
            raise HTTPException(status_code=400, detail="security_controls must be a JSON array")
        assets_doc["security_controls"] = sc_parsed

    # --- Parse asset_vulnerabilities JSON (optional) ---
    vuln_raw = asset_vulnerabilities_json.strip()
    if vuln_raw:
        try:
            vuln_parsed = json.loads(vuln_raw)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=400, detail=f"Invalid JSON in asset_vulnerabilities: {exc}"
            ) from exc
        if not isinstance(vuln_parsed, list):
            raise HTTPException(
                status_code=400, detail="asset_vulnerabilities must be a JSON array"
            )
        # Validate every CVE id
        for entry in vuln_parsed:
            if not isinstance(entry, dict):
                raise HTTPException(
                    status_code=400,
                    detail="Each asset_vulnerabilities entry must be a JSON object",
                )
            cve_id = entry.get("vuln_stix_id_ref", "")
            if not _validate_cve_id(cve_id):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Invalid CVE ID '{cve_id}'. "
                        "Must match CVE-<year>-<4+ digits>, e.g. CVE-2024-12345."
                    ),
                )
        assets_doc["asset_vulnerabilities"] = vuln_parsed

    session["assets_doc"] = assets_doc
    save_session(beacon_session, session)

    # --- Write to StorageBackend ---
    from beacon.config import load_config  # noqa: PLC0415
    from beacon.storage import create_storage_backend  # noqa: PLC0415

    ts = _dt.datetime.now().strftime("%Y%m%d%H%M")
    saved_filename = f"assets_{ts}.json"
    try:
        cfg = load_config()
        storage = create_storage_backend(cfg)
        storage.save(
            "assets",
            saved_filename,
            json.dumps(assets_doc, ensure_ascii=False, indent=2),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("assets_save_storage_failed", error=str(exc))
        saved_filename = None

    new_csrf = _generate_csrf_token()
    # Rebuild the stored assets files list for re-rendering
    try:
        cfg = load_config()  # type: ignore[assignment]
        storage = create_storage_backend(cfg)
        all_assets_files = storage.list_files("assets")
        stored_assets_files = [f for f in all_assets_files if f.startswith("assets_")]
    except Exception:  # noqa: BLE001
        stored_assets_files = []

    response = templates.TemplateResponse(
        request=request,
        name="assets.html",
        context={
            "active_tab": "assets",
            "csrf_token": new_csrf,
            "stored_assets_files": stored_assets_files,
            "assets_doc": assets_doc,
            "saved_filename": saved_filename,
        },
    )
    _set_csrf_cookie(response, new_csrf)
    return response


# ---------------------------------------------------------------------------
# Identity tab routes
# ---------------------------------------------------------------------------


@app.get("/identity")
async def identity_page(request: Request, beacon_session: str = Cookie(default="")):
    """Identity tab: list stored drafts + edit org-known fields when a doc is loaded."""
    from beacon.config import load_config  # noqa: PLC0415
    from beacon.storage import create_storage_backend  # noqa: PLC0415

    try:
        cfg = load_config()
        storage = create_storage_backend(cfg)
        all_files = storage.list_files("assets")
        stored_identity_files = [f for f in all_files if f.startswith("identity_assets_")]
    except Exception:  # noqa: BLE001
        stored_identity_files = []

    session = load_session(beacon_session) if beacon_session else None
    identity_doc = session.get("identity_doc") if session else None

    csrf_token = _generate_csrf_token()
    response = templates.TemplateResponse(
        request=request,
        name="identity.html",
        context={
            "active_tab": "identity",
            "csrf_token": csrf_token,
            "stored_identity_files": stored_identity_files,
            "identity_doc": identity_doc,
            "saved_filename": None,
        },
    )
    _set_csrf_cookie(response, csrf_token)
    return response


@app.post("/identity/load-stored/{filename}")
async def identity_load_stored(
    request: Request,
    filename: str,
    csrf_token: str = Form(default=""),
    beacon_csrf: str = Cookie(default=""),
    beacon_session: str = Cookie(default=""),
):
    """Load a stored identity_assets_*.json draft from StorageBackend into session."""
    _verify_csrf(beacon_csrf, csrf_token)

    from beacon.config import load_config  # noqa: PLC0415
    from beacon.storage import create_storage_backend  # noqa: PLC0415

    try:
        cfg = load_config()
        storage = create_storage_backend(cfg)
        raw = storage.load("assets", filename)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail=f"Stored identity draft not found: {filename}"
        ) from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400, detail=f"Invalid JSON in stored identity: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="identity_assets.json must be a JSON object")

    session: dict = {}
    if beacon_session:
        existing = load_session(beacon_session)
        if existing:
            session = existing
    session["identity_doc"] = data

    if beacon_session and load_session(beacon_session) is not None:
        save_session(beacon_session, session)
        session_id = beacon_session
    else:
        session_id = create_session(session)

    new_csrf = _generate_csrf_token()
    response = RedirectResponse(url="/identity", status_code=303)
    response.set_cookie(
        "beacon_session", session_id, httponly=True, secure=True, samesite="lax", max_age=86400
    )
    _set_csrf_cookie(response, new_csrf)
    return response


@app.post("/identity/save")
async def identity_save(
    request: Request,
    beacon_session: str = Cookie(default=""),
    beacon_csrf: str = Cookie(default=""),
    csrf_token: str = Form(default=""),
    identity_count: int = Form(default=0),
    has_access_json: str = Form(default=""),
):
    """Persist edited identity fields back into the session doc and write a new
    timestamped identity_assets_<ts>.json to StorageBackend.
    """
    _verify_csrf(beacon_csrf, csrf_token)

    if not beacon_session:
        raise HTTPException(status_code=400, detail="No session")
    session = load_session(beacon_session)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    identity_doc = session.get("identity_doc")
    if identity_doc is None:
        raise HTTPException(status_code=400, detail="No identity doc loaded in session")

    form_data = await request.form()

    identities_list: list[dict] = identity_doc.get("identities", [])
    for idx in range(identity_count):
        identity_id_key = f"identity_id_{idx}"
        identity_id = form_data.get(identity_id_key, "")
        if not identity_id:
            continue

        for identity in identities_list:
            if identity.get("id") == identity_id:
                identity["description"] = str(
                    form_data.get(f"identity_description_{idx}", "") or ""
                ).strip()
                raw_roles = str(form_data.get(f"identity_roles_{idx}", "") or "").strip()
                identity["roles"] = (
                    [r.strip() for r in raw_roles.split(",") if r.strip()] if raw_roles else []
                )
                hvit_val = form_data.get(f"identity_hvit_{idx}", "")
                identity["is_high_value_impersonation_target"] = hvit_val in ("1", "true", "on")
                raw_rf = str(form_data.get(f"identity_risk_factors_{idx}", "") or "").strip()
                identity["impersonation_risk_factors"] = (
                    [r.strip() for r in raw_rf.split(",") if r.strip()] if raw_rf else []
                )
                break

    identity_doc["identities"] = identities_list

    # --- Parse has_access JSON (optional) ---
    ha_raw = has_access_json.strip()
    if ha_raw:
        try:
            ha_parsed = json.loads(ha_raw)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=400, detail=f"Invalid JSON in has_access: {exc}"
            ) from exc
        if not isinstance(ha_parsed, list):
            raise HTTPException(status_code=400, detail="has_access must be a JSON array")
        identity_doc["has_access"] = ha_parsed

    session["identity_doc"] = identity_doc
    save_session(beacon_session, session)

    from beacon.config import load_config  # noqa: PLC0415
    from beacon.storage import create_storage_backend  # noqa: PLC0415

    ts = _dt.datetime.now().strftime("%Y%m%d%H%M")
    saved_filename = f"identity_assets_{ts}.json"
    try:
        cfg = load_config()
        storage = create_storage_backend(cfg)
        storage.save(
            "assets",
            saved_filename,
            json.dumps(identity_doc, ensure_ascii=False, indent=2),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("identity_save_storage_failed", error=str(exc))
        saved_filename = None

    new_csrf = _generate_csrf_token()
    try:
        cfg = load_config()  # type: ignore[assignment]
        storage = create_storage_backend(cfg)
        all_files = storage.list_files("assets")
        stored_identity_files = [f for f in all_files if f.startswith("identity_assets_")]
    except Exception:  # noqa: BLE001
        stored_identity_files = []

    response = templates.TemplateResponse(
        request=request,
        name="identity.html",
        context={
            "active_tab": "identity",
            "csrf_token": new_csrf,
            "stored_identity_files": stored_identity_files,
            "identity_doc": identity_doc,
            "saved_filename": saved_filename,
        },
    )
    _set_csrf_cookie(response, new_csrf)
    return response


# ---------------------------------------------------------------------------
# Accounts tab routes
# ---------------------------------------------------------------------------


@app.get("/accounts")
async def accounts_page(request: Request, beacon_session: str = Cookie(default="")):
    """Accounts tab: list stored drafts + edit org-known fields when a doc is loaded."""
    from beacon.config import load_config  # noqa: PLC0415
    from beacon.storage import create_storage_backend  # noqa: PLC0415

    try:
        cfg = load_config()
        storage = create_storage_backend(cfg)
        all_files = storage.list_files("assets")
        stored_accounts_files = [f for f in all_files if f.startswith("user_accounts_")]
    except Exception:  # noqa: BLE001
        stored_accounts_files = []

    session = load_session(beacon_session) if beacon_session else None
    accounts_doc = session.get("accounts_doc") if session else None

    csrf_token = _generate_csrf_token()
    response = templates.TemplateResponse(
        request=request,
        name="accounts.html",
        context={
            "active_tab": "accounts",
            "csrf_token": csrf_token,
            "stored_accounts_files": stored_accounts_files,
            "accounts_doc": accounts_doc,
            "saved_filename": None,
        },
    )
    _set_csrf_cookie(response, csrf_token)
    return response


@app.post("/accounts/load-stored/{filename}")
async def accounts_load_stored(
    request: Request,
    filename: str,
    csrf_token: str = Form(default=""),
    beacon_csrf: str = Cookie(default=""),
    beacon_session: str = Cookie(default=""),
):
    """Load a stored user_accounts_*.json draft from StorageBackend into session."""
    _verify_csrf(beacon_csrf, csrf_token)

    from beacon.config import load_config  # noqa: PLC0415
    from beacon.storage import create_storage_backend  # noqa: PLC0415

    try:
        cfg = load_config()
        storage = create_storage_backend(cfg)
        raw = storage.load("assets", filename)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail=f"Stored accounts draft not found: {filename}"
        ) from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400, detail=f"Invalid JSON in stored accounts: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="user_accounts.json must be a JSON object")

    session: dict = {}
    if beacon_session:
        existing = load_session(beacon_session)
        if existing:
            session = existing
    session["accounts_doc"] = data

    if beacon_session and load_session(beacon_session) is not None:
        save_session(beacon_session, session)
        session_id = beacon_session
    else:
        session_id = create_session(session)

    new_csrf = _generate_csrf_token()
    response = RedirectResponse(url="/accounts", status_code=303)
    response.set_cookie(
        "beacon_session", session_id, httponly=True, secure=True, samesite="lax", max_age=86400
    )
    _set_csrf_cookie(response, new_csrf)
    return response


@app.post("/accounts/save")
async def accounts_save(
    request: Request,
    beacon_session: str = Cookie(default=""),
    beacon_csrf: str = Cookie(default=""),
    csrf_token: str = Form(default=""),
    account_count: int = Form(default=0),
    account_on_asset_json: str = Form(default=""),
):
    """Persist edited accounts fields back into the session doc and write a new
    timestamped user_accounts_<ts>.json to StorageBackend.
    """
    _verify_csrf(beacon_csrf, csrf_token)

    if not beacon_session:
        raise HTTPException(status_code=400, detail="No session")
    session = load_session(beacon_session)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    accounts_doc = session.get("accounts_doc")
    if accounts_doc is None:
        raise HTTPException(status_code=400, detail="No accounts doc loaded in session")

    form_data = await request.form()

    accounts_list: list[dict] = accounts_doc.get("user_accounts", [])
    for idx in range(account_count):
        acct_id_key = f"acct_id_{idx}"
        acct_id = form_data.get(acct_id_key, "")
        if not acct_id:
            continue

        for acct in accounts_list:
            if acct.get("id") == acct_id:
                acct["display_name"] = str(
                    form_data.get(f"acct_display_name_{idx}", "") or ""
                ).strip()
                acct["account_type"] = str(form_data.get(f"acct_type_{idx}", "") or "").strip()
                priv_val = form_data.get(f"acct_privileged_{idx}", "")
                acct["is_privileged"] = priv_val in ("1", "true", "on")
                svc_val = form_data.get(f"acct_service_{idx}", "")
                acct["is_service_account"] = svc_val in ("1", "true", "on")
                acct["description"] = str(
                    form_data.get(f"acct_description_{idx}", "") or ""
                ).strip()
                break

    accounts_doc["user_accounts"] = accounts_list

    # --- Parse account_on_asset JSON (optional) ---
    aoa_raw = account_on_asset_json.strip()
    if aoa_raw:
        try:
            aoa_parsed = json.loads(aoa_raw)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=400, detail=f"Invalid JSON in account_on_asset: {exc}"
            ) from exc
        if not isinstance(aoa_parsed, list):
            raise HTTPException(status_code=400, detail="account_on_asset must be a JSON array")
        accounts_doc["account_on_asset"] = aoa_parsed

    session["accounts_doc"] = accounts_doc
    save_session(beacon_session, session)

    from beacon.config import load_config  # noqa: PLC0415
    from beacon.storage import create_storage_backend  # noqa: PLC0415

    ts = _dt.datetime.now().strftime("%Y%m%d%H%M")
    saved_filename = f"user_accounts_{ts}.json"
    try:
        cfg = load_config()
        storage = create_storage_backend(cfg)
        storage.save(
            "assets",
            saved_filename,
            json.dumps(accounts_doc, ensure_ascii=False, indent=2),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("accounts_save_storage_failed", error=str(exc))
        saved_filename = None

    new_csrf = _generate_csrf_token()
    try:
        cfg = load_config()  # type: ignore[assignment]
        storage = create_storage_backend(cfg)
        all_files = storage.list_files("assets")
        stored_accounts_files = [f for f in all_files if f.startswith("user_accounts_")]
    except Exception:  # noqa: BLE001
        stored_accounts_files = []

    response = templates.TemplateResponse(
        request=request,
        name="accounts.html",
        context={
            "active_tab": "accounts",
            "csrf_token": new_csrf,
            "stored_accounts_files": stored_accounts_files,
            "accounts_doc": accounts_doc,
            "saved_filename": saved_filename,
        },
    )
    _set_csrf_cookie(response, new_csrf)
    return response


# ---------------------------------------------------------------------------
# Backward-compatibility redirects
# ---------------------------------------------------------------------------


@app.get("/review")
async def review_redirect():
    """Redirect /review to /pir (backward compat, Initiative I Phase 2)."""
    return RedirectResponse(url="/pir", status_code=302)


@app.get("/generate")
async def generate_redirect():
    """Redirect /generate to /pir (backward compat, Initiative I Phase 2)."""
    return RedirectResponse(url="/pir", status_code=302)


# ---------------------------------------------------------------------------
# Artifact viewer routes (kept as-is for backward compatibility)
# ---------------------------------------------------------------------------


@app.post("/review/save")
async def review_save(
    request: Request,
    beacon_session: str = Cookie(default=""),
    beacon_csrf: str = Cookie(default=""),
    pir_index: int = Form(...),
    description: str = Form(default=""),
    rationale: str = Form(default=""),
    collection_focus: str = Form(default=""),
    csrf_token: str = Form(default=""),
    actor_index: str = Form(default=""),
    actor_excluded: str = Form(default=""),
    actor_exclusion_reason: str = Form(default=""),
    actor_manual_likelihood: str = Form(default=""),
    actor_rationale_append: str = Form(default=""),
):
    """Legacy route — delegates to pir_save with /pir redirect."""
    _verify_csrf(beacon_csrf, csrf_token)

    if not beacon_session:
        raise HTTPException(status_code=400, detail="No session")
    session = load_session(beacon_session)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    pirs = session.get("pirs", [])
    if pir_index < 0 or pir_index >= len(pirs):
        raise HTTPException(status_code=400, detail="Invalid PIR index")

    if actor_index != "":
        try:
            actor_idx = int(actor_index)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid actor index")

        actors = pirs[pir_index].get("prioritized_actors", [])
        if actor_idx < 0 or actor_idx >= len(actors):
            raise HTTPException(status_code=400, detail="Invalid actor index")

        excluded = actor_excluded in ("1", "true", "on")
        reason = actor_exclusion_reason.strip() or None

        manual_likelihood = None
        if actor_manual_likelihood.strip():
            try:
                val = float(actor_manual_likelihood)
            except ValueError:
                raise HTTPException(
                    status_code=400, detail="actor_manual_likelihood must be a number"
                )
            if not (0.0 <= val <= 1.0):
                raise HTTPException(
                    status_code=400,
                    detail="actor_manual_likelihood must be between 0.0 and 1.0",
                )
            manual_likelihood = val

        rationale_app = actor_rationale_append.strip() or None

        updated = dict(actors[actor_idx])
        updated["excluded_by_analyst"] = excluded
        updated["exclusion_reason"] = reason
        updated["manual_likelihood_override"] = manual_likelihood
        updated["analyst_rationale_append"] = rationale_app

        from pydantic import ValidationError  # noqa: PLC0415

        from beacon.analysis.actor_triage import PrioritizedActor  # noqa: PLC0415

        try:
            PrioritizedActor.model_validate(updated)
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        actors[actor_idx] = updated
        pirs[pir_index]["prioritized_actors"] = actors
    else:
        pirs[pir_index]["description"] = description
        pirs[pir_index]["rationale"] = rationale
        pirs[pir_index]["collection_focus"] = [
            line.strip() for line in collection_focus.splitlines() if line.strip()
        ]

    session["pirs"] = pirs
    save_session(beacon_session, session)

    return RedirectResponse(url="/pir", status_code=303)


@app.post("/review/approve")
async def review_approve(
    request: Request,
    beacon_session: str = Cookie(default=""),
    beacon_csrf: str = Cookie(default=""),
    csrf_token: str = Form(default=""),
):
    """Legacy route — delegates to pir_approve logic."""
    _verify_csrf(beacon_csrf, csrf_token)

    if not beacon_session:
        raise HTTPException(status_code=400, detail="No session")
    session = load_session(beacon_session)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    from beacon.config import load_config  # noqa: PLC0415
    from beacon.review.github import GHEClient, submit_pirs_for_review  # noqa: PLC0415

    cfg = load_config()
    try:
        client = GHEClient(token=cfg.ghe_token, repo=cfg.ghe_repo, api_base=cfg.ghe_api_base)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    pirs = session.get("pirs", [])
    collection_plan_text = session.get("collection_plan", "") or None
    results = submit_pirs_for_review(pirs, client, collection_plan_text)

    created = [
        {"pir_id": r.pir_id, "issue_number": r.issue_number, "url": r.html_url} for r in results
    ]
    return JSONResponse({"created": created})


@app.get("/review/pir/{pir_id}")
async def review_pir(request: Request, pir_id: str):
    """Legacy route — redirect to /pir/{pir_id}."""
    return RedirectResponse(url=f"/pir/{pir_id}", status_code=302)


@app.get("/review/export")
async def review_export(beacon_session: str = Cookie(default="")):
    """Download pir_output.json from the current session (legacy route kept)."""
    if not beacon_session:
        raise HTTPException(status_code=400, detail="No session")
    session = load_session(beacon_session)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    pirs = session.get("pirs", [])
    content = json.dumps(wrap_envelope(pirs), ensure_ascii=False, indent=2).encode("utf-8")
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=pir_output.json"},
    )


@app.get("/review/artifacts/{filename}")
async def review_artifact(request: Request, filename: str):
    """Read-only viewer for a generated artifact (Initiative H Phase 6).

    Only the six filenames whitelisted in ``_ARTIFACT_FILENAMES`` are
    served; anything else is a 404. JSON files are pretty-printed,
    Markdown is rendered in a ``<pre>`` block (no markdown→HTML
    conversion to keep the dep surface minimal), and YAML is returned
    verbatim.
    """
    if filename not in _ARTIFACT_FILENAMES:
        raise HTTPException(status_code=404, detail="Unknown artifact")
    output_dir = _resolve_output_dir()
    path = output_dir / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"Artifact not found: {filename}")

    raw_text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix == ".json":
        try:
            parsed = json.loads(raw_text)
            display_text = json.dumps(parsed, ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            display_text = raw_text
        viewer_kind = "json"
    elif suffix in (".md", ".markdown"):
        display_text = raw_text
        viewer_kind = "markdown"
    elif suffix in (".yaml", ".yml"):
        display_text = raw_text
        viewer_kind = "yaml"
    else:  # pragma: no cover - whitelisted to known suffixes
        display_text = raw_text
        viewer_kind = "text"

    return templates.TemplateResponse(
        request=request,
        name="artifact.html",
        context={
            "filename": filename,
            "display_text": display_text,
            "viewer_kind": viewer_kind,
            "size_bytes": path.stat().st_size,
        },
    )


@app.get("/review/artifacts/{filename}/raw")
async def review_artifact_raw(filename: str):
    """Serve an artifact verbatim (text/plain) for download or curl access."""
    if filename not in _ARTIFACT_FILENAMES:
        raise HTTPException(status_code=404, detail="Unknown artifact")
    output_dir = _resolve_output_dir()
    path = output_dir / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"Artifact not found: {filename}")
    return PlainTextResponse(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# REST API routes (kept for React SPA migration compatibility)
# ---------------------------------------------------------------------------


@app.get("/api/pir")
async def api_pir(beacon_session: str = Cookie(default="")):
    """Return PIR list as JSON."""
    if not beacon_session:
        return JSONResponse({"pirs": []})
    session = load_session(beacon_session)
    if session is None:
        return JSONResponse({"pirs": []})
    return JSONResponse({"pirs": session.get("pirs", [])})


@app.post("/api/generate")
async def api_generate(
    context_file: UploadFile = File(...),
    model_simple: str = Form(default=""),
    model_medium: str = Form(default=""),
    model_complex: str = Form(default=""),
):
    """REST endpoint: run pipeline and return PIR JSON directly."""
    cfg = _build_config(model_simple, model_medium, model_complex)

    content = await _read_upload(context_file)
    suffix = Path(context_file.filename or "ctx.json").suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        pirs, collection_plan_md = _run_pipeline(tmp_path, config=cfg)
    finally:
        tmp_path.unlink(missing_ok=True)

    # Persist PIR to StorageBackend (matches assets/identity/user_accounts pattern)
    from beacon.storage import create_storage_backend  # noqa: PLC0415

    try:
        storage = create_storage_backend(cfg)
        ts = _dt.datetime.now().strftime("%Y%m%d%H%M")
        storage.save(
            "pir",
            f"pir_output_{ts}.json",
            json.dumps(wrap_envelope(pirs), ensure_ascii=False, indent=2),
        )
        if collection_plan_md:
            storage.save("pir", f"collection_plan_{ts}.md", collection_plan_md)
    except Exception as exc:  # noqa: BLE001
        logger.warning("pir_save_storage_failed", error=str(exc))

    return JSONResponse({"pirs": pirs, "collection_plan": collection_plan_md})


# ---------------------------------------------------------------------------
# Internal pipeline runner
# ---------------------------------------------------------------------------


def _build_config(model_simple: str, model_medium: str, model_complex: str):
    """Build a Config with optional model overrides. Falls back to env-var defaults."""
    from beacon.config import load_config  # noqa: PLC0415

    cfg = load_config()
    if model_simple:
        cfg.llm_model_simple = model_simple
    if model_medium:
        cfg.llm_model_medium = model_medium
    if model_complex:
        cfg.llm_model_complex = model_complex
    return cfg


def _run_pipeline(context_path: Path, *, config=None) -> tuple[list[dict], str]:
    """Execute the BEACON pipeline and return (pirs_as_dicts, collection_plan_markdown).

    Side-effects: also builds and stores assets.json, identity_assets.json, and
    user_accounts.json drafts via StorageBackend.  The return tuple is unchanged
    for backward compatibility; the three artifact files are written as a
    side-effect so callers do not need updating.
    """
    from beacon.analysis.asset_mapper import load_asset_tags, map_asset_tags  # noqa: PLC0415
    from beacon.analysis.assets_generator import generate_assets_json  # noqa: PLC0415
    from beacon.analysis.element_extractor import extract  # noqa: PLC0415
    from beacon.analysis.identity_assets_generator import (  # noqa: PLC0415
        generate_identity_assets_json,
    )
    from beacon.analysis.risk_scorer import score  # noqa: PLC0415
    from beacon.analysis.threat_mapper import load_taxonomy, map_threats  # noqa: PLC0415
    from beacon.analysis.user_accounts_generator import (  # noqa: PLC0415
        generate_user_accounts_json,
    )
    from beacon.generator.pir_builder import build_pirs  # noqa: PLC0415
    from beacon.generator.report_builder import build_collection_plan  # noqa: PLC0415
    from beacon.ingest.context_parser import parse  # noqa: PLC0415

    ctx = parse(context_path, config=config)
    taxonomy = load_taxonomy(None)
    asset_tags_dict = load_asset_tags(None)

    elements = extract(ctx)
    asset_tag_list = map_asset_tags(elements, asset_tags_dict)
    threat = map_threats(elements, taxonomy)
    risk = score(elements, threat, use_llm=True, config=config)

    # Generate the assets draft up front so the per-asset tag union can constrain
    # asset_weight_rules (SAGE matches those rules against per-asset tags, never
    # the org-level union). Reused for the companion-artifact write below.
    _assets_data = generate_assets_json(ctx)
    available_asset_tags = {
        tag for asset in _assets_data.get("assets", []) for tag in asset.get("tags", [])
    }

    pirs = build_pirs(
        elements,
        threat,
        risk,
        asset_tag_list,
        asset_tags_dict,
        use_llm=True,
        config=config,
        available_asset_tags=available_asset_tags,
    )

    plan = build_collection_plan(elements, threat, risk, pirs)
    # Render to markdown string (reuse write helper by capturing output)
    from beacon.generator.report_builder import write_collection_plan  # noqa: PLC0415

    # write_collection_plan expects a Path; write to tmp and read back
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w", encoding="utf-8") as f:
        tmp_md = Path(f.name)
    write_collection_plan(plan, tmp_md)
    collection_plan_md = tmp_md.read_text(encoding="utf-8")
    tmp_md.unlink(missing_ok=True)

    # --- Companion artifacts: assets / identity / accounts ---
    from beacon.config import load_config  # noqa: PLC0415
    from beacon.storage import create_storage_backend  # noqa: PLC0415

    try:
        _cfg = config if config is not None else load_config()
        _storage = create_storage_backend(_cfg)
        _ts = _dt.datetime.now().strftime("%Y%m%d%H%M")

        # _assets_data was already generated above (used for available_asset_tags).
        _storage.save(
            "assets",
            f"assets_{_ts}.json",
            json.dumps(_assets_data, indent=2, ensure_ascii=False),
        )

        _identity_data = generate_identity_assets_json(ctx)
        _storage.save(
            "assets",
            f"identity_assets_{_ts}.json",
            json.dumps(_identity_data, indent=2, ensure_ascii=False),
        )

        _accounts_data = generate_user_accounts_json(ctx)
        _storage.save(
            "assets",
            f"user_accounts_{_ts}.json",
            json.dumps(_accounts_data, indent=2, ensure_ascii=False),
        )
    except Exception as _exc:
        logger.warning("companion_artifacts_failed", error=str(_exc))

    return [p.model_dump() for p in pirs], collection_plan_md
