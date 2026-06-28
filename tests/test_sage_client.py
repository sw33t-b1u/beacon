"""Tests for src/beacon/sage/client.py and risk_scorer use_sage integration."""

from __future__ import annotations

import base64
import json
import time
from unittest.mock import MagicMock, patch

from beacon.sage.client import SageAPIClient


def _fake_jwt(exp: float) -> str:
    """Build a dummy JWT whose middle segment encodes ``{"exp": exp}``.

    The signature segment is a non-verifying placeholder — the client only
    base64url-decodes the payload segment to schedule cache expiry.
    """

    def _seg(obj: dict) -> str:
        raw = json.dumps(obj).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    header = _seg({"alg": "RS256", "typ": "JWT"})
    payload = _seg({"exp": exp})
    return f"{header}.{payload}.dummysignature"


class TestSageAPIClientObservationCount:
    def _make_client(self):
        return SageAPIClient("http://localhost:8000")

    def _mock_response(self, actors: list[dict]) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"actors": actors}
        mock_resp.raise_for_status.return_value = None
        return mock_resp

    def test_matching_actor_returns_count(self):
        client = self._make_client()
        actors = [
            {"tags": ["apt-china", "espionage"]},
            {"tags": ["ransomware"]},
        ]
        with patch("beacon.sage.client.httpx") as mock_httpx:
            mock_httpx.get.return_value = self._mock_response(actors)
            mock_httpx.TimeoutException = Exception
            mock_httpx.HTTPError = Exception
            count = client.get_actor_observation_count(["apt-china"])

        assert count == 1

    def test_multiple_matching_actors(self):
        client = self._make_client()
        actors = [
            {"tags": ["apt-china", "espionage"]},
            {"tags": ["apt-china", "ip-theft"]},
            {"tags": ["ransomware"]},
        ]
        with patch("beacon.sage.client.httpx") as mock_httpx:
            mock_httpx.get.return_value = self._mock_response(actors)
            mock_httpx.TimeoutException = Exception
            mock_httpx.HTTPError = Exception
            count = client.get_actor_observation_count(["apt-china"])

        assert count == 2

    def test_no_matching_tags_returns_zero(self):
        client = self._make_client()
        actors = [{"tags": ["ransomware"]}]
        with patch("beacon.sage.client.httpx") as mock_httpx:
            mock_httpx.get.return_value = self._mock_response(actors)
            mock_httpx.TimeoutException = Exception
            mock_httpx.HTTPError = Exception
            count = client.get_actor_observation_count(["apt-north-korea"])

        assert count == 0

    def test_empty_tags_returns_zero_without_api_call(self):
        client = self._make_client()
        with patch("beacon.sage.client.httpx") as mock_httpx:
            count = client.get_actor_observation_count([])

        mock_httpx.get.assert_not_called()
        assert count == 0

    def test_timeout_returns_zero_with_warning(self, caplog):
        import httpx2 as httpx  # noqa: PLC0415

        client = self._make_client()
        with patch("beacon.sage.client.httpx") as mock_httpx:
            mock_httpx.TimeoutException = httpx.TimeoutException
            mock_httpx.HTTPError = httpx.HTTPError
            mock_httpx.get.side_effect = httpx.TimeoutException("timed out")

            count = client.get_actor_observation_count(["apt-china"])

        assert count == 0

    def test_http_error_returns_zero(self):
        import httpx2 as httpx  # noqa: PLC0415

        client = self._make_client()
        with patch("beacon.sage.client.httpx") as mock_httpx:
            mock_httpx.TimeoutException = httpx.TimeoutException
            mock_httpx.HTTPError = httpx.HTTPError
            mock_httpx.get.side_effect = httpx.HTTPStatusError(
                "404", request=MagicMock(), response=MagicMock()
            )

            count = client.get_actor_observation_count(["apt-china"])

        assert count == 0


class TestRiskScorerUseSage:
    """Test that risk_scorer.score integrates SAGE observations correctly."""

    def _make_elements(self):
        from beacon.analysis.element_extractor import ExtractedElements  # noqa: PLC0415

        return ExtractedElements(
            org_industry="manufacturing",
            org_unit_name="",
            org_unit_type="company",
            org_geographies=["Japan"],
            org_regulatory_context=["ISO27001"],
            strategic_sensitivity=[],
            project_data_types=[],
            project_cloud_providers=[],
            crown_jewel_ids=["CJ-1"],
            crown_jewel_systems=["PLM"],
            crown_jewel_impacts=["high"],
            crown_jewel_details=[],
            critical_asset_ids=[],
            critical_asset_details=[],
            has_ot_connectivity=False,
            has_stock_listing=False,
            active_vendors=[],
            active_triggers=[],
            source_element_ids=["CJ-1"],
        )

    def _make_threat(self):
        from beacon.analysis.threat_mapper import ThreatProfile  # noqa: PLC0415

        return ThreatProfile(
            threat_actor_tags=["apt-china", "espionage"],
            matched_categories=["state_sponsored.China"],
            notable_groups=["APT10"],
            priority_ttps=["T1190"],
            active_triggers=[],
        )

    def test_use_sage_false_does_not_call_api(self):
        from beacon.analysis.risk_scorer import score  # noqa: PLC0415

        mock_client = MagicMock()
        score(self._make_elements(), self._make_threat(), use_sage=False, sage_client=mock_client)

        mock_client.get_actor_observation_count.assert_not_called()

    def test_use_sage_true_no_client_does_not_crash(self):
        from beacon.analysis.risk_scorer import score  # noqa: PLC0415

        # sage_client=None → should not crash
        result = score(self._make_elements(), self._make_threat(), use_sage=True, sage_client=None)
        assert result.likelihood >= 1

    def test_observation_count_ge_1_boosts_likelihood(self):
        from beacon.analysis.risk_scorer import score  # noqa: PLC0415

        mock_client = MagicMock()
        mock_client.get_actor_observation_count.return_value = 3

        baseline = score(self._make_elements(), self._make_threat(), use_sage=False)
        boosted = score(
            self._make_elements(), self._make_threat(), use_sage=True, sage_client=mock_client
        )

        assert boosted.likelihood == min(baseline.likelihood + 1, 5)

    def test_observation_count_zero_does_not_boost(self):
        from beacon.analysis.risk_scorer import score  # noqa: PLC0415

        mock_client = MagicMock()
        mock_client.get_actor_observation_count.return_value = 0

        baseline = score(self._make_elements(), self._make_threat(), use_sage=False)
        result = score(
            self._make_elements(), self._make_threat(), use_sage=True, sage_client=mock_client
        )

        assert result.likelihood == baseline.likelihood

    def test_sage_observation_in_rationale(self):
        from beacon.analysis.risk_scorer import score  # noqa: PLC0415

        mock_client = MagicMock()
        mock_client.get_actor_observation_count.return_value = 5

        result = score(
            self._make_elements(), self._make_threat(), use_sage=True, sage_client=mock_client
        )

        assert "SAGE observations: 5" in result.rationale

    def test_likelihood_capped_at_5(self):
        from beacon.analysis.risk_scorer import score  # noqa: PLC0415
        from beacon.analysis.threat_mapper import ThreatProfile  # noqa: PLC0415

        # Construct a high-score threat to get likelihood=5 baseline
        threat = ThreatProfile(
            threat_actor_tags=["apt-china"],
            matched_categories=["a", "b", "c"],
            notable_groups=[],
            priority_ttps=[],
            active_triggers=["it_ot_convergence"],
        )

        mock_client = MagicMock()
        mock_client.get_actor_observation_count.return_value = 10

        result = score(self._make_elements(), threat, use_sage=True, sage_client=mock_client)

        assert result.likelihood <= 5


class TestSageAPIClientAuthHeaders:
    """OIDC / static-token behavior of `_auth_headers()` (BEACON 3.0.2)."""

    HTTPS_URL = "https://sage-api-256710017041.us-central1.run.app"
    HTTP_URL = "http://localhost:8000"

    def _future_token(self) -> str:
        return _fake_jwt(time.time() + 3600)

    # (a) static token wins and OIDC is never consulted ------------------

    def test_static_constructor_token_is_sent_and_oidc_not_called(self):
        client = SageAPIClient(self.HTTPS_URL, bearer_token="static-abc")
        with patch("google.oauth2.id_token.fetch_id_token") as mock_fetch:
            headers = client._auth_headers()

        assert headers == {"Authorization": "Bearer static-abc"}
        mock_fetch.assert_not_called()

    def test_static_env_token_is_sent_and_oidc_not_called(self, monkeypatch):
        monkeypatch.setenv("SAGE_API_AUTH_TOKEN", "env-token-xyz")
        client = SageAPIClient(self.HTTPS_URL)
        with patch("google.oauth2.id_token.fetch_id_token") as mock_fetch:
            headers = client._auth_headers()

        assert headers == {"Authorization": "Bearer env-token-xyz"}
        mock_fetch.assert_not_called()

    # (b) no static token + OIDC succeeds -------------------------------

    def test_oidc_token_attached_when_no_static_token(self, monkeypatch):
        monkeypatch.delenv("SAGE_API_AUTH_TOKEN", raising=False)
        client = SageAPIClient(self.HTTPS_URL)
        token = self._future_token()
        with patch("google.oauth2.id_token.fetch_id_token", return_value=token) as mock_fetch:
            headers = client._auth_headers()

        assert headers == {"Authorization": f"Bearer {token}"}
        mock_fetch.assert_called_once()
        # audience must be the configured base_url.
        _request_arg, audience_arg = mock_fetch.call_args.args
        assert audience_arg == self.HTTPS_URL

    # (c) OIDC fetch raises → no header, fail-soft funnel ---------------

    def test_oidc_failure_returns_no_header(self, monkeypatch):
        monkeypatch.delenv("SAGE_API_AUTH_TOKEN", raising=False)
        client = SageAPIClient(self.HTTPS_URL)
        with patch(
            "google.oauth2.id_token.fetch_id_token",
            side_effect=RuntimeError("no metadata server"),
        ):
            headers = client._auth_headers()

        assert headers == {}

    def test_oidc_failure_search_actors_fails_soft(self, monkeypatch):
        import httpx2 as httpx  # noqa: PLC0415

        monkeypatch.delenv("SAGE_API_AUTH_TOKEN", raising=False)
        client = SageAPIClient(self.HTTPS_URL)
        with (
            patch(
                "google.oauth2.id_token.fetch_id_token",
                side_effect=RuntimeError("no metadata server"),
            ),
            patch("beacon.sage.client.httpx") as mock_httpx,
        ):
            mock_httpx.TimeoutException = httpx.TimeoutException
            mock_httpx.HTTPError = httpx.HTTPError
            mock_httpx.get.side_effect = httpx.HTTPStatusError(
                "403", request=MagicMock(), response=MagicMock()
            )
            result = client.search_actors("Salt Typhoon")

        # header-less request → server 403 → fail-soft empty list.
        assert result == []
        _, kwargs = mock_httpx.get.call_args
        assert kwargs["headers"] == {}

    # (d) caching: fetch happens exactly once --------------------------

    def test_oidc_token_cached_across_calls(self, monkeypatch):
        monkeypatch.delenv("SAGE_API_AUTH_TOKEN", raising=False)
        client = SageAPIClient(self.HTTPS_URL)
        token = self._future_token()
        with patch("google.oauth2.id_token.fetch_id_token", return_value=token) as mock_fetch:
            first = client._auth_headers()
            second = client._auth_headers()

        assert first == second == {"Authorization": f"Bearer {token}"}
        mock_fetch.assert_called_once()

    # HTTPS-only: plaintext base_url never gets a token -----------------

    def test_http_base_url_never_attaches_oidc(self, monkeypatch):
        monkeypatch.delenv("SAGE_API_AUTH_TOKEN", raising=False)
        client = SageAPIClient(self.HTTP_URL)
        token = self._future_token()
        with patch("google.oauth2.id_token.fetch_id_token", return_value=token) as mock_fetch:
            headers = client._auth_headers()

        assert headers == {}
        mock_fetch.assert_not_called()

    def test_http_base_url_never_attaches_static_token(self):
        client = SageAPIClient(self.HTTP_URL, bearer_token="static-abc")
        assert client._auth_headers() == {}


class TestSageAPIClientIndicatorExtraction:
    def _make_client(self):
        return SageAPIClient("http://localhost:8000")

    def test_get_indicators_for_actors_calls_sage(self):
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"indicators": [{"value": "203.0.113.10"}]}
        mock_resp.raise_for_status.return_value = None
        with patch("beacon.sage.client.httpx") as mock_httpx:
            mock_httpx.get.return_value = mock_resp
            mock_httpx.TimeoutException = Exception
            mock_httpx.HTTPError = Exception
            result = client.get_indicators_for_actors(["intrusion-set--a"], limit=5)

        assert result == [{"value": "203.0.113.10"}]
        url = mock_httpx.get.call_args[0][0]
        params = mock_httpx.get.call_args[1]["params"]
        assert url.endswith("/indicators")
        assert ("actor_id", "intrusion-set--a") in params
        assert ("limit", 5) in params

    def test_get_indicators_for_actors_empty_input_no_call(self):
        client = self._make_client()
        with patch("beacon.sage.client.httpx") as mock_httpx:
            assert client.get_indicators_for_actors([]) == []
            mock_httpx.get.assert_not_called()

    def test_export_stix_returns_bytes(self):
        client = self._make_client()
        mock_resp = MagicMock()
        mock_resp.content = b'{"type":"bundle"}'
        mock_resp.raise_for_status.return_value = None
        with patch("beacon.sage.client.httpx") as mock_httpx:
            mock_httpx.get.return_value = mock_resp
            payload = client.export_stix(["intrusion-set--a"], limit=7)

        assert payload == b'{"type":"bundle"}'
        params = mock_httpx.get.call_args[1]["params"]
        assert ("actor_id", "intrusion-set--a") in params
        assert ("limit", 7) in params
        assert ("download", "true") in params
