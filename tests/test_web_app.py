"""Tests for src/beacon/web/app.py using FastAPI TestClient."""

from __future__ import annotations

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
                "tool_sophistication": 0.3,
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
