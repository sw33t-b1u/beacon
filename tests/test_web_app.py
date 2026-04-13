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


def _make_pipeline_mock(pirs=None, plan="## Collection Plan\n- item1"):
    """Return a mock for _run_pipeline that returns sample data."""
    if pirs is None:
        pirs = [SAMPLE_PIR]
    return MagicMock(return_value=(pirs, plan))


client = TestClient(app, raise_server_exceptions=True)


def _get_csrf(test_client: TestClient | None = None) -> tuple[str, dict[str, str]]:
    """GET / to obtain a CSRF cookie and return (csrf_token, cookies_dict).

    The CSRF token is embedded in the cookie; we also extract it from the
    index page response (the GET / handler sets the cookie value which is
    the same token passed to the template).
    """
    c = test_client or client
    resp = c.get("/")
    csrf_cookie = resp.cookies.get("beacon_csrf", "")
    return csrf_cookie, {"beacon_csrf": csrf_cookie}


class TestIndexRoute:
    def test_get_returns_200(self):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_get_sets_csrf_cookie(self):
        resp = client.get("/")
        assert "beacon_csrf" in resp.cookies

    def test_get_contains_form(self):
        resp = client.get("/")
        assert b"context_file" in resp.content or b"Generate" in resp.content


class TestGenerateRoute:
    def test_post_redirects_to_review(self):
        csrf_token, cookies = _get_csrf()
        context_bytes = SAMPLE_CONTEXT_PATH.read_bytes()

        session_client = TestClient(app, cookies=cookies)
        with patch("beacon.web.app._run_pipeline", _make_pipeline_mock()):
            resp = session_client.post(
                "/generate",
                files={"context_file": ("sample.json", context_bytes, "application/json")},
                data={"no_llm": "true", "csrf_token": csrf_token},
                follow_redirects=False,
            )

        assert resp.status_code == 303
        assert resp.headers["location"] == "/review"

    def test_post_sets_session_cookie(self):
        csrf_token, cookies = _get_csrf()
        context_bytes = SAMPLE_CONTEXT_PATH.read_bytes()

        session_client = TestClient(app, cookies=cookies)
        with patch("beacon.web.app._run_pipeline", _make_pipeline_mock()):
            resp = session_client.post(
                "/generate",
                files={"context_file": ("sample.json", context_bytes, "application/json")},
                data={"no_llm": "true", "csrf_token": csrf_token},
                follow_redirects=False,
            )

        assert "beacon_session" in resp.cookies

    def test_post_without_csrf_returns_403(self):
        context_bytes = SAMPLE_CONTEXT_PATH.read_bytes()
        fresh = TestClient(app, cookies={})
        with patch("beacon.web.app._run_pipeline", _make_pipeline_mock()):
            resp = fresh.post(
                "/generate",
                files={"context_file": ("sample.json", context_bytes, "application/json")},
                data={"no_llm": "true"},
                follow_redirects=False,
            )
        assert resp.status_code == 403

    def test_post_with_wrong_csrf_returns_403(self):
        _, cookies = _get_csrf()
        context_bytes = SAMPLE_CONTEXT_PATH.read_bytes()

        session_client = TestClient(app, cookies=cookies)
        with patch("beacon.web.app._run_pipeline", _make_pipeline_mock()):
            resp = session_client.post(
                "/generate",
                files={"context_file": ("sample.json", context_bytes, "application/json")},
                data={"no_llm": "true", "csrf_token": "wrong-token"},
                follow_redirects=False,
            )
        assert resp.status_code == 403


def _create_session_with_csrf() -> tuple[str, dict[str, str]]:
    """Helper: POST /generate and return (session_id, merged_cookies)."""
    csrf_token, cookies = _get_csrf()
    context_bytes = SAMPLE_CONTEXT_PATH.read_bytes()
    session_client = TestClient(app, cookies=cookies)
    with patch("beacon.web.app._run_pipeline", _make_pipeline_mock()):
        resp = session_client.post(
            "/generate",
            files={"context_file": ("sample.json", context_bytes, "application/json")},
            data={"no_llm": "true", "csrf_token": csrf_token},
            follow_redirects=False,
        )
    sid = resp.cookies.get("beacon_session", "")
    new_csrf = resp.cookies.get("beacon_csrf", "")
    return sid, {"beacon_session": sid, "beacon_csrf": new_csrf}


class TestReviewRoute:
    def test_review_without_session_shows_no_pirs(self):
        fresh = TestClient(app, cookies={})
        resp = fresh.get("/review")
        assert resp.status_code == 200
        assert b"No PIRs" in resp.content or b"Generate" in resp.content

    def test_review_with_session_shows_pir(self):
        _, cookies = _create_session_with_csrf()
        session_client = TestClient(app, cookies=cookies)
        resp = session_client.get("/review")
        assert resp.status_code == 200
        assert b"PIR-2026-001" in resp.content


class TestReviewSaveRoute:
    def test_save_updates_description(self):
        _, cookies = _create_session_with_csrf()
        # GET /review to get a fresh CSRF token for the save form
        session_client = TestClient(app, cookies=cookies)
        review_resp = session_client.get("/review")
        csrf_token = review_resp.cookies.get("beacon_csrf", cookies.get("beacon_csrf", ""))
        cookies["beacon_csrf"] = csrf_token
        session_client = TestClient(app, cookies=cookies)

        resp = session_client.post(
            "/review/save",
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
        review_resp = session_client.get("/review")
        csrf_token = review_resp.cookies.get("beacon_csrf", cookies.get("beacon_csrf", ""))
        cookies["beacon_csrf"] = csrf_token
        session_client = TestClient(app, cookies=cookies)

        session_client.post(
            "/review/save",
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
            "/review/save",
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
                "/generate",
                files={"context_file": ("huge.json", huge, "application/json")},
                data={"no_llm": "true", "csrf_token": csrf_token},
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
