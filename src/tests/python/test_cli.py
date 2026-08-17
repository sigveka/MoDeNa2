"""
Tests for modena.__main__ (the ``modena`` console script)
----------------------------------------------------------
The CLI had no coverage at all, which is how `modena model ls` shipped
reading an ``argPos`` key off outputs and parameters months after the
named-parameter rework removed it — its sibling `_model_show` was updated in
the same change and `_model_ls` was not.

Covers:
  - parser construction: group list, leaf handlers, bare-group help
  - argPos is read only off inputs (the regression above)
  - find_file: absolute paths, direct hits, recursive search, misses
  - fw run: --dir honoured, non-.py and missing files rejected cleanly
  - sweep: --param spec validation, empty-grid rejection
  - launcher kwargs: reset defaults off, qadapter=None passes through
  - install/init argument handling

No MongoDB, no libmodena, no FireWorks launchpad required.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import modena.__main__ as cli


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _args(**kw):
    """Build a stand-in for an argparse.Namespace."""
    ns = MagicMock()
    for k, v in kw.items():
        setattr(ns, k, v)
    return ns


def _launcher_args(**overrides):
    """Defaults matching what _add_launcher_args() produces."""
    base = dict(jobs=0, sequential=False, reset=False, launcher='rapidfire',
                escalate_at=0, qadapter=None, fworker=None, launch_dir='.')
    base.update(overrides)
    return _args(**base)


def _fake_model(inputs, outputs, params):
    """A SurrogateModel stand-in shaped like the real MongoEngine document.

    Crucially, only inputs carry an ``argPos`` key — outputs and parameters
    are plain ``MinMax`` documents, exactly as stored.  Indexing ``argPos``
    on them raises KeyError, the way mongoengine's EmbeddedDocument does.
    """
    class _Strict(dict):
        def __getitem__(self, key):
            if key not in self:
                raise KeyError(key)
            return super().__getitem__(key)

    sf = MagicMock()
    sf.name = 'someFunction'
    sf.__getitem__.side_effect = {
        'inputs':     {k: _Strict(argPos=i, min=0.0, max=1.0)
                       for i, k in enumerate(inputs)},
        'outputs':    {k: _Strict(min=0.0, max=1.0) for k in outputs},
        'parameters': {k: _Strict(min=0.0, max=1.0) for k in params},
    }.__getitem__

    m = MagicMock()
    m._id = 'someModel'
    m.surrogateFunction = sf
    m.parameters = {k: 1.0 for k in params}
    m.substituteModels = []
    return m


# ---------------------------------------------------------------------------
# Parser structure
# ---------------------------------------------------------------------------

class TestParser:

    def test_builds(self):
        assert cli._build_parser() is not None

    def test_groups_metavar_matches_registered_groups(self):
        """_GROUPS is advertised in --help; it must match what is registered."""
        parser = cli._build_parser()
        sub = next(a for a in parser._actions if a.dest == 'group')
        # Registered choices include no aliases at the top level.
        assert set(sub.choices) == set(cli._GROUPS)

    @pytest.mark.parametrize('argv', [
        ['model', 'ls'], ['model', 'list'], ['model', 'show', 'x'],
        ['model', 'freeze'], ['model', 'restore'], ['model', 'migrate'],
        ['model', 'refit', 'x'],
        ['fw', 'status'], ['fw', 'ls'], ['fw', 'reset'], ['fw', 'rerun', '1'],
        ['fw', 'orphans'], ['fw', 'run', '--script', 's.sh'],
        ['init', 'all'], ['install', '.'], ['sweep', 'm', '--param', 'a=0:1:2'],
        ['simulate'], ['doctor'], ['quickstart'],
    ])
    def test_every_leaf_command_has_a_handler(self, argv):
        args = cli._build_parser().parse_args(argv)
        assert callable(args.func)

    @pytest.mark.parametrize('group', ['fw', 'model'])
    def test_bare_group_prints_help_instead_of_erroring(self, group, capsys):
        """`modena fw` used to exit 2 with a two-line usage error."""
        args = cli._build_parser().parse_args([group])
        args.func(args)
        assert group in capsys.readouterr().out

    def test_sweep_requires_param(self):
        with pytest.raises(SystemExit):
            cli._build_parser().parse_args(['sweep', 'model'])

    def test_reset_defaults_to_off_on_every_launching_command(self):
        """Launching a workflow must not silently wipe the launchpad."""
        for argv in (['init', 'all'], ['simulate'], ['model', 'refit', 'm']):
            args = cli._build_parser().parse_args(argv)
            assert args.reset is False, argv


# ---------------------------------------------------------------------------
# model ls / show — the argPos regression
# ---------------------------------------------------------------------------

class TestModelListing:

    def test_ls_does_not_read_argpos_off_outputs_or_parameters(self, capsys):
        """Regression: outputs/parameters are MinMax — they have no argPos."""
        m = _fake_model(['x', 'y'], ['out'], ['P0', 'P1'])
        with patch.object(cli, 'SurrogateModel') as sm:
            sm.objects = [m]
            cli._model_ls(_args())
        out = capsys.readouterr().out
        assert 'out = someFunction( x, y  ;  P0, P1 )' in out

    def test_ls_orders_inputs_by_argpos(self, capsys):
        m = _fake_model(['a', 'b', 'c'], ['out'], [])
        # Reverse the stored argPos so declaration order alone cannot pass.
        ins = m.surrogateFunction['inputs']
        ins['a']['argPos'], ins['c']['argPos'] = 2, 0
        with patch.object(cli, 'SurrogateModel') as sm:
            sm.objects = [m]
            cli._model_ls(_args())
        assert 'c, b, a' in capsys.readouterr().out

    def test_ls_reports_empty_database(self, capsys):
        with patch.object(cli, 'SurrogateModel') as sm:
            sm.objects = []
            cli._model_ls(_args())
        assert 'No surrogate models' in capsys.readouterr().out

    def test_show_does_not_read_argpos_off_outputs_or_parameters(self, capsys):
        m = _fake_model(['x'], ['out'], ['P0'])
        with patch.object(cli, 'SurrogateModel') as sm:
            sm.objects.get.return_value = m
            cli._model_show(_args(id='someModel'))
        out = capsys.readouterr().out
        assert 'Parameters: P0' in out
        assert 'P0 = 1.0' in out


# ---------------------------------------------------------------------------
# find_file
# ---------------------------------------------------------------------------

class TestFindFile:

    def test_absolute_path_does_not_raise(self, tmp_path):
        """Path.rglob refuses absolute patterns with NotImplementedError."""
        f = tmp_path / 'wf.yaml'
        f.write_text('x')
        assert cli.find_file(str(f)) == f

    def test_absolute_path_missing_returns_none(self, tmp_path):
        assert cli.find_file(str(tmp_path / 'nope.yaml')) is None

    def test_relative_direct_hit(self, tmp_path):
        (tmp_path / 'wf.yaml').write_text('x')
        assert cli.find_file('wf.yaml', tmp_path) == tmp_path / 'wf.yaml'

    def test_recursive_search(self, tmp_path):
        nested = tmp_path / 'a' / 'b'
        nested.mkdir(parents=True)
        (nested / 'wf.yaml').write_text('x')
        assert cli.find_file('wf.yaml', tmp_path) == nested / 'wf.yaml'

    def test_missing_returns_none(self, tmp_path):
        assert cli.find_file('nope.yaml', tmp_path) is None


# ---------------------------------------------------------------------------
# fw run
# ---------------------------------------------------------------------------

class TestFwRun:

    def test_rejects_missing_dir(self, tmp_path):
        args = _args(dir=str(tmp_path / 'nope'), script=None,
                     workflow=None, py=None)
        with pytest.raises(SystemExit) as exc:
            cli._fw_run(args)
        assert exc.value.code == 1

    def test_py_rejects_non_python_file(self, tmp_path):
        """Used to die with AttributeError: 'NoneType' has no attribute 'loader'."""
        f = tmp_path / 'wf.txt'
        f.write_text('print("hi")')
        args = _args(dir=str(tmp_path), script=None, workflow=None, py='wf.txt')
        with pytest.raises(SystemExit) as exc:
            cli._fw_run(args)
        assert exc.value.code == 1

    def test_py_rejects_missing_file(self, tmp_path):
        args = _args(dir=str(tmp_path), script=None, workflow=None, py='nope.py')
        with pytest.raises(SystemExit) as exc:
            cli._fw_run(args)
        assert exc.value.code == 1

    def test_py_executes_in_rundir(self, tmp_path):
        """--dir was validated and then ignored for --py."""
        (tmp_path / 'wf.py').write_text(
            'import os, pathlib\n'
            'pathlib.Path("cwd.txt").write_text(os.getcwd())\n'
        )
        args = _args(dir=str(tmp_path), script=None, workflow=None, py='wf.py')
        origin = Path.cwd()
        cli._fw_run(args)
        assert Path(tmp_path / 'cwd.txt').read_text() == str(tmp_path.resolve())
        assert Path.cwd() == origin, 'cwd must be restored'

    def test_py_restores_cwd_after_failure(self, tmp_path):
        (tmp_path / 'wf.py').write_text('raise RuntimeError("boom")\n')
        args = _args(dir=str(tmp_path), script=None, workflow=None, py='wf.py')
        origin = Path.cwd()
        with pytest.raises(RuntimeError):
            cli._fw_run(args)
        assert Path.cwd() == origin

    def test_script_writes_workflow_into_rundir(self, tmp_path, capsys):
        args = _args(dir=str(tmp_path), script='./run.sh',
                     workflow=None, py=None)
        cli._fw_run(args)
        generated = tmp_path / 'workflow.yaml'
        assert generated.is_file()
        body = generated.read_text()
        assert '{{modena.Strategy.BackwardMappingScriptTask}}' in body
        assert str(tmp_path.resolve()) in body


# ---------------------------------------------------------------------------
# sweep argument handling
# ---------------------------------------------------------------------------

class TestSweep:

    def _run(self, **kw):
        opts = dict(model_id='m', param=[], fix=None, out=None)
        opts.update(kw)
        with patch.dict(sys.modules, {'modena': MagicMock()}):
            cli._sweep(_args(**opts))

    @pytest.mark.parametrize('spec', [
        'D=0.01:0.02',      # too few fields
        'D=a:b:3',          # non-numeric bounds
        'D=0:1:x',          # non-integer count
        'noequalssign',     # missing '='
    ])
    def test_rejects_malformed_param(self, spec):
        with pytest.raises(SystemExit) as exc:
            self._run(param=[spec])
        assert exc.value.code == 1

    @pytest.mark.parametrize('n', ['0', '-3'])
    def test_rejects_empty_grid(self, n):
        """n < 1 collapsed the cartesian product and hit IndexError on rows[0]."""
        with pytest.raises(SystemExit) as exc:
            self._run(param=[f'D=0:1:{n}'])
        assert exc.value.code == 1

    def test_rejects_malformed_fix(self):
        with pytest.raises(SystemExit) as exc:
            self._run(param=['D=0:1:2'], fix=['rho0'])
        assert exc.value.code == 1


# ---------------------------------------------------------------------------
# Launcher kwargs
# ---------------------------------------------------------------------------

class TestLauncherKwargs:

    def test_reset_is_off_by_default(self):
        assert cli._build_run_kwargs(_launcher_args())['reset'] is False

    def test_reset_passes_through(self):
        assert cli._build_run_kwargs(_launcher_args(reset=True))['reset'] is True

    def test_sequential_means_one_job(self):
        kw = cli._build_run_kwargs(_launcher_args(jobs=8, sequential=True))
        assert kw['njobs'] == 1

    def test_jobs_passes_through(self):
        assert cli._build_run_kwargs(_launcher_args(jobs=4))['njobs'] == 4

    def test_rapidfire_omits_queue_kwargs(self):
        kw = cli._build_run_kwargs(_launcher_args())
        assert 'qadapter' not in kw and 'escalate_at' not in kw

    @pytest.mark.parametrize('launcher', ['qlaunch', 'auto'])
    def test_missing_qadapter_is_not_rejected_here(self, launcher):
        """Runner.run() falls back to QUEUEADAPTER_LOC; rejecting None made
        that documented fallback unreachable."""
        kw = cli._build_run_kwargs(_launcher_args(launcher=launcher))
        assert kw['qadapter'] is None

    def test_escalate_at_only_for_auto(self):
        assert 'escalate_at' in cli._build_run_kwargs(
            _launcher_args(launcher='auto', qadapter='q.yaml'))
        assert 'escalate_at' not in cli._build_run_kwargs(
            _launcher_args(launcher='qlaunch', qadapter='q.yaml'))

    def test_launch_reports_run_valueerror_cleanly(self, capsys):
        """A bad launcher combination must not surface as a traceback."""
        fake = MagicMock()
        fake.run.side_effect = ValueError('needs a qadapter')
        with patch.dict(sys.modules, {'modena': fake}):
            with pytest.raises(SystemExit) as exc:
                cli._launch(MagicMock(), _launcher_args(launcher='qlaunch'))
        assert exc.value.code == 1
        assert 'needs a qadapter' in capsys.readouterr().err


# ---------------------------------------------------------------------------
# install
# ---------------------------------------------------------------------------

class TestInstall:

    def test_validates_all_packages_before_installing_any(self, tmp_path):
        """A typo in the last argument used to abort mid-install."""
        good = tmp_path / 'good'
        good.mkdir()
        (good / 'pyproject.toml').write_text('[project]\nname="good"\n')
        bad = tmp_path / 'bad'
        bad.mkdir()

        args = _args(packages=[str(good), str(bad)], prefix=str(tmp_path / 'p'))
        with patch.object(cli, '_ensure_models_path_registered') as reg, \
             patch('subprocess.run') as sp:
            with pytest.raises(SystemExit) as exc:
                cli._install_models(args)
        assert exc.value.code == 1
        assert sp.call_count == 0, 'nothing may be installed'
        assert reg.call_count == 0

    def test_registers_resolved_prefix_once(self, tmp_path):
        """An unresolved prefix was appended on every run under a symlinked home."""
        cfg = tmp_path / '.modena' / 'config.toml'
        prefix = tmp_path / 'models'
        prefix.mkdir()
        with patch.object(cli.Path, 'home', return_value=tmp_path):
            cli._ensure_models_path_registered(prefix)
            cli._ensure_models_path_registered(prefix)
        from modena.Registry import _load_toml
        assert _load_toml(cfg)['models']['paths'] == [str(prefix.resolve())]


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

class TestInit:

    def test_all_is_recognised_among_other_arguments(self):
        """`args.models == ['all']` missed `modena init all extraModel`."""
        fake_modena = MagicMock()
        fake_modena.SurrogateModel.get_instances.return_value = []
        # _init_models re-imports ModelRegistry from modena.Registry, so the
        # patch has to land there rather than on the cli module attribute.
        with patch.dict(sys.modules, {'modena': fake_modena}), \
             patch('modena.Registry.ModelRegistry') as reg:
            reg.return_value.load.return_value.active_packages.return_value = {}
            with pytest.raises(SystemExit) as exc:
                cli._init_models(_launcher_args(models=['all', 'other']))
        # 'all' selected everything (nothing registered) rather than being
        # reported as a missing model id.
        assert exc.value.code == 0


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------

class TestDoctor:

    def test_exits_nonzero_when_a_check_fails(self):
        """`modena doctor` returned 0 unconditionally, so it could not gate CI."""
        with patch.object(cli, '_find_project_config', return_value=None):
            with pytest.raises(SystemExit) as exc:
                cli._doctor(_args())
        assert exc.value.code == 1


# ---------------------------------------------------------------------------
# Legacy-schema migration (modena model migrate)
# ---------------------------------------------------------------------------
# argPos was removed from outputs and parameters by the named-parameter
# rework.  MinMax is a strict EmbeddedDocument, so a database written before
# that change cannot be READ at all -- mongoengine raises FieldDoesNotExist
# from inside its deserialiser and every command dies with a traceback.
#
# These use a hand-rolled fake rather than mongomock because _find_legacy_fields
# deliberately bypasses mongoengine: the whole point is that these documents
# cannot be loaded through it.

def _legacy_doc():
    return {
        '_id': 'legacy_fn',
        'inputs':     {'T':  {'min': 0.0, 'max': 1.0, 'argPos': 0}},
        'outputs':    {'y':  {'min': 0.0, 'max': 1.0, 'argPos': 0}},
        'parameters': {'p0': {'min': 0.0, 'max': 1.0, 'argPos': 0},
                       'p1': {'min': 0.0, 'max': 1.0, 'argPos': 1}},
    }


class _FakeCollection:
    def __init__(self, docs):
        self.docs = {d['_id']: d for d in docs}

    def find(self):
        return list(self.docs.values())

    def update_one(self, flt, update):
        doc = self.docs[flt['_id']]
        for path in update['$unset']:
            section, name, key = path.split('.')
            doc[section][name].pop(key, None)


class _FakeDB(dict):
    def __getitem__(self, name):
        return self.setdefault(name, _FakeCollection([]))


@pytest.fixture
def fake_db(monkeypatch):
    db = _FakeDB()
    db['surrogate_function'] = _FakeCollection([_legacy_doc()])
    monkeypatch.setattr('mongoengine.connection.get_db', lambda *a, **k: db)
    return db


class TestMigrate:

    def test_finds_only_outputs_and_parameters(self, fake_db):
        """Inputs legitimately carry argPos and must be left alone."""
        (_coll, _id, paths), = cli._find_legacy_fields()
        assert sorted(paths) == ['outputs.y.argPos',
                                 'parameters.p0.argPos',
                                 'parameters.p1.argPos']
        assert not any(p.startswith('inputs.') for p in paths)

    def test_check_does_not_modify(self, fake_db, capsys):
        cli._model_migrate(_args(check=True))
        assert 'not modified' in capsys.readouterr().out
        doc = fake_db['surrogate_function'].docs['legacy_fn']
        assert 'argPos' in doc['outputs']['y'], 'argPos removed despite --check'

    def test_strips_stale_fields_and_is_idempotent(self, fake_db, capsys):
        cli._model_migrate(_args(check=False))
        capsys.readouterr()

        doc = fake_db['surrogate_function'].docs['legacy_fn']
        assert 'argPos' not in doc['outputs']['y']
        assert 'argPos' not in doc['parameters']['p0']
        assert doc['inputs']['T']['argPos'] == 0, 'input argPos must survive'
        assert doc['outputs']['y']['min'] == 0.0, 'min/max must survive'
        assert not cli._find_legacy_fields()

        cli._model_migrate(_args(check=False))
        assert 'nothing to migrate' in capsys.readouterr().out

    def test_clean_database_is_a_no_op(self, monkeypatch, capsys):
        db = _FakeDB()
        db['surrogate_function'] = _FakeCollection([{
            '_id': 'clean_fn',
            'inputs':     {'T':  {'min': 0.0, 'max': 1.0, 'argPos': 0}},
            'outputs':    {'y':  {'min': 0.0, 'max': 1.0}},
            'parameters': {'p0': {'min': 0.0, 'max': 1.0}},
        }])
        monkeypatch.setattr('mongoengine.connection.get_db', lambda *a, **k: db)
        cli._model_migrate(_args(check=False))
        assert 'nothing to migrate' in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Legacy-database error reporting and remaining parser contracts
# ---------------------------------------------------------------------------

def test_field_does_not_exist_is_reported_with_the_remedy(monkeypatch, capsys):
    """A legacy database must produce guidance, not a mongoengine traceback.

    Drives the real ``_main`` dispatch rather than a copy of it, so the test
    fails if the handler is removed from ``_main``.
    """
    from mongoengine.errors import FieldDoesNotExist

    def _boom(_a):
        raise FieldDoesNotExist(
            'The fields "{\'argPos\'}" do not exist on the document "MinMax"')

    monkeypatch.setattr(cli, '_model_ls', _boom)
    monkeypatch.setattr(sys, 'argv', ['modena', 'model', 'ls'])

    with pytest.raises(SystemExit) as exc:
        cli._main()

    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert 'older MoDeNa schema' in err
    assert 'modena model migrate --check' in err
    assert 'Traceback' not in err


def test_ls_and_list_are_the_same_command():
    parser = cli._build_parser()
    assert parser.parse_args(['model', 'ls']).func is \
           parser.parse_args(['model', 'list']).func


def test_every_group_has_a_description():
    """`-h` on a group should explain the group, not just list flags."""
    import argparse as _ap
    parser = cli._build_parser()
    action = next(a for a in parser._actions
                  if isinstance(a, _ap._SubParsersAction))
    undocumented = [n for n, p in action.choices.items() if not p.description]
    assert not undocumented, f'groups without a description: {undocumented}'


def test_model_ls_and_show_agree_on_ordering(capsys):
    """Both must derive ordering the same way, or they disagree about a model."""
    m = _fake_model(['b', 'a'], ['out'], ['P0', 'P1'])
    # Separate patches: _model_ls iterates SurrogateModel.objects while
    # _model_show calls .objects.get(), and one MagicMock attribute cannot
    # sensibly be both a list and an object with .get().
    with patch.object(cli, 'SurrogateModel') as sm:
        sm.objects = [m]
        cli._model_ls(_args())
        ls_out = capsys.readouterr().out
    with patch.object(cli, 'SurrogateModel') as sm:
        sm.objects.get.return_value = m
        cli._model_show(_args(id='someModel'))
        show_out = capsys.readouterr().out
    assert 'b, a' in ls_out and 'Inputs:     b, a' in show_out
    assert 'P0, P1' in ls_out and 'Parameters: P0, P1' in show_out
