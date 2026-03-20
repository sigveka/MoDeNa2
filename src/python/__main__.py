'''@cond

   ooo        ooooo           oooooooooo.             ooooo      ooo
   `88.       .888'           `888'   `Y8b            `888b.     `8'
    888b     d'888   .ooooo.   888      888  .ooooo.   8 `88b.    8   .oooo.
    8 Y88. .P  888  d88' `88b  888      888 d88' `88b  8   `88b.  8  `P  )88b
    8  `888'   888  888   888  888      888 888ooo888  8     `88b.8   .oP"888
    8    Y     888  888   888  888     d88' 888    .o  8       `888  d8(  888
   o8o        o888o `Y8bod8P' o888bood8P'   `Y8bod8P' o8o        `8  `Y888""8o

Copyright
    2014-2026 MoDeNa Consortium, All rights reserved.

License
    This file is part of Modena.

    The Modena interface library is free software; you can redistribute it
    and/or modify it under the terms of the GNU Lesser General Public License
    as published by the Free Software Foundation, either version 3 of the
    License, or (at your option) any later version.

    Modena is distributed in the hope that it will be useful, but WITHOUT ANY
    WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
    FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
    details.

    You should have received a copy of the GNU General Public License along
    with Modena.  If not, see <http://www.gnu.org/licenses/>.
@endcond'''
"""
@namespace  python.__main__
@brief      MoDeNa command-line interface.

@author     Sigve Karolius
@copyright  2014-2018, MoDeNa Project. GNU Public License.
"""
import sys
from argparse import ArgumentParser
from os import getcwd, walk
from os.path import abspath, isabs, join, lexists

from modena import __version__ as MODENA_VERSION
from modena import SurrogateModel
from modena.Registry import ModelRegistry, _find_project_config

from jinja2 import Template

# ── terminal symbols ──────────────────────────────────────────────────────── #
_OK   = '\u2713'   # ✓
_FAIL = '\u2717'   # ✗
_SKIP = '\u2014'   # — (optional / not set)

vstring = f'%(prog)s version {MODENA_VERSION}'


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #

def _lpad_cmd(fn):
    """Call fn(lp) with a connected ModenaLaunchPad; exit 1 on failure."""
    try:
        import modena
        lp = modena.lpad()
        fn(lp)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)


def find_file(name: str, path: str = getcwd()) -> str | None:
    for (root, dirs, files) in walk(path):
        if name in files:
            return join(root, name)


# ------------------------------------------------------------------ #
# fw subcommand handlers                                              #
# ------------------------------------------------------------------ #

def _fw_status(_args):
    _lpad_cmd(lambda lp: lp.status())


def _fw_reset(args):
    if not args.force:
        ans = input('[modena] Reset launchpad? All fireworks will be deleted. [y/N] ')
        if ans.strip().lower() not in ('y', 'yes'):
            print('[modena] Reset cancelled.')
            return
    _lpad_cmd(lambda lp: (lp.reset('', require_password=False),
                          print('[modena] Launchpad reset.')))


def _fw_rerun(args):
    _lpad_cmd(lambda lp: lp.rerun(args.fw_id))


def _fw_orphans(args):
    _lpad_cmd(lambda lp: lp.defuse_orphans(max_age_seconds=args.max_age))


def _fw_run(args):
    rundir = getcwd()
    if args.dir:
        rundir = args.dir if isabs(args.dir) else abspath(join(rundir, args.dir))
        assert lexists(rundir), f"Directory {rundir} does not exist"

    if args.script:
        fname = 'workflow.yaml'
        WORKFLOW = '''
# ************ Auto-generated File ************
fws      :
- fw_id : -1
  spec :
    _launch_dir : "{{ rundir }}"
    _tasks      :
      - _fw_name      : "{{ '{{modena.Strategy.BackwardMappingScriptTask}}' }}"
        script        : "{{ script }}"
        use_shell     : true
        defuse_bad_rc : true
name     : "Simulation"
links    :
  -1: []
metadata : { }
'''
        Template(WORKFLOW, trim_blocks=True, lstrip_blocks=True).stream(
            rundir=rundir, script=args.script
        ).dump(fname)
        print(f'[modena] Generated {fname}')
        print(f'[modena] Run with: lpad add {fname} && rlaunch rapidfire')

    elif args.workflow:
        import subprocess
        f = find_file(args.workflow)
        if f is None:
            print(f'[modena] ERROR: workflow file "{args.workflow}" not found.', file=sys.stderr)
            sys.exit(1)
        subprocess.run(['lpad', 'add', f], check=True)
        subprocess.run(['rlaunch', 'rapidfire'], check=True)

    elif args.py:
        import importlib.util, pathlib
        spec = importlib.util.spec_from_file_location('_modena_wf', args.py)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)


# ------------------------------------------------------------------ #
# model subcommand handlers                                           #
# ------------------------------------------------------------------ #

def _model_ls(_args):
    models = list(SurrogateModel.objects)
    if not models:
        print('[modena] No surrogate models in database. Run initModels first.')
        return
    for m in models:
        sf = m.surrogateFunction
        inputs  = sorted(sf['inputs'],     key=lambda k: sf['inputs'][k]['argPos'])
        outputs = sorted(sf['outputs'],    key=lambda k: sf['outputs'][k]['argPos'])
        params  = sorted(sf['parameters'], key=lambda k: sf['parameters'][k]['argPos'])
        sig = (', '.join(outputs) + ' = ' + sf.name
               + '( ' + ', '.join(inputs) + '  ;  ' + ', '.join(params) + ' )')
        trained = '  [trained]' if m.parameters else '  [untrained]'
        print(f'{m._id}{trained}')
        print(f'  {sig}')


def _model_show(args):
    try:
        m = SurrogateModel.objects.get(_id=args.id)
    except SurrogateModel.DoesNotExist:
        print(f'[modena] Model "{args.id}" not found.', file=sys.stderr)
        sys.exit(1)

    sf = m.surrogateFunction
    inputs  = sorted(sf['inputs'],     key=lambda k: sf['inputs'][k]['argPos'])
    outputs = sorted(sf['outputs'],    key=lambda k: sf['outputs'][k]['argPos'])
    params  = sorted(sf['parameters'], key=lambda k: sf['parameters'][k]['argPos'])

    print(f'Model:      {m._id}')
    print(f'Type:       {type(m).__name__}')
    print(f'Function:   {sf.name}')
    print(f'Inputs:     {", ".join(inputs)}')
    print(f'Outputs:    {", ".join(outputs)}')
    print(f'Parameters: {", ".join(params)}')
    if m.parameters:
        print(f'Fitted parameters:')
        for k, v in zip(params, m.parameters):
            print(f'  {k} = {v}')
    else:
        print('Status:     untrained')
    if m.substituteModels:
        subs = ', '.join(s._id for s in m.substituteModels)
        print(f'Substitutes: {subs}')


def _model_freeze(args):
    ModelRegistry().freeze(args.output)


def _model_restore(args):
    ModelRegistry().restore(args.input, verify_only=args.verify_only)


# ------------------------------------------------------------------ #
# doctor                                                              #
# ------------------------------------------------------------------ #

def _doctor(_args):
    """Run environment health checks."""
    import importlib.metadata
    import os

    _results = []   # (ok, label, detail, hint)

    def _row(ok, label, detail, hint=None):
        _results.append((ok, label, detail, hint))
        sym = _OK if ok else _FAIL
        print(f'  {sym}  {label:<30} {detail}')
        if not ok and hint:
            for line in hint.splitlines():
                print(f'       {line}')

    def _opt(present, label, detail):
        sym = _OK if present else _SKIP
        print(f'  {sym}  {label:<30} {detail}')

    def _env(var, default=None):
        val = os.environ.get(var)
        if val:
            print(f'  {_OK}  {var:<30} {val}')
        elif default:
            print(f'  {_SKIP}  {var:<30} (default: {default})')
        else:
            print(f'  {_SKIP}  {var:<30} (not set)')

    print()
    print(f'  modena {MODENA_VERSION}   Python {sys.version.split()[0]}')
    print()

    # ── Core ──────────────────────────────────────────────────────────
    print('  Core')
    try:
        import modena.libmodena as _lm
        _row(True, 'libmodena.so', getattr(_lm, '__file__', 'loaded'))
    except Exception as exc:
        _row(False, 'libmodena.so', str(exc)[:60],
             'Build and install:\n       cmake -B build . && cmake --install build')

    cfg = _find_project_config()
    if cfg:
        _row(True, 'modena.toml', str(cfg))
    else:
        _row(False, 'modena.toml', 'not found in cwd or any parent',
             'Create one in your project directory:\n'
             '       [models]\n'
             '       paths = ["./models"]')

    # ── Database ──────────────────────────────────────────────────────
    print()
    print('  Database')
    uri = os.environ.get('MODENA_URI', 'mongodb://localhost:27017/modena')
    try:
        from modena.Launchpad import ModenaLaunchPad
        lp = ModenaLaunchPad.from_modena_uri(server_selection_timeout_ms=2000)
        info = lp.db.client.server_info()
        _row(True, 'MongoDB', f'{uri}   (server v{info.get("version", "?")})')
    except Exception as exc:
        _row(False, 'MongoDB', f'{uri}',
             f'{exc}\n'
             '       Start MongoDB:\n'
             '         sudo systemctl start mongod\n'
             '         mongod --dbpath /data/db')

    # ── Python packages ───────────────────────────────────────────────
    print()
    print('  Python packages')
    for pkg in ('scipy', 'fireworks', 'mongoengine', 'jinja2', 'pymongo'):
        try:
            _row(True, pkg, importlib.metadata.version(pkg))
        except importlib.metadata.PackageNotFoundError:
            _row(False, pkg, 'not installed', f'pip install {pkg}')

    for pkg in ('CoolProp', 'rpy2'):
        try:
            _opt(True, pkg, f'{importlib.metadata.version(pkg)}   (optional)')
        except importlib.metadata.PackageNotFoundError:
            _opt(False, pkg, 'not installed   (optional)')

    # ── Environment ───────────────────────────────────────────────────
    print()
    print('  Environment')
    _env('MODENA_URI',                'mongodb://localhost:27017/modena')
    _env('MODENA_SURROGATE_LIB_DIR')
    _env('MODENA_LOG_LEVEL',          'INFO')
    _env('MODENA_PATH')

    # ── Summary ───────────────────────────────────────────────────────
    print()
    failures = [r for r in _results if not r[0]]
    if failures:
        print(f'  {len(failures)} check(s) failed. See hints above.')
    else:
        print(f'  All checks passed.')
    print()


# ------------------------------------------------------------------ #
# quickstart                                                          #
# ------------------------------------------------------------------ #

_QUICKSTART = """\

  MoDeNa replaces expensive sub-models (CFD, DEM, ...) with cheap surrogate
  functions trained automatically and stored in MongoDB.  The loop is:

    C/Fortran/Python app  →  modena_model_call()  →  compiled .so surrogate
                                                   ↑ re-trains when out-of-bounds

  ─────────────────────────────────────────────────────────────────────────────
  Prerequisites
  ─────────────────────────────────────────────────────────────────────────────

    1. MongoDB running
         sudo systemctl start mongod

    2. modena installed
         cmake -B build . && cmake --install build
         # or: pip install modena

    3. Check your setup
         modena doctor

  ─────────────────────────────────────────────────────────────────────────────
  Step 1 — Create a project
  ─────────────────────────────────────────────────────────────────────────────

    mkdir myproject && cd myproject

    Create modena.toml:
        [models]
        paths = ["./models"]

    The paths list points to directories where model packages are installed.
    Run buildModels (cmake) to install your model packages there.

  ─────────────────────────────────────────────────────────────────────────────
  Step 2 — Define a surrogate model
  ─────────────────────────────────────────────────────────────────────────────

    Create myModel/python/myModel.py:

        import modena
        from modena import BackwardMappingModel, CFunction, ModenaFireTask
        import modena.Strategy as Strategy
        from fireworks.utilities.fw_utilities import explicit_serialize

        @explicit_serialize
        class MyExactSim(ModenaFireTask):
            def task(self, fw_spec):
                x = self['point']['x']
                self['point']['y'] = expensive_simulation(x)

        f = CFunction(
            Ccode=\'\'\'
        #include "modena.h"
        void myModel(const modena_model_t* model,
                     const double* inputs, double* outputs)
        {
            {% block variables %}{% endblock %}
            outputs[0] = parameters[0] * x + parameters[1];
        }
        \'\'\',
            inputs    = {'x': {'min': 0.0, 'max': 1.0}},
            outputs   = {'y': {'min': -1e99, 'max': 1e99, 'argPos': 0}},
            parameters= {'a': {'min': -1e9, 'max': 1e9, 'argPos': 0},
                         'b': {'min': -1e9, 'max': 1e9, 'argPos': 1}},
        )

        m = BackwardMappingModel(
            _id='myModel',
            surrogateFunction=f,
            exactTask=MyExactSim(),
            substituteModels=[],
            initialisationStrategy=Strategy.InitialPoints(
                initialPoints={'x': [0.1, 0.5, 0.9]}),
            outOfBoundsStrategy=Strategy.ExtendSpaceStochasticSampling(
                nNewPoints=2, sampler=Strategy.LatinHypercube()),
            parameterFittingStrategy=Strategy.NonLinFitWithErrorContol(
                crossValidation=Strategy.Holdout(testDataPercentage=0.2),
                acceptanceCriterion=Strategy.MaxError(threshold=0.05),
                optimizer=Strategy.TrustRegionReflective(),
                improveErrorStrategy=Strategy.StochasticSampling(nNewPoints=2)),
        )

  ─────────────────────────────────────────────────────────────────────────────
  Step 3 — Register in FW_config.yaml
  ─────────────────────────────────────────────────────────────────────────────

    Create FW_config.yaml in your run directory:

        ADD_USER_PACKAGES:
            - modena
            - myModel

    Every package that defines FireTask subclasses must appear here.
    FireWorks imports them before deserializing tasks from MongoDB.

  ─────────────────────────────────────────────────────────────────────────────
  Step 4 — Write initModels and workflow scripts
  ─────────────────────────────────────────────────────────────────────────────

    initModels (make executable: chmod +x initModels):
        #!/usr/bin/env python3
        import modena, myModel
        modena.run([myModel.m])

    workflow:
        #!/usr/bin/env python3
        import modena, myModel
        from fireworks import Firework, Workflow

        # ... build your macroscopic simulation workflow ...
        wf = Workflow([Firework(...)], name='myWorkflow')
        modena.run(wf)

  ─────────────────────────────────────────────────────────────────────────────
  Step 5 — Run
  ─────────────────────────────────────────────────────────────────────────────

    ./initModels   # trains the surrogate (runs exact simulations + fitting)
    ./workflow     # runs your macroscopic simulation

  ─────────────────────────────────────────────────────────────────────────────
  Useful commands
  ─────────────────────────────────────────────────────────────────────────────

    modena doctor                  check your setup
    modena model ls                list all trained surrogate models
    modena model show myModel      inputs, outputs, fitted parameters
    modena fw status               FireWorks queue state
    modena fw reset                clear the queue and start fresh
    modena fw orphans              re-queue stuck fireworks

    # Inspect the computational graph after a run:
    import modena
    lp = modena.lpad()
    lp.retrace_to_origin(fw_id)    # print ancestor graph + return Firework list

  ─────────────────────────────────────────────────────────────────────────────
  Controlling verbosity
  ─────────────────────────────────────────────────────────────────────────────

    MODENA_LOG_LEVEL=WARNING ./initModels    # quiet
    MODENA_LOG_LEVEL=DEBUG   ./initModels    # modena debug, FireWorks quiet
    MODENA_LOG_LEVEL=DEBUG_VERBOSE ./initModels   # everything

    # or in script:
    import modena
    modena.configure_logging(level='DEBUG_VERBOSE', file='run.log')

  ─────────────────────────────────────────────────────────────────────────────
  See also
  ─────────────────────────────────────────────────────────────────────────────

    docs/quick-start-developer.md   full developer guide
    examples/twoTanks/              minimal end-to-end example
    examples/coolProp/              pure-Python exact task example
    examples/CLAUDE.md              model author reference

"""


def _quickstart(_args):
    print(_QUICKSTART)


# ------------------------------------------------------------------ #
# Entry point                                                         #
# ------------------------------------------------------------------ #

def _main():
    """Console script entry point for the ``modena`` command."""
    parser = ArgumentParser(
        prog='modena',
        description='MoDeNa surrogate-model framework CLI',
    )
    parser.add_argument('--version', action='version', version=vstring)

    groups = parser.add_subparsers(dest='group', metavar='{fw,model,doctor,quickstart}')

    # ---------------------------------------------------------------- #
    # modena fw                                                         #
    # ---------------------------------------------------------------- #
    fw_parser = groups.add_parser(
        'fw',
        help='FireWorks launchpad commands',
        description='Inspect and manage the FireWorks launchpad and workflow queue.',
    )
    fw_sub = fw_parser.add_subparsers(dest='command', metavar='<command>')
    fw_sub.required = True

    # modena fw status
    p = fw_sub.add_parser('status', help='Show all Firework IDs, names, and states')
    p.set_defaults(func=_fw_status)

    # modena fw reset
    p = fw_sub.add_parser('reset', help='Reset the launchpad (clears all fireworks)')
    p.add_argument('--force', action='store_true', help='Skip confirmation prompt')
    p.set_defaults(func=_fw_reset)

    # modena fw rerun
    p = fw_sub.add_parser('rerun', help='Re-queue a FIZZLED or COMPLETED firework')
    p.add_argument('fw_id', type=int, help='Firework ID to re-run')
    p.set_defaults(func=_fw_rerun)

    # modena fw orphans
    p = fw_sub.add_parser(
        'orphans',
        help='Re-queue RUNNING/RESERVED fireworks whose process has died',
    )
    p.add_argument(
        '--max-age', type=int, default=3600, metavar='SECONDS',
        help='Age threshold in seconds (default: 3600)',
    )
    p.set_defaults(func=_fw_orphans)

    # modena fw run
    p = fw_sub.add_parser('run', help='Run a workflow script or YAML file')
    p.add_argument('-d', '--dir', type=str, help='Working directory')
    run_opts = p.add_mutually_exclusive_group(required=True)
    run_opts.add_argument('--script', type=str, help='Shell script to wrap as a BackwardMappingScriptTask')
    run_opts.add_argument('--workflow', type=str, help='FireWorks .yaml workflow file')
    run_opts.add_argument('--py', type=str, help='Python workflow script to execute')
    p.set_defaults(func=_fw_run)

    # ---------------------------------------------------------------- #
    # modena model                                                      #
    # ---------------------------------------------------------------- #
    model_parser = groups.add_parser(
        'model',
        help='Surrogate model database commands',
        description='Inspect and manage surrogate models stored in MongoDB.',
    )
    model_sub = model_parser.add_subparsers(dest='command', metavar='<command>')
    model_sub.required = True

    # modena model ls
    p = model_sub.add_parser('ls', help='List all surrogate models')
    p.set_defaults(func=_model_ls)

    # modena model show
    p = model_sub.add_parser('show', help='Show details for a specific model')
    p.add_argument('id', type=str, help='Model ID (e.g. flowRate)')
    p.set_defaults(func=_model_show)

    # modena model freeze
    p = model_sub.add_parser(
        'freeze',
        help='Snapshot model parameters and package versions to a lock file',
    )
    p.add_argument(
        '-o', '--output', type=str, default='modena.lock',
        help='Lock file path (default: modena.lock)',
    )
    p.set_defaults(func=_model_freeze)

    # modena model restore
    p = model_sub.add_parser(
        'restore',
        help='Restore model parameters from a lock file',
    )
    p.add_argument(
        '-i', '--input', type=str, default='modena.lock',
        help='Lock file path (default: modena.lock)',
    )
    p.add_argument(
        '--verify-only', action='store_true',
        help='Only check version consistency; do not restore DB',
    )
    p.set_defaults(func=_model_restore)

    # ---------------------------------------------------------------- #
    # modena doctor                                                     #
    # ---------------------------------------------------------------- #
    p = groups.add_parser(
        'doctor',
        help='Check environment, dependencies, and MongoDB connectivity',
        description='Run health checks and report the status of the MoDeNa environment.',
    )
    p.set_defaults(func=_doctor)

    # ---------------------------------------------------------------- #
    # modena quickstart                                                 #
    # ---------------------------------------------------------------- #
    p = groups.add_parser(
        'quickstart',
        help='Print a step-by-step guide to using MoDeNa',
        description='Print a concise introduction and usage guide for MoDeNa.',
    )
    p.set_defaults(func=_quickstart)

    # ---------------------------------------------------------------- #
    # Dispatch                                                          #
    # ---------------------------------------------------------------- #
    args = parser.parse_args()

    if args.group is None:
        parser.print_help()
    else:
        args.func(args)


if __name__ == '__main__':
    _main()
