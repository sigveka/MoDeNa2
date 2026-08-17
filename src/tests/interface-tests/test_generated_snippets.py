"""Compile (and where possible run) the snippets modena.Integration generates.

A generated snippet that does not compile is worse than no snippet: it looks
authoritative.  Writing these templates produced four bugs that only real
compilation caught -- C++ indexing by position instead of name, Fortran
positions declared plain `integer`, `300000_c_double` (an integer literal
cannot take a real kind suffix), and MATLAB `set` colliding with an Octave
builtin.  Pure-Python assertions would have missed all four.

Registered under the `integration` label: needs MongoDB, an initialised
model, a toolchain, and the installed headers.
"""
import os
import subprocess
import sys
import sysconfig
from pathlib import Path

import pytest

MODEL_ID = os.environ.get('MODENA_SNIPPET_MODEL', 'flowRate')
PREFIX = Path(os.environ.get('MODENA_PREFIX', Path.home()))
LIB = PREFIX / 'lib' / 'modena'
INC = PREFIX / 'include'
PY_INC = sysconfig.get_paths()['include']


def _generate(tmp_path, language):
    import modena
    from modena.Integration import LANGUAGES, snippet
    model = modena.SurrogateModel.load(MODEL_ID)
    s = snippet(model, language)
    path = tmp_path / f"example.{s['extension']}"
    path.write_text(s['code'])
    return path, s


def _run(cmd, cwd):
    env = dict(os.environ, MODENA_LIB_DIR=str(LIB))
    return subprocess.run(cmd, cwd=cwd, env=env, shell=isinstance(cmd, str),
                          capture_output=True, text=True, timeout=300)


@pytest.mark.integration
@pytest.mark.parametrize('language,compiler,cmd', [
    ('c', 'gcc', ['gcc', '-o', 'ex', 'example.c',
                  f'-I{INC}', f'-I{INC}/modena', f'-I{PY_INC}',
                  f'-L{LIB}', f'-Wl,-rpath,{LIB}', '-lmodena']),
    ('cpp', 'g++', ['g++', '-std=c++17', '-o', 'ex', 'example.cpp',
                    f'-I{INC}', f'-I{INC}/modena', f'-I{PY_INC}',
                    f'-L{LIB}', f'-Wl,-rpath,{LIB}', '-lmodena']),
    ('fortran', 'gfortran', ['gfortran', '-o', 'ex', 'example.f90',
                             f'-I{INC}/modena', f'-L{LIB}',
                             f'-Wl,-rpath,{LIB}',
                             '-lfmodena_oop', '-lfmodena', '-lmodena']),
])
def test_generated_snippet_compiles_and_runs(tmp_path, language, compiler, cmd):
    if not any((Path(p) / compiler).is_file()
               for p in os.environ.get('PATH', '').split(os.pathsep) if p):
        pytest.skip(f'{compiler} not available')
    _generate(tmp_path, language)

    build = _run(cmd, tmp_path)
    assert build.returncode == 0, f'{language} did not compile:\n{build.stderr}'

    run = _run(['./ex'], tmp_path)
    assert run.returncode == 0, (
        f'{language} exited {run.returncode} '
        f'(200 = out of bounds: placeholder values left the trained domain)\n'
        f'{run.stdout}\n{run.stderr}'
    )


@pytest.mark.integration
def test_generated_python_snippet_runs(tmp_path):
    path, _ = _generate(tmp_path, 'python')
    r = _run([sys.executable, path.name], tmp_path)
    assert r.returncode == 0, f'{r.stdout}\n{r.stderr}'
