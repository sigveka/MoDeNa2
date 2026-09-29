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

Together, nothing in the ``@pytest.mark.integration`` tier (now split into
``installed`` and ``live``) could execute by any invocation.  The tests below
fail rather than skip if either returns.

The tiers themselves are checked too: every CTest entry must carry exactly one
of the labels ``unit`` / ``installed`` / ``live``, and every pytest file that
CTest runs with ``-m <tier>`` must actually carry that marker -- otherwise the
selection deselects it and it passes by never running.

The oracle for "is there a build to test?" is deliberately the filesystem, not
anything the suite configures -- otherwise these guards could be disabled by
the same mistake they are meant to catch.
"""

import os
import re
import sys
from pathlib import Path

import pytest


_TESTS_PY_DIR = Path(__file__).parent.resolve()
_REPO_ROOT    = _TESTS_PY_DIR.parent.parent.parent.resolve()
_IFACE_DIR    = _TESTS_PY_DIR.parent / 'interface-tests'

#: The CTest tier labels, mirroring the markers in src/tests/pytest.ini.
TIERS = ('unit', 'installed', 'live')


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
# The installed tier must be reachable
# ---------------------------------------------------------------------------

@needs_a_build
class TestInstalledTierIsReachable:

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

    def test_the_installed_marker_is_actually_used(self):
        """A tier with no members is not a tier."""
        marked = [
            path for path in _TESTS_PY_DIR.glob('test_*.py')
            if _uses_marker(path, 'installed')
        ]
        assert marked, 'no test carries @pytest.mark.installed'


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
# Every test belongs to exactly one tier
# ---------------------------------------------------------------------------

def _ctest_entries():
    """``{test name: [[labels], ...]}`` for every add_test() under src/.

    One inner list per set_tests_properties(... LABELS) call naming the test,
    so a test registered in both arms of an if/elseif (the MATLAB smoke) is
    judged per registration rather than as the union of both.  Parsed
    statically from the CMakeLists files so the check needs no build
    directory.  A test with no LABELS anywhere maps to an empty list.
    """
    entries = {}
    for cmakelists in (_REPO_ROOT / 'src').rglob('CMakeLists.txt'):
        text = '\n'.join(
            line for line in cmakelists.read_text().splitlines()
            if not line.lstrip().startswith('#')
        )
        for name in re.findall(r'add_test\(\s*NAME\s+(\w+)', text):
            entries.setdefault(name, [])
        for body in re.findall(r'set_tests_properties\((.*?)\)', text, re.S):
            names, _, props = body.partition('PROPERTIES')
            labels = re.search(r'LABELS\s+"([^"]*)"', props)
            if not labels:
                continue
            for name in names.split():
                entries.setdefault(name, []).append(labels.group(1).split(';'))
    return entries


def _uses_marker(path, marker):
    """True when *path* applies ``pytest.mark.<marker>`` as code, not text."""
    return re.search(
        rf'^\s*(@pytest\.mark\.{marker}\b'
        rf'|pytestmark\s*=.*pytest\.mark\.{marker}\b)',
        path.read_text(), re.M,
    ) is not None


def _pytestmark_tier(path):
    """The tier named by a module-level ``pytestmark``, or None."""
    match = re.search(r'^pytestmark\s*=\s*pytest\.mark\.(\w+)',
                      path.read_text(), re.M)
    return match.group(1) if match else None


class TestTiersAreAssigned:

    def test_ctest_entries_were_found(self):
        """Guards the parser: an empty result would make the rest vacuous."""
        entries = _ctest_entries()
        assert 'modena_python_unit' in entries
        assert 'modena_iface_cpp_smoke' in entries

    def test_every_ctest_entry_has_exactly_one_tier(self):
        """`ctest -L <tier>` must partition the suite.

        A test with no tier is run by nobody who selects by tier; a test with
        two is run twice and belongs to neither.  The retired `integration`
        label meant three different things at once -- needs an install, needs
        a live database, needs a fitted model -- which is why it is rejected
        by name as well.
        """
        problems = []
        for name, registrations in sorted(_ctest_entries().items()):
            if not registrations:
                problems.append(f'{name}: no LABELS at all')
            for labels in registrations:
                tiers = [label for label in labels if label in TIERS]
                if len(tiers) != 1:
                    problems.append(
                        f'{name}: tiers {tiers or "none"} in {labels}')
                if 'integration' in labels:
                    problems.append(f'{name}: retired label `integration`')
        assert not problems, (
            f'each CTest entry needs exactly one of {TIERS}:\n  '
            + '\n  '.join(problems)
        )

    def test_no_live_test_under_python(self):
        """conftest.py here stubs the database, so `live` cannot pass here."""
        offenders = [
            path.name for path in _TESTS_PY_DIR.glob('test_*.py')
            if _uses_marker(path, 'live')
        ]
        assert not offenders, (
            f'live-tier tests belong in interface-tests/: {offenders}'
        )

    @pytest.mark.parametrize(
        'path', sorted(_IFACE_DIR.glob('test_*.py')), ids=lambda p: p.name,
    )
    def test_interface_pytest_file_matches_its_ctest_selection(self, path):
        """CTest runs each of these with `-m <tier>`: the marks must agree.

        A test lacking the mark is deselected by that `-m` and reports as
        passed without running.
        """
        tier = _pytestmark_tier(path)
        assert tier in TIERS, (
            f'{path.name} needs a module-level `pytestmark = '
            f'pytest.mark.<tier>` with tier in {TIERS}'
        )
        cmake = (_IFACE_DIR / 'CMakeLists.txt').read_text()
        selected = re.search(
            re.escape(path.name) + r'"?\s+-m\s+"?(\w+)', cmake,
        )
        assert selected, f'{path.name} is not run by any CTest entry'
        assert selected.group(1) == tier, (
            f'{path.name} is marked `{tier}` but CTest selects '
            f'`-m {selected.group(1)}`'
        )


# ---------------------------------------------------------------------------
# Skips must be justified
# ---------------------------------------------------------------------------

#: Set in the environment of the child pytest run TestSkipsAreHonest starts.
_SKIP_AUDIT_CHILD = 'MODENA_SKIP_AUDIT_CHILD'


@needs_a_build
class TestSkipsAreHonest:

    def test_no_skip_reason_claims_modena_is_missing(self):
        """Run the suite and reject any skip blaming a missing MoDeNa.

        Catches new guards that repeat the original mistake, not just the two
        already fixed.

        The child run must not start this test again.  It used to exclude it
        with ``--deselect <file>::TestSkipsAreHonest``, but a deselect nodeid
        is relative to pytest's rootdir: when src/tests/pytest.ini moved the
        rootdir up a level the nodeid stopped matching, and every child
        spawned another child.  An environment flag does not depend on where
        the rootdir is.
        """
        import subprocess

        if os.environ.get(_SKIP_AUDIT_CHILD):
            pytest.skip('inside the audit run this test started')

        result = subprocess.run(
            [sys.executable, '-m', 'pytest', str(_TESTS_PY_DIR),
             '-q', '-rs', '-p', 'no:cacheprovider'],
            capture_output=True, text=True, cwd=str(_TESTS_PY_DIR),
            env={**os.environ, _SKIP_AUDIT_CHILD: '1'},
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
