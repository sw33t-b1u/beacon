"""Test configuration and shared helpers.

Provides load_cmd_module() to import scripts from the cmd/ directory
without conflicting with Python's stdlib 'cmd' module.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_CMD_DIR = Path(__file__).parent.parent / "cmd"


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
