"""Tests for context_parser.py — Markdown path (Phase 2)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from beacon.ingest.schema import BusinessContext

FIXTURES = Path(__file__).parent / "fixtures"


def _finance_context_dict() -> dict:
    """Expected BusinessContext structure for sample_context_finance.md."""
    return {
        "organization": {
            "name": "Acme Finance Corp",
            "industry": "finance",
            "sub_industries": [],
            "geography": ["Japan", "South Korea"],
            "employee_count_range": "1000-5000",
            "revenue_range_usd": "1B-10B",
            "stock_listed": True,
            "regulatory_context": ["APPI", "FISC"],
        },
        "strategic_objectives": [
            {
                "id": "OBJ-001",
                "title": "Digital Transformation",
                "description": "Migrating core banking to cloud",
                "timeline": "2026",
                "sensitivity": "high",
                "key_decisions": [],
            }
        ],
        "projects": [
            {
                "id": "PROJ-001",
                "name": "Core Banking Migration",
                "status": "in_progress",
                "sensitivity": "critical",
                "involved_vendors": ["Microsoft", "Accenture"],
                "cloud_providers": ["Azure"],
                "data_types": ["financial", "personal"],
            }
        ],
        "crown_jewels": [
            {
                "id": "CJ-001",
                "name": "Core Banking System",
                "system": "core banking",
                "business_impact": "critical",
                "exposure_risk": "medium",
            }
        ],
        "supply_chain": {
            "critical_vendors": ["Microsoft", "Accenture"],
            "cloud_providers": ["Azure"],
            "ot_connectivity": False,
        },
        "recent_incidents": [],
    }


class TestParseMarkdownMocked:
    def test_parse_markdown_calls_llm(self):
        """Verify that parse_markdown invokes call_llm_json with 'simple' task."""
        md_path = FIXTURES / "sample_context_finance.md"
        mock_response = _finance_context_dict()

        with patch("beacon.llm.client.call_llm_json", return_value=mock_response) as mock_llm:
            from beacon.ingest.context_parser import parse_markdown

            parse_markdown(md_path)

        mock_llm.assert_called_once()
        call_args = mock_llm.call_args
        assert call_args[0][0] == "simple"  # task type

    def test_parse_markdown_returns_business_context(self):
        md_path = FIXTURES / "sample_context_finance.md"
        mock_response = _finance_context_dict()

        with patch("beacon.llm.client.call_llm_json", return_value=mock_response):
            from beacon.ingest.context_parser import parse_markdown

            ctx = parse_markdown(md_path)

        assert isinstance(ctx, BusinessContext)
        assert ctx.organization.industry == "finance"

    def test_parse_markdown_prompt_contains_document(self):
        """Verify that the document text is included in the prompt."""
        md_path = FIXTURES / "sample_context_finance.md"
        mock_response = _finance_context_dict()
        captured_prompt = []

        def capture_call(task, prompt, **kwargs):
            captured_prompt.append(prompt)
            return mock_response

        with patch("beacon.llm.client.call_llm_json", side_effect=capture_call):
            from beacon.ingest.context_parser import parse_markdown

            parse_markdown(md_path)

        assert len(captured_prompt) == 1
        # Document text should be in the prompt
        assert "Acme Finance Corp" in captured_prompt[0]

    def test_parse_dispatch_md_extension(self):
        """parse() should route .md files to parse_markdown."""
        md_path = FIXTURES / "sample_context_finance.md"
        mock_response = _finance_context_dict()

        with patch("beacon.llm.client.call_llm_json", return_value=mock_response):
            from beacon.ingest.context_parser import parse

            ctx = parse(md_path, no_llm=False)

        assert ctx.organization.industry == "finance"

    def test_parse_no_llm_md_raises(self):
        """parse() with --no-llm and .md input should raise NotImplementedError."""
        md_path = FIXTURES / "sample_context_finance.md"

        from beacon.ingest.context_parser import parse

        with pytest.raises(NotImplementedError, match="Markdown input requires LLM"):
            parse(md_path, no_llm=True)

    def test_parse_markdown_validates_schema(self):
        """Returned object must pass Pydantic validation."""
        md_path = FIXTURES / "sample_context_finance.md"
        mock_response = _finance_context_dict()

        with patch("beacon.llm.client.call_llm_json", return_value=mock_response):
            from beacon.ingest.context_parser import parse_markdown

            ctx = parse_markdown(md_path)

        # Verify Pydantic model fields are accessible
        assert ctx.organization.name is not None
        assert isinstance(ctx.projects, list)
        assert isinstance(ctx.crown_jewels, list)

    def test_parse_markdown_invalid_llm_response_raises(self):
        """LLM returning invalid schema should raise ValidationError."""
        md_path = FIXTURES / "sample_context_finance.md"
        # Missing required 'organization' field
        bad_response = {"not_valid": True}

        with patch("beacon.llm.client.call_llm_json", return_value=bad_response):
            from beacon.ingest.context_parser import parse_markdown

            with pytest.raises(Exception):  # pydantic.ValidationError
                parse_markdown(md_path)


@pytest.mark.integration
class TestParseMarkdownIntegration:
    """Integration test — requires real Vertex AI. Run with: make test-integration"""

    def test_parse_finance_md_real_llm(self):
        import os

        if not os.environ.get("GCP_PROJECT_ID"):
            pytest.skip("GCP_PROJECT_ID not set")

        from beacon.ingest.context_parser import parse_markdown

        md_path = FIXTURES / "sample_context_finance.md"
        ctx = parse_markdown(md_path)

        assert isinstance(ctx, BusinessContext)
        assert ctx.organization.industry in {"finance", "technology", "other"}
        assert len(ctx.organization.geography) > 0
