"""Tests for Collection tab routes and TRACE runner (Initiative I Phase 4)."""

from __future__ import annotations

import io
import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from beacon.web.app import app

client = TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _csrf_pair(response):
    """Extract (csrf_token_cookie, csrf_token_value) from a GET response.

    Returns a tuple suitable for setting headers/form fields in a POST.
    The cookie is already set on the TestClient via its cookie jar.
    """
    # TestClient persists cookies between requests; extract the value.
    token = response.cookies.get("beacon_csrf", "")
    return token


# ---------------------------------------------------------------------------
# GET /collection
# ---------------------------------------------------------------------------


class TestCollectionPage:
    def test_get_returns_200(self):
        resp = client.get("/collection")
        assert resp.status_code == 200

    def test_shows_no_trace_message_when_not_configured(self, monkeypatch):
        monkeypatch.setenv("TRACE_ROOT_PATH", "")
        resp = client.get("/collection")
        assert resp.status_code == 200
        assert "TRACE パスが設定されていません" in resp.text

    def test_shows_forms_when_configured(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRACE_ROOT_PATH", str(tmp_path))
        resp = client.get("/collection")
        assert resp.status_code == 200
        assert "Crawl Single URL" in resp.text
        assert "Crawl Batch" in resp.text
        assert "Crawl History" in resp.text

    def test_active_tab_is_collection(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRACE_ROOT_PATH", str(tmp_path))
        resp = client.get("/collection")
        assert resp.status_code == 200
        assert "collection" in resp.text

    def test_shows_crawl_history_from_state_file(self, monkeypatch, tmp_path):
        """When crawl_state.json exists, history is rendered in the table."""
        state = [
            {
                "url": "https://example.com/report",
                "status": "success",
                "timestamp": "2026-05-25T12:00:00",
                "stix_object_count": 42,
            }
        ]
        (tmp_path / "output").mkdir()
        (tmp_path / "output" / "crawl_state.json").write_text(json.dumps(state), encoding="utf-8")
        monkeypatch.setenv("TRACE_ROOT_PATH", str(tmp_path))
        resp = client.get("/collection")
        assert resp.status_code == 200
        assert "https://example.com/report" in resp.text
        assert "success" in resp.text

    def test_no_crash_when_crawl_state_missing(self, monkeypatch, tmp_path):
        """Missing crawl_state.json should not cause a 500."""
        monkeypatch.setenv("TRACE_ROOT_PATH", str(tmp_path))
        resp = client.get("/collection")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /collection/crawl-single
# ---------------------------------------------------------------------------


class TestCollectionCrawlSingle:
    def _get_csrf(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRACE_ROOT_PATH", str(tmp_path))
        resp = client.get("/collection")
        return resp.cookies.get("beacon_csrf", "")

    def test_returns_200_on_success(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRACE_ROOT_PATH", str(tmp_path))
        csrf = self._get_csrf(monkeypatch, tmp_path)

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.stdout = '{"stix_objects": 5}'
        mock_result.stderr = ""
        mock_result.return_code = 0
        mock_result.stix_object_count = 5
        mock_result.pir_relevance_score = 0.85

        with patch("beacon.trace.runner.subprocess.run") as mock_run:
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdout = '{"stix_objects": 5}'
            mock_proc.stderr = ""
            mock_run.return_value = mock_proc

            resp = client.post(
                "/collection/crawl-single",
                data={
                    "url": "https://example.com/report",
                    "csrf_token": csrf,
                },
                cookies={"beacon_csrf": csrf},
            )

        assert resp.status_code == 200
        assert "成功" in resp.text

    def test_shows_error_result_on_nonzero_return_code(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRACE_ROOT_PATH", str(tmp_path))
        csrf = self._get_csrf(monkeypatch, tmp_path)

        with patch("beacon.trace.runner.subprocess.run") as mock_run:
            mock_proc = MagicMock()
            mock_proc.returncode = 1
            mock_proc.stdout = ""
            mock_proc.stderr = "something went wrong"
            mock_run.return_value = mock_proc

            resp = client.post(
                "/collection/crawl-single",
                data={
                    "url": "https://example.com/report",
                    "csrf_token": csrf,
                },
                cookies={"beacon_csrf": csrf},
            )

        assert resp.status_code == 200
        assert "失敗" in resp.text

    def test_invalid_url_returns_failure(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRACE_ROOT_PATH", str(tmp_path))
        csrf = self._get_csrf(monkeypatch, tmp_path)

        # subprocess should NOT be called for invalid URLs
        with patch("beacon.trace.runner.subprocess.run") as mock_run:
            resp = client.post(
                "/collection/crawl-single",
                data={
                    "url": "ftp://malicious.example.com",
                    "csrf_token": csrf,
                },
                cookies={"beacon_csrf": csrf},
            )
            mock_run.assert_not_called()

        assert resp.status_code == 200
        assert "失敗" in resp.text

    def test_csrf_mismatch_returns_403(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRACE_ROOT_PATH", str(tmp_path))
        resp = client.post(
            "/collection/crawl-single",
            data={
                "url": "https://example.com",
                "csrf_token": "wrong-token",
            },
            cookies={"beacon_csrf": "cookie-token"},
        )
        assert resp.status_code == 403

    def test_no_trace_path_shows_message(self, monkeypatch):
        monkeypatch.setenv("TRACE_ROOT_PATH", "")
        # Need a CSRF cookie first — get from the collection page
        resp_get = client.get("/collection")
        csrf = resp_get.cookies.get("beacon_csrf", "fallback")

        resp = client.post(
            "/collection/crawl-single",
            data={
                "url": "https://example.com/report",
                "csrf_token": csrf,
            },
            cookies={"beacon_csrf": csrf},
        )
        assert resp.status_code == 200
        assert "TRACE パスが設定されていません" in resp.text


# ---------------------------------------------------------------------------
# POST /collection/crawl-batch
# ---------------------------------------------------------------------------


class TestCollectionCrawlBatch:
    def _get_csrf(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRACE_ROOT_PATH", str(tmp_path))
        resp = client.get("/collection")
        return resp.cookies.get("beacon_csrf", "")

    def _yaml_file(self, content: str = "sources:\n  - url: https://example.com\n"):
        """Return an in-memory file-like object for upload."""
        return ("sources.yaml", io.BytesIO(content.encode()), "application/octet-stream")

    def test_returns_200_on_success(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRACE_ROOT_PATH", str(tmp_path))
        csrf = self._get_csrf(monkeypatch, tmp_path)

        with patch("beacon.trace.runner.subprocess.run") as mock_run:
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdout = '{"stix_objects": 10}'
            mock_proc.stderr = ""
            mock_run.return_value = mock_proc

            resp = client.post(
                "/collection/crawl-batch",
                data={"csrf_token": csrf},
                files={"sources_file": self._yaml_file()},
                cookies={"beacon_csrf": csrf},
            )

        assert resp.status_code == 200
        assert "成功" in resp.text

    def test_shows_batch_failure(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRACE_ROOT_PATH", str(tmp_path))
        csrf = self._get_csrf(monkeypatch, tmp_path)

        with patch("beacon.trace.runner.subprocess.run") as mock_run:
            mock_proc = MagicMock()
            mock_proc.returncode = 2
            mock_proc.stdout = ""
            mock_proc.stderr = "batch error"
            mock_run.return_value = mock_proc

            resp = client.post(
                "/collection/crawl-batch",
                data={"csrf_token": csrf},
                files={"sources_file": self._yaml_file()},
                cookies={"beacon_csrf": csrf},
            )

        assert resp.status_code == 200
        assert "失敗" in resp.text

    def test_csrf_mismatch_returns_403(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRACE_ROOT_PATH", str(tmp_path))
        resp = client.post(
            "/collection/crawl-batch",
            data={"csrf_token": "bad"},
            files={"sources_file": self._yaml_file()},
            cookies={"beacon_csrf": "other"},
        )
        assert resp.status_code == 403

    def test_no_trace_path_shows_message(self, monkeypatch):
        monkeypatch.setenv("TRACE_ROOT_PATH", "")
        resp_get = client.get("/collection")
        csrf = resp_get.cookies.get("beacon_csrf", "fallback")

        yaml_file = ("sources.yaml", io.BytesIO(b"sources: []"), "application/octet-stream")
        resp = client.post(
            "/collection/crawl-batch",
            data={"csrf_token": csrf},
            files={"sources_file": yaml_file},
            cookies={"beacon_csrf": csrf},
        )
        assert resp.status_code == 200
        assert "TRACE パスが設定されていません" in resp.text


# ---------------------------------------------------------------------------
# GET /collection/api/crawl-state
# ---------------------------------------------------------------------------


class TestCollectionApiCrawlState:
    def test_returns_error_when_not_configured(self, monkeypatch):
        monkeypatch.setenv("TRACE_ROOT_PATH", "")
        resp = client.get("/collection/api/crawl-state")
        assert resp.status_code == 200
        data = resp.json()
        assert data["entries"] == []
        assert "error" in data

    def test_returns_entries_from_crawl_state(self, monkeypatch, tmp_path):
        state = [
            {
                "url": "https://example.com/apt-report",
                "status": "success",
                "timestamp": "2026-05-24T10:00:00",
                "stix_object_count": 7,
            }
        ]
        (tmp_path / "output").mkdir()
        (tmp_path / "output" / "crawl_state.json").write_text(json.dumps(state), encoding="utf-8")
        monkeypatch.setenv("TRACE_ROOT_PATH", str(tmp_path))
        resp = client.get("/collection/api/crawl-state")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["entries"]) == 1
        assert data["entries"][0]["url"] == "https://example.com/apt-report"

    def test_returns_empty_list_when_no_state_file(self, monkeypatch, tmp_path):
        monkeypatch.setenv("TRACE_ROOT_PATH", str(tmp_path))
        resp = client.get("/collection/api/crawl-state")
        assert resp.status_code == 200
        data = resp.json()
        assert data["entries"] == []


# ---------------------------------------------------------------------------
# CrawlResult dataclass
# ---------------------------------------------------------------------------


class TestCrawlResult:
    def test_defaults(self):
        from beacon.trace.runner import CrawlResult

        r = CrawlResult(success=True, stdout="ok", stderr="", return_code=0)
        assert r.stix_object_count == 0
        assert r.pir_relevance_score == 0.0

    def test_custom_fields(self):
        from beacon.trace.runner import CrawlResult

        r = CrawlResult(
            success=True,
            stdout="output",
            stderr="",
            return_code=0,
            stix_object_count=15,
            pir_relevance_score=0.92,
        )
        assert r.stix_object_count == 15
        assert r.pir_relevance_score == pytest.approx(0.92)


# ---------------------------------------------------------------------------
# run_crawl_single unit tests
# ---------------------------------------------------------------------------


class TestRunCrawlSingle:
    def test_empty_trace_root_returns_failure(self):
        from beacon.trace.runner import run_crawl_single

        result = run_crawl_single("https://example.com", "")
        assert not result.success
        assert "TRACE パスが設定されていません" in result.stderr

    def test_invalid_url_scheme_returns_failure(self, tmp_path):
        from beacon.trace.runner import run_crawl_single

        result = run_crawl_single("ftp://bad.example.com", str(tmp_path))
        assert not result.success
        assert "http/https" in result.stderr

    def test_nonexistent_trace_root_returns_failure(self):
        from beacon.trace.runner import run_crawl_single

        result = run_crawl_single("https://example.com", "/nonexistent/path/xyz")
        assert not result.success
        assert "does not exist" in result.stderr

    def test_success_result_on_zero_returncode(self, tmp_path):
        from beacon.trace.runner import run_crawl_single

        with patch("beacon.trace.runner.subprocess.run") as mock_run:
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdout = '{"stix_objects": 3}'
            mock_proc.stderr = ""
            mock_run.return_value = mock_proc

            result = run_crawl_single("https://example.com", str(tmp_path))

        assert result.success
        assert result.return_code == 0
        assert result.stix_object_count == 3

    def test_failure_result_on_nonzero_returncode(self, tmp_path):
        from beacon.trace.runner import run_crawl_single

        with patch("beacon.trace.runner.subprocess.run") as mock_run:
            mock_proc = MagicMock()
            mock_proc.returncode = 1
            mock_proc.stdout = ""
            mock_proc.stderr = "error message"
            mock_run.return_value = mock_proc

            result = run_crawl_single("https://example.com", str(tmp_path))

        assert not result.success
        assert result.stderr == "error message"

    def test_timeout_returns_failure(self, tmp_path):
        from beacon.trace.runner import run_crawl_single

        with patch("beacon.trace.runner.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="uv", timeout=300)
            result = run_crawl_single("https://example.com", str(tmp_path))

        assert not result.success
        assert "timed out" in result.stderr
        assert result.return_code == -1

    def test_oserror_returns_failure(self, tmp_path):
        from beacon.trace.runner import run_crawl_single

        with patch("beacon.trace.runner.subprocess.run") as mock_run:
            mock_run.side_effect = OSError("uv not found")
            result = run_crawl_single("https://example.com", str(tmp_path))

        assert not result.success
        assert "Failed to start" in result.stderr
        assert result.return_code == -1

    def test_subprocess_called_with_correct_args(self, tmp_path):
        from beacon.trace.runner import run_crawl_single

        with patch("beacon.trace.runner.subprocess.run") as mock_run:
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdout = ""
            mock_proc.stderr = ""
            mock_run.return_value = mock_proc

            run_crawl_single("https://example.com/report", str(tmp_path))

        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert "cmd.crawl_single" in cmd
        assert "--url" in cmd
        assert "https://example.com/report" in cmd
        assert call_args[1]["cwd"] == str(tmp_path)


# ---------------------------------------------------------------------------
# run_crawl_batch unit tests
# ---------------------------------------------------------------------------


class TestRunCrawlBatch:
    def test_empty_trace_root_returns_failure(self, tmp_path):
        from beacon.trace.runner import run_crawl_batch

        result = run_crawl_batch(str(tmp_path / "sources.yaml"), "")
        assert not result.success
        assert "TRACE パスが設定されていません" in result.stderr

    def test_nonexistent_trace_root_returns_failure(self, tmp_path):
        from beacon.trace.runner import run_crawl_batch

        result = run_crawl_batch(str(tmp_path / "sources.yaml"), "/nonexistent/xyz")
        assert not result.success
        assert "does not exist" in result.stderr

    def test_success_result(self, tmp_path):
        from beacon.trace.runner import run_crawl_batch

        yaml_path = str(tmp_path / "sources.yaml")
        with patch("beacon.trace.runner.subprocess.run") as mock_run:
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdout = '{"stix_objects": 12}'
            mock_proc.stderr = ""
            mock_run.return_value = mock_proc

            result = run_crawl_batch(yaml_path, str(tmp_path))

        assert result.success
        assert result.stix_object_count == 12

    def test_timeout_returns_failure(self, tmp_path):
        from beacon.trace.runner import run_crawl_batch

        with patch("beacon.trace.runner.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="uv", timeout=300)
            result = run_crawl_batch(str(tmp_path / "sources.yaml"), str(tmp_path))

        assert not result.success
        assert "timed out" in result.stderr

    def test_subprocess_called_with_correct_args(self, tmp_path):
        from beacon.trace.runner import run_crawl_batch

        yaml_path = str(tmp_path / "sources.yaml")
        with patch("beacon.trace.runner.subprocess.run") as mock_run:
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdout = ""
            mock_proc.stderr = ""
            mock_run.return_value = mock_proc

            run_crawl_batch(yaml_path, str(tmp_path))

        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert "cmd.crawl_batch" in cmd
        assert "--sources" in cmd
        assert yaml_path in cmd
        assert call_args[1]["cwd"] == str(tmp_path)


# ---------------------------------------------------------------------------
# load_crawl_state unit tests
# ---------------------------------------------------------------------------


class TestLoadCrawlState:
    def test_empty_trace_root_returns_empty(self):
        from beacon.trace.runner import load_crawl_state

        assert load_crawl_state("") == []

    def test_nonexistent_root_returns_empty(self):
        from beacon.trace.runner import load_crawl_state

        assert load_crawl_state("/nonexistent/path/xyz") == []

    def test_reads_from_output_subdir(self, tmp_path):
        from beacon.trace.runner import load_crawl_state

        state = [{"url": "https://a.com", "status": "success"}]
        (tmp_path / "output").mkdir()
        (tmp_path / "output" / "crawl_state.json").write_text(json.dumps(state), encoding="utf-8")
        result = load_crawl_state(str(tmp_path))
        assert len(result) == 1
        assert result[0]["url"] == "https://a.com"

    def test_reads_from_root_when_no_output_subdir(self, tmp_path):
        from beacon.trace.runner import load_crawl_state

        state = [{"url": "https://b.com", "status": "fail"}]
        (tmp_path / "crawl_state.json").write_text(json.dumps(state), encoding="utf-8")
        result = load_crawl_state(str(tmp_path))
        assert len(result) == 1

    def test_invalid_json_returns_empty(self, tmp_path):
        from beacon.trace.runner import load_crawl_state

        (tmp_path / "crawl_state.json").write_text("not valid json", encoding="utf-8")
        result = load_crawl_state(str(tmp_path))
        assert result == []

    def test_dict_with_entries_key(self, tmp_path):
        from beacon.trace.runner import load_crawl_state

        state = {"entries": [{"url": "https://c.com"}]}
        (tmp_path / "crawl_state.json").write_text(json.dumps(state), encoding="utf-8")
        result = load_crawl_state(str(tmp_path))
        assert len(result) == 1

    def test_missing_file_returns_empty(self, tmp_path):
        from beacon.trace.runner import load_crawl_state

        assert load_crawl_state(str(tmp_path)) == []


# ---------------------------------------------------------------------------
# _validate_url tests
# ---------------------------------------------------------------------------


class TestValidateUrl:
    def test_http_ok(self):
        from beacon.trace.runner import _validate_url

        assert _validate_url("http://example.com") is True

    def test_https_ok(self):
        from beacon.trace.runner import _validate_url

        assert _validate_url("https://example.com/report?id=1") is True

    def test_ftp_rejected(self):
        from beacon.trace.runner import _validate_url

        assert _validate_url("ftp://example.com") is False

    def test_empty_rejected(self):
        from beacon.trace.runner import _validate_url

        assert _validate_url("") is False

    def test_no_netloc_rejected(self):
        from beacon.trace.runner import _validate_url

        assert _validate_url("https://") is False

    def test_javascript_scheme_rejected(self):
        from beacon.trace.runner import _validate_url

        assert _validate_url("javascript:alert(1)") is False


# ---------------------------------------------------------------------------
# _parse_stdout_metadata tests
# ---------------------------------------------------------------------------


class TestParseStdoutMetadata:
    def test_parses_stix_objects_key(self):
        from beacon.trace.runner import _parse_stdout_metadata

        stdout = '{"stix_objects": 7, "pir_relevance": 0.75}'
        count, relevance = _parse_stdout_metadata(stdout)
        assert count == 7
        assert relevance == pytest.approx(0.75)

    def test_parses_stix_count_key(self):
        from beacon.trace.runner import _parse_stdout_metadata

        stdout = '{"stix_count": 3}'
        count, _ = _parse_stdout_metadata(stdout)
        assert count == 3

    def test_parses_relevance_score_key(self):
        from beacon.trace.runner import _parse_stdout_metadata

        stdout = '{"relevance_score": 0.5}'
        _, relevance = _parse_stdout_metadata(stdout)
        assert relevance == pytest.approx(0.5)

    def test_non_json_lines_skipped(self):
        from beacon.trace.runner import _parse_stdout_metadata

        stdout = 'Starting crawl...\n{"stix_objects": 2}\nDone.'
        count, _ = _parse_stdout_metadata(stdout)
        assert count == 2

    def test_empty_stdout_returns_zeros(self):
        from beacon.trace.runner import _parse_stdout_metadata

        count, relevance = _parse_stdout_metadata("")
        assert count == 0
        assert relevance == 0.0
