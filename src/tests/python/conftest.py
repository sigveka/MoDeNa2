"""
conftest.py — session-level setup for MoDeNa Python unit tests.

Stubs out heavy or environment-specific dependencies so that the Python
submodules (Launchpad, Registry, Runner) can be imported and tested without:
  - A running MongoDB instance
  - A compiled libmodena.so

Tests that do require the full stack are marked @pytest.mark.integration
and are skipped by default (run with: ctest -L integration  or
pytest -m integration).
"""

import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Locate source tree
# ---------------------------------------------------------------------------
_TESTS_PY_DIR = Path(__file__).parent.resolve()
_SRC_PYTHON   = (_TESTS_PY_DIR.parent.parent / 'python').resolve()

# ---------------------------------------------------------------------------
# Patch mongoengine.connect globally so SurrogateModel.py's module-level
# connect() call becomes a no-op.  This avoids needing a live MongoDB or
# the mongomock package just to import the module.
# ---------------------------------------------------------------------------
import mongoengine as _me
_connect_patcher = patch('mongoengine.connect', return_value=MagicMock())
_connect_patcher.start()

os.environ.setdefault('MODENA_URI', 'mongodb://localhost/testdb')

# ---------------------------------------------------------------------------
# Create a minimal 'modena' package stub in sys.modules.
# This prevents __init__.py from running (which would load libmodena.so,
# call rinterface.initr(), and connect to MongoDB).  Submodule imports such
# as 'from modena.Launchpad import X' still work because __path__ points at
# the source tree.
# ---------------------------------------------------------------------------
if 'modena' not in sys.modules:
    _pkg = types.ModuleType('modena')
    _pkg.__path__    = [str(_SRC_PYTHON)]
    _pkg.__package__ = 'modena'
    _pkg.__version__ = '0.0.0-test'
    sys.modules['modena'] = _pkg

# Ensure src/python is importable directly (for submodule imports)
if str(_SRC_PYTHON) not in sys.path:
    sys.path.insert(0, str(_SRC_PYTHON))


# ---------------------------------------------------------------------------
# Custom markers
# ---------------------------------------------------------------------------
def pytest_configure(config):
    config.addinivalue_line(
        'markers',
        'integration: requires a live MongoDB instance and the full modena stack',
    )
