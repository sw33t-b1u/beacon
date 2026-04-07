"""Tests for src/beacon/sage/client.py and risk_scorer use_sage integration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from beacon.sage.client import SageAPIClient


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
        import httpx  # noqa: PLC0415

        client = self._make_client()
        with patch("beacon.sage.client.httpx") as mock_httpx:
            mock_httpx.TimeoutException = httpx.TimeoutException
            mock_httpx.HTTPError = httpx.HTTPError
            mock_httpx.get.side_effect = httpx.TimeoutException("timed out")

            count = client.get_actor_observation_count(["apt-china"])

        assert count == 0

    def test_http_error_returns_zero(self):
        import httpx  # noqa: PLC0415

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
            org_geographies=["Japan"],
            strategic_sensitivity=[],
            project_data_types=[],
            project_cloud_providers=[],
            crown_jewel_ids=["CJ-1"],
            crown_jewel_systems=["PLM"],
            crown_jewel_impacts=["high"],
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
            active_triggers=["ot_connectivity"],
        )

        mock_client = MagicMock()
        mock_client.get_actor_observation_count.return_value = 10

        result = score(self._make_elements(), threat, use_sage=True, sage_client=mock_client)

        assert result.likelihood <= 5
