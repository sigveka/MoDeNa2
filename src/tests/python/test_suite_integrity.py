"""
Tests about the test suite itself.
-----------------------------------

A skipped test reads as "not applicable here".  These check that it is not
instead "unreachable everywhere".

Both failure modes were live in this repository until 2026-09-29:

* ``conftest.py`` installs a stub ``modena`` package so the unit tier does not
  need libmodena, rpy2 or MongoDB.  The stub carried none of the installed
  paths, so ``_modena_installed()`` in ``test_compile_surrogate.py`` returned
  False on every machine and its 11 tests skipped permanently -- with the
  reason "modena not installed" on a machine where it was installed.
* The ``modena_python_integration`` CTest entry was ``DISABLED TRUE`` with a
  comment saying to "enable with ctest -L integration".  ``DISABLED`` overrides
  label selection, so that command silently listed every other test and never
  this one.

Together, nothing in the ``@pytest.mark.integration`` tier could execute by
any invocation.  The tests below fail rather than skip if either returns.

The oracle for "is there a build to test?" is deliberately the filesystem, not
anything the suite configures -- otherwise these guards could be disabled by
the same mistake they are meant to catch.
"""

import os
import sys
from pathlib import Path

import pytest


_TESTS_PY_DIR = Path(__file__).parent.resolve()
_REPO_ROOT    = _TESTS_PY_DIR.parent.parent.parent.resolve()


def _build_exists_on_disk():
    """Independent evidence that MoDeNa has been built or installed.

    Does not consult conftest, ``modena``, or any guard under test.
    """
    if os.environ.get('MODENA_PATHS_FILE'):
        return Path(os.environ['MODENA_PATHS_FILE']).is_file()
    if any(_REPO_ROOT.glob('build*/src/python/_paths.py')):
        return True
    return any(
        (Path(entry) / 'modena' / '_paths.py').is_file()
        for entry in sys.path
        if entry
    )


#: Skipping *these* is honest only when there is genuinely nothing built.
needs_a_build = pytest.mark.skipif(
    not _build_exists_on_disk(),
    reason='MoDeNa has not been built or installed on this machine',
)


# ---------------------------------------------------------------------------
# The integration tier must be reachable
# ---------------------------------------------------------------------------

@needs_a_build
class TestIntegrationTierIsReachable:

    def test_conftest_publishes_the_build_paths(self):
        """The stub must carry the real include and lib directories."""
        import modena
        for name in ('MODENA_INCLUDE_DIR', 'MODENA_LIB_DIR'):
            assert hasattr(modena, name), (
                f'conftest stub does not expose {name}; every guard asking '
                f'"is modena built?" will answer no and its tests will skip '
                f'on every machine'
            )

    def test_published_paths_point_at_real_directories(self):
        import modena
        for name in ('MODENA_INCLUDE_DIR', 'MODENA_LIB_DIR'):
            path = Path(getattr(modena, name))
            assert path.is_dir(), f'{name} is not a directory: {path}'

    def test_libmodena_is_importable(self):
        """`pytest.importorskip('modena.libmodena')` must be able to succeed."""
        import importlib
        try:
            importlib.import_module('modena.libmodena')
        except ImportError as exc:
            pytest.fail(
                f'modena.libmodena is not importable under pytest ({exc}); '
                f'every importorskip on it skips unconditionally'
            )

    def test_the_installed_guard_agrees_with_the_filesystem(self):
        """`_modena_installed()` must not answer False beside a real build."""
        sys.path.insert(0, str(_TESTS_PY_DIR))
        try:
            from test_compile_surrogate import _modena_installed
        finally:
            sys.path.pop(0)
        assert _modena_installed(), (
            '_modena_installed() is False although a build exists; the tests '
            'it guards would skip with a reason that is not true'
        )

    def test_the_integration_marker_is_actually_used(self):
        """A tier with no members is not a tier."""
        marked = [
            path for path in _TESTS_PY_DIR.glob('test_*.py')
            if 'pytest.mark.integration' in path.read_text()
        ]
        assert marked, 'no test carries @pytest.mark.integration'


# ---------------------------------------------------------------------------
# No CTest entry may be switched off
# ---------------------------------------------------------------------------

class TestNoCTestEntryIsDisabled:

    def test_no_cmake_test_sets_disabled(self):
        """`DISABLED TRUE` cannot be undone by `ctest -L <label>`.

        CMake's DISABLED property removes a test from every invocation, label
        selection included.  A suite that wants a tier to be opt-in should say
        so with a label and `ctest -LE`, so that the default run still reports
        it rather than pretending it does not exist.
        """
        offenders = []
        for cmakelists in (_REPO_ROOT / 'src').rglob('CMakeLists.txt'):
            text = cmakelists.read_text()
            for number, line in enumerate(text.splitlines(), start=1):
                stripped = line.strip()
                if stripped.startswith('#'):
                    continue
                if 'DISABLED' in stripped and 'TRUE' in stripped:
                    rel = cmakelists.relative_to(_REPO_ROOT)
                    offenders.append(f'{rel}:{number}: {stripped}')
        assert not offenders, (
            'CTest entries are disabled outright:\n  ' + '\n  '.join(offenders)
        )


# ---------------------------------------------------------------------------
# Skips must be justified
# ---------------------------------------------------------------------------

@needs_a_build
class TestSkipsAreHonest:

    def test_no_skip_reason_claims_modena_is_missing(self):
        """Run the suite and reject any skip blaming a missing MoDeNa.

        Catches new guards that repeat the original mistake, not just the two
        already fixed.
        """
        import subprocess

        result = subprocess.run(
            [sys.executable, '-m', 'pytest', str(_TESTS_PY_DIR),
             '-q', '-rs', '-p', 'no:cacheprovider',
             '--deselect', f'{Path(__file__).name}::TestSkipsAreHonest'],
            capture_output=True, text=True, cwd=str(_TESTS_PY_DIR),
        )
        suspicious = [
            line for line in result.stdout.splitlines()
            if line.startswith('SKIPPED')
            and any(
                phrase in line.lower()
                for phrase in ('not installed', 'not built', 'no module named')
            )
        ]
        assert not suspicious, (
            'tests skipped claiming MoDeNa is unavailable, but it is built '
            'here:\n  ' + '\n  '.join(suspicious)
        )
