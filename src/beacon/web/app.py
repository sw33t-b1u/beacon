"""FastAPI web application for BEACON PIR generation and review."""

from __future__ import annotations

import datetime as _dt
import json
import os
import secrets
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import Cookie, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from beacon.web.session import cleanup_old_sessions, create_session, load_session, save_session

logger = structlog.get_logger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

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
    """Dashboard placeholder — full implementation in Phase 5."""
    return templates.TemplateResponse(
        request=request,
        name="base.html",
        context={
            "active_tab": "dashboard",
            "content_override": "Dashboard — coming in Phase 5",
        },
    )


@app.get("/collection")
async def collection(request: Request):
    """Collection tab placeholder — full implementation in Phase 4."""
    return templates.TemplateResponse(
        request=request,
        name="base.html",
        context={
            "active_tab": "collection",
            "content_override": "Collection — coming in Phase 4",
        },
    )


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
async def settings(request: Request):
    """Settings tab placeholder — full implementation in Phase 6."""
    return templates.TemplateResponse(
        request=request,
        name="base.html",
        context={
            "active_tab": "settings",
            "content_override": "Settings — coming in Phase 6",
        },
    )


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

    session_data = {"pirs": pirs, "collection_plan": ""}
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

    session_data = {"pirs": pirs, "collection_plan": ""}
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
        return JSONResponse({"error": "No session"}, status_code=400)
    session = load_session(beacon_session)
    if session is None:
        return JSONResponse({"error": "Session not found or expired"}, status_code=404)

    pirs = session.get("pirs", [])
    if pir_index < 0 or pir_index >= len(pirs):
        return JSONResponse({"error": "Invalid PIR index"}, status_code=400)

    if actor_index != "":
        # Actor-level edit
        try:
            actor_idx = int(actor_index)
        except ValueError:
            return JSONResponse({"error": "Invalid actor index"}, status_code=400)

        actors = pirs[pir_index].get("prioritized_actors", [])
        if actor_idx < 0 or actor_idx >= len(actors):
            return JSONResponse({"error": "Invalid actor index"}, status_code=400)

        excluded = actor_excluded in ("1", "true", "on")
        reason = actor_exclusion_reason.strip() or None

        manual_likelihood = None
        if actor_manual_likelihood.strip():
            try:
                val = float(actor_manual_likelihood)
            except ValueError:
                return JSONResponse(
                    {"error": "actor_manual_likelihood must be a number"}, status_code=400
                )
            if not (0.0 <= val <= 1.0):
                return JSONResponse(
                    {"error": "actor_manual_likelihood must be between 0.0 and 1.0"},
                    status_code=400,
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
            return JSONResponse({"error": str(exc)}, status_code=400)

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
        return JSONResponse({"error": "No session"}, status_code=400)
    session = load_session(beacon_session)
    if session is None:
        return JSONResponse({"error": "Session not found or expired"}, status_code=404)

    from beacon.config import load_config  # noqa: PLC0415
    from beacon.review.github import GHEClient, submit_pirs_for_review  # noqa: PLC0415

    cfg = load_config()
    try:
        client = GHEClient(token=cfg.ghe_token, repo=cfg.ghe_repo, api_base=cfg.ghe_api_base)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

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
        return JSONResponse({"error": "No session"}, status_code=400)
    session = load_session(beacon_session)
    if session is None:
        return JSONResponse({"error": "Session not found or expired"}, status_code=404)

    pirs = session.get("pirs", [])
    content = json.dumps(pirs, ensure_ascii=False, indent=2).encode("utf-8")
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
        return JSONResponse({"error": "No session"}, status_code=400)
    session = load_session(beacon_session)
    if session is None:
        return JSONResponse({"error": "Session not found or expired"}, status_code=404)

    pirs = session.get("pirs", [])
    if pir_index < 0 or pir_index >= len(pirs):
        return JSONResponse({"error": "Invalid PIR index"}, status_code=400)

    if actor_index != "":
        try:
            actor_idx = int(actor_index)
        except ValueError:
            return JSONResponse({"error": "Invalid actor index"}, status_code=400)

        actors = pirs[pir_index].get("prioritized_actors", [])
        if actor_idx < 0 or actor_idx >= len(actors):
            return JSONResponse({"error": "Invalid actor index"}, status_code=400)

        excluded = actor_excluded in ("1", "true", "on")
        reason = actor_exclusion_reason.strip() or None

        manual_likelihood = None
        if actor_manual_likelihood.strip():
            try:
                val = float(actor_manual_likelihood)
            except ValueError:
                return JSONResponse(
                    {"error": "actor_manual_likelihood must be a number"}, status_code=400
                )
            if not (0.0 <= val <= 1.0):
                return JSONResponse(
                    {"error": "actor_manual_likelihood must be between 0.0 and 1.0"},
                    status_code=400,
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
            return JSONResponse({"error": str(exc)}, status_code=400)

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
        return JSONResponse({"error": "No session"}, status_code=400)
    session = load_session(beacon_session)
    if session is None:
        return JSONResponse({"error": "Session not found or expired"}, status_code=404)

    from beacon.config import load_config  # noqa: PLC0415
    from beacon.review.github import GHEClient, submit_pirs_for_review  # noqa: PLC0415

    cfg = load_config()
    try:
        client = GHEClient(token=cfg.ghe_token, repo=cfg.ghe_repo, api_base=cfg.ghe_api_base)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)

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
        return JSONResponse({"error": "No session"}, status_code=400)
    session = load_session(beacon_session)
    if session is None:
        return JSONResponse({"error": "Session not found or expired"}, status_code=404)

    pirs = session.get("pirs", [])
    content = json.dumps(pirs, ensure_ascii=False, indent=2).encode("utf-8")
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
    """Execute the BEACON pipeline and return (pirs_as_dicts, collection_plan_markdown)."""
    from beacon.analysis.asset_mapper import load_asset_tags, map_asset_tags  # noqa: PLC0415
    from beacon.analysis.element_extractor import extract  # noqa: PLC0415
    from beacon.analysis.risk_scorer import score  # noqa: PLC0415
    from beacon.analysis.threat_mapper import load_taxonomy, map_threats  # noqa: PLC0415
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
    pirs = build_pirs(
        elements, threat, risk, asset_tag_list, asset_tags_dict, use_llm=True, config=config
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

    return [p.model_dump() for p in pirs], collection_plan_md
