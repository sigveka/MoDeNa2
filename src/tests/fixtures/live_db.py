"""
CTest fixture: a test database holding a freshly fitted flowRate
----------------------------------------------------------------
The live tier evaluates a real surrogate out of a real MongoDB.  This used to
be prepared by hand -- examples/twoTanks/buildModels, `modena fw reset
--force`, initModels -- against whatever database MODENA_URI named.  Only CI
knew the order, and on a developer machine the reset step wipes the
launchpad of the working database.

  setup    drop the test database, install examples/MoDeNaModels/flowRate
           into <workdir>/models, reset the FireWorks launchpad, fit flowRate
  cleanup  drop the test database

The database comes from MODENA_URI, which CTest sets from the MODENA_TEST_URI
cache variable; its name must start with `modena_` and contain `test`
(checked at configure time and again here).  MODENA_PATH and
MODENA_SURROGATE_LIB_DIR point into <workdir>, so nothing is written outside
the build tree -- except that `modena install` records its prefix in
~/.modena/config.toml, which is why that step runs with HOME=<workdir>/home.
PYTHONUSERBASE keeps the real user site-packages importable meanwhile.
"""
import argparse
import os
import re
import shutil
import site
import subprocess
import sys
from pathlib import Path

MODEL_ID = 'flowRate'


def _database():
    uri = os.environ['MODENA_URI']
    name = re.search(r'/([^/?]+)(\?.*)?$', uri)
    name = name.group(1) if name else ''
    if not re.match(r'^modena_.*test', name):
        sys.exit(f'refusing to touch database {name!r} from MODENA_URI={uri}: '
                 f'the live fixture drops it, so its name must start with '
                 f'"modena_" and contain "test"')
    return uri, name


def _drop(uri, name):
    import pymongo
    client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=5000)
    try:
        client.drop_database(name)
    except pymongo.errors.PyMongoError as exc:
        sys.exit(f'no MongoDB reachable at {uri}: {exc}')
    finally:
        client.close()


def _modena(workdir, *args, env=None):
    """Run `python -m modena <args>`; on failure show its output and exit."""
    print(f'$ modena {" ".join(args)}', flush=True)
    result = subprocess.run(
        [sys.executable, '-m', 'modena', *args],
        cwd=workdir, env=env or os.environ,
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        sys.exit(f'`modena {" ".join(args)}` exited {result.returncode}')


def setup(workdir: Path, models_src: Path):
    uri, name = _database()
    _drop(uri, name)

    # Start from nothing: a stale install or surrogate library from a
    # previous run is exactly what a fixture exists to rule out.
    if workdir.name != 'test-live':
        sys.exit(f'refusing to clear {workdir}: expected a directory named test-live')
    shutil.rmtree(workdir, ignore_errors=True)
    home = workdir / 'home'
    for d in (home, Path(os.environ['MODENA_PATH']),
              Path(os.environ['MODENA_SURROGATE_LIB_DIR'])):
        d.mkdir(parents=True, exist_ok=True)

    install_env = dict(os.environ, HOME=str(home),
                       PYTHONUSERBASE=site.getuserbase())
    _modena(workdir, 'install', '--prefix', os.environ['MODENA_PATH'],
            str(models_src / MODEL_ID), env=install_env)
    # FireWorks keeps its id counters in the same database and refuses to
    # queue anything until they exist ("Could not get next FW id").
    _modena(workdir, 'fw', 'reset', '--force')
    _modena(workdir, 'init', MODEL_ID)
    print(f'{MODEL_ID} fitted in {uri}')


def cleanup():
    uri, name = _database()
    _drop(uri, name)
    print(f'dropped {name}')


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument('action', choices=('setup', 'cleanup'))
    parser.add_argument('--workdir', type=Path, required=True)
    parser.add_argument('--models-src', type=Path)
    args = parser.parse_args()
    if args.action == 'setup':
        if args.models_src is None:
            parser.error('setup needs --models-src')
        setup(args.workdir, args.models_src)
    else:
        cleanup()


if __name__ == '__main__':
    main()
