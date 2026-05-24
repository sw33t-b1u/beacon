"""CLI flag tests for cmd/generate_pir.py --no-sage (Initiative G Phase 6).

Verifies that the --no-sage flag short-circuits the actor_triage IR-boost
call and marks every prioritized_actor with data_quality.ir_boost_skipped=True.
The flag is independent of --use-sage (which targets risk_scorer's separate
observation-count boost).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import load_cmd_module

_FIXTURE = Path(__file__).parent / "fixtures" / "sample_context_manufacturing.json"
_mod = load_cmd_module("generate_pir")


@pytest.fixture
def _run_pir(tmp_path):
    """Helper: invoke cmd.generate_pir.main with given extra args; return parsed PIR doc.

    Per-test env isolation is left to the caller (monkeypatch.delenv / setenv)
    so a test that needs SAGE_API_URL set can do so without the fixture
    unsetting it back to ''.
    """

    def _runner(extra_args: list[str]) -> dict:
        out = tmp_path / "pir_output.json"
        argv = [
            "--context",
            str(_FIXTURE),
            "--no-llm",
            "--output",
            str(out),
            "--collection-plan",
            "/dev/null",
            "--sources-candidate",
            "/dev/null",
            *extra_args,
        ]
        rc = _mod.main(argv)
        assert rc == 0
        return json.loads(out.read_text())

    return _runner


class TestNoSageFlag:
    def test_flag_sets_ir_boost_skipped_true(self, _run_pir, monkeypatch):
        monkeypatch.delenv("SAGE_API_URL", raising=False)
        doc = _run_pir(["--no-sage"])
        # Sanity: PIRs should be generated for the manufacturing fixture.
        assert len(doc["pirs"]) >= 1
        # Every prioritized_actor on every PIR must carry ir_boost_skipped=True.
        for pir in doc["pirs"]:
            for actor in pir["prioritized_actors"]:
                assert actor["score_breakdown"]["data_quality"]["ir_boost_skipped"] is True

    def test_flag_yields_neutral_ir_factors(self, _run_pir, monkeypatch):
        monkeypatch.delenv("SAGE_API_URL", raising=False)
        doc = _run_pir(["--no-sage"])
        for pir in doc["pirs"]:
            for actor in pir["prioritized_actors"]:
                cap = actor["score_breakdown"]["capability"]
                opp = actor["score_breakdown"]["opportunity"]
                assert cap["ir_observed_capability"] == 1.0
                assert opp["ir_observed_opportunity"] == 1.0

    def test_flag_does_not_attempt_sage_call(self, _run_pir, monkeypatch):
        monkeypatch.delenv("SAGE_API_URL", raising=False)
        # Patching the constructor verifies the IR-boost path skips SAGE entirely.
        with patch("beacon.sage.client.SageAPIClient") as mock_ctor:
            doc = _run_pir(["--no-sage"])
        mock_ctor.assert_not_called()
        assert len(doc["pirs"]) >= 1

    def test_schema_version_is_1_0_0(self, _run_pir, monkeypatch):
        monkeypatch.delenv("SAGE_API_URL", raising=False)
        doc = _run_pir(["--no-sage"])
        assert doc["schema_version"] == "1.0.0"


class TestSageUrlUnsetEquivalentToNoSage:
    """When SAGE_API_URL is unset, IR-boost is auto-skipped without --no-sage."""

    def test_unset_sage_url_sets_ir_boost_skipped(self, _run_pir, monkeypatch):
        monkeypatch.delenv("SAGE_API_URL", raising=False)
        doc = _run_pir([])
        for pir in doc["pirs"]:
            for actor in pir["prioritized_actors"]:
                assert actor["score_breakdown"]["data_quality"]["ir_boost_skipped"] is True


class TestSageUrlSetButFailsFailsSoft:
    """When SAGE_API_URL is set but the call raises, fail-soft sets degraded=True."""

    def test_sage_unreachable_sets_degraded(self, _run_pir, monkeypatch):
        import httpx  # noqa: PLC0415

        monkeypatch.setenv("SAGE_API_URL", "http://invalid.localhost:9999")
        # Patch SageAPIClient to raise on get_recent_incidents.
        mock_client = MagicMock()
        mock_client.get_recent_incidents.side_effect = httpx.ConnectError("simulated")
        with patch("beacon.sage.client.SageAPIClient", return_value=mock_client):
            doc = _run_pir([])
        # All prioritized_actors should be degraded (degraded loop short-circuits
        # after first failure, but every actor inherits the sage_degraded flag).
        any_degraded = any(
            actor["score_breakdown"]["data_quality"]["degraded"] is True
            for pir in doc["pirs"]
            for actor in pir["prioritized_actors"]
        )
        assert any_degraded
        # ir_boost_skipped stays False — this is a runtime failure, not a deliberate skip.
        for pir in doc["pirs"]:
            for actor in pir["prioritized_actors"]:
                assert actor["score_breakdown"]["data_quality"]["ir_boost_skipped"] is False
