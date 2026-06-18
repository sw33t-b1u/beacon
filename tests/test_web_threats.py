"""Tests for Threats tab routes in beacon/web/app.py (Initiative I Phase 3)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from beacon.web.app import app

client = TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# /threats — HTML page
# ---------------------------------------------------------------------------


class TestThreatsPage:
    def test_get_returns_200(self):
        resp = client.get("/threats")
        assert resp.status_code == 200

    def test_get_shows_offline_message_when_sage_not_configured(self, monkeypatch):
        monkeypatch.setenv("SAGE_API_URL", "")
        resp = client.get("/threats")
        assert resp.status_code == 200
        assert "SAGE" in resp.text
        assert "未接続" in resp.text

    def test_get_shows_ui_when_sage_configured(self, monkeypatch):
        monkeypatch.setenv("SAGE_API_URL", "http://sage:8080")
        resp = client.get("/threats")
        assert resp.status_code == 200
        # Must show view-switching elements
        assert "Actor" in resp.text
        assert "Asset" in resp.text

    def test_get_has_time_range_buttons(self, monkeypatch):
        monkeypatch.setenv("SAGE_API_URL", "http://sage:8080")
        resp = client.get("/threats")
        assert resp.status_code == 200
        assert "1M" in resp.text
        assert "3M" in resp.text
        assert "6M" in resp.text
        assert "1Y" in resp.text

    def test_active_tab_is_threats(self, monkeypatch):
        monkeypatch.setenv("SAGE_API_URL", "http://sage:8080")
        resp = client.get("/threats")
        # base.html marks the active tab with class="active"
        assert "threats" in resp.text


# ---------------------------------------------------------------------------
# /threats/api/actors
# ---------------------------------------------------------------------------


class TestThreatsApiActors:
    def test_returns_empty_list_when_sage_not_configured(self, monkeypatch):
        monkeypatch.setenv("SAGE_API_URL", "")
        resp = client.get("/threats/api/actors?name=APT")
        assert resp.status_code == 200
        data = resp.json()
        assert data["actors"] == []
        assert "error" in data

    def test_returns_actors_from_sage(self, monkeypatch):
        monkeypatch.setenv("SAGE_API_URL", "http://sage:8080")
        fake_actors = [
            {
                "stix_id": "intrusion-set--apt28",
                "name": "APT28",
                "aliases": ["Fancy Bear"],
                "sophistication_level": "advanced",
                "last_seen": "2026-01-15",
            },
        ]
        mock_client = MagicMock()
        mock_client.search_actors.return_value = fake_actors

        with patch("beacon.sage.client.SageAPIClient", return_value=mock_client):
            resp = client.get("/threats/api/actors?name=APT28")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["actors"]) == 1
        assert data["actors"][0]["name"] == "APT28"

    def test_empty_name_still_calls_search(self, monkeypatch):
        monkeypatch.setenv("SAGE_API_URL", "http://sage:8080")
        mock_client = MagicMock()
        mock_client.search_actors.return_value = []

        with patch("beacon.sage.client.SageAPIClient", return_value=mock_client):
            resp = client.get("/threats/api/actors")

        assert resp.status_code == 200
        data = resp.json()
        assert data["actors"] == []
        mock_client.search_actors.assert_called_once_with("")

    def test_sage_returns_empty_list_on_error(self, monkeypatch):
        """search_actors is fail-soft — should return empty list, not 500."""
        monkeypatch.setenv("SAGE_API_URL", "http://sage:8080")
        mock_client = MagicMock()
        mock_client.search_actors.return_value = []  # client already ate the error

        with patch("beacon.sage.client.SageAPIClient", return_value=mock_client):
            resp = client.get("/threats/api/actors?name=Unknown")

        assert resp.status_code == 200
        assert resp.json()["actors"] == []


# ---------------------------------------------------------------------------
# /threats/api/actor-ttps
# ---------------------------------------------------------------------------


class TestThreatsApiActorTTPs:
    def test_returns_error_when_sage_not_configured(self, monkeypatch):
        monkeypatch.setenv("SAGE_API_URL", "")
        resp = client.get("/threats/api/actor-ttps?actor_id=apt28")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ttps"] == []
        assert "error" in data

    def test_returns_ttps_from_sage(self, monkeypatch):
        monkeypatch.setenv("SAGE_API_URL", "http://sage:8080")
        fake_ttps = [
            {
                "ttp_id": "T1190",
                "name": "Exploit Public-Facing Application",
                "phase": "initial-access",
                "last_seen": "2026-02-01",
            },
        ]
        mock_client = MagicMock()
        mock_client.get_actor_ttps.return_value = fake_ttps

        with patch("beacon.sage.client.SageAPIClient", return_value=mock_client):
            url = "/threats/api/actor-ttps?actor_id=apt28&since=2026-01-01&until=2026-06-01"
            resp = client.get(url)

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["ttps"]) == 1
        assert data["ttps"][0]["ttp_id"] == "T1190"
        mock_client.get_actor_ttps.assert_called_once_with(
            "apt28", since="2026-01-01", until="2026-06-01"
        )

    def test_since_until_optional(self, monkeypatch):
        monkeypatch.setenv("SAGE_API_URL", "http://sage:8080")
        mock_client = MagicMock()
        mock_client.get_actor_ttps.return_value = []

        with patch("beacon.sage.client.SageAPIClient", return_value=mock_client):
            resp = client.get("/threats/api/actor-ttps?actor_id=apt28")

        assert resp.status_code == 200
        mock_client.get_actor_ttps.assert_called_once_with("apt28", since=None, until=None)


# ---------------------------------------------------------------------------
# /threats/api/threat-summary
# ---------------------------------------------------------------------------


class TestThreatsApiThreatSummary:
    def test_returns_error_when_sage_not_configured(self, monkeypatch):
        monkeypatch.setenv("SAGE_API_URL", "")
        resp = client.get("/threats/api/threat-summary?asset=asset-001")
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data

    def test_returns_summary_from_sage(self, monkeypatch):
        monkeypatch.setenv("SAGE_API_URL", "http://sage:8080")
        fake_summary = {
            "attack_paths": [{"path": "A→B→C"}],
            "choke_points": [{"name": "Firewall-1"}],
            "vulnerabilities": [{"cve_id": "CVE-2026-1234", "description": "Heap overflow"}],
            "incidents": [{"incident_id": "INC-2026-01", "name": "Breach attempt"}],
        }
        mock_client = MagicMock()
        mock_client.get_threat_summary.return_value = fake_summary

        with patch("beacon.sage.client.SageAPIClient", return_value=mock_client):
            url = "/threats/api/threat-summary?asset=asset-001&since=2026-01-01&until=2026-06-01"
            resp = client.get(url)

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["attack_paths"]) == 1
        assert data["choke_points"][0]["name"] == "Firewall-1"
        mock_client.get_threat_summary.assert_called_once_with(
            "asset-001", since="2026-01-01", until="2026-06-01"
        )

    def test_since_until_optional(self, monkeypatch):
        monkeypatch.setenv("SAGE_API_URL", "http://sage:8080")
        mock_client = MagicMock()
        mock_client.get_threat_summary.return_value = {}

        with patch("beacon.sage.client.SageAPIClient", return_value=mock_client):
            resp = client.get("/threats/api/threat-summary?asset=asset-002")

        assert resp.status_code == 200
        mock_client.get_threat_summary.assert_called_once_with("asset-002", since=None, until=None)

    def test_empty_summary_returns_empty_dict(self, monkeypatch):
        monkeypatch.setenv("SAGE_API_URL", "http://sage:8080")
        mock_client = MagicMock()
        mock_client.get_threat_summary.return_value = {}

        with patch("beacon.sage.client.SageAPIClient", return_value=mock_client):
            resp = client.get("/threats/api/threat-summary?asset=unknown-asset")

        assert resp.status_code == 200
        assert resp.json() == {}


# ---------------------------------------------------------------------------
# SageAPIClient — new Threats-tab methods
# ---------------------------------------------------------------------------


class TestSageClientSearchActors:
    def _make_client(self):
        from beacon.sage.client import SageAPIClient  # noqa: PLC0415

        return SageAPIClient("http://localhost:8000")

    def test_returns_actors_list(self):
        import httpx2 as httpx  # noqa: PLC0415

        client_obj = self._make_client()
        fake_data = {"actors": [{"stix_id": "intrusion-set--apt28", "name": "APT28"}]}
        mock_resp = MagicMock()
        mock_resp.json.return_value = fake_data
        mock_resp.raise_for_status.return_value = None

        with patch("beacon.sage.client.httpx") as mock_httpx:
            mock_httpx.get.return_value = mock_resp
            mock_httpx.TimeoutException = httpx.TimeoutException
            mock_httpx.HTTPError = httpx.HTTPError
            result = client_obj.search_actors("APT28")

        assert len(result) == 1
        assert result[0]["name"] == "APT28"

    def test_timeout_returns_empty_list(self):
        import httpx2 as httpx  # noqa: PLC0415

        client_obj = self._make_client()
        with patch("beacon.sage.client.httpx") as mock_httpx:
            mock_httpx.TimeoutException = httpx.TimeoutException
            mock_httpx.HTTPError = httpx.HTTPError
            mock_httpx.get.side_effect = httpx.TimeoutException("timed out")
            result = client_obj.search_actors("APT")

        assert result == []

    def test_http_error_returns_empty_list(self):
        import httpx2 as httpx  # noqa: PLC0415

        client_obj = self._make_client()
        with patch("beacon.sage.client.httpx") as mock_httpx:
            mock_httpx.TimeoutException = httpx.TimeoutException
            mock_httpx.HTTPError = httpx.HTTPError
            mock_httpx.get.side_effect = httpx.HTTPStatusError(
                "404", request=MagicMock(), response=MagicMock()
            )
            result = client_obj.search_actors("APT")

        assert result == []

    def test_bare_list_response_accepted(self):
        import httpx2 as httpx  # noqa: PLC0415

        client_obj = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = [{"stix_id": "intrusion-set--lazarus", "name": "Lazarus"}]
        mock_resp.raise_for_status.return_value = None

        with patch("beacon.sage.client.httpx") as mock_httpx:
            mock_httpx.get.return_value = mock_resp
            mock_httpx.TimeoutException = httpx.TimeoutException
            mock_httpx.HTTPError = httpx.HTTPError
            result = client_obj.search_actors("Lazarus")

        assert len(result) == 1
        assert result[0]["name"] == "Lazarus"


class TestSageClientGetActorTTPs:
    def _make_client(self):
        from beacon.sage.client import SageAPIClient  # noqa: PLC0415

        return SageAPIClient("http://localhost:8000")

    def test_returns_ttps_from_dict_response(self):
        import httpx2 as httpx  # noqa: PLC0415

        client_obj = self._make_client()
        fake_data = {"ttps": [{"ttp_id": "T1190", "name": "Exploit Public-Facing App"}]}
        mock_resp = MagicMock()
        mock_resp.json.return_value = fake_data
        mock_resp.raise_for_status.return_value = None

        with patch("beacon.sage.client.httpx") as mock_httpx:
            mock_httpx.get.return_value = mock_resp
            mock_httpx.TimeoutException = httpx.TimeoutException
            mock_httpx.HTTPError = httpx.HTTPError
            result = client_obj.get_actor_ttps("apt28", since="2026-01-01")

        assert len(result) == 1
        assert result[0]["ttp_id"] == "T1190"

    def test_timeout_returns_empty_list(self):
        import httpx2 as httpx  # noqa: PLC0415

        client_obj = self._make_client()
        with patch("beacon.sage.client.httpx") as mock_httpx:
            mock_httpx.TimeoutException = httpx.TimeoutException
            mock_httpx.HTTPError = httpx.HTTPError
            mock_httpx.get.side_effect = httpx.TimeoutException("slow")
            result = client_obj.get_actor_ttps("apt28")

        assert result == []

    def test_http_error_returns_empty_list(self):
        import httpx2 as httpx  # noqa: PLC0415

        client_obj = self._make_client()
        with patch("beacon.sage.client.httpx") as mock_httpx:
            mock_httpx.TimeoutException = httpx.TimeoutException
            mock_httpx.HTTPError = httpx.HTTPError
            mock_httpx.get.side_effect = httpx.HTTPStatusError(
                "500", request=MagicMock(), response=MagicMock()
            )
            result = client_obj.get_actor_ttps("apt28")

        assert result == []

    def test_params_passed_correctly(self):
        import httpx2 as httpx  # noqa: PLC0415

        client_obj = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ttps": []}
        mock_resp.raise_for_status.return_value = None

        with patch("beacon.sage.client.httpx") as mock_httpx:
            mock_httpx.get.return_value = mock_resp
            mock_httpx.TimeoutException = httpx.TimeoutException
            mock_httpx.HTTPError = httpx.HTTPError
            client_obj.get_actor_ttps("actor-x", since="2026-01-01", until="2026-06-01")

        call_kwargs = mock_httpx.get.call_args
        params = call_kwargs[1]["params"]
        assert params["actor_id"] == "actor-x"
        assert params["since"] == "2026-01-01"
        assert params["until"] == "2026-06-01"

    def test_none_since_until_not_sent(self):
        import httpx2 as httpx  # noqa: PLC0415

        client_obj = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ttps": []}
        mock_resp.raise_for_status.return_value = None

        with patch("beacon.sage.client.httpx") as mock_httpx:
            mock_httpx.get.return_value = mock_resp
            mock_httpx.TimeoutException = httpx.TimeoutException
            mock_httpx.HTTPError = httpx.HTTPError
            client_obj.get_actor_ttps("actor-x")

        call_kwargs = mock_httpx.get.call_args
        params = call_kwargs[1]["params"]
        assert "since" not in params
        assert "until" not in params


class TestSageClientGetThreatSummary:
    def _make_client(self):
        from beacon.sage.client import SageAPIClient  # noqa: PLC0415

        return SageAPIClient("http://localhost:8000")

    def test_returns_summary_dict(self):
        import httpx2 as httpx  # noqa: PLC0415

        client_obj = self._make_client()
        fake_data = {
            "attack_paths": [],
            "choke_points": [{"name": "FW-1"}],
            "vulnerabilities": [],
            "incidents": [],
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = fake_data
        mock_resp.raise_for_status.return_value = None

        with patch("beacon.sage.client.httpx") as mock_httpx:
            mock_httpx.get.return_value = mock_resp
            mock_httpx.TimeoutException = httpx.TimeoutException
            mock_httpx.HTTPError = httpx.HTTPError
            result = client_obj.get_threat_summary("asset-001")

        assert result["choke_points"][0]["name"] == "FW-1"

    def test_timeout_returns_empty_dict(self):
        import httpx2 as httpx  # noqa: PLC0415

        client_obj = self._make_client()
        with patch("beacon.sage.client.httpx") as mock_httpx:
            mock_httpx.TimeoutException = httpx.TimeoutException
            mock_httpx.HTTPError = httpx.HTTPError
            mock_httpx.get.side_effect = httpx.TimeoutException("slow")
            result = client_obj.get_threat_summary("asset-001")

        assert result == {}

    def test_http_error_returns_empty_dict(self):
        import httpx2 as httpx  # noqa: PLC0415

        client_obj = self._make_client()
        with patch("beacon.sage.client.httpx") as mock_httpx:
            mock_httpx.TimeoutException = httpx.TimeoutException
            mock_httpx.HTTPError = httpx.HTTPError
            mock_httpx.get.side_effect = httpx.HTTPStatusError(
                "503", request=MagicMock(), response=MagicMock()
            )
            result = client_obj.get_threat_summary("asset-001")

        assert result == {}

    def test_non_dict_response_returns_empty_dict(self):
        import httpx2 as httpx  # noqa: PLC0415

        client_obj = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = ["unexpected", "list"]
        mock_resp.raise_for_status.return_value = None

        with patch("beacon.sage.client.httpx") as mock_httpx:
            mock_httpx.get.return_value = mock_resp
            mock_httpx.TimeoutException = httpx.TimeoutException
            mock_httpx.HTTPError = httpx.HTTPError
            result = client_obj.get_threat_summary("asset-001")

        assert result == {}

    def test_params_passed_correctly(self):
        import httpx2 as httpx  # noqa: PLC0415

        client_obj = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {}
        mock_resp.raise_for_status.return_value = None

        with patch("beacon.sage.client.httpx") as mock_httpx:
            mock_httpx.get.return_value = mock_resp
            mock_httpx.TimeoutException = httpx.TimeoutException
            mock_httpx.HTTPError = httpx.HTTPError
            client_obj.get_threat_summary("asset-007", since="2026-01-01", until="2026-03-31")

        call_kwargs = mock_httpx.get.call_args
        params = call_kwargs[1]["params"]
        assert params["asset"] == "asset-007"
        assert params["since"] == "2026-01-01"
        assert params["until"] == "2026-03-31"
