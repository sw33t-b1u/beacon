"""Tests for the unified ``beacon`` CLI (Initiative H Phase 6).

Exercises the click group entry point at ``beacon.cli:cli``:

* All 8 subcommands appear in ``beacon --help``.
* Each subcommand resolves to the underlying ``cmd/*.py`` ``main(argv)``
  with ``_from_beacon_cli=True`` (suppresses the deprecation banner) and
  the original flag set passes through.
* ``pir-generate`` translates ``--output-dir`` into the per-artifact
  path triple expected by ``cmd.generate_pir.main``.
* ``pir-generate --no-web`` skips ``beacon.web.launcher.launch_web``.
* ``pir-generate`` without ``--no-web`` invokes ``launch_web``.
* Direct ``cmd.<name>.main()`` invocation still emits the legacy
  ``DeprecationWarning`` to stderr (verifies the suppression toggle
  defaults to False).
"""

from __future__ import annotations

import io
from contextlib import redirect_stderr
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from beacon.cli import cli
from tests.conftest import load_cmd_module


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestRootHelpListsAllSubcommands:
    """`beacon --help` should advertise every committed subcommand."""

    EXPECTED = (
        "pir-generate",
        "assets-generate",
        "identity-generate",
        "accounts-generate",
        "submit-review",
        "taxonomy-refresh",
        "misp-cache-refresh",
        "web",
    )

    def test_help_exits_zero(self, runner):
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0

    @pytest.mark.parametrize("name", EXPECTED)
    def test_help_lists_each_subcommand(self, runner, name):
        result = runner.invoke(cli, ["--help"])
        assert name in result.output


class TestSubcommandHelpReachesDelegate:
    """Each subcommand's `--help` should succeed without invoking the delegate."""

    CASES = (
        "pir-generate",
        "assets-generate",
        "identity-generate",
        "accounts-generate",
        "submit-review",
        "taxonomy-refresh",
        "misp-cache-refresh",
        "web",
    )

    @pytest.mark.parametrize("name", CASES)
    def test_subcommand_help(self, runner, name):
        result = runner.invoke(cli, [name, "--help"])
        assert result.exit_code == 0
        assert name in result.output or "Options" in result.output


class TestPirGenerateOutputDirTranslation:
    """`pir-generate --output-dir X` must compose <X>/{pir_output.json,…}."""

    def test_output_dir_translates_to_three_paths(self, runner, tmp_path):
        out_dir = tmp_path / "run1"
        captured_argv: list[list[str]] = []

        def _fake_main(argv, *, _from_beacon_cli=False):
            captured_argv.append(list(argv))
            assert _from_beacon_cli is True
            return 0

        fake_generate_pir = MagicMock()
        fake_generate_pir.main = _fake_main
        with patch(
            "beacon.cli._load_cmd_module",
            return_value=fake_generate_pir,
        ):
            with patch("beacon.web.launcher.launch_web") as mock_launch:
                mock_launch.return_value = "http://127.0.0.1:5555/"
                result = runner.invoke(
                    cli,
                    [
                        "pir-generate",
                        "--context",
                        "fake.json",
                        "--output-dir",
                        str(out_dir),
                        "--no-web",
                    ],
                )

        assert result.exit_code == 0, result.output
        assert captured_argv, "delegate was never called"
        argv = captured_argv[0]
        assert argv[0:2] == ["--context", "fake.json"]
        # Three artifact paths are derived from --output-dir.
        assert "--output" in argv
        assert str(out_dir / "pir_output.json") in argv
        assert "--collection-plan" in argv
        assert str(out_dir / "collection_plan.md") in argv
        assert "--sources-candidate" in argv
        assert str(out_dir / "sources_candidate.yaml") in argv

    def test_no_sage_flag_passes_through(self, runner, tmp_path):
        captured_argv: list[list[str]] = []

        def _fake_main(argv, *, _from_beacon_cli=False):
            captured_argv.append(list(argv))
            return 0

        fake_module = MagicMock()
        fake_module.main = _fake_main
        with patch("beacon.cli._load_cmd_module", return_value=fake_module):
            with patch("beacon.web.launcher.launch_web"):
                result = runner.invoke(
                    cli,
                    [
                        "pir-generate",
                        "--context",
                        "fake.json",
                        "--output-dir",
                        str(tmp_path / "run"),
                        "--no-sage",
                        "--no-web",
                    ],
                )
        assert result.exit_code == 0, result.output
        assert "--no-sage" in captured_argv[0]


class TestPirGenerateNoWebSuppressesLauncher:
    """`pir-generate --no-web` MUST skip the web launcher."""

    def test_no_web_skips_launcher(self, runner, tmp_path):
        fake_module = MagicMock()
        fake_module.main = lambda argv, *, _from_beacon_cli=False: 0
        with patch("beacon.cli._load_cmd_module", return_value=fake_module):
            with patch("beacon.web.launcher.launch_web") as mock_launch:
                result = runner.invoke(
                    cli,
                    [
                        "pir-generate",
                        "--context",
                        "fake.json",
                        "--output-dir",
                        str(tmp_path / "run"),
                        "--no-web",
                    ],
                )
        assert result.exit_code == 0, result.output
        mock_launch.assert_not_called()

    def test_default_invokes_launcher(self, runner, tmp_path):
        fake_module = MagicMock()
        fake_module.main = lambda argv, *, _from_beacon_cli=False: 0
        with patch("beacon.cli._load_cmd_module", return_value=fake_module):
            with patch("beacon.web.launcher.launch_web") as mock_launch:
                mock_launch.return_value = "http://127.0.0.1:5555/"
                result = runner.invoke(
                    cli,
                    [
                        "pir-generate",
                        "--context",
                        "fake.json",
                        "--output-dir",
                        str(tmp_path / "run"),
                    ],
                )
        assert result.exit_code == 0, result.output
        mock_launch.assert_called_once()
        assert "http://127.0.0.1:5555/" in result.output


class TestSubcommandPassThrough:
    """Verb-noun subcommands pass extra args verbatim to the delegate."""

    CASES = (
        ("assets-generate", "generate_assets"),
        ("identity-generate", "generate_identity_assets"),
        ("accounts-generate", "generate_user_accounts"),
        ("submit-review", "submit_for_review"),
        ("taxonomy-refresh", "update_taxonomy"),
        ("misp-cache-refresh", "refresh_misp_cache"),
        ("web", "web_app"),
    )

    @pytest.mark.parametrize("subcommand,cmd_module", CASES)
    def test_extra_args_pass_through(self, runner, subcommand, cmd_module):
        captured: dict = {}

        def _fake_main(argv, *, _from_beacon_cli=False):
            captured["argv"] = list(argv)
            captured["beacon_flag"] = _from_beacon_cli
            return 0

        fake_module = MagicMock()
        fake_module.main = _fake_main
        with patch("beacon.cli._load_cmd_module", return_value=fake_module) as load_mock:
            result = runner.invoke(cli, [subcommand, "--alpha", "x", "--beta"])
        assert result.exit_code == 0, result.output
        load_mock.assert_called_once_with(cmd_module)
        assert captured["argv"] == ["--alpha", "x", "--beta"]
        assert captured["beacon_flag"] is True

    def test_delegate_failure_propagates_exit_code(self, runner):
        fake_module = MagicMock()
        fake_module.main = lambda argv, *, _from_beacon_cli=False: 7
        with patch("beacon.cli._load_cmd_module", return_value=fake_module):
            result = runner.invoke(cli, ["taxonomy-refresh"])
        assert result.exit_code == 7


class TestLegacyCmdEmitsDeprecation:
    """Direct `python -m cmd.<name>` invocation must still warn."""

    def test_submit_for_review_warns(self):
        mod = load_cmd_module("submit_for_review")
        buf = io.StringIO()
        with redirect_stderr(buf):
            try:
                mod.main(["--help"])
            except SystemExit:
                pass
        assert "DeprecationWarning" in buf.getvalue()
        assert "beacon submit-review" in buf.getvalue()

    def test_generate_pir_warns(self):
        mod = load_cmd_module("generate_pir")
        buf = io.StringIO()
        with redirect_stderr(buf):
            try:
                mod.main(["--help"])
            except SystemExit:
                pass
        assert "DeprecationWarning" in buf.getvalue()
        assert "beacon pir-generate" in buf.getvalue()

    def test_beacon_cli_suppresses_deprecation_banner(self):
        mod = load_cmd_module("submit_for_review")
        buf = io.StringIO()
        with redirect_stderr(buf):
            try:
                mod.main(["--help"], _from_beacon_cli=True)
            except SystemExit:
                pass
        assert "DeprecationWarning" not in buf.getvalue()
