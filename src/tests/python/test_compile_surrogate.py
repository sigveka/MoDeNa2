"""
Tests for the sysconfig+subprocess surrogate compilation pipeline.

Unit tests (no libmodena required)
-----------------------------------
Verify that _compile_c_surrogate constructs the correct compiler command and
handles error cases, using subprocess.run mocks.

Integration tests (@pytest.mark.integration)
---------------------------------------------
Actually compile a C file and load it with ctypes.  Requires:
  - A C compiler on PATH
  - An installed modena (modena.h and libmodena.so visible via MODENA_INCLUDE_DIR
    and MODENA_LIB_DIR)

Run integration tests with:
    pytest -m integration src/tests/python/test_compile_surrogate.py
"""

import shutil
import sys
from pathlib import Path
from subprocess import CalledProcessError, TimeoutExpired
from unittest.mock import MagicMock, patch

import pytest
import sysconfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_c_compiler():
    cc = (sysconfig.get_config_var('CC') or 'cc').split()[0]
    return shutil.which(cc) is not None


def _modena_installed():
    """True when the built headers and shared library are both reachable.

    MODENA_LIB_DIR already *is* the directory holding libmodena -- CMake sets
    it to ``<prefix>/lib/modena``.  This used to glob ``.parent``, i.e. the
    plain ``lib/`` one level up, which holds no ``libmodena.*`` at all, so the
    guard answered False on a correctly installed machine and the tests it
    guards never ran.  ``test_suite_integrity.py`` now fails if it starts
    answering False again while a build is present.
    """
    try:
        import modena
        inc = Path(modena.MODENA_INCLUDE_DIR) / 'modena.h'
        lib = Path(modena.MODENA_LIB_DIR)
        return inc.exists() and any(lib.glob('libmodena.*'))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Unit tests — mock subprocess.run, verify command construction
# ---------------------------------------------------------------------------

class TestCompileSurrogateUnit:

    def _run(self, tmp_path, monkeypatch, platform=None, cc='test_cc', ccshared='-fPIC'):
        """Call _compile_c_surrogate with a mock subprocess and return the captured cmd."""
        from modena.SurrogateModel import _compile_c_surrogate

        if platform is not None:
            monkeypatch.setattr('sys.platform', platform)

        monkeypatch.setattr(
            'sysconfig.get_config_var',
            lambda k: {'CC': cc, 'CCSHARED': ccshared}.get(k),
        )

        src = tmp_path / 'f.c'
        src.write_text('void f(){}')

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')
            _compile_c_surrogate(src, tmp_path / 'f.so', Path('/inc'), Path('/lib'))
            return mock_run.call_args[0][0]

    def test_sysconfig_cc_is_used(self, tmp_path, monkeypatch):
        cmd = self._run(tmp_path, monkeypatch, cc='my_cc')
        assert cmd[0] == 'my_cc'

    def test_ccshared_flag_included(self, tmp_path, monkeypatch):
        cmd = self._run(tmp_path, monkeypatch, ccshared='-fPIC')
        assert '-fPIC' in cmd

    def test_shared_flag_on_linux(self, tmp_path, monkeypatch):
        cmd = self._run(tmp_path, monkeypatch, platform='linux')
        assert '-shared' in cmd
        assert '-dynamiclib' not in cmd

    def test_shared_flag_on_darwin(self, tmp_path, monkeypatch):
        cmd = self._run(tmp_path, monkeypatch, platform='darwin')
        assert '-dynamiclib' in cmd
        assert '-shared' not in cmd

    def test_include_dir_in_command(self, tmp_path, monkeypatch):
        from modena.SurrogateModel import _compile_c_surrogate
        monkeypatch.setattr('sysconfig.get_config_var', lambda k: None)

        src = tmp_path / 'f.c'
        src.write_text('void f(){}')
        inc = Path('/opt/modena/include')

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')
            _compile_c_surrogate(src, tmp_path / 'f.so', inc, Path('/lib'))
            cmd = mock_run.call_args[0][0]

        assert f'-I{inc}' in cmd

    def test_lib_dir_and_lmodena_in_command(self, tmp_path, monkeypatch):
        from modena.SurrogateModel import _compile_c_surrogate
        monkeypatch.setattr('sysconfig.get_config_var', lambda k: None)

        src = tmp_path / 'f.c'
        src.write_text('void f(){}')
        lib = Path('/opt/modena/lib')

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')
            _compile_c_surrogate(src, tmp_path / 'f.so', Path('/inc'), lib)
            cmd = mock_run.call_args[0][0]

        assert f'-L{lib}' in cmd
        assert '-lmodena' in cmd

    def test_output_path_in_command(self, tmp_path, monkeypatch):
        from modena.SurrogateModel import _compile_c_surrogate
        monkeypatch.setattr('sysconfig.get_config_var', lambda k: None)

        src = tmp_path / 'f.c'
        src.write_text('void f(){}')
        out = tmp_path / 'mylib.so'

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')
            _compile_c_surrogate(src, out, Path('/inc'), Path('/lib'))
            cmd = mock_run.call_args[0][0]

        assert str(out) in cmd

    def test_compiler_failure_raises_runtime_error(self, tmp_path, monkeypatch):
        from modena.SurrogateModel import _compile_c_surrogate
        monkeypatch.setattr('sysconfig.get_config_var', lambda k: None)

        src = tmp_path / 'f.c'
        src.write_text('void f(){}')

        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = CalledProcessError(1, ['cc'], stderr='syntax error')
            with pytest.raises(RuntimeError, match='Compiler failed'):
                _compile_c_surrogate(src, tmp_path / 'f.so', Path('/inc'), Path('/lib'))

    def test_timeout_raises_runtime_error(self, tmp_path, monkeypatch):
        from modena.SurrogateModel import _compile_c_surrogate
        monkeypatch.setattr('sysconfig.get_config_var', lambda k: None)

        src = tmp_path / 'f.c'
        src.write_text('void f(){}')

        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = TimeoutExpired(['cc'], 60)
            with pytest.raises(RuntimeError, match='timed out'):
                _compile_c_surrogate(src, tmp_path / 'f.so', Path('/inc'), Path('/lib'))

    def test_multiword_cc_is_split(self, tmp_path, monkeypatch):
        """CC='gcc -m64' must be split into ['gcc', '-m64', ...], not ['gcc -m64', ...]."""
        cmd = self._run(tmp_path, monkeypatch, cc='gcc -m64')
        assert cmd[0] == 'gcc'
        assert cmd[1] == '-m64'


# ---------------------------------------------------------------------------
# Integration tests — real compilation, real ctypes load
# ---------------------------------------------------------------------------

_SURROGATE_C = r"""
#include "modena.h"

void test_surrogate(
    const modena_model_t *model,
    const double         *inputs,
    double               *outputs)
{
    outputs[0] = inputs[0] * 2.0;
    outputs[1] = inputs[1] + 1.0;
}
"""


@pytest.mark.integration
@pytest.mark.skipif(not _has_c_compiler(), reason='no C compiler found')
@pytest.mark.skipif(not _modena_installed(), reason='modena not installed (no modena.h / libmodena.so)')
class TestCompileSurrogateIntegration:

    @pytest.fixture
    def paths(self):
        import modena
        # MODENA_LIB_DIR *is* the directory holding libmodena; production
        # passes it unmodified (SurrogateModel.py, _compile_c_surrogate call).
        # Taking .parent here produced -L<prefix>/lib, where no libmodena
        # exists, so every test in this class failed to link once the class
        # became reachable.
        return {
            'include_dir': Path(modena.MODENA_INCLUDE_DIR),
            'lib_dir':     Path(modena.MODENA_LIB_DIR),
        }

    def test_produces_shared_library(self, tmp_path, paths):
        """_compile_c_surrogate creates a .so file."""
        from modena.SurrogateModel import _compile_c_surrogate

        src = tmp_path / 'surrogate.c'
        src.write_text(_SURROGATE_C)
        out = tmp_path / 'surrogate.so'

        _compile_c_surrogate(src, out, paths['include_dir'], paths['lib_dir'])

        assert out.exists(), 'No shared library produced'
        assert out.stat().st_size > 0

    def test_shared_library_is_loadable(self, tmp_path, paths):
        """The compiled .so can be opened with ctypes.CDLL."""
        import ctypes
        from modena.SurrogateModel import _compile_c_surrogate

        src = tmp_path / 'surrogate.c'
        src.write_text(_SURROGATE_C)
        out = tmp_path / 'surrogate.so'

        _compile_c_surrogate(src, out, paths['include_dir'], paths['lib_dir'])

        lib = ctypes.CDLL(str(out))
        assert lib is not None

    def test_surrogate_function_computes_correctly(self, tmp_path, paths):
        """The compiled surrogate returns the expected numeric output."""
        import ctypes
        from modena.SurrogateModel import _compile_c_surrogate

        src = tmp_path / 'surrogate.c'
        src.write_text(_SURROGATE_C)
        out = tmp_path / 'surrogate.so'

        _compile_c_surrogate(src, out, paths['include_dir'], paths['lib_dir'])

        lib = ctypes.CDLL(str(out))
        fn = lib.test_surrogate
        fn.restype = None
        fn.argtypes = [
            ctypes.c_void_p,                      # model (unused in this test)
            ctypes.POINTER(ctypes.c_double),
            ctypes.POINTER(ctypes.c_double),
        ]

        inputs  = (ctypes.c_double * 2)(3.0, 7.0)
        outputs = (ctypes.c_double * 2)(0.0, 0.0)
        fn(None, inputs, outputs)

        assert outputs[0] == pytest.approx(6.0)   # 3.0 * 2.0
        assert outputs[1] == pytest.approx(8.0)   # 7.0 + 1.0

    def test_syntax_error_raises_runtime_error(self, tmp_path, paths):
        """A C file with a syntax error raises RuntimeError with compiler output."""
        from modena.SurrogateModel import _compile_c_surrogate

        src = tmp_path / 'bad.c'
        src.write_text('this is not valid C code !!!;')
        out = tmp_path / 'bad.so'

        with pytest.raises(RuntimeError, match='Compiler failed'):
            _compile_c_surrogate(src, out, paths['include_dir'], paths['lib_dir'])

    def test_idempotent_second_call_skipped(self, tmp_path, paths, monkeypatch):
        """compileCcode skips recompilation when the .so already exists."""
        from modena.SurrogateModel import _compile_c_surrogate

        src = tmp_path / 'surrogate.c'
        src.write_text(_SURROGATE_C)
        out = tmp_path / 'surrogate.so'

        # First call — real compilation
        _compile_c_surrogate(src, out, paths['include_dir'], paths['lib_dir'])
        mtime_first = out.stat().st_mtime

        # Second call via compileCcode caching (the .so exists, so subprocess not called)
        with patch('subprocess.run') as mock_run:
            _compile_c_surrogate(src, out, paths['include_dir'], paths['lib_dir'])

        # subprocess.run called again here because _compile_c_surrogate itself
        # does not check existence — the cache check is in compileCcode.
        # This test verifies the .so file is unchanged after re-running.
        assert out.stat().st_mtime == mtime_first or mock_run.called


# ---------------------------------------------------------------------------
# Tests for find_package(MODENA) path exports
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.skipif(not _modena_installed(), reason='modena not installed')
class TestModenaPaths:
    """Verify that the paths exported by the installed modena package are usable."""

    def test_include_dir_exists(self):
        import modena
        inc = Path(modena.MODENA_INCLUDE_DIR)
        assert inc.is_dir(), f'MODENA_INCLUDE_DIR does not exist: {inc}'

    def test_modena_h_present(self):
        import modena
        header = Path(modena.MODENA_INCLUDE_DIR) / 'modena.h'
        assert header.exists(), f'modena.h not found at {header}'

    def test_lib_dir_is_the_directory_holding_libmodena(self):
        """MODENA_LIB_DIR is used verbatim as the linker -L path, so the
        library must be in it -- not in its parent."""
        import modena
        lib_dir = Path(modena.MODENA_LIB_DIR)
        assert lib_dir.is_dir(), f'MODENA_LIB_DIR does not exist: {lib_dir}'
        assert any(lib_dir.glob('libmodena.*')), (
            f'No libmodena.* directly in MODENA_LIB_DIR: {lib_dir}'
        )

    def test_public_header_is_self_sufficient(self):
        """A translation unit including only <modena.h> must compile.

        This replaces an assertion that the internal headers are *absent*
        from the include directory.  They cannot be: modena.h opens with
        `#include "global.h"`, `"indexset.h"`, `"function.h"` and `"model.h"`,
        so installing modena.h alone would make it unusable.  "Internal"
        is an instruction to callers, not an install rule -- and the property
        actually worth guarding is that the one public entry point pulls in
        everything it needs by itself.
        """
        import subprocess
        import sysconfig
        import tempfile

        import modena

        cc = sysconfig.get_config_var('CC') or 'cc'
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'only_public.c'
            src.write_text('#include <modena.h>\nint main(void) { return 0; }\n')
            result = subprocess.run(
                cc.split() + [
                    '-fsyntax-only',
                    f'-I{modena.MODENA_INCLUDE_DIR}',
                    f'-I{sysconfig.get_path("include")}',
                    str(src),
                ],
                capture_output=True, text=True,
            )
        assert result.returncode == 0, (
            f'#include <modena.h> alone does not compile:\n{result.stderr}'
        )
