"""FastAPI web application for BEACON PIR generation and review."""

from __future__ import annotations

import json
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import Cookie, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from beacon.web.session import cleanup_old_sessions, create_session, load_session, save_session

logger = structlog.get_logger(__name__)

_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


@asynccontextmanager
async def _lifespan(app: FastAPI):
    cleanup_old_sessions()
    yield


app = FastAPI(title="BEACON PIR Generator", lifespan=_lifespan)


# ---------------------------------------------------------------------------
# HTML routes (Jinja2)
# ---------------------------------------------------------------------------


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.post("/generate")
async def generate(
    request: Request,
    context_file: UploadFile = File(...),
    no_llm: str = Form(default="true"),
    model_simple: str = Form(default=""),
    model_medium: str = Form(default=""),
    model_complex: str = Form(default=""),
):
    """Run PIR pipeline on uploaded business context file, store results in session."""
    no_llm_bool = no_llm.lower() not in {"false", "0", "no"}
    cfg = _build_config(model_simple, model_medium, model_complex)

    suffix = Path(context_file.filename or "ctx.json").suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await context_file.read())
        tmp_path = Path(tmp.name)

    try:
        pirs, collection_plan_md = _run_pipeline(tmp_path, no_llm=no_llm_bool, config=cfg)
    finally:
        tmp_path.unlink(missing_ok=True)

    session_data = {
        "pirs": pirs,
        "collection_plan": collection_plan_md,
    }
    session_id = create_session(session_data)

    response = RedirectResponse(url="/review", status_code=303)
    response.set_cookie("beacon_session", session_id, httponly=True, max_age=86400)
    return response


@app.post("/load")
async def load_pir(
    request: Request,
    pir_file: UploadFile = File(...),
):
    """Load an existing pir_output.json into a session for review."""
    raw = await pir_file.read()
    try:
        data = json.loads(raw)
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

    response = RedirectResponse(url="/review", status_code=303)
    response.set_cookie("beacon_session", session_id, httponly=True, max_age=86400)
    return response


@app.get("/review")
async def review(request: Request, beacon_session: str = Cookie(default="")):
    session = load_session(beacon_session) if beacon_session else None
    pirs = session["pirs"] if session else []
    collection_plan = session.get("collection_plan", "") if session else ""
    return templates.TemplateResponse(
        request=request,
        name="review.html",
        context={"pirs": pirs, "collection_plan": collection_plan},
    )


@app.post("/review/save")
async def review_save(
    request: Request,
    beacon_session: str = Cookie(default=""),
    pir_index: int = Form(...),
    description: str = Form(default=""),
    rationale: str = Form(default=""),
    collection_focus: str = Form(default=""),
):
    """Update editable fields for a PIR in the session."""
    if not beacon_session:
        return JSONResponse({"error": "No session"}, status_code=400)
    session = load_session(beacon_session)
    if session is None:
        return JSONResponse({"error": "Session not found or expired"}, status_code=404)

    pirs = session.get("pirs", [])
    if pir_index < 0 or pir_index >= len(pirs):
        return JSONResponse({"error": "Invalid PIR index"}, status_code=400)

    pirs[pir_index]["description"] = description
    pirs[pir_index]["rationale"] = rationale
    # collection_focus is stored as a list; split on newlines
    pirs[pir_index]["collection_focus"] = [
        line.strip() for line in collection_focus.splitlines() if line.strip()
    ]
    session["pirs"] = pirs
    save_session(beacon_session, session)

    return RedirectResponse(url="/review", status_code=303)


@app.post("/review/approve")
async def review_approve(
    request: Request,
    beacon_session: str = Cookie(default=""),
):
    """Create GHE Issues for all PIRs in the current session."""
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


@app.get("/review/export")
async def review_export(beacon_session: str = Cookie(default="")):
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
    no_llm: str = Form(default="true"),
    model_simple: str = Form(default=""),
    model_medium: str = Form(default=""),
    model_complex: str = Form(default=""),
):
    """REST endpoint: run pipeline and return PIR JSON directly."""
    no_llm_bool = no_llm.lower() not in {"false", "0", "no"}
    cfg = _build_config(model_simple, model_medium, model_complex)

    suffix = Path(context_file.filename or "ctx.json").suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await context_file.read())
        tmp_path = Path(tmp.name)

    try:
        pirs, collection_plan_md = _run_pipeline(tmp_path, no_llm=no_llm_bool, config=cfg)
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


def _run_pipeline(context_path: Path, *, no_llm: bool, config=None) -> tuple[list[dict], str]:
    """Execute the BEACON pipeline and return (pirs_as_dicts, collection_plan_markdown)."""
    from beacon.analysis.asset_mapper import load_asset_tags, map_asset_tags  # noqa: PLC0415
    from beacon.analysis.element_extractor import extract  # noqa: PLC0415
    from beacon.analysis.risk_scorer import score  # noqa: PLC0415
    from beacon.analysis.threat_mapper import load_taxonomy, map_threats  # noqa: PLC0415
    from beacon.generator.pir_builder import build_pirs  # noqa: PLC0415
    from beacon.generator.report_builder import build_collection_plan  # noqa: PLC0415
    from beacon.ingest.context_parser import parse  # noqa: PLC0415

    use_llm = not no_llm

    ctx = parse(context_path, no_llm=no_llm, config=config)
    taxonomy = load_taxonomy(None)
    asset_tags_dict = load_asset_tags(None)

    elements = extract(ctx)
    asset_tag_list = map_asset_tags(elements, asset_tags_dict)
    threat = map_threats(elements, taxonomy, use_llm=use_llm, config=config)
    risk = score(elements, threat, use_llm=use_llm, config=config)
    pirs = build_pirs(
        elements, threat, risk, asset_tag_list, asset_tags_dict, use_llm=use_llm, config=config
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
