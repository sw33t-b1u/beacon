"""Tests for llm/client.py — Vertex AI is fully mocked."""

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


class TestCallLlm:
    def test_returns_model_text(self):
        config = _make_config()
        expected = '{"key": "value"}'

        with (
            patch("beacon.llm.client._ensure_initialized"),
            patch("beacon.llm.client.GenerativeModel") as mock_model,
        ):
            mock_instance = MagicMock()
            mock_instance.generate_content.return_value = _mock_response(expected)
            mock_model.return_value = mock_instance

            from beacon.llm.client import call_llm

            result = call_llm("simple", "test prompt", config=config)

        assert result == expected

    def test_selects_correct_model_for_task(self):
        config = _make_config()

        with (
            patch("beacon.llm.client._ensure_initialized"),
            patch("beacon.llm.client.GenerativeModel") as mock_model,
        ):
            mock_instance = MagicMock()
            mock_instance.generate_content.return_value = _mock_response("{}")
            mock_model.return_value = mock_instance

            from beacon.llm.client import call_llm

            call_llm("complex", "test", config=config)

        mock_model.assert_called_once_with("gemini-2.5-pro")

    def test_medium_model_selected(self):
        config = _make_config()

        with (
            patch("beacon.llm.client._ensure_initialized"),
            patch("beacon.llm.client.GenerativeModel") as mock_model,
        ):
            mock_instance = MagicMock()
            mock_instance.generate_content.return_value = _mock_response("{}")
            mock_model.return_value = mock_instance

            from beacon.llm.client import call_llm

            call_llm("medium", "test", config=config)

        mock_model.assert_called_once_with("gemini-2.5-flash")


class TestCallLlmJson:
    def test_parses_json_response(self):
        config = _make_config()
        payload = {"threat_actor_tags": ["apt-china"], "notable_groups": ["APT41"]}

        with (
            patch("beacon.llm.client._ensure_initialized"),
            patch("beacon.llm.client.GenerativeModel") as mock_model,
        ):
            mock_instance = MagicMock()
            mock_instance.generate_content.return_value = _mock_response(json.dumps(payload))
            mock_model.return_value = mock_instance

            from beacon.llm.client import call_llm_json

            result = call_llm_json("simple", "test", config=config)

        assert result == payload

    def test_raises_on_invalid_json(self):
        config = _make_config()

        with (
            patch("beacon.llm.client._ensure_initialized"),
            patch("beacon.llm.client.GenerativeModel") as mock_model,
        ):
            mock_instance = MagicMock()
            mock_instance.generate_content.return_value = _mock_response("not json at all")
            mock_model.return_value = mock_instance

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

    def test_threat_tag_completion_prompt_has_placeholders(self):
        from beacon.llm.client import load_prompt

        text = load_prompt("threat_tag_completion.md")
        assert "{{INDUSTRY}}" in text
        assert "{{EXISTING_TAGS}}" in text


class TestEnsureInitialized:
    def test_calls_vertexai_init(self):
        config = _make_config(gcp_project_id="my-project", vertex_location="us-central1")

        import beacon.llm.client as client_module

        client_module._initialized = False
        client_module._config = None

        with patch("beacon.llm.client.vertexai") as mock_vertexai:
            from beacon.llm.client import _ensure_initialized

            _ensure_initialized(config)

        mock_vertexai.init.assert_called_once_with(project="my-project", location="us-central1")

    def test_skips_reinit_same_config(self):
        config = _make_config()

        import beacon.llm.client as client_module

        client_module._initialized = True
        client_module._config = config

        with patch("beacon.llm.client.vertexai") as mock_vertexai:
            from beacon.llm.client import _ensure_initialized

            _ensure_initialized(config)

        mock_vertexai.init.assert_not_called()
        # Reset for other tests
        client_module._initialized = False
        client_module._config = None


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
