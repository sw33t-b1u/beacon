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


class TestIndexRoute:
    def test_get_returns_200(self):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_get_contains_form(self):
        resp = client.get("/")
        assert b"context_file" in resp.content or b"Generate" in resp.content


class TestGenerateRoute:
    def test_post_redirects_to_review(self):
        context_bytes = SAMPLE_CONTEXT_PATH.read_bytes()

        with patch("beacon.web.app._run_pipeline", _make_pipeline_mock()):
            resp = client.post(
                "/generate",
                files={"context_file": ("sample.json", context_bytes, "application/json")},
                data={"no_llm": "true"},
                follow_redirects=False,
            )

        assert resp.status_code == 303
        assert resp.headers["location"] == "/review"

    def test_post_sets_session_cookie(self):
        context_bytes = SAMPLE_CONTEXT_PATH.read_bytes()

        with patch("beacon.web.app._run_pipeline", _make_pipeline_mock()):
            resp = client.post(
                "/generate",
                files={"context_file": ("sample.json", context_bytes, "application/json")},
                data={"no_llm": "true"},
                follow_redirects=False,
            )

        assert "beacon_session" in resp.cookies


class TestReviewRoute:
    def _create_session_with_pirs(self):
        """Helper: post to /generate and get session cookie."""
        context_bytes = SAMPLE_CONTEXT_PATH.read_bytes()
        with patch("beacon.web.app._run_pipeline", _make_pipeline_mock()):
            resp = client.post(
                "/generate",
                files={"context_file": ("sample.json", context_bytes, "application/json")},
                data={"no_llm": "true"},
                follow_redirects=False,
            )
        return resp.cookies.get("beacon_session")

    def test_review_without_session_shows_no_pirs(self):
        # Fresh client with no cookies
        fresh = TestClient(app, cookies={})
        resp = fresh.get("/review")
        assert resp.status_code == 200
        assert b"No PIRs" in resp.content or b"Generate" in resp.content

    def test_review_with_session_shows_pir(self):
        sid = self._create_session_with_pirs()
        resp = client.get("/review", cookies={"beacon_session": sid})
        assert resp.status_code == 200
        assert b"PIR-2026-001" in resp.content


class TestReviewSaveRoute:
    def _create_session(self):
        context_bytes = SAMPLE_CONTEXT_PATH.read_bytes()
        with patch("beacon.web.app._run_pipeline", _make_pipeline_mock()):
            resp = client.post(
                "/generate",
                files={"context_file": ("sample.json", context_bytes, "application/json")},
                data={"no_llm": "true"},
                follow_redirects=False,
            )
        return resp.cookies.get("beacon_session")

    def test_save_updates_description(self):
        sid = self._create_session()
        resp = client.post(
            "/review/save",
            data={
                "pir_index": "0",
                "description": "Updated description",
                "rationale": "Updated rationale",
                "collection_focus": "Track IOC A\nTrack IOC B",
            },
            cookies={"beacon_session": sid},
            follow_redirects=False,
        )
        assert resp.status_code == 303

        # Verify via /api/pir
        api_resp = client.get("/api/pir", cookies={"beacon_session": sid})
        pirs = api_resp.json()["pirs"]
        assert pirs[0]["description"] == "Updated description"

    def test_save_persists_collection_focus_as_list(self):
        sid = self._create_session()
        client.post(
            "/review/save",
            data={
                "pir_index": "0",
                "description": "desc",
                "rationale": "rat",
                "collection_focus": "Item A\nItem B\n\nItem C",
            },
            cookies={"beacon_session": sid},
            follow_redirects=False,
        )
        api_resp = client.get("/api/pir", cookies={"beacon_session": sid})
        focus = api_resp.json()["pirs"][0]["collection_focus"]
        assert "Item A" in focus
        assert "Item B" in focus
        assert "Item C" in focus
        assert "" not in focus


class TestExportRoute:
    def _create_session(self):
        context_bytes = SAMPLE_CONTEXT_PATH.read_bytes()
        with patch("beacon.web.app._run_pipeline", _make_pipeline_mock()):
            resp = client.post(
                "/generate",
                files={"context_file": ("sample.json", context_bytes, "application/json")},
                data={"no_llm": "true"},
                follow_redirects=False,
            )
        return resp.cookies.get("beacon_session")

    def test_export_returns_valid_json(self):
        sid = self._create_session()
        resp = client.get("/review/export", cookies={"beacon_session": sid})
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/json")
        data = resp.json()
        assert isinstance(data, list)
        assert data[0]["pir_id"] == "PIR-2026-001"

    def test_export_without_session_returns_error(self):
        fresh = TestClient(app, cookies={})
        resp = fresh.get("/review/export")
        assert resp.status_code in (400, 404)


class TestAPIPirRoute:
    def test_api_pir_returns_empty_without_session(self):
        fresh = TestClient(app, cookies={})
        resp = fresh.get("/api/pir")
        assert resp.status_code == 200
        assert resp.json() == {"pirs": []}

    def test_api_pir_returns_pirs_with_session(self):
        context_bytes = SAMPLE_CONTEXT_PATH.read_bytes()
        with patch("beacon.web.app._run_pipeline", _make_pipeline_mock()):
            gen_resp = client.post(
                "/generate",
                files={"context_file": ("sample.json", context_bytes, "application/json")},
                data={"no_llm": "true"},
                follow_redirects=False,
            )
        sid = gen_resp.cookies.get("beacon_session")
        resp = client.get("/api/pir", cookies={"beacon_session": sid})
        assert resp.status_code == 200
        assert len(resp.json()["pirs"]) > 0
