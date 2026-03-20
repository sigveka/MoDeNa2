"""
Tests for modena.Runner (modena.run)
-------------------------------------
Covers:
  - run() with a Workflow  — resets, adds, calls rapidfire, returns lpad
  - run() with a Firework  — wraps in Workflow automatically
  - run() reset=False      — does not call lpad.reset()
  - run() reset=True       — calls lpad.reset() with correct args
  - run() empty model list — short-circuits before rapidfire
  - run() prints done msg  — output contains 'done'
  - run() passes sleep_time to rapidfire
  - run() passes timeout to rapidfire when set

No MongoDB or libmodena required.
"""

import pytest
from unittest.mock import MagicMock, patch, call


def _make_lpad():
    """Return a minimal mock LaunchPad."""
    lp = MagicMock()
    lp.get_fw_ids.return_value = []
    lp.state_summary.return_value = 'COMPLETED=1'
    return lp


# ---------------------------------------------------------------------------
# Basic invocation
# ---------------------------------------------------------------------------

class TestRunBasic:

    def test_returns_launchpad(self):
        from fireworks import Firework, Workflow
        from modena.Runner import run
        lp = _make_lpad()
        with patch('fireworks.core.rocket_launcher.rapidfire'):
            result = run(Workflow([Firework([])]), lpad=lp, reset=False)
        assert result is lp

    def test_adds_workflow_to_lpad(self):
        from fireworks import Firework, Workflow
        from modena.Runner import run
        lp = _make_lpad()
        wf = Workflow([Firework([])])
        with patch('fireworks.core.rocket_launcher.rapidfire'):
            run(wf, lpad=lp, reset=False)
        lp.add_wf.assert_called_once_with(wf)

    def test_calls_rapidfire(self):
        from fireworks import Firework, Workflow
        from modena.Runner import run
        lp = _make_lpad()
        with patch('fireworks.core.rocket_launcher.rapidfire') as mock_rf:
            run(Workflow([Firework([])]), lpad=lp, reset=False)
        mock_rf.assert_called_once()

    def test_prints_done(self, capsys):
        from fireworks import Firework, Workflow
        from modena.Runner import run
        lp = _make_lpad()
        with patch('fireworks.core.rocket_launcher.rapidfire'):
            run(Workflow([Firework([])]), lpad=lp, reset=False)
        assert 'done' in capsys.readouterr().out.lower()


# ---------------------------------------------------------------------------
# Firework (not Workflow) input
# ---------------------------------------------------------------------------

class TestRunWithFirework:

    def test_single_firework_wrapped_in_workflow(self):
        from fireworks import Firework
        from modena.Runner import run
        lp = _make_lpad()
        with patch('fireworks.core.rocket_launcher.rapidfire'):
            run(Firework([]), lpad=lp, reset=False)
        lp.add_wf.assert_called_once()


# ---------------------------------------------------------------------------
# reset behaviour
# ---------------------------------------------------------------------------

class TestRunReset:

    def test_reset_true_calls_lpad_reset(self):
        from fireworks import Firework, Workflow
        from modena.Runner import run
        lp = _make_lpad()
        with patch('fireworks.core.rocket_launcher.rapidfire'):
            run(Workflow([Firework([])]), lpad=lp, reset=True)
        lp.reset.assert_called_once_with('', require_password=False)

    def test_reset_false_does_not_call_lpad_reset(self):
        from fireworks import Firework, Workflow
        from modena.Runner import run
        lp = _make_lpad()
        with patch('fireworks.core.rocket_launcher.rapidfire'):
            run(Workflow([Firework([])]), lpad=lp, reset=False)
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

    def test_empty_list_prints_nothing_to_do(self, capsys):
        from modena.Runner import run
        lp = _make_lpad()
        with patch('fireworks.core.rocket_launcher.rapidfire'):
            run([], lpad=lp)
        out = capsys.readouterr().out
        assert 'nothing' in out.lower() or 'no model' in out.lower()


# ---------------------------------------------------------------------------
# rapidfire kwargs forwarding
# ---------------------------------------------------------------------------

class TestRunRapidfireKwargs:

    def test_sleep_time_forwarded(self):
        from fireworks import Firework, Workflow
        from modena.Runner import run
        lp = _make_lpad()
        with patch('fireworks.core.rocket_launcher.rapidfire') as mock_rf:
            run(Workflow([Firework([])]), lpad=lp, reset=False, sleep_time=5)
        _, kwargs = mock_rf.call_args
        assert kwargs.get('sleep_time') == 5

    def test_timeout_forwarded_when_set(self):
        from fireworks import Firework, Workflow
        from modena.Runner import run
        lp = _make_lpad()
        with patch('fireworks.core.rocket_launcher.rapidfire') as mock_rf:
            run(Workflow([Firework([])]), lpad=lp, reset=False, timeout=120)
        _, kwargs = mock_rf.call_args
        assert kwargs.get('timeout') == 120

    def test_timeout_not_forwarded_when_none(self):
        from fireworks import Firework, Workflow
        from modena.Runner import run
        lp = _make_lpad()
        with patch('fireworks.core.rocket_launcher.rapidfire') as mock_rf:
            run(Workflow([Firework([])]), lpad=lp, reset=False, timeout=None)
        _, kwargs = mock_rf.call_args
        assert 'timeout' not in kwargs
