"""Tests for PIR-driven discovery in the Collection tab."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from beacon.trace.runner import DiscoveryResult
from beacon.web.app import app


def _client_and_csrf(trace_root: str) -> tuple[TestClient, str]:
    client = TestClient(app, raise_server_exceptions=True)
    resp = client.get("/collection")
    csrf = resp.cookies.get("beacon_csrf", "")
    # Preserve the CSRF cookie while letting the test pass TRACE_ROOT_PATH via env.
    client.cookies.set("beacon_csrf", csrf)
    return client, csrf


class TestCollectionDiscoveryPage:
    def test_get_collection_shows_discovery_form_when_trace_configured(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRACE_ROOT_PATH", str(tmp_path))
        client, _ = _client_and_csrf(str(tmp_path))

        resp = client.get("/collection")

        assert resp.status_code == 200
        assert "PIR-driven Article Discovery" in resp.text
        assert "/collection/discover" in resp.text
        assert "discover-pir" in resp.text
        assert "Include recent unmatched articles" in resp.text


class TestCollectionDiscoverRoute:
    def test_discover_renders_candidate_table(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRACE_ROOT_PATH", str(tmp_path))
        client, csrf = _client_and_csrf(str(tmp_path))
        result = DiscoveryResult(
            success=True,
            stdout=json.dumps({"candidates": []}),
            stderr="",
            return_code=0,
            candidates=[
                {
                    "url": "https://example.com/salt-typhoon",
                    "title": "Salt Typhoon targets edge devices",
                    "source_name": "Example Feed",
                    "published_at": "2026-06-15T10:00:00Z",
                    "matched_pir_ids": ["PIR-2026-001"],
                    "matched_terms": ["salt typhoon", "apt-china"],
                    "score": 0.9,
                    "summary": "Fixture summary",
                }
            ],
            candidate_count=1,
            window={"from": "2026-06-01", "to": "2026-06-30"},
        )

        with patch("beacon.trace.runner.run_discover_pir", return_value=result) as mock_run:
            resp = client.post(
                "/collection/discover",
                data={
                    "csrf_token": csrf,
                    "pir_path": str(tmp_path / "pir_output.json"),
                    "catalog_path": "input/source_catalog.yaml",
                    "from_date": "2026-06-01",
                    "to_date": "2026-06-30",
                    "since_days": "30",
                    "max_candidates": "25",
                    "include_recent": "1",
                },
            )

        assert resp.status_code == 200
        assert "Candidates: 1" in resp.text
        assert "Salt Typhoon targets edge devices" in resp.text
        assert "PIR-2026-001" in resp.text
        assert "salt typhoon, apt-china" in resp.text
        mock_run.assert_called_once()
        _, kwargs = mock_run.call_args
        assert kwargs["catalog_path"] == "input/source_catalog.yaml"
        assert kwargs["from_date"] == "2026-06-01"
        assert kwargs["to_date"] == "2026-06-30"
        assert kwargs["since_days"] == 30
        assert kwargs["max_candidates"] == 25
        assert kwargs["include_recent"] is True

    def test_discover_shows_failure(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRACE_ROOT_PATH", str(tmp_path))
        client, csrf = _client_and_csrf(str(tmp_path))
        result = DiscoveryResult(
            success=False,
            stdout="",
            stderr="catalog_not_found",
            return_code=2,
        )

        with patch("beacon.trace.runner.run_discover_pir", return_value=result):
            resp = client.post(
                "/collection/discover",
                data={
                    "csrf_token": csrf,
                    "pir_path": str(tmp_path / "pir_output.json"),
                    "since_days": "30",
                    "max_candidates": "25",
                    "include_recent": "1",
                },
            )

        assert resp.status_code == 200
        assert "失敗" in resp.text
        assert "catalog_not_found" in resp.text

    def test_discover_csrf_mismatch_returns_403(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRACE_ROOT_PATH", str(tmp_path))
        client = TestClient(app, cookies={"beacon_csrf": "cookie-token"})

        resp = client.post(
            "/collection/discover",
            data={
                "csrf_token": "wrong-token",
                "pir_path": str(tmp_path / "pir_output.json"),
            },
        )

        assert resp.status_code == 403


class TestRunDiscoverPir:
    def test_empty_trace_root_returns_failure(self):
        from beacon.trace.runner import run_discover_pir

        result = run_discover_pir("/tmp/pir_output.json", "")

        assert not result.success
        assert "TRACE パスが設定されていません" in result.stderr

    def test_success_parses_candidate_json(self, tmp_path):
        from beacon.trace.runner import run_discover_pir

        payload = {
            "window": {"from": "2026-06-01", "to": "2026-06-30"},
            "candidates": [{"url": "https://example.com/a", "score": 0.8}],
        }
        with patch("beacon.trace.runner.subprocess.run") as mock_run:
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdout = json.dumps(payload)
            mock_proc.stderr = ""
            mock_run.return_value = mock_proc

            result = run_discover_pir(
                "/tmp/pir_output.json",
                str(tmp_path),
                catalog_path="input/source_catalog.yaml",
                from_date="2026-06-01",
                to_date="2026-06-30",
                since_days=30,
                max_candidates=25,
                include_recent=True,
            )

        assert result.success
        assert result.candidate_count == 1
        assert result.window == {"from": "2026-06-01", "to": "2026-06-30"}
        cmd = mock_run.call_args[0][0]
        assert cmd[:3] == ["uv", "run", "trace"]
        assert "discover-pir" in cmd
        assert "--json" in cmd
        assert "--catalog" in cmd
        assert "input/source_catalog.yaml" in cmd
        assert "--max-candidates" in cmd
        assert "25" in cmd
        assert "--include-recent" in cmd

    def test_nonzero_return_code_keeps_diagnostics(self, tmp_path):
        from beacon.trace.runner import run_discover_pir

        with patch("beacon.trace.runner.subprocess.run") as mock_run:
            mock_proc = MagicMock()
            mock_proc.returncode = 2
            mock_proc.stdout = "not json"
            mock_proc.stderr = "bad pir"
            mock_run.return_value = mock_proc

            result = run_discover_pir("/tmp/pir_output.json", str(tmp_path))

        assert not result.success
        assert result.return_code == 2
        assert result.stderr == "bad pir"
        assert result.candidates == []

    def test_timeout_returns_failure(self, tmp_path):
        from beacon.trace.runner import run_discover_pir

        with patch("beacon.trace.runner.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="uv", timeout=300)
            result = run_discover_pir("/tmp/pir_output.json", str(tmp_path))

        assert not result.success
        assert "timed out" in result.stderr
        assert result.return_code == -1


def test_default_discovery_pir_reference_uses_gcs_storage_key(monkeypatch):
    from beacon.web.app import _default_discovery_pir_reference

    class FakeStorage:
        def list_files(self, category: str):
            assert category == "pir"
            return ["pir_output_202606301000.json", "pir_output_202606301159.json"]

    monkeypatch.setenv("BEACON_STORAGE", "gcs")
    monkeypatch.setenv("BEACON_STORAGE_BUCKET", "cti-bucket")
    monkeypatch.setenv("BEACON_STORAGE_PREFIX", "prod/")
    monkeypatch.setattr("beacon.storage.create_storage_backend", lambda cfg: FakeStorage())

    assert _default_discovery_pir_reference() == "prod/pir/pir_output_202606301159.json"


def test_default_discovery_pir_reference_keeps_local_absolute_default(monkeypatch):
    from pathlib import Path

    from beacon.web.app import _default_discovery_pir_reference

    monkeypatch.setenv("BEACON_STORAGE", "local")
    monkeypatch.delenv("BEACON_OUTPUT_DIR", raising=False)

    assert _default_discovery_pir_reference() == str((Path("output") / "pir_output.json").resolve())
