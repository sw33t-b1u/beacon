"""Tests for beacon/ingest/misp_client.py — MispClient with graceful degradation."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from beacon.ingest.misp_client import ActorAttributes, MispClient

FIXTURES = Path(__file__).parent / "fixtures"
MINIMAL_FIXTURE = FIXTURES / "misp_galaxy_minimal.json"
REAL_CACHE = Path(__file__).parents[2] / "cache" / "misp-threat-actor.json"


# ---------------------------------------------------------------------------
# (a) Success path — cache present, actor found
# ---------------------------------------------------------------------------


class TestSuccessPath:
    def setup_method(self):
        self.client = MispClient(cache_path=MINIMAL_FIXTURE)

    def test_actor_found_returns_actor_attributes(self):
        result = self.client.get_actor("APT28")
        assert result is not None
        assert isinstance(result, ActorAttributes)

    def test_source_is_misp_cache(self):
        result = self.client.get_actor("APT28")
        assert result.source == "misp_cache"

    def test_degraded_false_on_success(self):
        result = self.client.get_actor("APT28")
        assert result.degraded is False

    def test_aliases_populated(self):
        result = self.client.get_actor("APT28")
        assert "Fancy Bear" in result.aliases
        assert "STRONTIUM" in result.aliases

    def test_target_industries_populated(self):
        result = self.client.get_actor("APT28")
        assert "Government" in result.target_industries

    def test_target_geographies_populated(self):
        result = self.client.get_actor("APT28")
        assert "United States" in result.target_geographies

    def test_valid_sophistication_ov_preserved(self):
        result = self.client.get_actor("APT28")
        assert result.sophistication == "advanced"

    def test_valid_motivation_ov_preserved(self):
        result = self.client.get_actor("FIN7")
        assert result.primary_motivation == "personal-gain"


# ---------------------------------------------------------------------------
# (b) Actor not found
# ---------------------------------------------------------------------------


class TestActorNotFound:
    def setup_method(self):
        self.client = MispClient(cache_path=MINIMAL_FIXTURE)

    def test_returns_none_for_unknown_name(self):
        assert self.client.get_actor("nonexistent-actor-xyz") is None

    def test_returns_none_for_partial_match(self):
        # "APT" is a prefix, not an exact match
        assert self.client.get_actor("APT") is None


# ---------------------------------------------------------------------------
# (c) Cache file missing
# ---------------------------------------------------------------------------


class TestCacheMissing:
    def test_no_exception_on_missing_cache(self, tmp_path):
        client = MispClient(cache_path=tmp_path / "no_such_file.json")
        result = client.get_actor("APT28")
        assert result is None

    def test_client_initializes_without_raising(self, tmp_path):
        # Must not raise even when cache file is absent
        MispClient(cache_path=tmp_path / "no_such_file.json")


# ---------------------------------------------------------------------------
# (d) Malformed cache JSON
# ---------------------------------------------------------------------------


class TestMalformedCache:
    def test_no_exception_on_malformed_json(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid json!!!}", encoding="utf-8")
        client = MispClient(cache_path=bad)
        assert client.get_actor("APT28") is None

    def test_no_exception_on_empty_file(self, tmp_path):
        empty = tmp_path / "empty.json"
        empty.write_text("", encoding="utf-8")
        client = MispClient(cache_path=empty)
        assert client.get_actor("APT28") is None


# ---------------------------------------------------------------------------
# (e) PyMISP not installed / no server_url
# ---------------------------------------------------------------------------


class TestPyMISPGraceDegradation:
    def test_cache_works_without_pymisp_import(self, monkeypatch):
        """Cache-based lookup succeeds regardless of whether pymisp is importable."""
        monkeypatch.setitem(sys.modules, "pymisp", None)
        client = MispClient(cache_path=MINIMAL_FIXTURE)
        result = client.get_actor("APT28")
        assert result is not None
        assert result.source == "misp_cache"

    def test_live_path_returns_none_when_pymisp_unavailable(self, monkeypatch):
        """Server configured but pymisp not importable → returns None, no crash."""
        monkeypatch.setitem(sys.modules, "pymisp", None)
        client = MispClient(server_url="http://fake.misp.local", api_key="secret")
        result = client.get_actor("APT28")
        assert result is None

    def test_no_source_configured_returns_none(self):
        """Neither cache_path nor server_url → degraded, get_actor always None."""
        client = MispClient(cache_path=None, server_url=None)
        assert client.get_actor("APT28") is None


# ---------------------------------------------------------------------------
# (f) STIX OV normalization — invalid sophistication → None
# ---------------------------------------------------------------------------


class TestStixOvNormalization:
    def setup_method(self):
        self.client = MispClient(cache_path=MINIMAL_FIXTURE)

    def test_invalid_sophistication_normalized_to_none(self):
        result = self.client.get_actor("UnknownHacker")
        assert result is not None
        assert result.sophistication is None

    def test_invalid_cfr_type_of_incident_not_emitted_as_motivation(self):
        # "Espionage" is not a STIX motivation-ov value — must normalize to None
        result = self.client.get_actor("APT28")
        assert result is not None
        assert result.primary_motivation is None

    def test_valid_stix_motivation_ov_accepted(self):
        # "personal-gain" IS a STIX motivation-ov value
        result = self.client.get_actor("FIN7")
        assert result is not None
        assert result.primary_motivation == "personal-gain"

    def test_alias_lookup_works(self):
        result = self.client.get_actor("Fancy Bear")
        assert result is not None
        assert result.source == "misp_cache"

    def test_uuid_lookup_works(self):
        result = self.client.get_actor("test-apt28-uuid")
        assert result is not None

    def test_case_insensitive_name_match(self):
        result = self.client.get_actor("apt28")
        assert result is not None

    def test_case_insensitive_alias_match(self):
        result = self.client.get_actor("fancy bear")
        assert result is not None


# ---------------------------------------------------------------------------
# Integration smoke test — real cache file (skipped if absent)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_real_cache_apt29_aliases():
    """Smoke test: APT29 from the real MISP cache has non-empty aliases."""
    if not REAL_CACHE.exists():
        pytest.skip(f"Real cache not found at {REAL_CACHE}")
    client = MispClient(cache_path=REAL_CACHE)
    result = client.get_actor("APT29")
    assert result is not None, "APT29 not found in real MISP cache"
    assert len(result.aliases) > 0, "APT29 should have at least one alias (e.g. COZY BEAR)"
    assert result.source == "misp_cache"
    assert result.degraded is False


@pytest.mark.integration
def test_real_cache_cozy_bear_alias_lookup():
    """APT29 can also be resolved by its alias 'COZY BEAR'."""
    if not REAL_CACHE.exists():
        pytest.skip(f"Real cache not found at {REAL_CACHE}")
    client = MispClient(cache_path=REAL_CACHE)
    result = client.get_actor("COZY BEAR")
    assert result is not None
    assert "APT29" in result.aliases or any("APT29" in a for a in result.aliases)
