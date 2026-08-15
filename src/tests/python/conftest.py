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

# Eagerly import modena.SurrogateModel now so its module-level
# ``mongoengine.connect(...)`` call fires against the MagicMock stub above,
# not against whatever real connection a later mongomock fixture installs.
# Otherwise, running an integration test file in isolation triggers the
# import mid-fixture and blows up with "A different connection with alias
# `default` was already registered".
import modena.SurrogateModel  # noqa: F401 — imported for its side effect


# ---------------------------------------------------------------------------
# Custom markers
# ---------------------------------------------------------------------------
def pytest_configure(config):
    config.addinivalue_line(
        'markers',
        'integration: requires a live MongoDB instance and the full modena stack',
    )


# ---------------------------------------------------------------------------
# mongomock fixture — an in-memory MongoDB backing SurrogateModel documents
# ---------------------------------------------------------------------------

@pytest.fixture
def mongo_db():
    """Per-test in-memory MongoDB via mongomock.

    Yields the mongoengine connection alias.  On teardown the database is
    dropped and the global ``mongoengine.connect`` MagicMock stub reinstated
    so subsequent unit tests remain isolated.

    Usage::

        def test_saves_model(mongo_db):
            from modena.SurrogateModel import BackwardMappingModel
            m = BackwardMappingModel(...)
            m.save()
            reloaded = BackwardMappingModel.objects.first()
            assert reloaded._id == m._id

    Tests using this fixture pay a small setup/teardown cost (~5 ms) but
    exercise the real MongoEngine query path — the MagicMock stub used
    everywhere else cannot answer even ``Model.objects(...)`` calls.
    """
    import mongomock
    import mongoengine

    # Suspend the global connect() patch installed at module import.
    _connect_patcher.stop()

    alias = 'modena-test'
    mongoengine.disconnect(alias=alias)
    mongoengine.connect(
        db='modena-test',
        host='localhost',
        alias=alias,
        mongo_client_class=mongomock.MongoClient,
    )
    # Also register as the default alias so SurrogateModel documents (which
    # were declared without an explicit meta={'db_alias': ...}) resolve here.
    mongoengine.disconnect()
    mongoengine.connect(
        db='modena-test',
        host='localhost',
        mongo_client_class=mongomock.MongoClient,
    )
    try:
        yield alias
    finally:
        # Drop everything before disconnecting so the next test starts fresh
        conn = mongoengine.get_connection()
        conn.drop_database('modena-test')
        mongoengine.disconnect()
        mongoengine.disconnect(alias=alias)
        # Reinstate the global MagicMock stub for other tests
        _connect_patcher.start()
