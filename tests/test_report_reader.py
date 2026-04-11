"""Tests for ingest/report_reader.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from beacon.ingest.report_reader import _MAX_CHARS, read_report


def _patch_convert(text: str):
    """Patch _markitdown_convert to return the given text."""
    return patch("beacon.ingest.report_reader._markitdown_convert", return_value=text)


class TestReadReport:
    def test_converts_url_via_markitdown(self):
        with _patch_convert("APT29 used LODEINFO backdoor") as mock:
            result = read_report("https://example.com/report")
        mock.assert_called_once_with("https://example.com/report")
        assert "LODEINFO" in result

    def test_converts_http_url(self):
        with _patch_convert("CTI data") as mock:
            result = read_report("http://example.com/report")
        mock.assert_called_once_with("http://example.com/report")
        assert "CTI data" in result

    def test_converts_pdf_via_markitdown(self, tmp_path: Path):
        pdf = tmp_path / "report.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")

        with _patch_convert("TTP T1566 spearphishing") as mock:
            result = read_report(pdf)

        mock.assert_called_once_with(str(pdf))
        assert "T1566" in result

    def test_reads_text_file_directly(self, tmp_path: Path):
        report = tmp_path / "report.txt"
        report.write_text("Threat actor used spearphishing", encoding="utf-8")
        result = read_report(report)
        assert "spearphishing" in result

    def test_reads_markdown_file_directly(self, tmp_path: Path):
        report = tmp_path / "report.md"
        report.write_text("# CVE-2023-3519\nExploited by INC Ransomware", encoding="utf-8")
        result = read_report(report)
        assert "CVE-2023-3519" in result

    def test_raises_for_missing_file(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            read_report(tmp_path / "nonexistent.txt")

    def test_raises_for_missing_pdf(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            read_report(tmp_path / "missing.pdf")

    def test_truncates_to_default_max_chars(self, tmp_path: Path):
        report = tmp_path / "long.txt"
        report.write_text("a" * 50_000, encoding="utf-8")
        result = read_report(report)
        assert len(result) == _MAX_CHARS

    def test_respects_custom_max_chars(self, tmp_path: Path):
        report = tmp_path / "long.txt"
        report.write_text("a" * 50_000, encoding="utf-8")
        result = read_report(report, max_chars=5_000)
        assert len(result) == 5_000

    def test_url_truncated_to_max_chars(self):
        with _patch_convert("x" * 50_000):
            result = read_report("https://example.com/long", max_chars=8_000)
        assert len(result) == 8_000

    def test_pdf_truncated_to_max_chars(self, tmp_path: Path):
        pdf = tmp_path / "report.pdf"
        pdf.write_bytes(b"%PDF-1.4 fake")
        with _patch_convert("y" * 50_000):
            result = read_report(pdf, max_chars=3_000)
        assert len(result) == 3_000

    def test_raises_runtime_error_when_markitdown_missing(self, tmp_path: Path):
        pdf = tmp_path / "report.pdf"
        pdf.write_bytes(b"%PDF-1.4")

        with patch.dict("sys.modules", {"markitdown": None}):
            from beacon.ingest.report_reader import _markitdown_convert

            with pytest.raises(RuntimeError, match="markitdown is required"):
                _markitdown_convert(str(pdf))

    def test_default_max_chars_is_10000(self):
        assert _MAX_CHARS == 10_000
