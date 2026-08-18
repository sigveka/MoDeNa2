"""
Every language must agree on the workflow protocol status codes
----------------------------------------------------------------
The codes are defined in src/python/Strategy.py and mirrored as named
constants in each binding, because C, Fortran, MATLAB and R compare integers
rather than catching typed exceptions the way C++, Julia and Python do.  Five
copies of the same numbers is exactly the arrangement that let "201 = clean
exit" survive in six documents, so they are pinned here.

Marked integration: needs the installed headers, wrapper packages and
toolchains.
"""
import os
import shutil
import subprocess
import sysconfig
from pathlib import Path

import pytest

PREFIX = Path(os.environ.get('MODENA_PREFIX', Path.home()))
LIB = PREFIX / 'lib' / 'modena'
INC = PREFIX / 'include'
PY_INC = sysconfig.get_paths()['include']

#: name -> value, as defined in src/python/Strategy.py.
EXPECTED = {
    'OK': 0,
    'RETRAINED': 100,
    'OUT_OF_BOUNDS': 200,
    'MODEL_NOT_IN_DATABASE': 201,
    'PARAMETERS_NOT_VALID': 202,
}


def _run(cmd, cwd=None):
    env = dict(os.environ, MODENA_LIB_DIR=str(LIB),
               R_LIBS=str(PREFIX / 'lib' / 'R'))
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True,
                          text=True, timeout=300)


def _parsed(out):
    """Take the last whitespace-separated run of five integers."""
    for line in reversed(out.strip().splitlines()):
        parts = line.split()
        ints = [p for p in parts if p.lstrip('-').isdigit()]
        if len(ints) == 5:
            return [int(i) for i in ints]
    raise AssertionError(f'no five-integer line in:\n{out}')


@pytest.mark.integration
def test_python_is_the_source_of_truth():
    from modena.Strategy import (
        MODEL_NOT_IN_DATABASE, OUT_OF_BOUNDS, PARAMETERS_NOT_VALID,
    )
    assert OUT_OF_BOUNDS == EXPECTED['OUT_OF_BOUNDS']
    assert MODEL_NOT_IN_DATABASE == EXPECTED['MODEL_NOT_IN_DATABASE']
    assert PARAMETERS_NOT_VALID == EXPECTED['PARAMETERS_NOT_VALID']


@pytest.mark.integration
def test_c_enum_matches(tmp_path):
    if not shutil.which('gcc'):
        pytest.skip('gcc not available')
    src = tmp_path / 't.c'
    src.write_text(
        '#include <modena.h>\n#include <stdio.h>\n'
        'int main(void){printf("%d %d %d %d %d\\n", MODENA_OK,'
        ' MODENA_RETRAINED, MODENA_OUT_OF_BOUNDS,'
        ' MODENA_MODEL_NOT_IN_DATABASE, MODENA_PARAMETERS_NOT_VALID);'
        'return 0;}\n')
    build = _run(['gcc', '-o', 'a.out', 't.c', f'-I{INC}', f'-I{INC}/modena',
                  f'-I{PY_INC}', f'-L{LIB}', f'-Wl,-rpath,{LIB}', '-lmodena'],
                 cwd=tmp_path)
    assert build.returncode == 0, build.stderr
    run = _run(['./a.out'], cwd=tmp_path)
    assert _parsed(run.stdout) == list(EXPECTED.values())


@pytest.mark.integration
def test_fortran_parameters_match(tmp_path):
    if not shutil.which('gfortran'):
        pytest.skip('gfortran not available')
    src = tmp_path / 't.f90'
    src.write_text(
        'program t\n  use fmodena_oop\n  use iso_c_binding\n  implicit none\n'
        "  print '(5I6)', MODENA_OK, MODENA_RETRAINED, MODENA_OUT_OF_BOUNDS, &\n"
        '       MODENA_MODEL_NOT_IN_DATABASE, MODENA_PARAMETERS_NOT_VALID\n'
        'end program t\n')
    build = _run(['gfortran', '-o', 'a.out', 't.f90', f'-I{INC}/modena',
                  f'-L{LIB}', f'-Wl,-rpath,{LIB}',
                  '-lfmodena_oop', '-lfmodena', '-lmodena'], cwd=tmp_path)
    assert build.returncode == 0, build.stderr
    run = _run(['./a.out'], cwd=tmp_path)
    assert _parsed(run.stdout) == list(EXPECTED.values())


@pytest.mark.integration
def test_r_constants_match(tmp_path):
    if not shutil.which('Rscript'):
        pytest.skip('R not available')
    src = tmp_path / 't.R'
    src.write_text(
        'library(modena)\n'
        'cat(MODENA_OK, MODENA_RETRAINED, MODENA_OUT_OF_BOUNDS,\n'
        '    MODENA_MODEL_NOT_IN_DATABASE, MODENA_PARAMETERS_NOT_VALID, "\\n")\n')
    run = _run(['Rscript', 't.R'], cwd=tmp_path)
    assert run.returncode == 0, run.stderr
    assert _parsed(run.stdout) == list(EXPECTED.values())


@pytest.mark.integration
def test_matlab_constants_match(tmp_path):
    if not shutil.which('octave'):
        pytest.skip('octave not available')
    src = tmp_path / 't.m'
    src.write_text(
        'printf("%d %d %d %d %d\\n", Modena.OK, Modena.RETRAINED, ...\n'
        '       Modena.OUT_OF_BOUNDS, Modena.MODEL_NOT_IN_DATABASE, ...\n'
        '       Modena.PARAMETERS_NOT_VALID);\n')
    run = _run(['octave', '--no-gui', '--quiet',
                '--path', str(PREFIX / 'share' / 'modena' / 'matlab'),
                't.m'], cwd=tmp_path)
    assert run.returncode == 0, run.stderr
    assert _parsed(run.stdout) == list(EXPECTED.values())


@pytest.mark.integration
def test_error_message_describes_the_protocol_codes():
    """modena_error_message() returned "Unknown error" for every code that
    actually occurs -- its bounds check stopped at MODENA_MODEL_LAST (4)."""
    import ctypes
    lib = ctypes.CDLL(str(LIB / 'libmodena.so'))
    lib.modena_error_message.restype = ctypes.c_char_p
    for code in (200, 201, 202):
        msg = lib.modena_error_message(code).decode()
        assert msg != 'Unknown error', f'{code} has no message'
