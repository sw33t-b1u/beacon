"""Tests for approved candidate extraction from the Collection tab."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from beacon.trace.runner import CrawlResult
from beacon.web.app import app


def _client_and_csrf(monkeypatch, tmp_path: Path) -> tuple[TestClient, str]:
    monkeypatch.setenv("TRACE_ROOT_PATH", str(tmp_path))
    client = TestClient(app, raise_server_exceptions=True)
    resp = client.get("/collection")
    csrf = resp.cookies.get("beacon_csrf", "")
    client.cookies.set("beacon_csrf", csrf)
    return client, csrf


def _candidate(url: str = "https://example.com/salt-typhoon") -> str:
    return json.dumps(
        {
            "url": url,
            "title": "Salt Typhoon targets edge devices",
            "source_name": "Example Feed",
            "matched_pir_ids": ["PIR-2026-001"],
            "matched_terms": ["salt typhoon"],
            "score": 0.9,
        }
    )


class TestCollectionExtractApproved:
    def test_extract_approved_writes_sources_and_runs_crawl_batch(self, monkeypatch, tmp_path):
        client, csrf = _client_and_csrf(monkeypatch, tmp_path)
        captured: dict = {}

        def fake_run(yaml_path: str, trace_root: str, *, pir_path: str = "") -> CrawlResult:
            captured["trace_root"] = trace_root
            captured["pir_path"] = pir_path
            captured["payload"] = json.loads(Path(yaml_path).read_text(encoding="utf-8"))
            return CrawlResult(
                success=True,
                stdout="STIX bundle written: output/stix_bundle.json (7 objects)",
                stderr="",
                return_code=0,
                stix_object_count=7,
                pir_relevance_score=0.8,
            )

        with patch("beacon.trace.runner.run_crawl_batch", side_effect=fake_run) as mock_run:
            resp = client.post(
                "/collection/extract-approved",
                data={
                    "csrf_token": csrf,
                    "pir_path": str(tmp_path / "pir_output.json"),
                    "candidate_json": _candidate(),
                },
            )

        assert resp.status_code == 200
        assert "成功" in resp.text
        assert "STIX objects: 7" in resp.text
        mock_run.assert_called_once()
        assert captured["trace_root"] == str(tmp_path)
        assert captured["pir_path"] == str(tmp_path / "pir_output.json")
        assert captured["payload"] == {
            "version": 1,
            "sources": [
                {
                    "url": "https://example.com/salt-typhoon",
                    "label": "Example Feed: Salt Typhoon targets edge devices",
                    "task": "medium",
                    "pir_ids": ["PIR-2026-001"],
                }
            ],
        }

    def test_extract_approved_dedupes_candidate_urls(self, monkeypatch, tmp_path):
        client, csrf = _client_and_csrf(monkeypatch, tmp_path)
        captured: dict = {}

        def fake_run(yaml_path: str, trace_root: str, *, pir_path: str = "") -> CrawlResult:
            captured["payload"] = json.loads(Path(yaml_path).read_text(encoding="utf-8"))
            return CrawlResult(success=True, stdout="", stderr="", return_code=0)

        with patch("beacon.trace.runner.run_crawl_batch", side_effect=fake_run):
            resp = client.post(
                "/collection/extract-approved",
                data={
                    "csrf_token": csrf,
                    "pir_path": str(tmp_path / "pir_output.json"),
                    "candidate_json": [
                        _candidate("https://example.com/report"),
                        _candidate("https://example.com/report/"),
                    ],
                },
            )

        assert resp.status_code == 200
        assert len(captured["payload"]["sources"]) == 1

    def test_extract_approved_empty_selection_shows_failure(self, monkeypatch, tmp_path):
        client, csrf = _client_and_csrf(monkeypatch, tmp_path)

        with patch("beacon.trace.runner.run_crawl_batch") as mock_run:
            resp = client.post(
                "/collection/extract-approved",
                data={
                    "csrf_token": csrf,
                    "pir_path": str(tmp_path / "pir_output.json"),
                },
            )

        assert resp.status_code == 200
        assert "失敗" in resp.text
        assert "select at least one candidate article" in resp.text
        mock_run.assert_not_called()

    def test_extract_approved_rejects_invalid_url(self, monkeypatch, tmp_path):
        client, csrf = _client_and_csrf(monkeypatch, tmp_path)
        bad_candidate = json.dumps({"url": "javascript:alert(1)", "title": "bad"})

        with patch("beacon.trace.runner.run_crawl_batch") as mock_run:
            resp = client.post(
                "/collection/extract-approved",
                data={
                    "csrf_token": csrf,
                    "pir_path": str(tmp_path / "pir_output.json"),
                    "candidate_json": bad_candidate,
                },
            )

        assert resp.status_code == 200
        assert "selected candidate URL is not http(s)" in resp.text
        mock_run.assert_not_called()

    def test_extract_approved_csrf_mismatch_returns_403(self, tmp_path):
        client = TestClient(app, cookies={"beacon_csrf": "cookie-token"})

        resp = client.post(
            "/collection/extract-approved",
            data={
                "csrf_token": "wrong-token",
                "pir_path": str(tmp_path / "pir_output.json"),
                "candidate_json": _candidate(),
            },
        )

        assert resp.status_code == 403


class TestRunCrawlBatchWithPir:
    def test_pir_path_is_added_to_subprocess_args(self, tmp_path):
        from beacon.trace.runner import run_crawl_batch

        with patch("beacon.trace.runner.subprocess.run") as mock_run:
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdout = ""
            mock_proc.stderr = ""
            mock_run.return_value = mock_proc

            run_crawl_batch("/tmp/sources.yaml", str(tmp_path), pir_path="/tmp/pir_output.json")

        cmd = mock_run.call_args[0][0]
        assert "--pir" in cmd
        assert "/tmp/pir_output.json" in cmd
