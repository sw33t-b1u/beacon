"""Tests for llm/client.py — Google Gen AI is fully mocked."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from beacon.config import Config


def _make_config(**kwargs) -> Config:
    defaults = dict(
        gcp_project_id="test-project",
        vertex_location="us-central1",
        llm_model_simple="gemini-2.5-flash-lite",
        llm_model_medium="gemini-2.5-flash",
        llm_model_complex="gemini-2.5-pro",
    )
    defaults.update(kwargs)
    return Config(**defaults)


def _mock_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.text = text
    return resp


def _make_mock_genai(response_text: str) -> tuple[MagicMock, MagicMock]:
    """Return (mock_genai_module, mock_client_instance)."""
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = _mock_response(response_text)

    mock_genai = MagicMock()
    mock_genai.Client.return_value = mock_client

    return mock_genai, mock_client


def _reset_client():
    import beacon.llm.client as m

    m._client = None
    m._client_config = None


class TestCallLlm:
    def setup_method(self):
        _reset_client()

    def test_returns_model_text(self):
        config = _make_config()
        expected = '{"key": "value"}'
        mock_genai, _ = _make_mock_genai(expected)

        with patch("beacon.llm.client.genai", mock_genai):
            from beacon.llm.client import call_llm

            result = call_llm("simple", "test prompt", config=config)

        assert result == expected

    def test_selects_correct_model_for_task(self):
        config = _make_config()
        mock_genai, mock_client = _make_mock_genai("{}")

        with patch("beacon.llm.client.genai", mock_genai):
            from beacon.llm.client import call_llm

            call_llm("complex", "test", config=config)

        call_kwargs = mock_client.models.generate_content.call_args.kwargs
        assert call_kwargs["model"] == "gemini-2.5-pro"

    def test_medium_model_selected(self):
        config = _make_config()
        mock_genai, mock_client = _make_mock_genai("{}")

        with patch("beacon.llm.client.genai", mock_genai):
            from beacon.llm.client import call_llm

            call_llm("medium", "test", config=config)

        call_kwargs = mock_client.models.generate_content.call_args.kwargs
        assert call_kwargs["model"] == "gemini-2.5-flash"


class TestCallLlmJson:
    def setup_method(self):
        _reset_client()

    def test_parses_json_response(self):
        config = _make_config()
        payload = {"threat_actor_tags": ["apt-china"], "notable_groups": ["APT41"]}
        mock_genai, _ = _make_mock_genai(json.dumps(payload))

        with patch("beacon.llm.client.genai", mock_genai):
            from beacon.llm.client import call_llm_json

            result = call_llm_json("simple", "test", config=config)

        assert result == payload

    def test_raises_on_invalid_json(self):
        config = _make_config()
        mock_genai, _ = _make_mock_genai("not json at all")

        with patch("beacon.llm.client.genai", mock_genai):
            from beacon.llm.client import call_llm_json

            with pytest.raises(ValueError, match="non-JSON"):
                call_llm_json("simple", "test", config=config)


class TestLoadPrompt:
    def test_loads_existing_prompt(self):
        from beacon.llm.client import load_prompt

        text = load_prompt("context_structuring.md")
        assert "{{DOCUMENT}}" in text
        assert len(text) > 100

    def test_raises_for_missing_prompt(self):
        from beacon.llm.client import load_prompt

        with pytest.raises(FileNotFoundError):
            load_prompt("nonexistent_prompt.md")

    def test_pir_generation_prompt_has_placeholders(self):
        from beacon.llm.client import load_prompt

        text = load_prompt("pir_generation.md")
        assert "{{INDUSTRY}}" in text
        assert "{{DRAFT_DESCRIPTION}}" in text


class TestEnsureClient:
    def setup_method(self):
        _reset_client()

    def teardown_method(self):
        _reset_client()

    def test_creates_client_with_correct_args(self):
        config = _make_config(gcp_project_id="my-project", vertex_location="us-central1")
        mock_genai = MagicMock()

        with patch("beacon.llm.client.genai", mock_genai):
            from beacon.llm.client import _ensure_client

            _ensure_client(config)

        mock_genai.Client.assert_called_once_with(
            vertexai=True,
            project="my-project",
            location="us-central1",
        )

    def test_skips_reinit_same_config(self):
        config = _make_config()

        import beacon.llm.client as m

        existing_client = MagicMock()
        m._client = existing_client
        m._client_config = config

        mock_genai = MagicMock()
        with patch("beacon.llm.client.genai", mock_genai):
            from beacon.llm.client import _ensure_client

            result = _ensure_client(config)

        mock_genai.Client.assert_not_called()
        assert result is existing_client


@pytest.mark.integration
class TestCallLlmIntegration:
    """Integration tests — require real Vertex AI. Run with: make test-integration"""

    def test_simple_call_returns_json(self):
        """Smoke test: call gemini-2.5-flash-lite and get a JSON response."""
        import os

        if not os.environ.get("GCP_PROJECT_ID"):
            pytest.skip("GCP_PROJECT_ID not set")

        from beacon.llm.client import call_llm_json

        result = call_llm_json(
            "simple",
            'Return JSON: {"status": "ok", "message": "hello"}',
        )
        assert isinstance(result, dict)
        assert result.get("status") == "ok"
