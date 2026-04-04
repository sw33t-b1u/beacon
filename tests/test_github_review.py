"""Tests for src/beacon/review/github.py and cmd/submit_for_review.py."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from beacon.review.github import (
    GHEClient,
    build_issue_body,
    submit_pirs_for_review,
)
from tests.conftest import load_cmd_module

_submit_mod = load_cmd_module("submit_for_review")

SAMPLE_PIR = {
    "pir_id": "PIR-2026-001",
    "intelligence_level": "operational",
    "valid_from": "2026-04-04",
    "valid_until": "2026-07-04",
    "description": "APT groups targeting manufacturing IP.",
    "rationale": "Likelihood=3, Impact=4 — 業種×地域マッチ: China",
    "threat_actor_tags": ["apt-china", "espionage"],
    "asset_weight_rules": [
        {"tag": "plm", "criticality_multiplier": 2.5},
        {"tag": "ot", "criticality_multiplier": 2.0},
    ],
    "collection_focus": ["Monitor T1190 exploitation", "Track APT10 IOCs"],
    "risk_score": {"likelihood": 3, "impact": 4, "composite": 12},
}

SAMPLE_PIR_2 = {
    **SAMPLE_PIR,
    "pir_id": "PIR-2026-002",
    "intelligence_level": "strategic",
}


class TestGHEClientInit:
    def test_raises_if_token_missing(self):
        with pytest.raises(ValueError, match="GHE_TOKEN"):
            GHEClient(token="", repo="owner/repo")

    def test_raises_if_repo_missing(self):
        with pytest.raises(ValueError, match="GHE_REPO"):
            GHEClient(token="tok123", repo="")

    def test_init_success(self):
        client = GHEClient(token="tok123", repo="owner/repo")
        assert client._repo == "owner/repo"


class TestGHEClientCreateIssue:
    def _make_client(self):
        return GHEClient(token="tok123", repo="owner/repo")

    def test_posts_to_correct_endpoint(self):
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"number": 42, "html_url": "https://github.com/i/42"}
        mock_resp.raise_for_status.return_value = None

        with patch("beacon.review.github.httpx") as mock_httpx:
            mock_httpx.post.return_value = mock_resp
            result = client.create_issue("Title", "Body")

        mock_httpx.post.assert_called_once()
        call_kwargs = mock_httpx.post.call_args
        assert "/repos/owner/repo/issues" in call_kwargs[0][0]
        assert result["number"] == 42

    def test_includes_authorization_header(self):
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"number": 1, "html_url": "https://example.com"}
        mock_resp.raise_for_status.return_value = None

        with patch("beacon.review.github.httpx") as mock_httpx:
            mock_httpx.post.return_value = mock_resp
            client.create_issue("Title", "Body")

        headers = mock_httpx.post.call_args[1]["headers"]
        assert "Bearer tok123" in headers["Authorization"]


class TestBuildIssueBody:
    def test_contains_pir_id_level(self):
        body = build_issue_body(SAMPLE_PIR)
        # pir_id in title (not body) — but description and rationale must be in body
        assert "APT groups targeting manufacturing IP." in body

    def test_contains_risk_score(self):
        body = build_issue_body(SAMPLE_PIR)
        assert "L=3, I=4, Composite=12" in body

    def test_contains_threat_tags(self):
        body = build_issue_body(SAMPLE_PIR)
        assert "`apt-china`" in body
        assert "`espionage`" in body

    def test_contains_asset_rules(self):
        body = build_issue_body(SAMPLE_PIR)
        assert "plm" in body
        assert "2.5" in body

    def test_contains_collection_focus(self):
        body = build_issue_body(SAMPLE_PIR)
        assert "Monitor T1190 exploitation" in body

    def test_contains_review_checklist(self):
        body = build_issue_body(SAMPLE_PIR)
        assert "- [ ] Approved for SAGE deployment" in body

    def test_valid_dates_shown(self):
        body = build_issue_body(SAMPLE_PIR)
        assert "2026-04-04" in body
        assert "2026-07-04" in body


class TestSubmitPirsForReview:
    def _make_client(self):
        return GHEClient(token="tok123", repo="owner/repo")

    def _mock_issue_response(self, number: int) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "number": number,
            "html_url": f"https://github.com/owner/repo/issues/{number}",
        }
        mock_resp.raise_for_status.return_value = None
        return mock_resp

    def test_single_pir_creates_one_issue(self):
        client = self._make_client()
        with patch("beacon.review.github.httpx") as mock_httpx:
            mock_httpx.post.return_value = self._mock_issue_response(10)
            results = submit_pirs_for_review([SAMPLE_PIR], client)

        assert len(results) == 1
        assert results[0].pir_id == "PIR-2026-001"
        assert results[0].issue_number == 10

    def test_multiple_pirs_create_multiple_issues(self):
        client = self._make_client()
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.json.return_value = {
                "number": call_count,
                "html_url": f"https://github.com/i/{call_count}",
            }
            mock_resp.raise_for_status.return_value = None
            return mock_resp

        with patch("beacon.review.github.httpx") as mock_httpx:
            mock_httpx.post.side_effect = side_effect
            results = submit_pirs_for_review([SAMPLE_PIR, SAMPLE_PIR_2], client)

        assert len(results) == 2
        pir_ids = {r.pir_id for r in results}
        assert "PIR-2026-001" in pir_ids
        assert "PIR-2026-002" in pir_ids

    def test_collection_plan_attached_as_comment(self):
        client = self._make_client()
        issue_resp = MagicMock()
        issue_resp.json.return_value = {"number": 5, "html_url": "https://github.com/i/5"}
        issue_resp.raise_for_status.return_value = None
        comment_resp = MagicMock()
        comment_resp.raise_for_status.return_value = None

        with patch("beacon.review.github.httpx") as mock_httpx:
            mock_httpx.post.side_effect = [issue_resp, comment_resp]
            submit_pirs_for_review([SAMPLE_PIR], client, collection_plan_text="plan")

        # Should have been called twice: once for issue, once for comment
        assert mock_httpx.post.call_count == 2


class TestSubmitForReviewCLI:
    def test_missing_pir_file_returns_error(self, tmp_path):
        rc = _submit_mod.main(["--pir", str(tmp_path / "nonexistent.json")])
        assert rc == 1

    def test_missing_token_returns_error(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GHE_TOKEN", raising=False)
        monkeypatch.delenv("GHE_REPO", raising=False)

        pir_file = tmp_path / "pir_output.json"
        pir_file.write_text(json.dumps([SAMPLE_PIR]), encoding="utf-8")

        rc = _submit_mod.main(["--pir", str(pir_file)])
        assert rc == 1

    def test_success_prints_issue_url(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("GHE_TOKEN", "tok123")
        monkeypatch.setenv("GHE_REPO", "owner/repo")

        pir_file = tmp_path / "pir_output.json"
        pir_file.write_text(json.dumps([SAMPLE_PIR]), encoding="utf-8")

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "number": 99,
            "html_url": "https://github.com/owner/repo/issues/99",
        }
        mock_resp.raise_for_status.return_value = None

        with patch("beacon.review.github.httpx") as mock_httpx:
            mock_httpx.post.return_value = mock_resp
            rc = _submit_mod.main(["--pir", str(pir_file)])

        assert rc == 0
        captured = capsys.readouterr()
        assert "#99" in captured.out
        assert "PIR-2026-001" in captured.out
