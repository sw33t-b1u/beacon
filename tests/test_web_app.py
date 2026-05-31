"""Tests for src/beacon/web/app.py using FastAPI TestClient."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from beacon.web.app import app

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_PIR = {
    "pir_id": "PIR-2026-001",
    "intelligence_level": "operational",
    "valid_from": "2026-04-04",
    "valid_until": "2026-07-04",
    "description": "Test description",
    "rationale": "Test rationale",
    "threat_actor_tags": ["apt-china"],
    "asset_weight_rules": [{"tag": "plm", "criticality_multiplier": 2.5}],
    "collection_focus": ["Track IOCs"],
    "risk_score": {"likelihood": 3, "impact": 4, "composite": 12},
}

SAMPLE_CONTEXT_PATH = FIXTURES / "sample_context_manufacturing.json"


def _make_actor(i: int) -> dict:
    """Return a minimal PrioritizedActor-compatible dict with index-based likelihood."""
    return {
        "actor_id": f"actor-{i}",
        "name": f"Actor {i}",
        "aliases": [f"alias-{i}"],
        "likelihood": max(0.0, round(1.0 - i * 0.08, 2)),
        "score_breakdown": {
            "intent": {"score": 0.8, "motivation_alignment": 0.8, "industry_match": 1.0},
            "capability": {
                "score": 0.5,
                "sophistication_score": 0.5,
                "ttp_count_norm": 0.4,
                "recency_active_campaigns": 0.5,
                "tool_usage": 0.3,
                "targeting_persistence": 0.2,
                "evasion_capability": 0.4,
                "depth": 0.39,
                "breadth": 0.31,
            },
            "opportunity": {
                "score": 0.7,
                "victimology_match": 0.7,
                "geographic_match": 0.8,
                "surface_ttp_coverage": 0.5,
            },
            "data_quality": {"degraded": False, "missing_sources": []},
        },
        "rationale": {
            "text": f"Rationale for Actor {i}",
            "intent_factors": {},
            "capability_factors": {},
            "opportunity_factors": {},
        },
        "excluded_by_analyst": False,
        "exclusion_reason": None,
        "manual_likelihood_override": None,
        "analyst_rationale_append": None,
    }


def _create_session_with_actors_csrf(n_actors: int = 8) -> tuple[str, dict[str, str]]:
    """Create a session with a PIR having n_actors prioritized_actors; return (sid, cookies)."""
    from beacon.web.session import create_session  # noqa: PLC0415

    actors = [_make_actor(i) for i in range(n_actors)]
    pir = {**SAMPLE_PIR, "prioritized_actors": actors}
    session_id = create_session({"pirs": [pir], "collection_plan": ""})
    csrf_token, _ = _get_csrf()
    return session_id, {"beacon_session": session_id, "beacon_csrf": csrf_token}


def _make_pipeline_mock(pirs=None, plan="## Collection Plan\n- item1"):
    """Return a mock for _run_pipeline that returns sample data."""
    if pirs is None:
        pirs = [SAMPLE_PIR]
    return MagicMock(return_value=(pirs, plan))


client = TestClient(app, raise_server_exceptions=True)


def _get_csrf(test_client: TestClient | None = None) -> tuple[str, dict[str, str]]:
    """GET /pir to obtain a CSRF cookie and return (csrf_token, cookies_dict).

    The CSRF token is embedded in the cookie; we also extract it from the
    pir page response (the GET /pir handler sets the cookie value which is
    the same token passed to the template).
    """
    c = test_client or client
    resp = c.get("/pir")
    csrf_cookie = resp.cookies.get("beacon_csrf", "")
    return csrf_cookie, {"beacon_csrf": csrf_cookie}


class TestDashboardRoute:
    def test_dashboard_returns_200(self):
        resp = client.get("/dashboard")
        assert resp.status_code == 200

    def test_dashboard_shows_pir_count(self):
        mock_storage = MagicMock()
        mock_storage.list_files.side_effect = lambda cat: (
            ["pir_output_202605251700.json", "pir_output_202605261200.json"]
            if cat == "pir"
            else ["stix_bundle_001.json"]
        )
        with patch("beacon.storage.create_storage_backend", return_value=mock_storage):
            resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert b"2" in resp.content  # pir_count == 2

    def test_dashboard_without_sage(self):
        """Dashboard renders correctly even when SAGE is unavailable."""
        with patch("beacon.storage.create_storage_backend", side_effect=Exception("no storage")):
            resp = client.get("/dashboard")
        assert resp.status_code == 200
        # Shows "—" for SAGE stats since SAGE_API_URL is not set in tests and
        # actor/ttp/cve counts have no SAGE API endpoint
        assert (
            "—".encode() in resp.content
            or b"SAGE offline" in resp.content
            or b"Dashboard" in resp.content
        )


class TestRootRedirect:
    def test_get_redirects_to_dashboard(self):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/dashboard"

    def test_get_follows_redirect_to_dashboard(self):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Dashboard" in resp.content


class TestPirRoute:
    def test_get_returns_200(self):
        resp = client.get("/pir")
        assert resp.status_code == 200

    def test_get_sets_csrf_cookie(self):
        resp = client.get("/pir")
        assert "beacon_csrf" in resp.cookies

    def test_get_contains_generate_form(self):
        resp = client.get("/pir")
        assert b"context_file" in resp.content or b"Generate" in resp.content

    def test_get_contains_load_form(self):
        resp = client.get("/pir")
        assert b"pir_file" in resp.content or "読み込んで".encode() in resp.content

    def test_get_shows_stored_pirs_section(self):
        resp = client.get("/pir")
        assert b"Stored PIR" in resp.content


class TestReviewRedirect:
    def test_review_redirects_to_pir(self):
        resp = client.get("/review", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/pir"

    def test_generate_get_redirects_to_pir(self):
        resp = client.get("/generate", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/pir"


class TestGenerateRoute:
    def test_post_redirects_to_pir(self):
        csrf_token, cookies = _get_csrf()
        context_bytes = SAMPLE_CONTEXT_PATH.read_bytes()

        session_client = TestClient(app, cookies=cookies)
        with patch("beacon.web.app._run_pipeline", _make_pipeline_mock()):
            resp = session_client.post(
                "/pir/generate",
                files={"context_file": ("sample.json", context_bytes, "application/json")},
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )

        assert resp.status_code == 303
        assert resp.headers["location"] == "/pir"

    def test_post_sets_session_cookie(self):
        csrf_token, cookies = _get_csrf()
        context_bytes = SAMPLE_CONTEXT_PATH.read_bytes()

        session_client = TestClient(app, cookies=cookies)
        with patch("beacon.web.app._run_pipeline", _make_pipeline_mock()):
            resp = session_client.post(
                "/pir/generate",
                files={"context_file": ("sample.json", context_bytes, "application/json")},
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )

        assert "beacon_session" in resp.cookies

    def test_post_without_csrf_returns_403(self):
        context_bytes = SAMPLE_CONTEXT_PATH.read_bytes()
        fresh = TestClient(app, cookies={})
        with patch("beacon.web.app._run_pipeline", _make_pipeline_mock()):
            resp = fresh.post(
                "/pir/generate",
                files={"context_file": ("sample.json", context_bytes, "application/json")},
                data={},
                follow_redirects=False,
            )
        assert resp.status_code == 403

    def test_post_with_wrong_csrf_returns_403(self):
        _, cookies = _get_csrf()
        context_bytes = SAMPLE_CONTEXT_PATH.read_bytes()

        session_client = TestClient(app, cookies=cookies)
        with patch("beacon.web.app._run_pipeline", _make_pipeline_mock()):
            resp = session_client.post(
                "/pir/generate",
                files={"context_file": ("sample.json", context_bytes, "application/json")},
                data={"csrf_token": "wrong-token"},
                follow_redirects=False,
            )
        assert resp.status_code == 403


def _create_session_with_csrf() -> tuple[str, dict[str, str]]:
    """Helper: POST /pir/generate and return (session_id, merged_cookies)."""
    csrf_token, cookies = _get_csrf()
    context_bytes = SAMPLE_CONTEXT_PATH.read_bytes()
    session_client = TestClient(app, cookies=cookies)
    with patch("beacon.web.app._run_pipeline", _make_pipeline_mock()):
        resp = session_client.post(
            "/pir/generate",
            files={"context_file": ("sample.json", context_bytes, "application/json")},
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
    sid = resp.cookies.get("beacon_session", "")
    new_csrf = resp.cookies.get("beacon_csrf", "")
    return sid, {"beacon_session": sid, "beacon_csrf": new_csrf}


class TestPirPageWithSession:
    def test_pir_without_session_shows_no_review(self):
        fresh = TestClient(app, cookies={})
        resp = fresh.get("/pir")
        assert resp.status_code == 200
        # Review section only appears when PIRs are loaded — no PIR-2026-001
        assert b"PIR-2026-001" not in resp.content

    def test_pir_with_session_shows_pir(self):
        _, cookies = _create_session_with_csrf()
        session_client = TestClient(app, cookies=cookies)
        resp = session_client.get("/pir")
        assert resp.status_code == 200
        assert b"PIR-2026-001" in resp.content


class TestReviewRoute:
    def test_review_without_session_shows_no_pirs(self):
        fresh = TestClient(app, cookies={})
        resp = fresh.get("/review")
        # /review redirects to /pir
        assert resp.status_code == 200
        assert b"PIR-2026-001" not in resp.content

    def test_review_with_session_shows_pir(self):
        _, cookies = _create_session_with_csrf()
        session_client = TestClient(app, cookies=cookies)
        # /review redirects to /pir; follow redirect to check content
        resp = session_client.get("/review")
        assert resp.status_code == 200
        assert b"PIR-2026-001" in resp.content


class TestReviewSaveRoute:
    def test_save_updates_description(self):
        _, cookies = _create_session_with_csrf()
        # GET /pir to get a fresh CSRF token for the save form
        session_client = TestClient(app, cookies=cookies)
        review_resp = session_client.get("/pir")
        csrf_token = review_resp.cookies.get("beacon_csrf", cookies.get("beacon_csrf", ""))
        cookies["beacon_csrf"] = csrf_token
        session_client = TestClient(app, cookies=cookies)

        resp = session_client.post(
            "/pir/save",
            data={
                "pir_index": "0",
                "description": "Updated description",
                "rationale": "Updated rationale",
                "collection_focus": "Track IOC A\nTrack IOC B",
                "csrf_token": csrf_token,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303

        # Verify via /api/pir
        api_resp = session_client.get("/api/pir")
        pirs = api_resp.json()["pirs"]
        assert pirs[0]["description"] == "Updated description"

    def test_save_persists_collection_focus_as_list(self):
        _, cookies = _create_session_with_csrf()
        session_client = TestClient(app, cookies=cookies)
        review_resp = session_client.get("/pir")
        csrf_token = review_resp.cookies.get("beacon_csrf", cookies.get("beacon_csrf", ""))
        cookies["beacon_csrf"] = csrf_token
        session_client = TestClient(app, cookies=cookies)

        session_client.post(
            "/pir/save",
            data={
                "pir_index": "0",
                "description": "desc",
                "rationale": "rat",
                "collection_focus": "Item A\nItem B\n\nItem C",
                "csrf_token": csrf_token,
            },
            follow_redirects=False,
        )
        api_resp = session_client.get("/api/pir")
        focus = api_resp.json()["pirs"][0]["collection_focus"]
        assert "Item A" in focus
        assert "Item B" in focus
        assert "Item C" in focus
        assert "" not in focus


class TestExportRoute:
    def test_export_returns_valid_json(self):
        _, cookies = _create_session_with_csrf()
        session_client = TestClient(app, cookies=cookies)
        resp = session_client.get("/review/export")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/json")
        data = resp.json()
        assert isinstance(data, list)
        assert data[0]["pir_id"] == "PIR-2026-001"

    def test_export_without_session_returns_error(self):
        fresh = TestClient(app, cookies={})
        resp = fresh.get("/review/export")
        assert resp.status_code in (400, 404)

    def test_pir_export_returns_valid_json(self):
        _, cookies = _create_session_with_csrf()
        session_client = TestClient(app, cookies=cookies)
        resp = session_client.get("/pir/export")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/json")
        data = resp.json()
        assert isinstance(data, list)
        assert data[0]["pir_id"] == "PIR-2026-001"


class TestSessionSecurity:
    def test_path_traversal_session_id_rejected(self):
        """Malicious session_id with path traversal must not read arbitrary files."""
        malicious = TestClient(app, cookies={"beacon_session": "../../etc/passwd"})
        resp = malicious.get("/api/pir")
        assert resp.json() == {"pirs": []}

    def test_non_hex_session_id_rejected(self):
        malicious = TestClient(app, cookies={"beacon_session": "zzzz-not-valid"})
        resp = malicious.get("/review/export")
        assert resp.status_code in (400, 404)

    def test_save_with_invalid_session_id_is_noop(self):
        csrf_token, cookies = _get_csrf()
        cookies["beacon_session"] = "../../../tmp/evil"
        malicious = TestClient(app, cookies=cookies)
        resp = malicious.post(
            "/pir/save",
            data={
                "pir_index": "0",
                "description": "x",
                "rationale": "x",
                "collection_focus": "x",
                "csrf_token": csrf_token,
            },
            follow_redirects=False,
        )
        assert resp.status_code in (400, 404)


class TestUploadSizeLimit:
    def test_oversized_upload_returns_413(self):
        csrf_token, cookies = _get_csrf()
        # Create a file larger than 10 MB
        huge = b"x" * (11 * 1024 * 1024)
        session_client = TestClient(app, cookies=cookies)
        with patch("beacon.web.app._run_pipeline", _make_pipeline_mock()):
            resp = session_client.post(
                "/pir/generate",
                files={"context_file": ("huge.json", huge, "application/json")},
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )
        assert resp.status_code == 413


class TestAPIPirRoute:
    def test_api_pir_returns_empty_without_session(self):
        fresh = TestClient(app, cookies={})
        resp = fresh.get("/api/pir")
        assert resp.status_code == 200
        assert resp.json() == {"pirs": []}

    def test_api_pir_returns_pirs_with_session(self):
        _, cookies = _create_session_with_csrf()
        session_client = TestClient(app, cookies=cookies)
        resp = session_client.get("/api/pir")
        assert resp.status_code == 200
        assert len(resp.json()["pirs"]) > 0


# ---------------------------------------------------------------------------
# Helpers shared by actor-related test classes
# ---------------------------------------------------------------------------


def _actor_session_client(n_actors: int = 8) -> tuple[TestClient, dict[str, str], str]:
    """Return (client, cookies, csrf_token) for a session with n_actors.

    Calls GET /pir to obtain the fresh CSRF token the save form expects.
    """
    _, cookies = _create_session_with_actors_csrf(n_actors)
    pre_client = TestClient(app, cookies=cookies)
    pir_resp = pre_client.get("/pir")
    csrf = pir_resp.cookies.get("beacon_csrf", cookies.get("beacon_csrf", ""))
    cookies = {**cookies, "beacon_csrf": csrf}
    return TestClient(app, cookies=cookies), cookies, csrf


class TestPrioritizedActorView:
    def test_review_shows_top_5_prioritized_actors(self):
        _, cookies = _create_session_with_actors_csrf(n_actors=8)
        session_client = TestClient(app, cookies=cookies)
        resp = session_client.get("/pir")
        assert resp.status_code == 200
        # All 8 actors must be rendered in the HTML
        for i in range(8):
            assert f"Actor {i}".encode() in resp.content
        # Actors beyond index 4 are in a hidden wrapper
        assert b'class="actor-extra-0"' in resp.content
        # "Show all N actors" toggle button appears
        assert b"Show all 8 actors" in resp.content


class TestReviewSaveActorRoute:
    def test_review_save_actor_exclude(self):
        sc, cookies, csrf = _actor_session_client(n_actors=3)
        resp = sc.post(
            "/pir/save",
            data={
                "pir_index": "0",
                "actor_index": "0",
                "actor_excluded": "1",
                "actor_exclusion_reason": "False positive — no finance targeting observed",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303
        actors = sc.get("/api/pir").json()["pirs"][0]["prioritized_actors"]
        assert actors[0]["excluded_by_analyst"] is True
        assert actors[0]["exclusion_reason"] == "False positive — no finance targeting observed"

    def test_review_save_actor_exclude_requires_reason(self):
        sc, cookies, csrf = _actor_session_client(n_actors=1)
        resp = sc.post(
            "/pir/save",
            data={
                "pir_index": "0",
                "actor_index": "0",
                "actor_excluded": "1",
                # actor_exclusion_reason intentionally omitted
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 400

    def test_review_save_actor_likelihood_override(self):
        sc, cookies, csrf = _actor_session_client(n_actors=1)
        resp = sc.post(
            "/pir/save",
            data={
                "pir_index": "0",
                "actor_index": "0",
                "actor_manual_likelihood": "0.75",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303
        actors = sc.get("/api/pir").json()["pirs"][0]["prioritized_actors"]
        assert abs(actors[0]["manual_likelihood_override"] - 0.75) < 1e-9

    def test_review_save_actor_likelihood_override_out_of_range(self):
        sc, cookies, csrf = _actor_session_client(n_actors=1)
        resp = sc.post(
            "/pir/save",
            data={
                "pir_index": "0",
                "actor_index": "0",
                "actor_manual_likelihood": "1.5",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 400

    def test_review_save_actor_rationale_append(self):
        sc, cookies, csrf = _actor_session_client(n_actors=1)
        resp = sc.post(
            "/pir/save",
            data={
                "pir_index": "0",
                "actor_index": "0",
                "actor_rationale_append": "Additional analyst context here.",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303
        actors = sc.get("/api/pir").json()["pirs"][0]["prioritized_actors"]
        assert actors[0]["analyst_rationale_append"] == "Additional analyst context here."

    def test_review_export_reflects_actor_edits(self):
        sc, cookies, csrf = _actor_session_client(n_actors=2)
        sc.post(
            "/pir/save",
            data={
                "pir_index": "0",
                "actor_index": "1",
                "actor_excluded": "1",
                "actor_exclusion_reason": "Out of geographic scope",
                "actor_rationale_append": "Confirmed by IR team 2026-05-23",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        export_resp = sc.get("/review/export")
        assert export_resp.status_code == 200
        data = export_resp.json()
        assert isinstance(data, list)
        actor = data[0]["prioritized_actors"][1]
        assert actor["excluded_by_analyst"] is True
        assert actor["exclusion_reason"] == "Out of geographic scope"
        assert actor["analyst_rationale_append"] == "Confirmed by IR team 2026-05-23"

    def test_review_save_existing_pir_fields_still_work(self):
        sc, cookies, csrf = _actor_session_client(n_actors=2)
        resp = sc.post(
            "/pir/save",
            data={
                "pir_index": "0",
                "description": "Updated via regression test",
                "rationale": "Regression rationale",
                "collection_focus": "Track IOC X\nTrack IOC Y",
                "csrf_token": csrf,
                # actor_index absent → PIR-level edit
            },
            follow_redirects=False,
        )
        assert resp.status_code == 303
        pirs = sc.get("/api/pir").json()["pirs"]
        assert pirs[0]["description"] == "Updated via regression test"
        assert "Track IOC X" in pirs[0]["collection_focus"]

    def test_review_save_csrf_still_enforced(self):
        _, cookies = _create_session_with_actors_csrf(n_actors=1)
        # Deliberately mismatched CSRF cookie vs form token
        bad_cookies = {**cookies, "beacon_csrf": "legitimate-looking-cookie-token"}
        sc = TestClient(app, cookies=bad_cookies)
        resp = sc.post(
            "/pir/save",
            data={
                "pir_index": "0",
                "actor_index": "0",
                "actor_excluded": "1",
                "actor_exclusion_reason": "Test",
                "csrf_token": "different-form-token",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Companion artifact side-effects from _run_pipeline (Phase 2)
# ---------------------------------------------------------------------------


class TestRunPipelineCompanionArtifacts:
    """_run_pipeline stores assets/identity/accounts via StorageBackend as a side-effect."""

    def _call_generate(self, csrf_token: str, cookies: dict) -> None:
        """POST to /pir/generate with a real _run_pipeline mock that also invokes
        the companion-artifact logic (i.e. we do NOT mock _run_pipeline — we
        mock the StorageBackend and LLM call only)."""
        context_bytes = SAMPLE_CONTEXT_PATH.read_bytes()
        session_client = TestClient(app, cookies=cookies)
        return session_client.post(
            "/pir/generate",
            files={"context_file": ("sample.json", context_bytes, "application/json")},
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )

    def test_generate_stores_three_companion_artifacts(self, monkeypatch):
        monkeypatch.delenv("SAGE_API_URL", raising=False)
        csrf_token, cookies = _get_csrf()

        mock_storage = MagicMock()
        mock_storage.save = MagicMock()

        with (
            patch("beacon.llm.client.call_llm_json", return_value={}),
            patch("beacon.storage.create_storage_backend", return_value=mock_storage),
        ):
            resp = self._call_generate(csrf_token, cookies)

        # Must redirect (generate succeeded)
        assert resp.status_code == 303

        asset_filenames = [
            args[1] for args, _ in mock_storage.save.call_args_list if args[0] == "assets"
        ]
        has_assets = any(f.startswith("assets_") for f in asset_filenames)
        has_identity = any(f.startswith("identity_assets_") for f in asset_filenames)
        has_accounts = any(f.startswith("user_accounts_") for f in asset_filenames)
        assert has_assets and has_identity and has_accounts

    def test_companion_artifact_content_is_valid_json(self, monkeypatch):
        monkeypatch.delenv("SAGE_API_URL", raising=False)
        csrf_token, cookies = _get_csrf()

        mock_storage = MagicMock()
        mock_storage.save = MagicMock()

        with (
            patch("beacon.llm.client.call_llm_json", return_value={}),
            patch("beacon.storage.create_storage_backend", return_value=mock_storage),
        ):
            self._call_generate(csrf_token, cookies)

        import json as _json

        for args, _ in mock_storage.save.call_args_list:
            category, filename, content = args
            if category == "assets":
                parsed = _json.loads(content)
                assert isinstance(parsed, dict)

    def test_generate_still_returns_pirs_in_session(self, monkeypatch):
        """Companion artifact storage must not break PIR session creation."""
        monkeypatch.delenv("SAGE_API_URL", raising=False)
        csrf_token, cookies = _get_csrf()

        mock_storage = MagicMock()
        mock_storage.save = MagicMock()

        with (
            patch("beacon.llm.client.call_llm_json", return_value={}),
            patch("beacon.storage.create_storage_backend", return_value=mock_storage),
        ):
            resp = self._call_generate(csrf_token, cookies)

        assert resp.status_code == 303
        assert "beacon_session" in resp.cookies


# ---------------------------------------------------------------------------
# Assets tab tests
# ---------------------------------------------------------------------------

SAMPLE_ASSETS_DOC = {
    "_comment": "Test assets doc",
    "network_segments": [],
    "security_controls": [],
    "assets": [
        {
            "id": "asset-web-01",
            "name": "Web Server",
            "asset_type": "server",
            "environment": "onprem",
            "criticality": 8.0,
            "owner": "",
            "network_segment_id": "seg-0001-inet0-0000-000000000001",
            "exposed_to_internet": True,
            "tags": ["dmz"],
            "security_control_ids": [],
        },
        {
            "id": "asset-db-01",
            "name": "Database",
            "asset_type": "server",
            "environment": "onprem",
            "criticality": 10.0,
            "owner": "",
            "network_segment_id": "seg-0003-corp0-0000-000000000001",
            "exposed_to_internet": False,
            "tags": ["database"],
            "security_control_ids": [],
        },
    ],
    "asset_vulnerabilities": [],
    "asset_connections": [],
    "actor_targets": [],
}


def _create_assets_session(assets_doc: dict | None = None) -> tuple[str, dict[str, str]]:
    """Create a session containing an assets_doc; return (session_id, cookies_with_csrf)."""
    from beacon.web.session import create_session  # noqa: PLC0415

    doc = assets_doc if assets_doc is not None else SAMPLE_ASSETS_DOC
    session_id = create_session({"pirs": [], "collection_plan": "", "assets_doc": doc})
    csrf_token, _ = _get_csrf()
    return session_id, {"beacon_session": session_id, "beacon_csrf": csrf_token}


class TestAssetsRoute:
    """Tests for the Assets tab routes."""

    # ------------------------------------------------------------------
    # GET /assets
    # ------------------------------------------------------------------

    def test_get_returns_200(self):
        resp = client.get("/assets")
        assert resp.status_code == 200

    def test_get_shows_assets_section(self):
        resp = client.get("/assets")
        assert b"Assets" in resp.content

    def test_get_shows_nav_link(self):
        resp = client.get("/assets")
        # Nav must contain href="/assets"
        assert b'href="/assets"' in resp.content

    def test_get_sets_csrf_cookie(self):
        resp = client.get("/assets")
        assert "beacon_csrf" in resp.cookies

    def test_get_shows_stored_drafts_section(self):
        mock_storage = MagicMock()
        mock_storage.list_files.return_value = [
            "assets_202606010900.json",
            "assets_202606011000.json",
        ]
        with patch("beacon.storage.create_storage_backend", return_value=mock_storage):
            resp = client.get("/assets")
        assert resp.status_code == 200
        assert b"assets_202606010900.json" in resp.content

    def test_get_no_doc_loaded_shows_hint(self):
        fresh = TestClient(app, cookies={})
        resp = fresh.get("/assets")
        assert resp.status_code == 200
        # Without a loaded doc the template shows a hint to load a draft
        assert b"No assets draft loaded" in resp.content

    def test_get_with_loaded_doc_shows_assets_table(self):
        session_id, cookies = _create_assets_session()
        sc = TestClient(app, cookies=cookies)
        resp = sc.get("/assets")
        assert resp.status_code == 200
        assert b"asset-web-01" in resp.content
        assert b"asset-db-01" in resp.content

    # ------------------------------------------------------------------
    # POST /assets/load-stored/{filename}
    # ------------------------------------------------------------------

    def test_load_stored_loads_doc_into_session(self):
        csrf_token, cookies = _get_csrf()
        mock_storage = MagicMock()
        mock_storage.load.return_value = json.dumps(SAMPLE_ASSETS_DOC)
        sc = TestClient(app, cookies=cookies)
        with patch("beacon.storage.create_storage_backend", return_value=mock_storage):
            resp = sc.post(
                "/assets/load-stored/assets_202606011200.json",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/assets"
        # Session cookie must be set
        assert "beacon_session" in resp.cookies

    def test_load_stored_missing_file_returns_404(self):
        csrf_token, cookies = _get_csrf()
        mock_storage = MagicMock()
        mock_storage.load.side_effect = FileNotFoundError("not found")
        sc = TestClient(app, cookies=cookies)
        with patch("beacon.storage.create_storage_backend", return_value=mock_storage):
            resp = sc.post(
                "/assets/load-stored/assets_missing.json",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )
        assert resp.status_code == 404

    def test_load_stored_bad_json_returns_400(self):
        csrf_token, cookies = _get_csrf()
        mock_storage = MagicMock()
        mock_storage.load.return_value = "not json {"
        sc = TestClient(app, cookies=cookies)
        with patch("beacon.storage.create_storage_backend", return_value=mock_storage):
            resp = sc.post(
                "/assets/load-stored/assets_bad.json",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )
        assert resp.status_code == 400

    def test_load_stored_csrf_required(self):
        fresh = TestClient(app, cookies={})
        mock_storage = MagicMock()
        mock_storage.load.return_value = json.dumps(SAMPLE_ASSETS_DOC)
        with patch("beacon.storage.create_storage_backend", return_value=mock_storage):
            resp = fresh.post(
                "/assets/load-stored/assets_202606011200.json",
                data={},
                follow_redirects=False,
            )
        assert resp.status_code == 403

    # ------------------------------------------------------------------
    # POST /assets/save
    # ------------------------------------------------------------------

    def test_save_persists_owner(self):
        session_id, cookies = _create_assets_session()
        sc = TestClient(app, cookies=cookies)
        # Refresh CSRF from /assets
        assets_resp = sc.get("/assets")
        csrf = assets_resp.cookies.get("beacon_csrf", cookies["beacon_csrf"])
        cookies["beacon_csrf"] = csrf
        sc = TestClient(app, cookies=cookies)

        mock_storage = MagicMock()
        mock_storage.save = MagicMock()
        mock_storage.list_files.return_value = []
        with patch("beacon.storage.create_storage_backend", return_value=mock_storage):
            resp = sc.post(
                "/assets/save",
                data={
                    "csrf_token": csrf,
                    "asset_count": "2",
                    "asset_id_0": "asset-web-01",
                    "asset_owner_0": "webteam@example.com",
                    "asset_sc_ids_0": "",
                    "asset_id_1": "asset-db-01",
                    "asset_owner_1": "dbteam@example.com",
                    "asset_sc_ids_1": "ctrl-edr-001",
                    "security_controls_json": "",
                    "asset_vulnerabilities_json": "",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 200

        # Verify owner persisted in session
        from beacon.web.session import load_session  # noqa: PLC0415

        updated_session = load_session(session_id)
        assert updated_session is not None
        assets = updated_session["assets_doc"]["assets"]
        web_asset = next(a for a in assets if a["id"] == "asset-web-01")
        db_asset = next(a for a in assets if a["id"] == "asset-db-01")
        assert web_asset["owner"] == "webteam@example.com"
        assert db_asset["owner"] == "dbteam@example.com"
        assert "ctrl-edr-001" in db_asset["security_control_ids"]

    def test_save_persists_security_controls(self):
        session_id, cookies = _create_assets_session()
        sc = TestClient(app, cookies=cookies)
        assets_resp = sc.get("/assets")
        csrf = assets_resp.cookies.get("beacon_csrf", cookies["beacon_csrf"])
        cookies["beacon_csrf"] = csrf
        sc = TestClient(app, cookies=cookies)

        sc_json = json.dumps([{"id": "ctrl-edr-001", "name": "Falcon", "type": "edr"}])
        mock_storage = MagicMock()
        mock_storage.save = MagicMock()
        mock_storage.list_files.return_value = []
        with patch("beacon.storage.create_storage_backend", return_value=mock_storage):
            resp = sc.post(
                "/assets/save",
                data={
                    "csrf_token": csrf,
                    "asset_count": "0",
                    "security_controls_json": sc_json,
                    "asset_vulnerabilities_json": "",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 200

        from beacon.web.session import load_session  # noqa: PLC0415

        updated_session = load_session(session_id)
        assert updated_session is not None
        sc_list = updated_session["assets_doc"]["security_controls"]
        assert len(sc_list) == 1
        assert sc_list[0]["id"] == "ctrl-edr-001"

    def test_save_persists_asset_vulnerabilities(self):
        session_id, cookies = _create_assets_session()
        sc = TestClient(app, cookies=cookies)
        assets_resp = sc.get("/assets")
        csrf = assets_resp.cookies.get("beacon_csrf", cookies["beacon_csrf"])
        cookies["beacon_csrf"] = csrf
        sc = TestClient(app, cookies=cookies)

        vuln_json = json.dumps(
            [
                {
                    "vuln_stix_id_ref": "CVE-2024-12345",
                    "asset_id": "asset-web-01",
                    "remediation_status": "open",
                }
            ]
        )
        mock_storage = MagicMock()
        mock_storage.save = MagicMock()
        mock_storage.list_files.return_value = []
        with patch("beacon.storage.create_storage_backend", return_value=mock_storage):
            resp = sc.post(
                "/assets/save",
                data={
                    "csrf_token": csrf,
                    "asset_count": "0",
                    "security_controls_json": "",
                    "asset_vulnerabilities_json": vuln_json,
                },
                follow_redirects=False,
            )
        assert resp.status_code == 200

        from beacon.web.session import load_session  # noqa: PLC0415

        updated_session = load_session(session_id)
        assert updated_session is not None
        vulns = updated_session["assets_doc"]["asset_vulnerabilities"]
        assert len(vulns) == 1
        assert vulns[0]["vuln_stix_id_ref"] == "CVE-2024-12345"

    def test_save_malformed_cve_returns_400(self):
        session_id, cookies = _create_assets_session()
        sc = TestClient(app, cookies=cookies)
        assets_resp = sc.get("/assets")
        csrf = assets_resp.cookies.get("beacon_csrf", cookies["beacon_csrf"])
        cookies["beacon_csrf"] = csrf
        sc = TestClient(app, cookies=cookies)

        bad_vuln_json = json.dumps(
            [
                {
                    "vuln_stix_id_ref": "NOT-A-CVE",
                    "asset_id": "asset-web-01",
                    "remediation_status": "open",
                }
            ]
        )
        mock_storage = MagicMock()
        mock_storage.save = MagicMock()
        mock_storage.list_files.return_value = []
        with patch("beacon.storage.create_storage_backend", return_value=mock_storage):
            resp = sc.post(
                "/assets/save",
                data={
                    "csrf_token": csrf,
                    "asset_count": "0",
                    "security_controls_json": "",
                    "asset_vulnerabilities_json": bad_vuln_json,
                },
                follow_redirects=False,
            )
        assert resp.status_code == 400

    def test_save_malformed_cve_partial_format_returns_400(self):
        """CVE-2024-123 (only 3 digits) must be rejected."""
        session_id, cookies = _create_assets_session()
        sc = TestClient(app, cookies=cookies)
        assets_resp = sc.get("/assets")
        csrf = assets_resp.cookies.get("beacon_csrf", cookies["beacon_csrf"])
        cookies["beacon_csrf"] = csrf
        sc = TestClient(app, cookies=cookies)

        bad_vuln_json = json.dumps(
            [{"vuln_stix_id_ref": "CVE-2024-123", "asset_id": "asset-web-01"}]
        )
        mock_storage = MagicMock()
        mock_storage.save = MagicMock()
        mock_storage.list_files.return_value = []
        with patch("beacon.storage.create_storage_backend", return_value=mock_storage):
            resp = sc.post(
                "/assets/save",
                data={
                    "csrf_token": csrf,
                    "asset_count": "0",
                    "security_controls_json": "",
                    "asset_vulnerabilities_json": bad_vuln_json,
                },
                follow_redirects=False,
            )
        assert resp.status_code == 400

    def test_save_csrf_required(self):
        session_id, cookies = _create_assets_session()
        # Use mismatched CSRF
        bad_cookies = {**cookies, "beacon_csrf": "mismatch-token"}
        sc = TestClient(app, cookies=bad_cookies)
        resp = sc.post(
            "/assets/save",
            data={
                "csrf_token": "different-token",
                "asset_count": "0",
                "security_controls_json": "",
                "asset_vulnerabilities_json": "",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 403

    def test_save_writes_to_storage(self):
        session_id, cookies = _create_assets_session()
        sc = TestClient(app, cookies=cookies)
        assets_resp = sc.get("/assets")
        csrf = assets_resp.cookies.get("beacon_csrf", cookies["beacon_csrf"])
        cookies["beacon_csrf"] = csrf
        sc = TestClient(app, cookies=cookies)

        mock_storage = MagicMock()
        mock_storage.save = MagicMock()
        mock_storage.list_files.return_value = []
        with patch("beacon.storage.create_storage_backend", return_value=mock_storage):
            resp = sc.post(
                "/assets/save",
                data={
                    "csrf_token": csrf,
                    "asset_count": "0",
                    "security_controls_json": "",
                    "asset_vulnerabilities_json": "",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 200
        # Verify storage.save was called with category "assets" and a timestamped filename
        save_calls = mock_storage.save.call_args_list
        assert len(save_calls) >= 1
        category, filename, _ = save_calls[0][0]
        assert category == "assets"
        assert filename.startswith("assets_")
        assert filename.endswith(".json")

    def test_save_no_session_returns_400(self):
        csrf_token, cookies = _get_csrf()
        fresh = TestClient(app, cookies=cookies)
        resp = fresh.post(
            "/assets/save",
            data={
                "csrf_token": csrf_token,
                "asset_count": "0",
                "security_controls_json": "",
                "asset_vulnerabilities_json": "",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 400

    def test_save_session_without_assets_doc_returns_400(self):
        """Session that has PIRs but no assets_doc should return 400."""
        from beacon.web.session import create_session  # noqa: PLC0415

        session_id = create_session({"pirs": [], "collection_plan": ""})
        csrf_token, csrf_cookies = _get_csrf()
        cookies = {"beacon_session": session_id, "beacon_csrf": csrf_token}
        sc = TestClient(app, cookies=cookies)

        mock_storage = MagicMock()
        mock_storage.save = MagicMock()
        with patch("beacon.storage.create_storage_backend", return_value=mock_storage):
            resp = sc.post(
                "/assets/save",
                data={
                    "csrf_token": csrf_token,
                    "asset_count": "0",
                    "security_controls_json": "",
                    "asset_vulnerabilities_json": "",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Identity tab tests
# ---------------------------------------------------------------------------

SAMPLE_IDENTITY_DOC = {
    "identities": [
        {
            "id": "identity-001",
            "name": "Alice Smith",
            "identity_class": "individual",
            "sectors": ["technology"],
            "roles": [],
            "description": "",
            "is_high_value_impersonation_target": False,
            "impersonation_risk_factors": [],
        },
        {
            "id": "identity-002",
            "name": "Bob Jones",
            "identity_class": "individual",
            "sectors": [],
            "roles": ["admin"],
            "description": "IT administrator",
            "is_high_value_impersonation_target": False,
            "impersonation_risk_factors": [],
        },
    ],
    "has_access": [
        {
            "identity_id": "identity-001",
            "asset_id": "asset-web-01",
            "access_level": "read",
            "role": "analyst",
            "granted_at": "2026-01-01",
            "revoked_at": None,
        }
    ],
}


def _create_identity_session(
    identity_doc: dict | None = None,
) -> tuple[str, dict[str, str]]:
    """Create a session containing an identity_doc; return (session_id, cookies_with_csrf)."""
    from beacon.web.session import create_session  # noqa: PLC0415

    doc = identity_doc if identity_doc is not None else SAMPLE_IDENTITY_DOC
    session_id = create_session({"pirs": [], "collection_plan": "", "identity_doc": doc})
    csrf_token, _ = _get_csrf()
    return session_id, {"beacon_session": session_id, "beacon_csrf": csrf_token}


class TestIdentityRoute:
    """Tests for the Identity tab routes."""

    # ------------------------------------------------------------------
    # GET /identity
    # ------------------------------------------------------------------

    def test_get_returns_200(self):
        resp = client.get("/identity")
        assert resp.status_code == 200

    def test_get_shows_identity_section(self):
        resp = client.get("/identity")
        assert b"Identity" in resp.content

    def test_get_shows_nav_link(self):
        resp = client.get("/identity")
        assert b'href="/identity"' in resp.content

    def test_get_sets_csrf_cookie(self):
        resp = client.get("/identity")
        assert "beacon_csrf" in resp.cookies

    def test_get_shows_stored_drafts_section(self):
        mock_storage = MagicMock()
        mock_storage.list_files.return_value = [
            "identity_assets_202606010900.json",
            "identity_assets_202606011000.json",
        ]
        with patch("beacon.storage.create_storage_backend", return_value=mock_storage):
            resp = client.get("/identity")
        assert resp.status_code == 200
        assert b"identity_assets_202606010900.json" in resp.content

    def test_get_no_doc_loaded_shows_hint(self):
        fresh = TestClient(app, cookies={})
        resp = fresh.get("/identity")
        assert resp.status_code == 200
        assert b"No identity draft loaded" in resp.content

    def test_get_with_loaded_doc_shows_identities_table(self):
        session_id, cookies = _create_identity_session()
        sc = TestClient(app, cookies=cookies)
        resp = sc.get("/identity")
        assert resp.status_code == 200
        assert b"identity-001" in resp.content
        assert b"identity-002" in resp.content

    # ------------------------------------------------------------------
    # POST /identity/load-stored/{filename}
    # ------------------------------------------------------------------

    def test_load_stored_loads_doc_into_session(self):
        csrf_token, cookies = _get_csrf()
        mock_storage = MagicMock()
        mock_storage.load.return_value = json.dumps(SAMPLE_IDENTITY_DOC)
        sc = TestClient(app, cookies=cookies)
        with patch("beacon.storage.create_storage_backend", return_value=mock_storage):
            resp = sc.post(
                "/identity/load-stored/identity_assets_202606011200.json",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/identity"
        assert "beacon_session" in resp.cookies

    def test_load_stored_missing_file_returns_404(self):
        csrf_token, cookies = _get_csrf()
        mock_storage = MagicMock()
        mock_storage.load.side_effect = FileNotFoundError("not found")
        sc = TestClient(app, cookies=cookies)
        with patch("beacon.storage.create_storage_backend", return_value=mock_storage):
            resp = sc.post(
                "/identity/load-stored/identity_assets_missing.json",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )
        assert resp.status_code == 404

    def test_load_stored_bad_json_returns_400(self):
        csrf_token, cookies = _get_csrf()
        mock_storage = MagicMock()
        mock_storage.load.return_value = "not json {"
        sc = TestClient(app, cookies=cookies)
        with patch("beacon.storage.create_storage_backend", return_value=mock_storage):
            resp = sc.post(
                "/identity/load-stored/identity_assets_bad.json",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )
        assert resp.status_code == 400

    def test_load_stored_csrf_required(self):
        fresh = TestClient(app, cookies={})
        mock_storage = MagicMock()
        mock_storage.load.return_value = json.dumps(SAMPLE_IDENTITY_DOC)
        with patch("beacon.storage.create_storage_backend", return_value=mock_storage):
            resp = fresh.post(
                "/identity/load-stored/identity_assets_202606011200.json",
                data={},
                follow_redirects=False,
            )
        assert resp.status_code == 403

    # ------------------------------------------------------------------
    # POST /identity/save
    # ------------------------------------------------------------------

    def test_save_persists_description(self):
        session_id, cookies = _create_identity_session()
        sc = TestClient(app, cookies=cookies)
        identity_resp = sc.get("/identity")
        csrf = identity_resp.cookies.get("beacon_csrf", cookies["beacon_csrf"])
        cookies["beacon_csrf"] = csrf
        sc = TestClient(app, cookies=cookies)

        mock_storage = MagicMock()
        mock_storage.save = MagicMock()
        mock_storage.list_files.return_value = []
        with patch("beacon.storage.create_storage_backend", return_value=mock_storage):
            resp = sc.post(
                "/identity/save",
                data={
                    "csrf_token": csrf,
                    "identity_count": "2",
                    "identity_id_0": "identity-001",
                    "identity_description_0": "Updated description",
                    "identity_roles_0": "analyst",
                    "identity_hvit_0": "",
                    "identity_risk_factors_0": "",
                    "identity_id_1": "identity-002",
                    "identity_description_1": "",
                    "identity_roles_1": "admin",
                    "identity_hvit_1": "",
                    "identity_risk_factors_1": "",
                    "has_access_json": "",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 200

        from beacon.web.session import load_session  # noqa: PLC0415

        updated_session = load_session(session_id)
        assert updated_session is not None
        identities = updated_session["identity_doc"]["identities"]
        alice = next(i for i in identities if i["id"] == "identity-001")
        assert alice["description"] == "Updated description"
        assert "analyst" in alice["roles"]

    def test_save_persists_hvit_flag(self):
        session_id, cookies = _create_identity_session()
        sc = TestClient(app, cookies=cookies)
        identity_resp = sc.get("/identity")
        csrf = identity_resp.cookies.get("beacon_csrf", cookies["beacon_csrf"])
        cookies["beacon_csrf"] = csrf
        sc = TestClient(app, cookies=cookies)

        mock_storage = MagicMock()
        mock_storage.save = MagicMock()
        mock_storage.list_files.return_value = []
        with patch("beacon.storage.create_storage_backend", return_value=mock_storage):
            resp = sc.post(
                "/identity/save",
                data={
                    "csrf_token": csrf,
                    "identity_count": "1",
                    "identity_id_0": "identity-001",
                    "identity_description_0": "",
                    "identity_roles_0": "",
                    "identity_hvit_0": "1",
                    "identity_risk_factors_0": "executive, public-facing-brand",
                    "has_access_json": "",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 200

        from beacon.web.session import load_session  # noqa: PLC0415

        updated_session = load_session(session_id)
        assert updated_session is not None
        identities = updated_session["identity_doc"]["identities"]
        alice = next(i for i in identities if i["id"] == "identity-001")
        assert alice["is_high_value_impersonation_target"] is True
        assert "executive" in alice["impersonation_risk_factors"]

    def test_save_persists_has_access_json(self):
        session_id, cookies = _create_identity_session()
        sc = TestClient(app, cookies=cookies)
        identity_resp = sc.get("/identity")
        csrf = identity_resp.cookies.get("beacon_csrf", cookies["beacon_csrf"])
        cookies["beacon_csrf"] = csrf
        sc = TestClient(app, cookies=cookies)

        ha_json = json.dumps(
            [
                {
                    "identity_id": "identity-002",
                    "asset_id": "asset-db-01",
                    "access_level": "admin",
                    "role": "dba",
                }
            ]
        )
        mock_storage = MagicMock()
        mock_storage.save = MagicMock()
        mock_storage.list_files.return_value = []
        with patch("beacon.storage.create_storage_backend", return_value=mock_storage):
            resp = sc.post(
                "/identity/save",
                data={
                    "csrf_token": csrf,
                    "identity_count": "0",
                    "has_access_json": ha_json,
                },
                follow_redirects=False,
            )
        assert resp.status_code == 200

        from beacon.web.session import load_session  # noqa: PLC0415

        updated_session = load_session(session_id)
        assert updated_session is not None
        ha_list = updated_session["identity_doc"]["has_access"]
        assert len(ha_list) == 1
        assert ha_list[0]["identity_id"] == "identity-002"
        assert ha_list[0]["access_level"] == "admin"

    def test_save_writes_to_storage(self):
        session_id, cookies = _create_identity_session()
        sc = TestClient(app, cookies=cookies)
        identity_resp = sc.get("/identity")
        csrf = identity_resp.cookies.get("beacon_csrf", cookies["beacon_csrf"])
        cookies["beacon_csrf"] = csrf
        sc = TestClient(app, cookies=cookies)

        mock_storage = MagicMock()
        mock_storage.save = MagicMock()
        mock_storage.list_files.return_value = []
        with patch("beacon.storage.create_storage_backend", return_value=mock_storage):
            resp = sc.post(
                "/identity/save",
                data={
                    "csrf_token": csrf,
                    "identity_count": "0",
                    "has_access_json": "",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 200
        save_calls = mock_storage.save.call_args_list
        assert len(save_calls) >= 1
        category, filename, _ = save_calls[0][0]
        assert category == "assets"
        assert filename.startswith("identity_assets_")
        assert filename.endswith(".json")

    def test_save_csrf_required(self):
        session_id, cookies = _create_identity_session()
        bad_cookies = {**cookies, "beacon_csrf": "mismatch-token"}
        sc = TestClient(app, cookies=bad_cookies)
        resp = sc.post(
            "/identity/save",
            data={
                "csrf_token": "different-token",
                "identity_count": "0",
                "has_access_json": "",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 403

    def test_save_no_session_returns_400(self):
        csrf_token, cookies = _get_csrf()
        fresh = TestClient(app, cookies=cookies)
        resp = fresh.post(
            "/identity/save",
            data={
                "csrf_token": csrf_token,
                "identity_count": "0",
                "has_access_json": "",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 400

    def test_save_session_without_identity_doc_returns_400(self):
        from beacon.web.session import create_session  # noqa: PLC0415

        session_id = create_session({"pirs": [], "collection_plan": ""})
        csrf_token, _ = _get_csrf()
        cookies = {"beacon_session": session_id, "beacon_csrf": csrf_token}
        sc = TestClient(app, cookies=cookies)

        mock_storage = MagicMock()
        with patch("beacon.storage.create_storage_backend", return_value=mock_storage):
            resp = sc.post(
                "/identity/save",
                data={
                    "csrf_token": csrf_token,
                    "identity_count": "0",
                    "has_access_json": "",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Accounts tab tests
# ---------------------------------------------------------------------------

SAMPLE_ACCOUNTS_DOC = {
    "user_accounts": [
        {
            "id": "acct-001",
            "account_login": "alice",
            "display_name": "",
            "account_type": "windows",
            "is_privileged": False,
            "is_service_account": False,
            "identity_id": "identity-001",
            "description": "",
        },
        {
            "id": "acct-002",
            "account_login": "svc-backup",
            "display_name": "Backup Service",
            "account_type": "unix",
            "is_privileged": True,
            "is_service_account": True,
            "identity_id": None,
            "description": "Automated backup account",
        },
    ],
    "account_on_asset": [
        {
            "user_account_id": "acct-001",
            "asset_id": "asset-web-01",
            "first_seen": "2026-01-01",
            "last_seen": "2026-05-28",
        }
    ],
}


def _create_accounts_session(
    accounts_doc: dict | None = None,
) -> tuple[str, dict[str, str]]:
    """Create a session containing an accounts_doc; return (session_id, cookies_with_csrf)."""
    from beacon.web.session import create_session  # noqa: PLC0415

    doc = accounts_doc if accounts_doc is not None else SAMPLE_ACCOUNTS_DOC
    session_id = create_session({"pirs": [], "collection_plan": "", "accounts_doc": doc})
    csrf_token, _ = _get_csrf()
    return session_id, {"beacon_session": session_id, "beacon_csrf": csrf_token}


class TestAccountsRoute:
    """Tests for the Accounts tab routes."""

    # ------------------------------------------------------------------
    # GET /accounts
    # ------------------------------------------------------------------

    def test_get_returns_200(self):
        resp = client.get("/accounts")
        assert resp.status_code == 200

    def test_get_shows_accounts_section(self):
        resp = client.get("/accounts")
        assert b"Accounts" in resp.content

    def test_get_shows_nav_link(self):
        resp = client.get("/accounts")
        assert b'href="/accounts"' in resp.content

    def test_get_sets_csrf_cookie(self):
        resp = client.get("/accounts")
        assert "beacon_csrf" in resp.cookies

    def test_get_shows_stored_drafts_section(self):
        mock_storage = MagicMock()
        mock_storage.list_files.return_value = [
            "user_accounts_202606010900.json",
            "user_accounts_202606011000.json",
        ]
        with patch("beacon.storage.create_storage_backend", return_value=mock_storage):
            resp = client.get("/accounts")
        assert resp.status_code == 200
        assert b"user_accounts_202606010900.json" in resp.content

    def test_get_no_doc_loaded_shows_hint(self):
        fresh = TestClient(app, cookies={})
        resp = fresh.get("/accounts")
        assert resp.status_code == 200
        assert b"No accounts draft loaded" in resp.content

    def test_get_with_loaded_doc_shows_accounts_table(self):
        session_id, cookies = _create_accounts_session()
        sc = TestClient(app, cookies=cookies)
        resp = sc.get("/accounts")
        assert resp.status_code == 200
        assert b"acct-001" in resp.content
        assert b"acct-002" in resp.content

    # ------------------------------------------------------------------
    # POST /accounts/load-stored/{filename}
    # ------------------------------------------------------------------

    def test_load_stored_loads_doc_into_session(self):
        csrf_token, cookies = _get_csrf()
        mock_storage = MagicMock()
        mock_storage.load.return_value = json.dumps(SAMPLE_ACCOUNTS_DOC)
        sc = TestClient(app, cookies=cookies)
        with patch("beacon.storage.create_storage_backend", return_value=mock_storage):
            resp = sc.post(
                "/accounts/load-stored/user_accounts_202606011200.json",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/accounts"
        assert "beacon_session" in resp.cookies

    def test_load_stored_missing_file_returns_404(self):
        csrf_token, cookies = _get_csrf()
        mock_storage = MagicMock()
        mock_storage.load.side_effect = FileNotFoundError("not found")
        sc = TestClient(app, cookies=cookies)
        with patch("beacon.storage.create_storage_backend", return_value=mock_storage):
            resp = sc.post(
                "/accounts/load-stored/user_accounts_missing.json",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )
        assert resp.status_code == 404

    def test_load_stored_bad_json_returns_400(self):
        csrf_token, cookies = _get_csrf()
        mock_storage = MagicMock()
        mock_storage.load.return_value = "not json {"
        sc = TestClient(app, cookies=cookies)
        with patch("beacon.storage.create_storage_backend", return_value=mock_storage):
            resp = sc.post(
                "/accounts/load-stored/user_accounts_bad.json",
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )
        assert resp.status_code == 400

    def test_load_stored_csrf_required(self):
        fresh = TestClient(app, cookies={})
        mock_storage = MagicMock()
        mock_storage.load.return_value = json.dumps(SAMPLE_ACCOUNTS_DOC)
        with patch("beacon.storage.create_storage_backend", return_value=mock_storage):
            resp = fresh.post(
                "/accounts/load-stored/user_accounts_202606011200.json",
                data={},
                follow_redirects=False,
            )
        assert resp.status_code == 403

    # ------------------------------------------------------------------
    # POST /accounts/save
    # ------------------------------------------------------------------

    def test_save_persists_display_name(self):
        session_id, cookies = _create_accounts_session()
        sc = TestClient(app, cookies=cookies)
        accounts_resp = sc.get("/accounts")
        csrf = accounts_resp.cookies.get("beacon_csrf", cookies["beacon_csrf"])
        cookies["beacon_csrf"] = csrf
        sc = TestClient(app, cookies=cookies)

        mock_storage = MagicMock()
        mock_storage.save = MagicMock()
        mock_storage.list_files.return_value = []
        with patch("beacon.storage.create_storage_backend", return_value=mock_storage):
            resp = sc.post(
                "/accounts/save",
                data={
                    "csrf_token": csrf,
                    "account_count": "2",
                    "acct_id_0": "acct-001",
                    "acct_display_name_0": "Alice Smith",
                    "acct_type_0": "windows",
                    "acct_privileged_0": "",
                    "acct_service_0": "",
                    "acct_description_0": "",
                    "acct_id_1": "acct-002",
                    "acct_display_name_1": "Backup Service",
                    "acct_type_1": "unix",
                    "acct_privileged_1": "1",
                    "acct_service_1": "1",
                    "acct_description_1": "Automated backup account",
                    "account_on_asset_json": "",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 200

        from beacon.web.session import load_session  # noqa: PLC0415

        updated_session = load_session(session_id)
        assert updated_session is not None
        accounts = updated_session["accounts_doc"]["user_accounts"]
        alice = next(a for a in accounts if a["id"] == "acct-001")
        svc = next(a for a in accounts if a["id"] == "acct-002")
        assert alice["display_name"] == "Alice Smith"
        assert svc["is_privileged"] is True
        assert svc["is_service_account"] is True

    def test_save_persists_account_on_asset_json(self):
        session_id, cookies = _create_accounts_session()
        sc = TestClient(app, cookies=cookies)
        accounts_resp = sc.get("/accounts")
        csrf = accounts_resp.cookies.get("beacon_csrf", cookies["beacon_csrf"])
        cookies["beacon_csrf"] = csrf
        sc = TestClient(app, cookies=cookies)

        aoa_json = json.dumps(
            [
                {
                    "user_account_id": "acct-002",
                    "asset_id": "asset-db-01",
                    "first_seen": "2026-02-01",
                    "last_seen": "2026-05-28",
                }
            ]
        )
        mock_storage = MagicMock()
        mock_storage.save = MagicMock()
        mock_storage.list_files.return_value = []
        with patch("beacon.storage.create_storage_backend", return_value=mock_storage):
            resp = sc.post(
                "/accounts/save",
                data={
                    "csrf_token": csrf,
                    "account_count": "0",
                    "account_on_asset_json": aoa_json,
                },
                follow_redirects=False,
            )
        assert resp.status_code == 200

        from beacon.web.session import load_session  # noqa: PLC0415

        updated_session = load_session(session_id)
        assert updated_session is not None
        aoa_list = updated_session["accounts_doc"]["account_on_asset"]
        assert len(aoa_list) == 1
        assert aoa_list[0]["user_account_id"] == "acct-002"
        assert aoa_list[0]["first_seen"] == "2026-02-01"

    def test_save_writes_to_storage(self):
        session_id, cookies = _create_accounts_session()
        sc = TestClient(app, cookies=cookies)
        accounts_resp = sc.get("/accounts")
        csrf = accounts_resp.cookies.get("beacon_csrf", cookies["beacon_csrf"])
        cookies["beacon_csrf"] = csrf
        sc = TestClient(app, cookies=cookies)

        mock_storage = MagicMock()
        mock_storage.save = MagicMock()
        mock_storage.list_files.return_value = []
        with patch("beacon.storage.create_storage_backend", return_value=mock_storage):
            resp = sc.post(
                "/accounts/save",
                data={
                    "csrf_token": csrf,
                    "account_count": "0",
                    "account_on_asset_json": "",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 200
        save_calls = mock_storage.save.call_args_list
        assert len(save_calls) >= 1
        category, filename, _ = save_calls[0][0]
        assert category == "assets"
        assert filename.startswith("user_accounts_")
        assert filename.endswith(".json")

    def test_save_csrf_required(self):
        session_id, cookies = _create_accounts_session()
        bad_cookies = {**cookies, "beacon_csrf": "mismatch-token"}
        sc = TestClient(app, cookies=bad_cookies)
        resp = sc.post(
            "/accounts/save",
            data={
                "csrf_token": "different-token",
                "account_count": "0",
                "account_on_asset_json": "",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 403

    def test_save_no_session_returns_400(self):
        csrf_token, cookies = _get_csrf()
        fresh = TestClient(app, cookies=cookies)
        resp = fresh.post(
            "/accounts/save",
            data={
                "csrf_token": csrf_token,
                "account_count": "0",
                "account_on_asset_json": "",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 400

    def test_save_session_without_accounts_doc_returns_400(self):
        from beacon.web.session import create_session  # noqa: PLC0415

        session_id = create_session({"pirs": [], "collection_plan": ""})
        csrf_token, _ = _get_csrf()
        cookies = {"beacon_session": session_id, "beacon_csrf": csrf_token}
        sc = TestClient(app, cookies=cookies)

        mock_storage = MagicMock()
        with patch("beacon.storage.create_storage_backend", return_value=mock_storage):
            resp = sc.post(
                "/accounts/save",
                data={
                    "csrf_token": csrf_token,
                    "account_count": "0",
                    "account_on_asset_json": "",
                },
                follow_redirects=False,
            )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# PIR StorageBackend persistence tests
# ---------------------------------------------------------------------------


class TestPirStoragePersistence:
    """Verify that /pir/generate and /api/generate persist PIR to StorageBackend."""

    def test_pir_generate_persists_to_storage(self, monkeypatch, tmp_path):
        """POST /pir/generate writes pir_output_*.json to LocalStorage."""
        monkeypatch.setenv("BEACON_STORAGE", "local")
        monkeypatch.setenv("BEACON_STORAGE_BASE_DIR", str(tmp_path))

        csrf_token, cookies = _get_csrf()
        context_bytes = SAMPLE_CONTEXT_PATH.read_bytes()
        session_client = TestClient(app, cookies=cookies)

        mock_pirs = [{"pir_id": "PIR-1", "description": "Test PIR for storage"}]
        mock_plan = "# Collection plan\n- item1"

        with patch("beacon.web.app._run_pipeline", MagicMock(return_value=(mock_pirs, mock_plan))):
            resp = session_client.post(
                "/pir/generate",
                files={"context_file": ("sample.json", context_bytes, "application/json")},
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )

        assert resp.status_code == 303

        pir_dir = tmp_path / "pir"
        assert pir_dir.is_dir(), f"Expected pir/ subdir under {tmp_path}"
        pir_files = list(pir_dir.glob("pir_output_*.json"))
        assert len(pir_files) >= 1, f"No pir_output_*.json found in {pir_dir}"

        content = json.loads(pir_files[0].read_text(encoding="utf-8"))
        assert isinstance(content, list)
        assert content[0]["pir_id"] == "PIR-1"

    def test_api_generate_persists_to_storage(self, monkeypatch, tmp_path):
        """POST /api/generate writes pir_output_*.json to LocalStorage."""
        monkeypatch.setenv("BEACON_STORAGE", "local")
        monkeypatch.setenv("BEACON_STORAGE_BASE_DIR", str(tmp_path))

        context_bytes = SAMPLE_CONTEXT_PATH.read_bytes()

        mock_pirs = [{"pir_id": "PIR-API-1", "description": "API generated PIR"}]
        mock_plan = "# Collection plan\n- api-item"

        with patch("beacon.web.app._run_pipeline", MagicMock(return_value=(mock_pirs, mock_plan))):
            resp = client.post(
                "/api/generate",
                files={"context_file": ("sample.json", context_bytes, "application/json")},
            )

        assert resp.status_code == 200

        pir_dir = tmp_path / "pir"
        assert pir_dir.is_dir(), f"Expected pir/ subdir under {tmp_path}"
        pir_files = list(pir_dir.glob("pir_output_*.json"))
        assert len(pir_files) >= 1, f"No pir_output_*.json found in {pir_dir}"

    def test_pir_generate_storage_failure_does_not_break_handler(self, monkeypatch, capsys):
        """Storage save failure emits warning but handler still returns 303."""
        monkeypatch.setenv("BEACON_STORAGE", "local")
        monkeypatch.setenv("BEACON_STORAGE_BASE_DIR", "/nonexistent-path-does-not-matter")

        csrf_token, cookies = _get_csrf()
        context_bytes = SAMPLE_CONTEXT_PATH.read_bytes()
        session_client = TestClient(app, cookies=cookies)

        mock_pirs = [{"pir_id": "PIR-FAIL", "description": "Storage will fail"}]
        mock_plan = "# Collection plan\n- item"

        broken_storage = MagicMock()
        broken_storage.save.side_effect = Exception("simulated storage failure")

        with (
            patch("beacon.web.app._run_pipeline", MagicMock(return_value=(mock_pirs, mock_plan))),
            patch("beacon.storage.create_storage_backend", return_value=broken_storage),
        ):
            resp = session_client.post(
                "/pir/generate",
                files={"context_file": ("sample.json", context_bytes, "application/json")},
                data={"csrf_token": csrf_token},
                follow_redirects=False,
            )

        assert resp.status_code == 303, "Handler must still redirect even when storage fails"
        captured = capsys.readouterr()
        log_output = captured.out + captured.err
        assert "pir_save_storage_failed" in log_output, (
            "Expected warning log 'pir_save_storage_failed' not found in structlog output"
        )
