"""
@file    Selftest.py
@brief   ``modena doctor --selftest``: run an installed MoDeNa end to end.

``modena doctor`` checks that the pieces are present: libmodena loads,
MongoDB answers, the Python packages import.  None of that shows MoDeNa
*works*.  The selftest does what a user's first model does, with a bundled
one (examples/MoDeNaModels/flowRate, installed to
``<prefix>/share/modena/selftest``) so that it needs an install and nothing
else -- no source tree, no example directory:

  1. install the flowRate package (builds its exact-simulation binary)
  2. reset a FireWorks launchpad and fit flowRate (runs the exact simulation)
  3. evaluate the surrogate from Python, and check that an out-of-bounds
     call raises OutOfBounds carrying return code 200
  4. if a C compiler is present, compile and run the C snippet MoDeNa
     generates for the model

Everything happens in a database of its own on the MODENA_URI server
(``modena_selftest_<id>``) and a temporary directory, both removed at the
end.  ``modena install`` records its prefix in ~/.modena/config.toml, so it
runs with HOME pointing into the temporary directory; PYTHONUSERBASE keeps
the real user site-packages importable.

Steps 3-4 run in a subprocess: this process already imported
modena.SurrogateModel, which connected to the *user's* database at import.
"""

import json
import os
import re
import shutil
import site
import subprocess
import sys
import sysconfig
import tempfile
import uuid
from pathlib import Path

MODEL_ID = 'flowRate'

#: Runs in the subprocess: load, evaluate, provoke OutOfBounds, and render
#: the C snippet to argv[1].  Prints one JSON line.
_EVALUATE = r'''
import json, math, sys
import modena
from modena.Integration import snippet

m = modena.SurrogateModel.load(sys.argv[2])
mid = {n: (v.min + v.max) / 2.0 for n, v in m.inputs.items()}
out = m(mid)

oob = dict(mid)
first = next(iter(m.inputs))
oob[first] = m.inputs[first].max * 1e6
try:
    m(oob)
    code = None
except modena.OutOfBounds as exc:
    code = exc.returnCode

with open(sys.argv[1], 'w') as f:
    f.write(snippet(m, 'c')['code'])
print(json.dumps({'outputs': out, 'oob_code': code, 'point': mid}))
'''


def private_uri(uri):
    """*uri* with its database replaced by a fresh ``modena_selftest_<id>``.

    Host, credentials and query options are kept, so the selftest reaches
    the same server the user configured.
    """
    base, _, db_and_query = uri.rpartition('/')
    _, sep, query = db_and_query.partition('?')
    name = f'modena_selftest_{uuid.uuid4().hex[:12]}'
    return f'{base}/{name}{sep}{query}', name


def selftest_package_dir():
    """Where the bundled flowRate package was installed."""
    try:
        from modena._paths import MODENA_SELFTEST_DIR
        return Path(MODENA_SELFTEST_DIR) / MODEL_ID
    except ImportError:
        # _paths.py from before the selftest existed: derive from the
        # library directory, <prefix>/lib/modena.
        from modena._paths import MODENA_LIB_DIR
        return (Path(MODENA_LIB_DIR).parents[1]
                / 'share' / 'modena' / 'selftest' / MODEL_ID)


def _tail(text, n=15):
    return '\n'.join(text.strip().splitlines()[-n:])


class _Run:
    """The temporary directory, database and environment of one selftest."""

    def __init__(self, uri):
        self.uri, self.db = private_uri(uri)
        self.tmp = Path(tempfile.mkdtemp(prefix='modena-selftest-'))
        self.models = self.tmp / 'models'
        self.work = self.tmp / 'work'
        for d in (self.models, self.work, self.tmp / 'home',
                  self.tmp / 'surrogates'):
            d.mkdir()
        self.env = dict(
            os.environ,
            MODENA_URI=self.uri,
            MODENA_PATH=str(self.models),
            MODENA_SURROGATE_LIB_DIR=str(self.tmp / 'surrogates'),
        )

    def modena(self, *args, home=False, timeout=900):
        env = self.env
        if home:
            env = dict(env, HOME=str(self.tmp / 'home'),
                       PYTHONUSERBASE=site.getuserbase())
        return subprocess.run(
            [sys.executable, '-m', 'modena', *args],
            cwd=self.work, env=env, capture_output=True, text=True,
            timeout=timeout,
        )

    def cleanup(self):
        problems = []
        try:
            import pymongo
            client = pymongo.MongoClient(self.uri, serverSelectionTimeoutMS=5000)
            try:
                client.drop_database(self.db)
            finally:
                client.close()
        except Exception as exc:                        # noqa: BLE001
            problems.append(f'could not drop {self.db}: {exc}')
        shutil.rmtree(self.tmp, ignore_errors=True)
        return problems


def _steps(run):
    """Yield (ok, label, detail, hint) rows; stop at the first failure."""
    package = selftest_package_dir()
    if not (package / 'pyproject.toml').is_file():
        yield (False, 'bundled model', f'{package} not found',
               'Reinstall MoDeNa:  cmake --install build')
        return
    yield True, 'bundled model', str(package), None
    yield True, 'database', f'{run.db}  (dropped afterwards)', None

    for label, args, kw, hint in (
        ('install flowRate', ('install', '--prefix', str(run.models),
                              str(package)), {'home': True},
         'Needs a C compiler, CMake and pip (with network access for its '
         'build backend, scikit-build-core).'),
        ('reset launchpad', ('fw', 'reset', '--force'), {}, None),
        ('fit flowRate', ('init', MODEL_ID), {},
         'Runs the exact simulation (flowRateExact) at the initial points '
         'and fits the surrogate.'),
    ):
        result = run.modena(*args, **kw)
        if result.returncode != 0:
            detail = f'`modena {" ".join(args[:2])}` exited {result.returncode}'
            yield (False, label, detail,
                   ((hint + '\n') if hint else '')
                   + _tail(result.stdout + result.stderr))
            return
        yield True, label, 'ok', None

    snippet_c = run.work / 'example.c'
    result = subprocess.run(
        [sys.executable, '-c', _EVALUATE, str(snippet_c), MODEL_ID],
        cwd=run.work, env=run.env, capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        yield (False, 'evaluate from Python', f'exited {result.returncode}',
               _tail(result.stdout + result.stderr))
        return
    report = json.loads(result.stdout.strip().splitlines()[-1])
    values = report['outputs']
    good = all(isinstance(v, float) and v > 0 and v == v and v != float('inf')
               for v in values.values())
    shown = ', '.join(f'{k} = {v:.4g}' for k, v in values.items())
    yield (good, 'evaluate from Python', shown,
           None if good else 'expected finite, positive outputs')
    if not good:
        return

    from modena.Strategy import OUT_OF_BOUNDS
    code = report['oob_code']
    ok = code == OUT_OF_BOUNDS
    yield (ok, 'out-of-bounds signal',
           f'OutOfBounds, return code {code}' if code is not None
           else 'no exception raised',
           None if ok else f'expected OutOfBounds with return code {OUT_OF_BOUNDS}')
    if not ok:
        return

    yield from _c_snippet(run, snippet_c)


def _c_snippet(run, source):
    """Compile and run the generated C example against the installed library."""
    cc = (sysconfig.get_config_var('CC') or 'cc').split()[0]
    if shutil.which(cc) is None:
        # Not a failure: the C API is optional for a Python user.
        yield None, 'C snippet', f'skipped: no C compiler ({cc})', None
        return
    from modena._paths import MODENA_INCLUDE_DIR, MODENA_LIB_DIR
    inc = Path(MODENA_INCLUDE_DIR)
    exe = run.work / 'example'
    build = subprocess.run(
        [cc, '-o', str(exe), str(source),
         f'-I{inc.parent}', f'-I{inc}', f'-I{sysconfig.get_paths()["include"]}',
         f'-L{MODENA_LIB_DIR}', f'-Wl,-rpath,{MODENA_LIB_DIR}', '-lmodena'],
        cwd=run.work, capture_output=True, text=True, timeout=300,
    )
    if build.returncode != 0:
        yield (False, 'C snippet', 'did not compile', _tail(build.stderr))
        return
    ran = subprocess.run([str(exe)], cwd=run.work, env=run.env,
                         capture_output=True, text=True, timeout=300)
    if ran.returncode != 0:
        yield (False, 'C snippet', f'exited {ran.returncode}',
               _tail(ran.stdout + ran.stderr))
        return
    yield True, 'C snippet', 'compiled and ran against libmodena', None


def run_selftest(uri):
    """Run the selftest against the server in *uri*; yield result rows.

    Each row is ``(ok, label, detail, hint)``, in the shape ``modena doctor``
    prints; ``ok`` is None for a step skipped because an optional tool is
    missing.  The temporary database and directory are removed whatever
    happens, and the last row reports that.
    """
    run = _Run(uri)
    try:
        try:
            yield from _steps(run)
        except Exception as exc:                        # noqa: BLE001
            yield (False, 'selftest', f'{type(exc).__name__}: {exc}', None)
    finally:
        problems = run.cleanup()
    yield (not problems, 'cleanup',
           'removed' if not problems else '; '.join(problems), None)
