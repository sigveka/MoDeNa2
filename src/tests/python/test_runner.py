"""
Tests for modena.Runner (modena.run)
-------------------------------------
Covers:
  - run() with a Workflow  — resets, adds, calls rapidfire, returns lpad
  - run() with a Firework  — wraps in Workflow automatically
  - run() reset=False      — does not call lpad.reset()
  - run() reset=True       — calls lpad.reset() with correct args
  - run() empty model list — short-circuits before rapidfire
  - run() logs done msg    — log record contains 'done'
  - run() passes sleep_time to rapidfire
  - run() passes timeout to rapidfire when set

All tests use njobs=1 to keep execution in-process so that unittest.mock
patches on fireworks.core.rocket_launcher.rapidfire are visible to run().
With njobs>1, run() spawns worker processes that inherit a fresh Python
interpreter and bypass any in-process patches.

No MongoDB or libmodena required.
"""

import pytest
from unittest.mock import MagicMock, patch, call


def _make_lpad():
    """Return a minimal mock LaunchPad."""
    lp = MagicMock()
    lp.get_fw_ids.return_value = []
    lp.state_summary.return_value = 'COMPLETED=1'
    # No launches: run()/launch() look for failed ones afterwards, and a bare
    # MagicMock would answer with more MagicMocks rather than "none".
    lp.launches.find_one.return_value = None
    lp.launches.find.return_value = []
    return lp


# ---------------------------------------------------------------------------
# Basic invocation
# ---------------------------------------------------------------------------

class TestRunBasic:

    def test_returns_launchpad(self):
        from fireworks import Firework, Workflow
        from modena.Runner import run
        lp = _make_lpad()
        with patch('modena.Runner.rapidfire'):
            result = run(Workflow([Firework([])]), lpad=lp, reset=False, njobs=1)
        assert result is lp

    def test_adds_workflow_to_lpad(self):
        from fireworks import Firework, Workflow
        from modena.Runner import run
        lp = _make_lpad()
        wf = Workflow([Firework([])])
        with patch('modena.Runner.rapidfire'):
            run(wf, lpad=lp, reset=False, njobs=1)
        lp.add_wf.assert_called_once_with(wf)

    def test_calls_rapidfire(self):
        from fireworks import Firework, Workflow
        from modena.Runner import run
        lp = _make_lpad()
        with patch('modena.Runner.rapidfire') as mock_rf:
            run(Workflow([Firework([])]), lpad=lp, reset=False, njobs=1)
        mock_rf.assert_called_once()

    def test_logs_done(self, caplog):
        import logging
        from fireworks import Firework, Workflow
        from modena.Runner import run
        lp = _make_lpad()
        with caplog.at_level(logging.INFO, logger='modena.runner'):
            with patch('modena.Runner.rapidfire'):
                run(Workflow([Firework([])]), lpad=lp, reset=False, njobs=1)
        assert 'done' in caplog.text.lower()


# ---------------------------------------------------------------------------
# Firework (not Workflow) input
# ---------------------------------------------------------------------------

class TestRunWithFirework:

    def test_single_firework_wrapped_in_workflow(self):
        from fireworks import Firework
        from modena.Runner import run
        lp = _make_lpad()
        with patch('modena.Runner.rapidfire'):
            run(Firework([]), lpad=lp, reset=False, njobs=1)
        lp.add_wf.assert_called_once()


# ---------------------------------------------------------------------------
# reset behaviour
# ---------------------------------------------------------------------------

class TestRunReset:

    def test_reset_true_calls_lpad_reset(self):
        from fireworks import Firework, Workflow
        from modena.Runner import run
        lp = _make_lpad()
        with patch('modena.Runner.rapidfire'):
            run(Workflow([Firework([])]), lpad=lp, reset=True, njobs=1)
        lp.reset.assert_called_once_with('', require_password=False)

    def test_reset_false_does_not_call_lpad_reset(self):
        from fireworks import Firework, Workflow
        from modena.Runner import run
        lp = _make_lpad()
        with patch('modena.Runner.rapidfire'):
            run(Workflow([Firework([])]), lpad=lp, reset=False, njobs=1)
        lp.reset.assert_not_called()


# ---------------------------------------------------------------------------
# Empty model list
# ---------------------------------------------------------------------------

class TestRunEmptyModels:

    def test_empty_list_skips_rapidfire(self):
        from modena.Runner import run
        lp = _make_lpad()
        with patch('fireworks.core.rocket_launcher.rapidfire') as mock_rf:
            run([], lpad=lp)
        mock_rf.assert_not_called()

    def test_empty_list_returns_lpad(self):
        from modena.Runner import run
        lp = _make_lpad()
        with patch('fireworks.core.rocket_launcher.rapidfire'):
            result = run([], lpad=lp)
        assert result is lp

    def test_empty_list_logs_nothing_to_do(self, caplog):
        import logging
        from modena.Runner import run
        lp = _make_lpad()
        with caplog.at_level(logging.INFO, logger='modena.runner'):
            with patch('fireworks.core.rocket_launcher.rapidfire'):
                run([], lpad=lp)
        assert 'nothing' in caplog.text.lower() or 'no model' in caplog.text.lower()


# ---------------------------------------------------------------------------
# rapidfire kwargs forwarding
# ---------------------------------------------------------------------------

class TestRunRapidfireKwargs:

    def test_sleep_time_forwarded(self):
        from fireworks import Firework, Workflow
        from modena.Runner import run
        lp = _make_lpad()
        with patch('modena.Runner.rapidfire') as mock_rf:
            run(Workflow([Firework([])]), lpad=lp, reset=False, sleep_time=5, njobs=1)
        _, kwargs = mock_rf.call_args
        assert kwargs.get('sleep_time') == 5

    def test_timeout_forwarded_when_set(self):
        from fireworks import Firework, Workflow
        from modena.Runner import run
        lp = _make_lpad()
        with patch('modena.Runner.rapidfire') as mock_rf:
            run(Workflow([Firework([])]), lpad=lp, reset=False, timeout=120, njobs=1)
        _, kwargs = mock_rf.call_args
        assert kwargs.get('timeout') == 120

    def test_timeout_not_forwarded_when_none(self):
        from fireworks import Firework, Workflow
        from modena.Runner import run
        lp = _make_lpad()
        with patch('modena.Runner.rapidfire') as mock_rf:
            run(Workflow([Firework([])]), lpad=lp, reset=False, timeout=None, njobs=1)
        _, kwargs = mock_rf.call_args
        assert 'timeout' not in kwargs


# ---------------------------------------------------------------------------
# Local worker count (njobs)
# ---------------------------------------------------------------------------

class TestLocalWorkers:
    """njobs used to be silently ignored for 'rapidfire' and 'auto', so the
    CLI's --jobs / --sequential flags did nothing on the default launcher."""

    @pytest.mark.parametrize('njobs', [0, 1])
    def test_single_worker_runs_in_process(self, njobs):
        from fireworks import Firework, Workflow
        from modena.Runner import run
        lp = _make_lpad()
        with patch('modena.Runner.rapidfire') as mock_rf, \
             patch('modena.Runner.launch_multiprocess') as mock_mp:
            run(Workflow([Firework([])]), lpad=lp, reset=False, njobs=njobs)
        assert mock_rf.call_count == 1
        assert mock_mp.call_count == 0

    def test_multiple_workers_use_job_packing(self):
        from fireworks import Firework, Workflow
        from modena.Runner import run
        lp = _make_lpad()
        with patch('modena.Runner.rapidfire') as mock_rf, \
             patch('modena.Runner.launch_multiprocess') as mock_mp:
            run(Workflow([Firework([])]), lpad=lp, reset=False, njobs=4)
        assert mock_rf.call_count == 0
        _, kwargs = mock_mp.call_args
        assert kwargs['num_jobs'] == 4
        assert kwargs['nlaunches'] == 0        # run to completion
        assert kwargs['fworker'] is not None

    def test_auto_launcher_also_honours_njobs(self):
        from fireworks import Firework, Workflow
        from modena.Runner import run
        lp = _make_lpad()
        with patch('modena.Runner.launch_multiprocess') as mock_mp, \
             patch('modena.Runner._auto_supervisor'), \
             patch('modena.Runner._resolve_qadapter', return_value=MagicMock()):
            run(Workflow([Firework([])]), lpad=lp, reset=False,
                launcher='auto', njobs=3)
        _, kwargs = mock_mp.call_args
        assert kwargs['num_jobs'] == 3


# ---------------------------------------------------------------------------
# A failed firework must fail run() / launch()
# ---------------------------------------------------------------------------
# A task ends its workflow on an error by returning a defuse action, which
# FireWorks records as COMPLETED.  run() used to return normally regardless,
# so `modena.run(wf); print("Workflow complete.")` announced success for a
# simulation that had died.  The workflow_failed() action now records the
# reason, and run() raises WorkflowFailed when a launch of this run carries
# one -- or FIZZLED.

class TestFailureDetection:

    @pytest.fixture
    def lp(self):
        import mongomock
        db = mongomock.MongoClient().db
        lp = _make_lpad()
        lp.launches = db.launches
        lp.fireworks = db.fireworks
        return lp

    @staticmethod
    def _launch(lp, launch_id, fw_id, name, state='COMPLETED', stored=None, **action):
        lp.fireworks.insert_one({'fw_id': fw_id, 'name': name})
        lp.launches.insert_one({
            'launch_id': launch_id, 'fw_id': fw_id, 'state': state,
            'action': dict(action, stored_data=stored or {}),
        })

    def _run(self, lp, during):
        """run() with a fake worker that records *during*'s launches."""
        from fireworks import Firework, Workflow
        from modena.Runner import run
        with patch('modena.Runner.rapidfire',
                   side_effect=lambda *a, **k: during(lp)):
            return run(Workflow([Firework([])]), lpad=lp, reset=False, njobs=1)

    def test_a_recorded_failure_raises(self, lp):
        from modena.Runner import WorkflowFailed
        from modena.Strategy import FAILURE_KEY

        def worker(lp):
            self._launch(lp, 1, 7, 'simulation TwoTankModel', defuse_workflow=True,
                         stored={FAILURE_KEY: 'macroscopic simulation terminated: rc 1'})
        with pytest.raises(WorkflowFailed) as excinfo:
            self._run(lp, worker)
        assert excinfo.value.failures == [
            (7, 'simulation TwoTankModel', 'macroscopic simulation terminated: rc 1')]
        assert 'simulation TwoTankModel' in str(excinfo.value)

    def test_a_fizzled_launch_raises_with_the_last_traceback_line(self, lp):
        from modena.Runner import WorkflowFailed

        def worker(lp):
            self._launch(lp, 1, 3, 'fit', state='FIZZLED', stored={
                '_exception': {'_stacktrace': 'Traceback ...\nValueError: boom\n'}})
        with pytest.raises(WorkflowFailed) as excinfo:
            self._run(lp, worker)
        assert excinfo.value.failures == [(3, 'fit', 'ValueError: boom')]

    def test_failures_from_before_this_run_are_ignored(self, lp):
        from modena.Strategy import FAILURE_KEY
        self._launch(lp, 5, 1, 'old', stored={FAILURE_KEY: 'an earlier run'})

        def worker(lp):
            self._launch(lp, 6, 2, 'new')
        assert self._run(lp, worker) is lp

    def test_success_and_recoveries_return_normally(self, lp):
        def worker(lp):
            self._launch(lp, 1, 1, 'sim')                          # plain success
            self._launch(lp, 2, 2, 'sim', detours=[{'fws': []}])    # OOB detour
        assert self._run(lp, worker) is lp
