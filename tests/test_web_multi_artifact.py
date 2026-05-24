"""Tests for the multi-artifact landing page + viewer routes (Phase 6).

Covers the routes committed in ``docs/api-stability.md`` §3.8:

* ``GET /`` enumerates every present artifact in ``BEACON_OUTPUT_DIR``
  and exposes a ``/review/artifacts/{filename}`` link.
* ``GET /review/artifacts/{filename}`` serves a read-only viewer for
  any of the six whitelisted artifact filenames.
* ``GET /review/artifacts/{unknown}`` returns 404.
* ``GET /review/pir/{pir_id}`` loads ``pir_output.json`` from the
  output directory, locates the matching PIR, and renders the existing
  review template.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from beacon.web.app import app

SAMPLE_PIR = {
    "pir_id": "PIR-2026-001",
    "intelligence_level": "operational",
    "valid_from": "2026-04-04",
    "valid_until": "2026-07-04",
    "description": "Test description for multi-artifact",
    "rationale": "Test rationale",
    "threat_actor_tags": ["apt-china"],
    "asset_weight_rules": [{"tag": "plm", "criticality_multiplier": 2.5}],
    "collection_focus": ["Track IOCs"],
    "risk_score": {"likelihood": 3, "impact": 4, "composite": 12},
    "prioritized_actors": [],
}


@pytest.fixture
def output_dir(tmp_path, monkeypatch) -> Path:
    """A populated artifact dir wired to BEACON_OUTPUT_DIR for the request."""
    out = tmp_path / "run-1"
    out.mkdir()

    (out / "pir_output.json").write_text(
        json.dumps({"schema_version": "1.0.0", "pirs": [SAMPLE_PIR]}, indent=2),
        encoding="utf-8",
    )
    (out / "assets.json").write_text(
        json.dumps({"assets": [{"id": "asset-1", "name": "ERP"}]}, indent=2),
        encoding="utf-8",
    )
    (out / "identity_assets.json").write_text(
        json.dumps({"identities": [], "has_access": []}, indent=2),
        encoding="utf-8",
    )
    (out / "user_accounts.json").write_text(
        json.dumps({"user_accounts": [], "account_on_asset": []}, indent=2),
        encoding="utf-8",
    )
    (out / "collection_plan.md").write_text(
        "# Collection Plan\n\nP1: track APT activity.\n",
        encoding="utf-8",
    )
    (out / "sources_candidate.yaml").write_text(
        "version: 1\nsources: []\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("BEACON_OUTPUT_DIR", str(out))
    return out


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestLandingPageListsArtifacts:
    EXPECTED = (
        "pir_output.json",
        "assets.json",
        "identity_assets.json",
        "user_accounts.json",
        "collection_plan.md",
        "sources_candidate.yaml",
    )

    def test_landing_returns_200(self, output_dir, client):
        resp = client.get("/")
        assert resp.status_code == 200

    @pytest.mark.parametrize("name", EXPECTED)
    def test_each_artifact_listed(self, output_dir, client, name):
        resp = client.get("/")
        assert name in resp.text

    @pytest.mark.parametrize("name", EXPECTED)
    def test_view_link_to_artifact(self, output_dir, client, name):
        resp = client.get("/")
        assert f"/review/artifacts/{name}" in resp.text

    def test_output_dir_shown_in_header(self, output_dir, client):
        resp = client.get("/")
        assert str(output_dir) in resp.text


class TestLandingPageOmitsMissingArtifacts:
    def test_only_present_files_listed(self, tmp_path, monkeypatch):
        out = tmp_path / "partial"
        out.mkdir()
        (out / "pir_output.json").write_text(
            json.dumps({"schema_version": "1.0.0", "pirs": []}), encoding="utf-8"
        )
        # Only pir_output.json present — other 5 files MUST NOT be linked.
        monkeypatch.setenv("BEACON_OUTPUT_DIR", str(out))
        with TestClient(app) as client:
            resp = client.get("/")
        assert "/review/artifacts/pir_output.json" in resp.text
        assert "/review/artifacts/assets.json" not in resp.text
        assert "/review/artifacts/collection_plan.md" not in resp.text


class TestArtifactViewer:
    def test_json_artifact_pretty_printed(self, output_dir, client):
        resp = client.get("/review/artifacts/assets.json")
        assert resp.status_code == 200
        # Pretty-printed JSON renders inside <pre> with HTML-escaped quotes.
        assert "&#34;assets&#34;" in resp.text
        # And the raw endpoint serves the JSON unescaped for download.
        raw = client.get("/review/artifacts/assets.json/raw")
        assert '"assets":' in raw.text

    def test_markdown_artifact_renders(self, output_dir, client):
        resp = client.get("/review/artifacts/collection_plan.md")
        assert resp.status_code == 200
        assert "# Collection Plan" in resp.text

    def test_yaml_artifact_renders(self, output_dir, client):
        resp = client.get("/review/artifacts/sources_candidate.yaml")
        assert resp.status_code == 200
        assert "version: 1" in resp.text

    def test_unknown_filename_404(self, output_dir, client):
        resp = client.get("/review/artifacts/passwords.txt")
        assert resp.status_code == 404

    def test_known_filename_but_missing_file_404(self, tmp_path, monkeypatch):
        empty = tmp_path / "empty"
        empty.mkdir()
        monkeypatch.setenv("BEACON_OUTPUT_DIR", str(empty))
        with TestClient(app) as client:
            resp = client.get("/review/artifacts/pir_output.json")
        assert resp.status_code == 404

    def test_raw_endpoint_serves_text(self, output_dir, client):
        resp = client.get("/review/artifacts/collection_plan.md/raw")
        assert resp.status_code == 200
        assert resp.text == "# Collection Plan\n\nP1: track APT activity.\n"

    def test_path_traversal_rejected(self, output_dir, client):
        # The route signature constrains {filename} to a single segment;
        # any traversal attempt resolves to a non-whitelisted name → 404.
        resp = client.get("/review/artifacts/..%2Fsecret")
        assert resp.status_code == 404


class TestReviewPirRoute:
    def test_existing_pir_renders(self, output_dir, client):
        resp = client.get("/review/pir/PIR-2026-001")
        assert resp.status_code == 200
        # The review template emits the PIR's description for the analyst.
        assert "Test description for multi-artifact" in resp.text

    def test_missing_pir_returns_404(self, output_dir, client):
        resp = client.get("/review/pir/PIR-9999-NA")
        assert resp.status_code == 404

    def test_missing_output_file_returns_404(self, tmp_path, monkeypatch):
        empty = tmp_path / "empty"
        empty.mkdir()
        monkeypatch.setenv("BEACON_OUTPUT_DIR", str(empty))
        with TestClient(app) as client:
            resp = client.get("/review/pir/PIR-2026-001")
        assert resp.status_code == 404

    def test_bare_list_pir_output_supported(self, tmp_path, monkeypatch):
        out = tmp_path / "bare"
        out.mkdir()
        (out / "pir_output.json").write_text(json.dumps([SAMPLE_PIR]), encoding="utf-8")
        monkeypatch.setenv("BEACON_OUTPUT_DIR", str(out))
        with TestClient(app) as client:
            resp = client.get("/review/pir/PIR-2026-001")
        assert resp.status_code == 200


class TestBeaconOutputDirFallback:
    def test_default_output_dir_when_env_unset(self, monkeypatch, tmp_path):
        monkeypatch.delenv("BEACON_OUTPUT_DIR", raising=False)
        # cd into tmp_path so the default "output" relative dir is a fresh empty path
        monkeypatch.chdir(tmp_path)
        with TestClient(app) as client:
            resp = client.get("/")
        assert resp.status_code == 200
        # No artifacts present; helper text from index.html informs the operator.
        assert "Run <code>beacon pir-generate</code>" in resp.text or "No artifacts" in resp.text
