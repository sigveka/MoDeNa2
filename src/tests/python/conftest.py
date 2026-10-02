"""
conftest.py — session-level setup for MoDeNa Python unit tests.

Stubs out heavy or environment-specific dependencies so that the Python
submodules (Launchpad, Registry, Runner) can be imported and tested without:
  - A running MongoDB instance
  - A compiled libmodena.so

Tests that need the installed MoDeNa tree (headers, libmodena) are marked
@pytest.mark.installed and run in every default invocation; they skip only
when nothing has been built.  Select a tier with ``ctest -L unit|installed``
or ``pytest -m installed``.  The tiers are defined in ../pytest.ini.

No test in this directory may be marked ``live``: the stub below replaces the
database connection, so a test that needs a real MongoDB belongs in
../interface-tests/.  test_suite_integrity.py enforces that.
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
def _discover_build_paths():
    """Locate the CMake-generated ``_paths.py`` for the build under test.

    The stub below shadows the installed ``modena`` package, so without this
    the stub carries no ``MODENA_INCLUDE_DIR`` / ``MODENA_LIB_DIR`` and no
    ``modena.libmodena``.  Every guard that asks "is modena installed?" then
    answers *no* on every machine, and the whole ``@pytest.mark.installed``
    tier skips permanently instead of conditionally -- which is exactly what
    it did until this was added.  ``test_suite_integrity.py`` fails if that
    silently regresses.

    ``_paths.py.in`` is a template, so the source tree never has a usable
    copy.  Look for a configured one, nearest first:

      1. ``MODENA_PATHS_FILE`` -- set by the CTest entry, so ctest always
         tests the tree it just built.
      2. any ``build*/src/python/_paths.py`` under the repository root.
      3. an installed ``modena/_paths.py`` on ``sys.path``, skipping the
         source tree itself.

    Returns the parsed name -> value mapping, or ``{}`` when MoDeNa has not
    been built or installed -- in which case the installed tier skips for
    a real reason.
    """
    candidates = []

    env_path = os.environ.get('MODENA_PATHS_FILE')
    if env_path:
        candidates.append(Path(env_path))

    _REPO_ROOT = _SRC_PYTHON.parent.parent
    candidates.extend(sorted(_REPO_ROOT.glob('build*/src/python/_paths.py')))

    for entry in sys.path:
        if not entry or Path(entry).resolve() == _SRC_PYTHON:
            continue
        candidates.append(Path(entry) / 'modena' / '_paths.py')

    for candidate in candidates:
        try:
            if not candidate.is_file():
                continue
            namespace = {}
            exec(compile(candidate.read_text(), str(candidate), 'exec'), namespace)
        except (OSError, SyntaxError, ValueError):
            continue
        if 'MODENA_LIB_DIR' in namespace:
            return {k: v for k, v in namespace.items() if k.startswith('MODENA_')}

    return {}


if 'modena' not in sys.modules:
    _pkg = types.ModuleType('modena')
    _pkg.__path__    = [str(_SRC_PYTHON)]
    _pkg.__package__ = 'modena'
    _pkg.__version__ = '0.0.0-test'

    # Publish the real installed paths on the stub.  Tests that compile a
    # surrogate need the include and lib directories the build actually used.
    _BUILD_PATHS = _discover_build_paths()
    for _name, _value in _BUILD_PATHS.items():
        setattr(_pkg, _name, _value)

    # Put the library directory on the package __path__ so `import
    # modena.libmodena` finds the extension through the normal import system
    # -- lazily, on first use.  Loading it eagerly here would defeat the point
    # of the stub, which exists to keep the unit tier free of libmodena and
    # MongoDB.
    _LIB_DIR = _BUILD_PATHS.get('MODENA_LIB_DIR')
    if _LIB_DIR and Path(_LIB_DIR).is_dir():
        _pkg.__path__.append(str(_LIB_DIR))

    sys.modules['modena'] = _pkg

# Ensure src/python is importable directly (for submodule imports)
if str(_SRC_PYTHON) not in sys.path:
    sys.path.insert(0, str(_SRC_PYTHON))

# Eagerly import modena.SurrogateModel now so its module-level
# ``mongoengine.connect(...)`` call fires against the MagicMock stub above,
# not against whatever real connection a later mongomock fixture installs.
# Otherwise, running an installed-tier test file in isolation triggers the
# import mid-fixture and blows up with "A different connection with alias
# `default` was already registered".
import modena.SurrogateModel  # noqa: F401 — imported for its side effect


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
