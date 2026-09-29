"""
The out-of-bounds -> refit loop, end to end
--------------------------------------------
Every other live test evaluates a surrogate that is already fitted.  This one
runs the loop MoDeNa exists for: the twoTanks macroscopic simulation calls
flowRate, leaves its trained box, exits with 200, and FireWorks samples new
points, refits, and restarts the simulation -- until a run finishes inside
the box.

It installs the example packages itself (examples/MoDeNaModels/flowRate and
twoTank) and works in a database of its own, derived from MODENA_URI and
dropped afterwards, so it neither needs examples/twoTanks/buildModels to have
run nor touches the database the other live tests share.  HOME points into
the temporary directory because `modena install` registers its prefix in
~/.modena/config.toml; PYTHONUSERBASE keeps the real user site-packages
importable.

The refit count is pinned.  flowRate's initial points are sized from the
input envelope twoTanksMacroscopicProblem.C visits so that each input needs
at most one out-of-bounds widening: 1 to 3 refits (see the comment above
initialisationStrategy in flowRate.py).  The previous, narrow box took 42.
At least one refit proves the loop ran; more than six means the initial box
no longer fits the simulation.
"""
import os
import site
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.live

REPO = Path(__file__).resolve().parents[3]
MODELS_SRC = REPO / 'examples' / 'MoDeNaModels'
MODEL_ID = 'flowRate'

MIN_REFITS = 1
MAX_REFITS = 6

#: flowRate's initial box, from its initialPoints.  Loading a different
#: flowRate -- a stale copy registered elsewhere -- shows up here first.
INITIAL_BOUNDS = {
    'rho0':   (0.5, 3.5),
    'p0':     (4.2e4, 3.2e5),
    'p1Byp0': (0.03, 0.9),
}

MODENA_TOML = '''\
[logging]
  level = "INFO"
  file  = "modena.log"

[surrogate_functions]
  lib_dir = "."

[simulate]
  target = "twoTank.TwoTankModel"

[simulate.kwargs]
  end_time = 5.5
'''


def _private_uri():
    """MODENA_URI with its database replaced by a fresh, unique one."""
    uri = os.environ.get('MODENA_URI', 'mongodb://localhost:27017/test')
    base, _, db_and_query = uri.rpartition('/')
    _, sep, query = db_and_query.partition('?')
    name = f'modena_looptest_{uuid.uuid4().hex[:12]}'
    return f'{base}/{name}{sep}{query}', name


@pytest.fixture
def loop_env(tmp_path):
    """An isolated HOME, model prefix and database; the database is dropped."""
    pymongo = pytest.importorskip('pymongo')

    uri, db_name = _private_uri()
    client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=3000)
    try:
        client.server_info()
    except pymongo.errors.PyMongoError as exc:
        # A live-tier test with no database is a failure, not a skip: a skip
        # here is how a tier goes unrun without anyone noticing.
        pytest.fail(f'no MongoDB reachable at {uri}: {exc}')

    home, prefix, run = (tmp_path / d for d in ('home', 'models', 'run'))
    for d in (home, prefix, run):
        d.mkdir()
    (run / 'modena.toml').write_text(MODENA_TOML)

    env = dict(os.environ)
    env.update(
        HOME=str(home),
        PYTHONUSERBASE=site.getuserbase(),
        MODENA_URI=uri,
        MODENA_PATH=str(prefix),
    )
    try:
        yield {'env': env, 'run': run, 'prefix': prefix,
               'db': client[db_name]}
    finally:
        client.drop_database(db_name)
        client.close()


def _modena(ctx, *args, timeout=600):
    """Run `python -m modena <args>` in the run directory; fail with its log."""
    result = subprocess.run(
        [sys.executable, '-m', 'modena', *args],
        cwd=ctx['run'], env=ctx['env'],
        capture_output=True, text=True, timeout=timeout,
    )
    if result.returncode != 0:
        tail = '\n'.join((result.stdout + result.stderr).splitlines()[-40:])
        pytest.fail(f'`modena {" ".join(args)}` exited {result.returncode}:\n{tail}')
    return result


def _flowrate(db):
    doc = db.surrogate_model.find_one({'_id': MODEL_ID})
    assert doc is not None, f'{MODEL_ID} is not in the database'
    return doc


def test_out_of_bounds_loop_refits_a_bounded_number_of_times(loop_env):
    ctx, db = loop_env, loop_env['db']

    _modena(ctx, 'install', '--prefix', str(ctx['prefix']),
            str(MODELS_SRC / 'flowRate'), str(MODELS_SRC / 'twoTank'))
    # FireWorks keeps its id counters in the same database and refuses to
    # queue anything until they exist.
    _modena(ctx, 'fw', 'reset', '--force')
    _modena(ctx, 'init', MODEL_ID)

    initial = _flowrate(db)
    for name, (lo, hi) in INITIAL_BOUNDS.items():
        got = (initial['inputs'][name]['min'], initial['inputs'][name]['max'])
        assert got == pytest.approx((lo, hi)), (
            f'{MODEL_ID}.{name} starts at {got}, expected {(lo, hi)}: '
            f'the flowRate being initialised is not the one in {MODELS_SRC}'
        )
    n_initial = initial['nSamples']

    _modena(ctx, 'simulate')

    # The simulation workflow ends when a run finishes inside the box.  A
    # FIZZLED or DEFUSED firework means the loop gave up instead.
    unfinished = [
        (fw['name'], fw['state'])
        for fw in db.fireworks.find({'state': {'$ne': 'COMPLETED'}},
                                    {'name': 1, 'state': 1})
    ]
    assert not unfinished, f'fireworks did not complete: {unfinished}'

    # Each out-of-bounds event adds nNewPoints samples and refits once.
    # Strategies are stored under a meth_ prefix (SurrogateModel.loadType).
    final = _flowrate(db)
    n_new = final['meth_outOfBoundsStrategy']['nNewPoints']
    added = final['nSamples'] - n_initial
    assert added % n_new == 0, (
        f'{added} samples added, not a multiple of nNewPoints={n_new}: a fit '
        f'was rejected and improveErrorStrategy sampled extra points'
    )
    refits = added // n_new
    assert MIN_REFITS <= refits <= MAX_REFITS, (
        f'the twoTanks simulation refitted {MODEL_ID} {refits} times, '
        f'expected {MIN_REFITS}..{MAX_REFITS}; final bounds '
        + str({k: (v['min'], v['max']) for k, v in final['inputs'].items()})
    )
