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
import os
import sys
from argparse import ArgumentParser
from pathlib import Path

from modena import __version__ as MODENA_VERSION
from modena import SurrogateModel
from modena.Registry import ModelRegistry, _find_project_config

from jinja2 import Template
from mongoengine.errors import FieldDoesNotExist

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


def find_file(name: str, path: Path | None = None) -> Path | None:
    """Resolve *name* to an existing file, or return None.

    A path that already points at a file — absolute, or relative to *path* —
    is returned as-is.  Only a bare name that does not resolve directly is
    searched for recursively.  The direct hit has to be tried first because
    ``Path.rglob`` raises ``NotImplementedError`` on an absolute pattern.
    """
    base = path or Path.cwd()
    candidate = Path(name).expanduser()

    if candidate.is_absolute():
        return candidate if candidate.is_file() else None

    direct = base / candidate
    if direct.is_file():
        return direct

    return next(base.rglob(name), None)


# ------------------------------------------------------------------ #
# fw subcommand handlers                                              #
# ------------------------------------------------------------------ #

def _fw_status(_args):
    _lpad_cmd(lambda lp: lp.status())


def _fw_reset(args):
    if not args.force:
        try:
            ans = input('[modena] Reset launchpad? All fireworks will be deleted. [y/N] ')
        except EOFError:
            # Non-interactive stdin: treat an unanswerable prompt as "no"
            # rather than crashing with a traceback.
            print('[modena] No terminal to confirm on; pass --force to reset.',
                  file=sys.stderr)
            sys.exit(1)
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
    # --dir is the directory the workflow runs *in*: it is the _launch_dir
    # baked into a generated YAML, the search root for --workflow/--py, and
    # the working directory of everything this function spawns or executes.
    rundir = Path.cwd()
    if args.dir:
        rundir = Path(args.dir).expanduser().resolve()
        if not rundir.is_dir():
            print(f'[modena] ERROR: directory "{rundir}" does not exist.',
                  file=sys.stderr)
            sys.exit(1)

    if args.script:
        fname = rundir / 'workflow.yaml'
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
        ).dump(str(fname))
        print(f'[modena] Generated {fname}')
        print(f'[modena] Run with: lpad add {fname} && rlaunch rapidfire')

    elif args.workflow:
        import subprocess
        f = find_file(args.workflow, rundir)
        if f is None:
            print(f'[modena] ERROR: workflow file "{args.workflow}" not found '
                  f'in or below {rundir}.', file=sys.stderr)
            sys.exit(1)
        for cmd in (['lpad', 'add', str(f)], ['rlaunch', 'rapidfire']):
            try:
                subprocess.run(cmd, check=True, cwd=rundir)
            except FileNotFoundError:
                print(f'[modena] ERROR: "{cmd[0]}" not found on PATH — '
                      f'is FireWorks installed?', file=sys.stderr)
                sys.exit(1)
            except subprocess.CalledProcessError as exc:
                print(f'[modena] ERROR: {" ".join(cmd)} failed with exit '
                      f'status {exc.returncode}.', file=sys.stderr)
                sys.exit(exc.returncode)

    elif args.py:
        import importlib.util
        script = find_file(args.py, rundir)
        if script is None:
            print(f'[modena] ERROR: python workflow "{args.py}" not found '
                  f'in or below {rundir}.', file=sys.stderr)
            sys.exit(1)

        spec = importlib.util.spec_from_file_location('_modena_wf', script)
        # spec_from_file_location returns None for any suffix Python has no
        # loader for (.txt, .sh, ...); dereferencing spec.loader then fails
        # with an opaque AttributeError.
        if spec is None or spec.loader is None:
            print(f'[modena] ERROR: "{script}" is not an importable Python '
                  f'module (expected a .py file).', file=sys.stderr)
            sys.exit(1)

        mod = importlib.util.module_from_spec(spec)
        cwd = Path.cwd()
        os.chdir(rundir)
        try:
            spec.loader.exec_module(mod)
        finally:
            os.chdir(cwd)


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
        # Only inputs carry argPos on the stored document — vector inputs need
        # an explicit block-start position.  Outputs and parameters are ordered
        # by dict-key insertion, and that IS their argPos order; reading
        # ['argPos'] off them raises KeyError.  Keep this in step with
        # _model_show(), which does the same thing.
        inputs  = sorted(sf['inputs'], key=lambda k: sf['inputs'][k]['argPos'])
        outputs = list(sf['outputs'])
        params  = list(sf['parameters'])
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
    # Inputs still carry argPos on the embedded doc (vector inputs have
    # non-trivial block-start argPos).  Outputs and parameters are ordered
    # by dict-key insertion — that IS the argPos ordering.
    inputs  = sorted(sf['inputs'], key=lambda k: sf['inputs'][k]['argPos'])
    outputs = list(sf['outputs'])
    params  = list(sf['parameters'])

    print(f'Model:      {m._id}')
    print(f'Type:       {type(m).__name__}')
    print(f'Function:   {sf.name}')
    print(f'Inputs:     {", ".join(inputs)}')
    print(f'Outputs:    {", ".join(outputs)}')
    print(f'Parameters: {", ".join(params)}')
    if m.parameters:
        # m.parameters is a DictField(FloatField) — {name: value}.
        # Print in argPos order (matches ``Parameters:`` line above).
        print(f'Fitted parameters:')
        for name in params:
            print(f'  {name} = {m.parameters.get(name, "<unset>")}')
    else:
        print('Status:     untrained')
    if m.substituteModels:
        subs = ', '.join(s._id for s in m.substituteModels)
        print(f'Substitutes: {subs}')


def _model_freeze(args):
    ModelRegistry().freeze(args.output)


def _model_restore(args):
    ModelRegistry().restore(args.input, verify_only=args.verify_only)


#: Legacy embedded-document keys, mapped to the collection and the fields they
#: may contaminate.  ``argPos`` was removed from outputs and parameters by the
#: named-parameter rework: declaration order became authoritative.  ``MinMax``
#: is a strict EmbeddedDocument, so a stored ``argPos`` is not merely ignored —
#: mongoengine raises FieldDoesNotExist and the document cannot be read at all.
_LEGACY_KEYS = {'surrogate_function': (('outputs', 'parameters'), 'argPos')}


def _find_legacy_fields():
    """Return ``[(collection, _id, [dotted paths]), ...]`` for stale documents.

    Uses raw pymongo deliberately: the whole point is that these documents
    cannot be loaded through mongoengine.
    """
    from mongoengine.connection import get_db
    db = get_db()

    found = []
    for coll, (sections, key) in _LEGACY_KEYS.items():
        for doc in db[coll].find():
            paths = [
                f'{section}.{name}.{key}'
                for section in sections
                for name, spec in (doc.get(section) or {}).items()
                if isinstance(spec, dict) and key in spec
            ]
            if paths:
                found.append((coll, doc['_id'], paths))
    return found


def _model_migrate(args):
    """Strip fields that were removed from the schema but remain on disk."""
    from mongoengine.connection import get_db

    stale = _find_legacy_fields()
    if not stale:
        print('[modena] Database schema is current; nothing to migrate.')
        return

    n_fields = sum(len(paths) for _, _, paths in stale)
    verb = 'Would remove' if args.check else 'Removing'
    print(f'[modena] {verb} {n_fields} stale field(s) from '
          f'{len(stale)} document(s):')
    for coll, _id, paths in stale:
        print(f'  {coll}/{_id}')
        for p in paths:
            print(f'      {p}')

    if args.check:
        print('\n[modena] --check given; database not modified.')
        return

    db = get_db()
    for coll, _id, paths in stale:
        db[coll].update_one({'_id': _id}, {'$unset': {p: '' for p in paths}})

    remaining = _find_legacy_fields()
    if remaining:
        print(f'[modena] ERROR: {len(remaining)} document(s) still stale.',
              file=sys.stderr)
        sys.exit(1)
    print(f'\n[modena] Migrated {len(stale)} document(s).')


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
        print()
        # Non-zero exit so `modena doctor` is usable as a preflight gate in
        # CI and setup scripts.
        sys.exit(1)
    print(f'  All checks passed.')
    print()


# ------------------------------------------------------------------ #
# sweep                                                               #
# ------------------------------------------------------------------ #

def _sweep(args):
    """Evaluate a surrogate over a parameter sweep and write a CSV file."""
    import csv
    import itertools

    import numpy as np
    import modena

    model = modena.load(args.model_id)

    # Parse --param name=min:max:n
    sweep: dict[str, np.ndarray] = {}
    for spec in args.param:
        try:
            name, rng = spec.split('=', 1)
            lo, hi, n = rng.split(':')
            lo, hi, n = float(lo), float(hi), int(n)
        except ValueError:
            print(
                f'[modena] ERROR: --param {spec!r} must be name=min:max:n '
                f'(e.g. omega_eV=0.5:6.0:40)',
                file=sys.stderr,
            )
            sys.exit(1)
        # n < 1 makes np.linspace return an empty axis, which silently
        # collapses the whole cartesian product to zero rows.
        if n < 1:
            print(
                f'[modena] ERROR: --param {spec!r}: n must be at least 1, '
                f'got {n}.',
                file=sys.stderr,
            )
            sys.exit(1)
        sweep[name] = np.linspace(lo, hi, n)

    # Parse --fix name=value
    fixed: dict[str, float] = {}
    for spec in (args.fix or []):
        try:
            name, val = spec.split('=', 1)
            fixed[name] = float(val)
        except ValueError:
            print(
                f'[modena] ERROR: --fix {spec!r} must be name=value '
                f'(e.g. d_nm=100)',
                file=sys.stderr,
            )
            sys.exit(1)

    # Cartesian product over all sweep axes (single axis is the common case)
    names  = list(sweep)
    points = list(itertools.product(*[sweep[n] for n in names]))

    # Evaluate surrogate at each point.  A sweep is the operation most likely
    # to leave the trained domain, and callModel() deliberately propagates
    # OutOfBounds so non-workflow callers can react — so translate it here
    # instead of letting a traceback out.
    rows: list[dict] = []
    for pt in points:
        inp    = {**fixed, **dict(zip(names, pt))}
        try:
            result = model(inp)
        except modena.OutOfBounds:
            bounds = '\n'.join(
                f'           {k}: [{v.min:g}, {v.max:g}]'
                for k, v in model.inputs.items()
            )
            print(
                f'[modena] ERROR: point {inp} is outside the trained domain '
                f'of {args.model_id!r}.\n'
                f'         Trained bounds:\n{bounds}\n\n'
                f'         Narrow the sweep to fit, or extend the model first:\n'
                f'             modena init {args.model_id!r}',
                file=sys.stderr,
            )
            sys.exit(1)
        rows.append({**inp, **result})

    # Determine output file name
    safe_id = (
        args.model_id
        .replace('[', '_').replace(']', '')
        .replace('=', '_').replace(' ', '_')
        .replace('/', '_').replace(os.sep, '_')
    )
    out_file = args.out or f'{safe_id}_sweep.csv'

    # Write CSV
    fieldnames = list(rows[0].keys())
    with open(out_file, 'w', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f'[modena] Wrote {len(rows)} row(s) → {out_file}')


# ------------------------------------------------------------------ #
# simulate                                                            #
# ------------------------------------------------------------------ #

def _simulate(args):
    """Run a simulation workflow: read target and kwargs from modena.toml [simulate]."""
    import importlib
    import modena as _modena
    from modena.Registry import _find_project_config, _load_toml
    from modena.config_schema import SimulateConfig

    # Load [simulate] from the nearest modena.toml (provides defaults for both
    # target and kwargs; CLI positional arg overrides target only).
    proj = _find_project_config()
    data = _load_toml(proj) if proj else {}
    try:
        cfg = SimulateConfig.model_validate(data.get('simulate', {}))
    except Exception as exc:
        print(f'[modena] ERROR: invalid [simulate] section in modena.toml: {exc}',
              file=sys.stderr)
        sys.exit(1)

    target = args.target or cfg.target   # CLI overrides toml

    if target is None:
        print(
            '[modena] ERROR: no target specified. '
            'Pass "package.ClassName" or set [simulate] target in modena.toml.',
            file=sys.stderr,
        )
        sys.exit(1)

    parts = target.rsplit('.', 1)
    if len(parts) != 2:
        print(
            f'[modena] ERROR: target must be "package.ClassName", got {target!r}',
            file=sys.stderr,
        )
        sys.exit(1)
    package_name, class_name = parts

    try:
        module = importlib.import_module(package_name)
    except ImportError as exc:
        print(f'[modena] ERROR: cannot import {package_name!r}: {exc}', file=sys.stderr)
        sys.exit(1)

    cls = getattr(module, class_name, None)
    if cls is None:
        print(
            f'[modena] ERROR: {package_name!r} has no attribute {class_name!r}',
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        instance = cls(**(cfg.kwargs or {}))
    except Exception as exc:
        print(f'[modena] ERROR: could not instantiate {target}: {exc}', file=sys.stderr)
        sys.exit(1)

    from fireworks import Firework, Workflow
    wf = Workflow([Firework(instance, name=f'simulation {class_name}')], name='simulation')
    _launch(wf, args)


# ------------------------------------------------------------------ #
# install                                                             #
# ------------------------------------------------------------------ #

def _ensure_models_path_registered(prefix: Path) -> None:
    """Add *prefix* to ~/.modena/config.toml [models] paths if not already there."""
    from modena.Registry import _load_toml, _write_toml
    config_path = Path.home() / '.modena' / 'config.toml'
    config_path.parent.mkdir(parents=True, exist_ok=True)
    data = _load_toml(config_path)
    paths = data.setdefault('models', {}).setdefault('paths', [])
    registered = {str(Path(p).expanduser().resolve()) for p in paths}
    # Store the same resolved form the membership test uses, or a symlinked
    # $HOME re-appends the identical path on every install.
    resolved = str(prefix.resolve())
    if resolved not in registered:
        paths.append(resolved)
        _write_toml(config_path, data)
        print(f'[modena] Registered {resolved} in {config_path}')


def _build_run_kwargs(args) -> dict:
    """Build modena.run() kwargs from the common launcher CLI args."""
    njobs = 1 if args.sequential else args.jobs
    # `fw launch` omits --reset entirely (it only runs already-queued work),
    # so the attribute may be absent.
    run_kwargs = dict(njobs=njobs, launcher=args.launcher,
                      reset=getattr(args, 'reset', False))
    if args.launcher in ('qlaunch', 'auto'):
        # qadapter may legitimately be None: Runner.run() falls back to
        # QUEUEADAPTER_LOC in FW_config.yaml and raises a clear ValueError
        # when neither is set.  Rejecting None here made that fallback —
        # which --qadapter's own help advertises — unreachable.
        run_kwargs['qadapter']   = args.qadapter
        run_kwargs['fworker']    = args.fworker
        run_kwargs['launch_dir'] = args.launch_dir
    if args.launcher == 'auto':
        run_kwargs['escalate_at'] = args.escalate_at
    return run_kwargs


def _launch(wf_or_models, args) -> None:
    """Run a workflow through modena.run(), reporting launcher errors cleanly.

    ``run()`` validates the launcher/qadapter combination and raises
    ``ValueError``; surfacing that as a traceback would tell a CLI user
    nothing they can act on.
    """
    import modena as _modena
    try:
        _modena.run(wf_or_models, **_build_run_kwargs(args))
    except ValueError as exc:
        print(f'[modena] ERROR: {exc}', file=sys.stderr)
        sys.exit(1)


def _fw_launch(args):
    """Run workers against whatever is already queued."""
    import modena as _modena

    lp = _modena.lpad()
    ready = len(lp.get_fw_ids(query={'state': 'READY'}))
    waiting = len(lp.get_fw_ids(query={'state': 'WAITING'}))
    if not ready and not waiting:
        print('[modena] Launchpad has no queued work. Nothing to run.')
        return
    print(f'[modena] Running {ready} READY ({waiting} waiting) firework(s)...')

    kwargs = _build_run_kwargs(args)
    kwargs.pop('reset', None)          # launch() never resets; it only runs
    try:
        _modena.launch(lpad=lp, **kwargs)
    except ValueError as exc:
        print(f'[modena] ERROR: {exc}', file=sys.stderr)
        sys.exit(1)


def _init_models(args):
    """Run the initialisation workflow for registered surrogate models."""
    import importlib as _importlib
    import modena as _modena
    from modena.Registry import ModelRegistry as _ModelRegistry

    # Import every registered model package so their module-level model
    # instances are created and added to SurrogateModel.___refs___.
    # This is intentional here — the user explicitly asked to init all models.
    # (The general `import modena` no longer does this automatically at startup.)
    _reg = _ModelRegistry().load()
    for _dist in _reg.active_packages():
        # active_packages() reports *distribution* names, which differ from
        # the importable module name whenever the distribution uses a
        # separator ('my-model' installs as 'my_model').
        candidates = [_dist]
        if '-' in _dist or '.' in _dist:
            candidates.append(_dist.replace('-', '_').replace('.', '_'))
        for _name in candidates:
            try:
                _importlib.import_module(_name)
                break
            except ImportError as _e:
                _err = _e
        else:
            print(f'[modena] WARNING: could not import {_dist!r}: {_err}',
                  file=sys.stderr)

    all_models = list(_modena.SurrogateModel.get_instances())

    if 'all' in args.models:
        models = all_models
    else:
        by_id = {m._id: m for m in all_models}
        missing = [mid for mid in args.models if mid not in by_id]
        if missing:
            for mid in missing:
                print(f'[modena] ERROR: model not found: {mid}', file=sys.stderr)
            sys.exit(1)
        models = [by_id[mid] for mid in args.models]

    if not models:
        print('[modena] No models registered. Run "modena install" first.')
        sys.exit(0)

    print(f'[modena] Initialising {len(models)} model(s): '
          + ', '.join(m._id for m in models))
    _launch(models, args)


def _model_refit(args):
    """Re-run parameter fitting on a model's existing fitData."""
    import modena as _modena
    from modena.SurrogateModel import BackwardMappingModel
    from modena.Strategy import ParameterRefitting
    from fireworks import Firework, Workflow

    try:
        m = _modena.SurrogateModel.objects.get(_id=args.id)
    except _modena.SurrogateModel.DoesNotExist:
        print(f'[modena] ERROR: model "{args.id}" not found.', file=sys.stderr)
        sys.exit(1)

    if not isinstance(m, BackwardMappingModel):
        print(
            f'[modena] ERROR: "{args.id}" is a {type(m).__name__}, '
            f'not a BackwardMappingModel — only backward-mapping models '
            f'have a parameter fitting strategy.',
            file=sys.stderr,
        )
        sys.exit(1)

    m.reload('fitData')
    if not m.fitData:
        print(
            f'[modena] ERROR: model "{args.id}" has no fit data. '
            f'Run "modena init {args.id}" first to collect training samples.',
            file=sys.stderr,
        )
        sys.exit(1)

    n = len(next(iter(m.fitData.values())))
    print(f'[modena] Re-fitting "{args.id}" on {n} existing sample(s).')

    wf = Workflow(
        [Firework(ParameterRefitting(surrogateModelId=m._id),
                  name=f'{m._id} — refit')],
        name=f'refit {m._id}',
    )
    _launch(wf, args)


def _install_models(args):
    """Install local model packages to the MoDeNa models directory."""
    import subprocess
    import tempfile
    prefix = (
        Path(args.prefix).expanduser().resolve()
        if args.prefix
        else Path.home() / '.modena' / 'models'
    )

    # Validate every package up front.  Validating inside the install loop
    # meant a typo in the last argument aborted the run with the earlier
    # packages already installed.
    pkgs = [Path(p).expanduser().resolve() for p in args.packages]
    bad = [p for p in pkgs if not (p / 'pyproject.toml').is_file()]
    if bad:
        for p in bad:
            print(f'[modena] ERROR: {p} has no pyproject.toml', file=sys.stderr)
        sys.exit(1)

    _ensure_models_path_registered(prefix)
    for pkg in pkgs:
        print(f'[modena] Installing {pkg.name} → {prefix}')
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            # Copy source to temp dir so pip/setuptools build artifacts
            # (*.egg-info, build/) do not pollute the source tree.
            import shutil
            src_copy = tmp / pkg.name
            shutil.copytree(pkg, src_copy)
            wheel_dir = tmp / 'wheels'
            wheel_dir.mkdir()
            subprocess.run(
                [sys.executable, '-m', 'pip', 'wheel',
                 '--no-deps', '--wheel-dir', str(wheel_dir), str(src_copy)],
                check=True,
            )
            wheels = list(wheel_dir.glob('*.whl'))
            if not wheels:
                print(f'[modena] ERROR: no wheel produced for {pkg.name}',
                      file=sys.stderr)
                sys.exit(1)
            subprocess.run(
                [sys.executable, '-m', 'pip', 'install',
                 '--prefix', str(prefix), '--no-deps', str(wheels[0])],
                check=True,
            )
    print('\n[modena] Done. Packages importable after next "import modena".')


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

def _add_launcher_args(p, reset: bool = True) -> None:
    """Add --jobs, --sequential, --reset, --launcher, --qadapter, --fworker,
    --launch-dir, and --escalate-at to an ArgumentParser subcommand.

    ``reset=False`` omits --reset, for subcommands that only run already-queued
    work and have nothing to clear."""
    p.add_argument(
        '--jobs', '-j', type=int, default=0, metavar='N',
        help='rapidfire/auto: number of local worker processes (default: 1).  '
             'qlaunch: max HPC queue slots held simultaneously '
             '(default: 0 = unlimited)',
    )
    p.add_argument(
        '--sequential', action='store_true',
        help='Run sequentially in a single process '
             '(equivalent to --jobs 1; this is the default)',
    )
    if reset:
        p.add_argument(
        '--reset', action='store_true',
        help='Clear the launchpad before adding this workflow.  DESTRUCTIVE: '
             'deletes every existing firework and its run history.  Without '
             'this flag the new workflow is added alongside what is already '
             'queued.',
        )
    p.add_argument(
        '--launcher', choices=['rapidfire', 'qlaunch', 'auto'],
        default='rapidfire',
        help='"rapidfire" (default): local workers only.  '
             '"qlaunch": HPC queue only.  '
             '"auto": local workers + HPC escalation when queue depth exceeds '
             '--escalate-at.',
    )
    p.add_argument(
        '--escalate-at', type=int, default=0, metavar='N', dest='escalate_at',
        help='auto only: READY Firework count above which the supervisor '
             'starts submitting to HPC (default: 0)',
    )
    p.add_argument(
        '--qadapter', type=str, default=None, metavar='PATH',
        help='Path to qadapter.yaml.  Required with --launcher qlaunch or '
             'auto unless QUEUEADAPTER_LOC is set in FW_config.yaml.',
    )
    p.add_argument(
        '--fworker', type=str, default=None, metavar='PATH',
        help='Path to fworker.yaml.  Falls back to FWORKER_LOC in '
             'FW_config.yaml, then a default catch-all worker.',
    )
    p.add_argument(
        '--launch-dir', type=str, default='.', metavar='DIR',
        dest='launch_dir',
        help='Directory from which batch jobs are submitted (qlaunch/auto only)',
    )


#: Top-level command groups.  Single source of truth for both the subparser
#: metavar and the tests that guard against the two drifting apart.
_GROUPS = ('fw', 'model', 'init', 'install', 'sweep', 'simulate',
           'doctor', 'quickstart')


def _build_parser():
    """Construct the full argument parser.

    Separate from :func:`_main` so tests can inspect the command tree without
    parsing argv or dispatching a handler.
    """
    parser = ArgumentParser(
        prog='modena',
        description='MoDeNa surrogate-model framework CLI',
    )
    parser.add_argument('--version', action='version', version=vstring)

    groups = parser.add_subparsers(
        dest='group', metavar='{' + ','.join(_GROUPS) + '}')

    # ---------------------------------------------------------------- #
    # modena fw                                                         #
    # ---------------------------------------------------------------- #
    fw_parser = groups.add_parser(
        'fw',
        help='FireWorks launchpad commands',
        description='Inspect and manage the FireWorks launchpad and workflow queue.',
    )
    fw_sub = fw_parser.add_subparsers(dest='command', metavar='<command>')
    # No `required = True`: argparse would answer a bare `modena fw` with a
    # two-line usage error.  Printing the group's help instead shows the reader
    # the commands they were looking for.
    fw_parser.set_defaults(func=lambda _a, _p=fw_parser: _p.print_help())

    # modena fw status
    p = fw_sub.add_parser('status', aliases=['ls', 'list'],
                          help='Show all Firework IDs, names, and states')
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

    # modena fw launch
    p = fw_sub.add_parser(
        'launch',
        help='Run whatever is already queued on the launchpad',
        description=(
            'Start workers against the existing queue and keep going until no '
            'READY fireworks remain.\n\n'
            'This is how work queued by something that does not run it itself '
            'gets executed -- the portal\'s Collect Data tab, or an earlier '
            '"modena init --launcher qlaunch" whose jobs are still pending.\n\n'
            'FireWorks\' own "rlaunch" is not a substitute: it reads its own '
            'launchpad configuration rather than MODENA_URI, so it connects to '
            'a different database and sees none of this work.\n\n'
            'Examples:\n'
            '  modena fw launch\n'
            '  modena fw launch --jobs 4\n'
            '  modena fw launch --launcher qlaunch --qadapter qadapter.yaml'
        ),
    )
    _add_launcher_args(p, reset=False)
    p.set_defaults(func=_fw_launch)

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
    model_parser.set_defaults(func=lambda _a, _p=model_parser: _p.print_help())

    # modena model ls
    p = model_sub.add_parser('ls', aliases=['list'],
                             help='List all surrogate models')
    p.set_defaults(func=_model_ls)

    # modena model migrate
    p = model_sub.add_parser(
        'migrate',
        help='Remove fields left behind by an older MoDeNa schema',
        description=(
            'Strip embedded-document fields that the current schema no longer '
            'declares.  Removing a field from a strict EmbeddedDocument makes '
            'older documents unreadable rather than merely outdated, so a '
            'database written before the named-parameter rework must be '
            'repaired before any command can read it.'
        ),
    )
    p.add_argument(
        '--check', action='store_true',
        help='Report what would change without modifying the database',
    )
    p.set_defaults(func=_model_migrate)

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

    # modena model refit
    p = model_sub.add_parser(
        'refit',
        help='Re-run parameter fitting on a model\'s existing training data',
        description=(
            'Re-fit the surrogate parameters for a specific BackwardMappingModel '
            'using the fitData already stored in MongoDB — without re-running '
            'any exact simulations.\n\n'
            'Use this when you want to:\n'
            '  - Retry fitting after adjusting the acceptance threshold\n'
            '  - Apply a different fitting strategy or optimizer\n'
            '  - Recover from a failed fitting step without re-collecting data\n\n'
            'The model must already have training data '
            '(run "modena init" first if not).\n\n'
            'Examples:\n'
            "  modena model refit 'thermalDiffusion[material=Cu]'\n"
            "  modena model refit flowRate --sequential"
        ),
    )
    p.add_argument('id', type=str, help='Model ID (e.g. thermalDiffusion[material=Cu])')
    _add_launcher_args(p)
    p.set_defaults(func=_model_refit)

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
    # modena init                                                       #
    # ---------------------------------------------------------------- #
    p = groups.add_parser(
        'init',
        help='Run the initialisation workflow for registered surrogate models',
        description=(
            'Run the initialisation workflow (exact simulations + surrogate '
            'fitting) for all registered models, or for a specific subset.\n\n'
            'Examples:\n'
            '  modena init all\n'
            "  modena init 'thermalDiffusion[material=Cu]'\n"
            "  modena init 'dielectricFunction[material=Cu]' "
            "'surfaceImpedance[material=Cu]'"
        ),
    )
    p.add_argument(
        'models', nargs='+', metavar='MODEL_ID',
        help='"all" to initialise every registered model, '
             'or one or more specific model IDs',
    )
    _add_launcher_args(p)
    p.set_defaults(func=_init_models)

    # ---------------------------------------------------------------- #
    # modena install                                                    #
    # ---------------------------------------------------------------- #
    p = groups.add_parser(
        'install',
        help='Install model packages to the MoDeNa models directory',
        description=(
            'Install one or more local model packages to ~/.modena/models '
            '(or --prefix) and register the path in ~/.modena/config.toml '
            'so that "import modena" makes them importable automatically.\n\n'
            'Packages are installed with --no-deps; framework dependencies '
            '(modena, numpy, ...) are expected to be present already.\n\n'
            'Install in dependency order when packages depend on each other:\n'
            '  modena install dielectricFunction/ emiShielding/'
        ),
    )
    p.add_argument(
        'packages', nargs='+', metavar='PATH',
        help='Path(s) to package directories containing pyproject.toml',
    )
    p.add_argument(
        '--prefix', type=str, default=None, metavar='DIR',
        help='Install prefix (default: ~/.modena/models)',
    )
    p.set_defaults(func=_install_models)

    # ---------------------------------------------------------------- #
    # modena sweep                                                      #
    # ---------------------------------------------------------------- #
    p = groups.add_parser(
        'sweep',
        help='Evaluate a surrogate over a parameter sweep and write CSV',
        description=(
            'Load a trained surrogate model and evaluate it over a grid of '
            'input values, writing all inputs and outputs to a CSV file.\n\n'
            'Examples:\n'
            "  modena sweep 'surfaceImpedance[material=Cu]' "
            '--param omega_eV=0.5:6.0:40 --fix d_nm=100 --out Zs_spectrum.csv\n'
            "  modena sweep 'structuralSE[geometry=enclosure]' "
            '--param omega_eV=0.5:6.0:40 --out SE_3d_spectrum.csv\n'
            "  modena sweep flowRate --param D=0.005:0.02:20 "
            '--param rho0=1.0:5.0:10'
        ),
    )
    p.add_argument('model_id', metavar='MODEL_ID',
                   help='Surrogate model ID (e.g. flowRate)')
    p.add_argument(
        '--param', metavar='name=min:max:n', action='append', required=True,
        help='Swept parameter spec (repeat for multiple axes; '
             'cartesian product is evaluated)',
    )
    p.add_argument(
        '--fix', metavar='name=value', action='append', default=None,
        help='Fixed input value (may be repeated)',
    )
    p.add_argument(
        '--out', metavar='FILE', default=None,
        help='Output CSV file (default: <model_id>_sweep.csv)',
    )
    p.set_defaults(func=_sweep)

    # ---------------------------------------------------------------- #
    # modena simulate                                                   #
    # ---------------------------------------------------------------- #
    p = groups.add_parser(
        'simulate',
        help='Run a simulation workflow for a model class',
        description=(
            'Instantiate a BackwardMappingScriptTask subclass and run it as a '
            'FireWorks workflow.\n\n'
            'The target class is resolved by importing the package and calling '
            'the class, so find_binary() is invoked automatically.\n\n'
            'The target may be omitted if [simulate] target is set in modena.toml.\n\n'
            'Examples:\n'
            '  modena simulate "twoTank.TwoTankModel"\n'
            '  modena simulate   # reads target from modena.toml'
        ),
    )
    p.add_argument(
        'target', nargs='?', default=None,
        metavar='PACKAGE.CLASS',
        help='Model class as "package.ClassName" '
             '(overrides [simulate] target in modena.toml)',
    )
    _add_launcher_args(p)
    p.set_defaults(func=_simulate)

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

    return parser


def _main():
    """Console script entry point for the ``modena`` command."""
    parser = _build_parser()
    args = parser.parse_args()

    if args.group is None:
        parser.print_help()
        return

    try:
        args.func(args)
    except FieldDoesNotExist as exc:
        # A schema field was removed while documents on disk still carry it.
        # mongoengine surfaces this as a traceback from deep inside its
        # deserialiser, which tells the reader nothing about the remedy.
        print(f'[modena] ERROR: this database was written by an older MoDeNa '
              f'schema and cannot be read.\n'
              f'         {exc}\n\n'
              f'         Inspect the affected documents:\n'
              f'             modena model migrate --check\n'
              f'         Then repair them in place:\n'
              f'             modena model migrate',
              file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    _main()
