"""Test configuration and shared helpers.

Provides load_cmd_module() to import scripts from the cmd/ directory
without conflicting with Python's stdlib 'cmd' module, and
load_scripts_module() to import scripts from the scripts/ directory.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# Ambient environment variables that make the test suite non-hermetic.
# cmd/*.py call load_dotenv() at import time, so the developer's .env leaks
# into os.environ mid-session as soon as any test imports a cmd module:
#   - SAGE_API_URL: unmocked web routes then attempt real SAGE connections
#     (httpx, 5-10s timeout per call).
#   - BEACON_STORAGE(=gcs)/BEACON_STORAGE_*: unmocked routes build a REAL
#     GCSStorage client and hang on network (observed: full-suite stall at
#     TestDashboardRoute while the same test is instant standalone).
#   - GCP_PROJECT_ID: a missed LLM mock then builds a real Vertex AI client.
#   - GHE_TOKEN/GHE_REPO: review submission paths could reach GitHub.
#   - *_PROXY: an ambient SOCKS/HTTP proxy redirects httpx and can require
#     the optional 'socksio' dependency, turning failures into ImportError.
# Scrubbing them for every test makes the suite deterministic and fast
# regardless of the developer's shell or .env. Tests that need any of these
# must set them explicitly via monkeypatch AND mock the network layer.
_AMBIENT_ENV_KEYS_TO_SCRUB = (
    "SAGE_API_URL",
    "GCP_PROJECT_ID",
    "TRACE_ROOT_PATH",
    "ALL_PROXY",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)
_AMBIENT_ENV_PREFIXES_TO_SCRUB = ("BEACON_", "GHE_")


@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch):
    """Scrub ambient product/proxy env so tests never attempt real network."""
    import os  # noqa: PLC0415

    for _key in _AMBIENT_ENV_KEYS_TO_SCRUB:
        monkeypatch.delenv(_key, raising=False)
    for _key in list(os.environ):
        if _key.startswith(_AMBIENT_ENV_PREFIXES_TO_SCRUB):
            monkeypatch.delenv(_key, raising=False)


_PROJECT_ROOT = str(Path(__file__).parent.parent)
_CMD_DIR = Path(__file__).parent.parent / "cmd"
_SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"

# Move the project root and cmd/ directory to the end of sys.path so that
# Python's stdlib modules (e.g. 'cmd' used by pdb) are resolved before
# BEACON's cmd/ directory.
for _p in (_PROJECT_ROOT, str(_CMD_DIR)):
    if _p in sys.path:
        sys.path.remove(_p)
        sys.path.append(_p)


def load_cmd_module(name: str):
    """Load a script from cmd/<name>.py as a module, bypassing stdlib 'cmd' conflict.

    The module is cached in sys.modules as '_beacon_cmd_<name>' so repeated
    calls return the same object (important for patch() to work correctly).
    """
    cache_key = f"_beacon_cmd_{name}"
    if cache_key in sys.modules:
        return sys.modules[cache_key]

    path = _CMD_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(cache_key, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[cache_key] = module
    spec.loader.exec_module(module)
    return module


def load_scripts_module(name: str):
    """Load a script from scripts/<name>.py as a module.

    The module is cached in sys.modules as '_beacon_scripts_<name>' so
    repeated calls return the same object.
    """
    cache_key = f"_beacon_scripts_{name}"
    if cache_key in sys.modules:
        return sys.modules[cache_key]

    path = _SCRIPTS_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(cache_key, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[cache_key] = module
    spec.loader.exec_module(module)
    return module
