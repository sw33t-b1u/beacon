"""Tests for src/beacon/sage/client.py — get_recent_incidents (Initiative G Phase 6).

Verifies URL construction, query-param + Bearer-header propagation, response
parsing (both `{incidents: [...]}` and bare-list shapes), and raise-on-error
semantics (fail-loud, caller handles fail-soft).
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import httpx
import pytest

from beacon.sage.client import SageAPIClient


def _ok_response(payload: object) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


class TestGetRecentIncidentsURLConstruction:
    def test_url_includes_api_incidents_path(self):
        client = SageAPIClient("http://localhost:8000")
        with patch("beacon.sage.client.httpx") as mock_httpx:
            mock_httpx.get.return_value = _ok_response({"incidents": []})
            client.get_recent_incidents(date(2026, 1, 1), date(2026, 5, 24))
        called_url = mock_httpx.get.call_args.args[0]
        assert called_url == "http://localhost:8000/api/incidents"

    def test_trailing_slash_base_url_normalised(self):
        client = SageAPIClient("http://localhost:8000/")
        with patch("beacon.sage.client.httpx") as mock_httpx:
            mock_httpx.get.return_value = _ok_response({"incidents": []})
            client.get_recent_incidents(date(2026, 1, 1), date(2026, 5, 24))
        assert mock_httpx.get.call_args.args[0] == "http://localhost:8000/api/incidents"

    def test_since_until_in_params(self):
        client = SageAPIClient("http://localhost:8000")
        with patch("beacon.sage.client.httpx") as mock_httpx:
            mock_httpx.get.return_value = _ok_response({"incidents": []})
            client.get_recent_incidents(date(2025, 5, 24), date(2026, 5, 24))
        params = mock_httpx.get.call_args.kwargs["params"]
        assert params["since"] == "2025-05-24"
        assert params["until"] == "2026-05-24"

    def test_default_limit_50(self):
        client = SageAPIClient("http://localhost:8000")
        with patch("beacon.sage.client.httpx") as mock_httpx:
            mock_httpx.get.return_value = _ok_response({"incidents": []})
            client.get_recent_incidents(date(2026, 1, 1), date(2026, 5, 24))
        assert mock_httpx.get.call_args.kwargs["params"]["limit"] == 50

    def test_custom_limit_propagated(self):
        client = SageAPIClient("http://localhost:8000")
        with patch("beacon.sage.client.httpx") as mock_httpx:
            mock_httpx.get.return_value = _ok_response({"incidents": []})
            client.get_recent_incidents(date(2026, 1, 1), date(2026, 5, 24), limit=10)
        assert mock_httpx.get.call_args.kwargs["params"]["limit"] == 10

    def test_actor_stix_id_filter_omitted_when_none(self):
        client = SageAPIClient("http://localhost:8000")
        with patch("beacon.sage.client.httpx") as mock_httpx:
            mock_httpx.get.return_value = _ok_response({"incidents": []})
            client.get_recent_incidents(date(2026, 1, 1), date(2026, 5, 24))
        assert "actor_stix_id" not in mock_httpx.get.call_args.kwargs["params"]

    def test_actor_stix_id_filter_propagated(self):
        client = SageAPIClient("http://localhost:8000")
        with patch("beacon.sage.client.httpx") as mock_httpx:
            mock_httpx.get.return_value = _ok_response({"incidents": []})
            client.get_recent_incidents(
                date(2026, 1, 1),
                date(2026, 5, 24),
                actor_stix_id="intrusion-set--abc-123",
            )
        assert (
            mock_httpx.get.call_args.kwargs["params"]["actor_stix_id"] == "intrusion-set--abc-123"
        )


class TestGetRecentIncidentsAuth:
    def test_no_bearer_header_when_token_unset(self):
        client = SageAPIClient("http://localhost:8000", bearer_token="")
        with patch("beacon.sage.client.httpx") as mock_httpx:
            mock_httpx.get.return_value = _ok_response({"incidents": []})
            client.get_recent_incidents(date(2026, 1, 1), date(2026, 5, 24))
        headers = mock_httpx.get.call_args.kwargs["headers"]
        assert "Authorization" not in headers

    def test_bearer_header_sent_when_token_set(self):
        # HTTPS required: tokens are only attached over https:// (BEACON 3.0.2).
        client = SageAPIClient("https://localhost:8000", bearer_token="abc123")
        with patch("beacon.sage.client.httpx") as mock_httpx:
            mock_httpx.get.return_value = _ok_response({"incidents": []})
            client.get_recent_incidents(date(2026, 1, 1), date(2026, 5, 24))
        headers = mock_httpx.get.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer abc123"

    def test_bearer_sourced_from_env(self, monkeypatch):
        monkeypatch.setenv("SAGE_API_AUTH_TOKEN", "env-token")
        # HTTPS required: tokens are only attached over https:// (BEACON 3.0.2).
        client = SageAPIClient("https://localhost:8000")
        with patch("beacon.sage.client.httpx") as mock_httpx:
            mock_httpx.get.return_value = _ok_response({"incidents": []})
            client.get_recent_incidents(date(2026, 1, 1), date(2026, 5, 24))
        headers = mock_httpx.get.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer env-token"

    def test_explicit_empty_token_overrides_env(self, monkeypatch):
        monkeypatch.setenv("SAGE_API_AUTH_TOKEN", "env-token")
        client = SageAPIClient("http://localhost:8000", bearer_token="")
        with patch("beacon.sage.client.httpx") as mock_httpx:
            mock_httpx.get.return_value = _ok_response({"incidents": []})
            client.get_recent_incidents(date(2026, 1, 1), date(2026, 5, 24))
        headers = mock_httpx.get.call_args.kwargs["headers"]
        assert "Authorization" not in headers


class TestGetRecentIncidentsResponseParsing:
    def test_dict_with_incidents_key(self):
        client = SageAPIClient("http://localhost:8000")
        sample = [{"incident_stix_id": "incident--1"}]
        with patch("beacon.sage.client.httpx") as mock_httpx:
            mock_httpx.get.return_value = _ok_response({"incidents": sample, "count": 1})
            result = client.get_recent_incidents(date(2026, 1, 1), date(2026, 5, 24))
        assert result == sample

    def test_bare_list_response(self):
        client = SageAPIClient("http://localhost:8000")
        sample = [{"incident_stix_id": "incident--1"}, {"incident_stix_id": "incident--2"}]
        with patch("beacon.sage.client.httpx") as mock_httpx:
            mock_httpx.get.return_value = _ok_response(sample)
            result = client.get_recent_incidents(date(2026, 1, 1), date(2026, 5, 24))
        assert result == sample

    def test_empty_incidents_returns_empty_list(self):
        client = SageAPIClient("http://localhost:8000")
        with patch("beacon.sage.client.httpx") as mock_httpx:
            mock_httpx.get.return_value = _ok_response({"incidents": [], "count": 0})
            result = client.get_recent_incidents(date(2026, 1, 1), date(2026, 5, 24))
        assert result == []

    def test_malformed_response_returns_empty(self):
        # Neither dict-with-incidents nor list → defensive empty.
        client = SageAPIClient("http://localhost:8000")
        with patch("beacon.sage.client.httpx") as mock_httpx:
            mock_httpx.get.return_value = _ok_response(123)
            result = client.get_recent_incidents(date(2026, 1, 1), date(2026, 5, 24))
        assert result == []


class TestGetRecentIncidentsRaisesOnError:
    def test_timeout_propagates(self):
        client = SageAPIClient("http://localhost:8000")
        with patch("beacon.sage.client.httpx") as mock_httpx:
            mock_httpx.TimeoutException = httpx.TimeoutException
            mock_httpx.HTTPError = httpx.HTTPError
            mock_httpx.get.side_effect = httpx.TimeoutException("timed out")
            with pytest.raises(httpx.TimeoutException):
                client.get_recent_incidents(date(2026, 1, 1), date(2026, 5, 24))

    def test_http_error_propagates(self):
        client = SageAPIClient("http://localhost:8000")
        bad_resp = MagicMock()
        bad_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock()
        )
        with patch("beacon.sage.client.httpx") as mock_httpx:
            mock_httpx.HTTPError = httpx.HTTPError
            mock_httpx.TimeoutException = httpx.TimeoutException
            mock_httpx.get.return_value = bad_resp
            with pytest.raises(httpx.HTTPError):
                client.get_recent_incidents(date(2026, 1, 1), date(2026, 5, 24))
