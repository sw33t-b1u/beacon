"""Tests for src/beacon/web/launcher.py (Initiative H Phase 6).

The launcher spawns ``cmd/web_app.py`` in a detached subprocess on a
free local port, polls until the server returns HTTP, and returns the
URL. These tests never actually spin up uvicorn — both the readiness
probe (httpx) and the process spawn (subprocess.Popen) are mocked.

Coverage:

* Subprocess command line contains ``cmd/web_app.py`` plus the chosen
  ``--host`` and ``--port`` overrides.
* ``BEACON_OUTPUT_DIR`` is forwarded to the child env, resolved to an
  absolute path.
* Readiness probe is consulted; success returns the URL.
* On readiness timeout the URL is still returned (operator can refresh).
* When an explicit ``port=`` is given, the launcher does NOT pick a
  random free port.
* ``start_new_session=True`` is set on POSIX so the child outlives the
  parent CLI invocation.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from beacon.web import launcher


@pytest.fixture
def fake_popen():
    """Patch subprocess.Popen and capture the call arguments."""
    with patch("beacon.web.launcher.subprocess.Popen") as mock_popen:
        mock_popen.return_value = MagicMock(pid=12345)
        yield mock_popen


@pytest.fixture
def ready_immediately():
    """Stub httpx.get so the readiness probe returns 200 on first call."""
    fake_response = MagicMock()
    fake_response.status_code = 200
    with patch("beacon.web.launcher.httpx.get", return_value=fake_response) as mock_get:
        yield mock_get


class TestLaunchWebDispatch:
    def test_returns_url_with_explicit_port(self, fake_popen, ready_immediately, tmp_path):
        url = launcher.launch_web(tmp_path, port=58123)
        assert url == "http://127.0.0.1:58123/"

    def test_calls_cmd_web_app_script(self, fake_popen, ready_immediately, tmp_path):
        launcher.launch_web(tmp_path, port=58124)
        cmd_args = fake_popen.call_args[0][0]
        assert any("cmd/web_app.py" in str(arg) or arg.endswith("web_app.py") for arg in cmd_args)

    def test_passes_host_and_port_to_subprocess(self, fake_popen, ready_immediately, tmp_path):
        launcher.launch_web(tmp_path, port=58125)
        cmd_args = fake_popen.call_args[0][0]
        assert "--host" in cmd_args
        assert "--port" in cmd_args
        assert "58125" in cmd_args

    def test_picks_free_port_when_none(self, fake_popen, ready_immediately, tmp_path):
        with patch("beacon.web.launcher._find_free_port", return_value=49999):
            url = launcher.launch_web(tmp_path)
        assert url == "http://127.0.0.1:49999/"
        assert "49999" in fake_popen.call_args[0][0]


class TestLaunchWebEnvForwarding:
    def test_beacon_output_dir_is_absolute(self, fake_popen, ready_immediately, tmp_path):
        relative_path = Path("output")  # deliberately relative
        launcher.launch_web(relative_path, port=58126)
        env = fake_popen.call_args.kwargs["env"]
        assert "BEACON_OUTPUT_DIR" in env
        assert os.path.isabs(env["BEACON_OUTPUT_DIR"])

    def test_beacon_output_dir_value_round_trip(self, fake_popen, ready_immediately, tmp_path):
        launcher.launch_web(tmp_path, port=58127)
        env = fake_popen.call_args.kwargs["env"]
        assert env["BEACON_OUTPUT_DIR"] == str(tmp_path.resolve())

    def test_parent_env_inherited(self, fake_popen, ready_immediately, tmp_path, monkeypatch):
        monkeypatch.setenv("SAGE_API_URL", "http://sage.example/")
        launcher.launch_web(tmp_path, port=58128)
        env = fake_popen.call_args.kwargs["env"]
        assert env["SAGE_API_URL"] == "http://sage.example/"


class TestReadinessTimeout:
    def test_returns_url_even_on_timeout(self, fake_popen, tmp_path):
        # Every readiness probe raises ConnectError → wait_for_ready falls
        # through to False, but the URL is still returned.
        with patch(
            "beacon.web.launcher.httpx.get",
            side_effect=httpx.ConnectError("not yet"),
        ):
            url = launcher.launch_web(tmp_path, port=58129, timeout=0.05)
        assert url == "http://127.0.0.1:58129/"


class TestPosixDetached:
    def test_start_new_session_set_on_posix(self, fake_popen, ready_immediately, tmp_path):
        launcher.launch_web(tmp_path, port=58130)
        kwargs = fake_popen.call_args.kwargs
        if os.name == "posix":
            assert kwargs.get("start_new_session") is True


class TestWaitForReady:
    def test_success_returns_true_quickly(self):
        ok = MagicMock()
        ok.status_code = 200
        with patch("beacon.web.launcher.httpx.get", return_value=ok):
            assert launcher._wait_for_ready("http://127.0.0.1:1/", timeout=1.0) is True

    def test_timeout_returns_false(self):
        with patch(
            "beacon.web.launcher.httpx.get",
            side_effect=httpx.ConnectError("nope"),
        ):
            assert launcher._wait_for_ready("http://127.0.0.1:1/", timeout=0.05) is False

    def test_5xx_keeps_waiting(self):
        err = MagicMock()
        err.status_code = 503
        with patch("beacon.web.launcher.httpx.get", return_value=err):
            assert launcher._wait_for_ready("http://127.0.0.1:1/", timeout=0.05) is False
