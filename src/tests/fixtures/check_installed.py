"""
CTest fixture: is the installed MoDeNa the one this tree builds?
----------------------------------------------------------------
The installed and live tiers test whatever `cmake --install` last put in the
prefix, not the build directory.  Forgetting the install step therefore does
not fail them -- it quietly tests an older MoDeNa.  On the machine this was
written on, the installed libmodena was six weeks older than the build and
the installed Strategy.py and Integration.py lacked that day's commits, while
both tiers reported green.

This fails fast instead, naming what is stale:

  * the installed libmodena is missing, or older than the one just built;
  * an installed ``modena`` Python module differs from its source file.

The Python package is located with importlib.util.find_spec, which does not
execute it: importing ``modena`` loads libmodena and connects to MongoDB.
"""
import argparse
import filecmp
import importlib.util
import sys
from pathlib import Path


def _stale_library(built: Path, installed: Path):
    if not installed.exists():
        return f'{installed} does not exist'
    # IS_NEWER_THAN semantics: equal timestamps are fine, only strictly newer
    # is stale.  Contents cannot be compared -- install rewrites the RPATH.
    if built.stat().st_mtime > installed.stat().st_mtime:
        return f'{installed} is older than the build ({built})'
    return None


def _stale_python(source_dir: Path):
    spec = importlib.util.find_spec('modena')
    if spec is None or not spec.submodule_search_locations:
        return ['the modena Python package is not importable']
    installed_dir = Path(next(iter(spec.submodule_search_locations)))
    if installed_dir.resolve() == source_dir.resolve():
        return []           # running against the source tree itself
    stale = []
    for source in sorted(source_dir.glob('*.py')):
        installed = installed_dir / source.name
        if not installed.exists():
            stale.append(f'{installed} is missing')
        elif not filecmp.cmp(source, installed, shallow=False):
            stale.append(f'{installed} differs from {source}')
    return stale


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument('--built-lib', type=Path, required=True)
    parser.add_argument('--installed-lib', type=Path, required=True)
    parser.add_argument('--source-python', type=Path, required=True)
    args = parser.parse_args()

    problems = []
    lib = _stale_library(args.built_lib, args.installed_lib)
    if lib:
        problems.append(lib)
    problems.extend(_stale_python(args.source_python))

    if problems:
        print('The installed MoDeNa is not this build:', file=sys.stderr)
        for p in problems:
            print(f'  - {p}', file=sys.stderr)
        print('Run:  cmake --install build   (then re-run ctest)', file=sys.stderr)
        return 1
    print('installed MoDeNa matches this build')
    return 0


if __name__ == '__main__':
    sys.exit(main())
