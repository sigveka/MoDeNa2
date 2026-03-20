"""
Tests for modena.Launchpad
--------------------------
Covers:
  - ModenaConnectionError  message and inheritance
  - _pid_alive             with live and dead PIDs
  - _this_hostname         return type
  - state_counts           with mocked get_fw_ids
  - state_summary          empty and non-empty launchpad
  - reset                  warns when RUNNING/RESERVED fireworks exist
  - defuse_orphans         age-based detection, PID-based detection

None of these tests require a live MongoDB connection.
"""

import os
import pytest
from unittest.mock import MagicMock, patch, call
from datetime import datetime, timezone, timedelta


# ---------------------------------------------------------------------------
# ModenaConnectionError
# ---------------------------------------------------------------------------

class TestModenaConnectionError:

    def test_is_runtime_error(self):
        from modena.Launchpad import ModenaConnectionError
        assert issubclass(ModenaConnectionError, RuntimeError)

    def test_message_contains_uri(self):
        from modena.Launchpad import ModenaConnectionError
        uri = 'mongodb://myhost:27017/modena'
        msg = str(ModenaConnectionError(uri))
        assert uri in msg

    def test_message_contains_mongod_hint(self):
        from modena.Launchpad import ModenaConnectionError
        msg = str(ModenaConnectionError('mongodb://localhost:27017/test'))
        assert 'mongod' in msg

    def test_message_contains_modena_uri_hint(self):
        from modena.Launchpad import ModenaConnectionError
        msg = str(ModenaConnectionError('mongodb://localhost:27017/test'))
        assert 'MODENA_URI' in msg


# ---------------------------------------------------------------------------
# _pid_alive
# ---------------------------------------------------------------------------

class TestPidAlive:

    def test_current_process_is_alive(self):
        from modena.Launchpad import _pid_alive
        assert _pid_alive(os.getpid()) is True

    def test_nonexistent_pid_is_dead(self):
        from modena.Launchpad import _pid_alive
        # PID 999999999 is astronomically unlikely to exist
        assert _pid_alive(999_999_999) is False


# ---------------------------------------------------------------------------
# _this_hostname
# ---------------------------------------------------------------------------

class TestThisHostname:

    def test_returns_string(self):
        import socket
        from modena.Launchpad import _this_hostname
        assert _this_hostname() == socket.gethostname()


# ---------------------------------------------------------------------------
# state_counts / state_summary
# ---------------------------------------------------------------------------

_ALL_STATES = ['READY', 'RUNNING', 'WAITING', 'COMPLETED',
               'RESERVED', 'FIZZLED', 'DEFUSED', 'PAUSED']


class TestStateCounts:

    def _make_lpad(self, counts: dict):
        """Create a ModenaLaunchPad mock whose get_fw_ids returns counts."""
        from modena.Launchpad import ModenaLaunchPad
        lp = MagicMock(spec=ModenaLaunchPad)
        # get_fw_ids(query={'state': s}) returns a list of the right length
        def _get_fw_ids(query=None):
            state = (query or {}).get('state', '')
            return list(range(counts.get(state, 0)))
        lp.get_fw_ids.side_effect = _get_fw_ids
        return lp

    def test_all_zeros(self):
        from modena.Launchpad import ModenaLaunchPad
        lp = self._make_lpad({})
        result = ModenaLaunchPad.state_counts(lp)
        assert all(v == 0 for v in result.values())
        assert set(result.keys()) == set(_ALL_STATES)

    def test_mixed_counts(self):
        from modena.Launchpad import ModenaLaunchPad
        lp = self._make_lpad({'READY': 3, 'COMPLETED': 7})
        result = ModenaLaunchPad.state_counts(lp)
        assert result['READY'] == 3
        assert result['COMPLETED'] == 7
        assert result['RUNNING'] == 0


class TestStateSummary:

    def _lpad_with_counts(self, counts: dict):
        from modena.Launchpad import ModenaLaunchPad
        lp = MagicMock(spec=ModenaLaunchPad)
        lp.state_counts.return_value = {s: counts.get(s, 0) for s in _ALL_STATES}
        return lp

    def test_empty_launchpad(self):
        from modena.Launchpad import ModenaLaunchPad
        lp = self._lpad_with_counts({})
        assert ModenaLaunchPad.state_summary(lp) == 'empty'

    def test_non_empty_contains_nonzero_states(self):
        from modena.Launchpad import ModenaLaunchPad
        lp = self._lpad_with_counts({'READY': 2, 'COMPLETED': 5})
        summary = ModenaLaunchPad.state_summary(lp)
        assert 'READY=2' in summary
        assert 'COMPLETED=5' in summary

    def test_zero_states_omitted(self):
        from modena.Launchpad import ModenaLaunchPad
        lp = self._lpad_with_counts({'READY': 1})
        summary = ModenaLaunchPad.state_summary(lp)
        assert 'RUNNING' not in summary
        assert 'WAITING' not in summary


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------

class TestReset:

    def test_reset_warns_when_running_exist(self, capsys):
        from modena.Launchpad import ModenaLaunchPad
        lp = MagicMock(spec=ModenaLaunchPad)
        lp.get_fw_ids.side_effect = lambda query=None: (
            [1, 2] if (query or {}).get('state') == 'RUNNING' else []
        )
        with patch.object(ModenaLaunchPad.__bases__[0], 'reset', return_value=None):
            ModenaLaunchPad.reset(lp, '', require_password=False)
        out = capsys.readouterr().out
        assert 'WARNING' in out
        assert 'RUNNING' in out

    def test_reset_calls_super(self):
        from modena.Launchpad import ModenaLaunchPad
        lp = MagicMock(spec=ModenaLaunchPad)
        lp.get_fw_ids.return_value = []
        with patch.object(
            ModenaLaunchPad.__bases__[0], 'reset', return_value=None
        ) as mock_super_reset:
            ModenaLaunchPad.reset(lp, '', require_password=False)
            mock_super_reset.assert_called_once_with('', require_password=False)

    def test_reset_no_warning_when_empty(self, capsys):
        from modena.Launchpad import ModenaLaunchPad
        lp = MagicMock(spec=ModenaLaunchPad)
        lp.get_fw_ids.return_value = []
        with patch.object(ModenaLaunchPad.__bases__[0], 'reset', return_value=None):
            ModenaLaunchPad.reset(lp, '', require_password=False)
        assert 'WARNING' not in capsys.readouterr().out


# ---------------------------------------------------------------------------
# defuse_orphans
# ---------------------------------------------------------------------------

class TestDefuseOrphans:

    def _make_old_launch(self, seconds_ago: int, pid: int = 0, host: str = ''):
        launch = MagicMock()
        launch.time_start = datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)
        launch.pid  = pid
        launch.host = host
        return launch

    def test_no_running_fireworks_returns_zero(self):
        from modena.Launchpad import ModenaLaunchPad
        lp = MagicMock(spec=ModenaLaunchPad)
        lp.get_fw_ids.return_value = []
        result = ModenaLaunchPad.defuse_orphans(lp, max_age_seconds=3600)
        assert result == 0

    def test_old_firework_is_requeued(self):
        from modena.Launchpad import ModenaLaunchPad
        lp = MagicMock(spec=ModenaLaunchPad)

        def _get_fw_ids(query=None):
            return [42] if (query or {}).get('state') == 'RUNNING' else []

        lp.get_fw_ids.side_effect = _get_fw_ids

        fw = MagicMock()
        fw.launches = ['launch1']
        lp.get_fw_by_id.return_value = fw

        old_launch = self._make_old_launch(seconds_ago=7200)  # 2 h > 1 h threshold
        lp.get_launch_by_id.return_value = old_launch

        result = ModenaLaunchPad.defuse_orphans(lp, max_age_seconds=3600)
        assert result == 1
        lp.rerun_fw.assert_called_once_with(42)

    def test_recent_firework_not_requeued(self):
        from modena.Launchpad import ModenaLaunchPad
        lp = MagicMock(spec=ModenaLaunchPad)

        def _get_fw_ids(query=None):
            return [42] if (query or {}).get('state') == 'RUNNING' else []

        lp.get_fw_ids.side_effect = _get_fw_ids

        fw = MagicMock()
        fw.launches = ['launch1']
        lp.get_fw_by_id.return_value = fw

        recent_launch = self._make_old_launch(seconds_ago=60)  # 1 min < 1 h
        lp.get_launch_by_id.return_value = recent_launch

        result = ModenaLaunchPad.defuse_orphans(lp, max_age_seconds=3600)
        assert result == 0
        lp.rerun_fw.assert_not_called()

    def test_dead_pid_on_localhost_requeued(self):  # noqa — keep at end of class
        from modena.Launchpad import ModenaLaunchPad, _this_hostname
        lp = MagicMock(spec=ModenaLaunchPad)

        def _get_fw_ids(query=None):
            return [99] if (query or {}).get('state') == 'RUNNING' else []

        lp.get_fw_ids.side_effect = _get_fw_ids

        fw = MagicMock()
        fw.launches = ['launch1']
        lp.get_fw_by_id.return_value = fw

        # Recent launch (would not be caught by age check) but PID is dead
        dead_launch = self._make_old_launch(
            seconds_ago=30,
            pid=999_999_999,
            host=_this_hostname(),
        )
        lp.get_launch_by_id.return_value = dead_launch

        result = ModenaLaunchPad.defuse_orphans(lp, max_age_seconds=3600)
        assert result == 1
        lp.rerun_fw.assert_called_once_with(99)


# ---------------------------------------------------------------------------
# retrace_to_origin
# ---------------------------------------------------------------------------

def _make_fw(fw_id: int, name: str, task_names: list):
    """Build a minimal Firework-like mock."""
    fw = MagicMock()
    fw.fw_id = fw_id
    fw.name  = name
    fw.spec  = {'_tasks': [{'_fw_name': t} for t in task_names]}
    return fw


def _make_wf(fws: list, links: dict, states: dict):
    """Build a minimal Workflow-like mock.

    fws    — list of fw mocks
    links  — {parent_id: [child_id, ...]}
    states — {fw_id: state_str}
    """
    wf = MagicMock()
    wf.id_fw     = {fw.fw_id: fw for fw in fws}
    wf.links     = links
    wf.fw_states = states
    return wf


class TestRetraceToOrigin:

    def _lpad_with_wf(self, wf):
        from modena.Launchpad import ModenaLaunchPad
        lp = MagicMock(spec=ModenaLaunchPad)
        lp.get_wf_by_fw_id.return_value = wf
        return lp

    # ── linear chain: 1 → 2 → 3 ─────────────────────────────────────

    def _linear_wf(self):
        fw1 = _make_fw(1, 'root',   ['EmptyFireTask'])
        fw2 = _make_fw(2, 'middle', ['ExactSim'])
        fw3 = _make_fw(3, 'target', ['FitTask'])
        wf  = _make_wf(
            [fw1, fw2, fw3],
            links={1: [2], 2: [3], 3: []},
            states={1: 'COMPLETED', 2: 'COMPLETED', 3: 'COMPLETED'},
        )
        return wf, fw1, fw2, fw3

    def test_linear_returns_all_ancestors(self):
        from modena.Launchpad import ModenaLaunchPad
        wf, fw1, fw2, fw3 = self._linear_wf()
        lp = self._lpad_with_wf(wf)
        result = ModenaLaunchPad.retrace_to_origin(lp, fw_id=3)
        assert [fw.fw_id for fw in result] == [1, 2, 3]

    def test_linear_root_first_target_last(self):
        from modena.Launchpad import ModenaLaunchPad
        wf, fw1, fw2, fw3 = self._linear_wf()
        lp = self._lpad_with_wf(wf)
        result = ModenaLaunchPad.retrace_to_origin(lp, fw_id=3)
        assert result[0].fw_id == 1
        assert result[-1].fw_id == 3

    def test_trace_from_middle_excludes_target_descendants(self):
        from modena.Launchpad import ModenaLaunchPad
        wf, fw1, fw2, fw3 = self._linear_wf()
        lp = self._lpad_with_wf(wf)
        # Tracing from fw2 should include fw1 and fw2 but NOT fw3
        result = ModenaLaunchPad.retrace_to_origin(lp, fw_id=2)
        ids = [fw.fw_id for fw in result]
        assert 3 not in ids
        assert 1 in ids and 2 in ids

    # ── fan-in: two roots merge into one target ───────────────────────

    def test_fan_in_includes_both_roots(self):
        from modena.Launchpad import ModenaLaunchPad
        fw1 = _make_fw(1, 'rootA',  ['SimA'])
        fw2 = _make_fw(2, 'rootB',  ['SimB'])
        fw3 = _make_fw(3, 'target', ['FitTask'])
        wf  = _make_wf(
            [fw1, fw2, fw3],
            links={1: [3], 2: [3], 3: []},
            states={1: 'COMPLETED', 2: 'COMPLETED', 3: 'COMPLETED'},
        )
        lp = self._lpad_with_wf(wf)
        result = ModenaLaunchPad.retrace_to_origin(lp, fw_id=3)
        ids = {fw.fw_id for fw in result}
        assert ids == {1, 2, 3}

    def test_fan_in_target_is_last(self):
        from modena.Launchpad import ModenaLaunchPad
        fw1 = _make_fw(1, 'rootA',  ['SimA'])
        fw2 = _make_fw(2, 'rootB',  ['SimB'])
        fw3 = _make_fw(3, 'target', ['FitTask'])
        wf  = _make_wf(
            [fw1, fw2, fw3],
            links={1: [3], 2: [3], 3: []},
            states={1: 'COMPLETED', 2: 'COMPLETED', 3: 'COMPLETED'},
        )
        lp = self._lpad_with_wf(wf)
        result = ModenaLaunchPad.retrace_to_origin(lp, fw_id=3)
        assert result[-1].fw_id == 3

    # ── isolated target (no parents) ─────────────────────────────────

    def test_single_node_returns_itself(self):
        from modena.Launchpad import ModenaLaunchPad
        fw1 = _make_fw(1, 'alone', ['SomeTask'])
        wf  = _make_wf(
            [fw1],
            links={1: []},
            states={1: 'COMPLETED'},
        )
        lp = self._lpad_with_wf(wf)
        result = ModenaLaunchPad.retrace_to_origin(lp, fw_id=1)
        assert len(result) == 1
        assert result[0].fw_id == 1

    # ── print output ─────────────────────────────────────────────────

    def test_print_contains_fw_id(self, capsys):
        from modena.Launchpad import ModenaLaunchPad
        wf, *_ = self._linear_wf()
        lp = self._lpad_with_wf(wf)
        ModenaLaunchPad.retrace_to_origin(lp, fw_id=3)
        out = capsys.readouterr().out
        assert 'fw:3' in out

    def test_print_contains_target_star(self, capsys):
        from modena.Launchpad import ModenaLaunchPad
        wf, *_ = self._linear_wf()
        lp = self._lpad_with_wf(wf)
        ModenaLaunchPad.retrace_to_origin(lp, fw_id=3)
        out = capsys.readouterr().out
        assert '★' in out

    def test_print_contains_task_names(self, capsys):
        from modena.Launchpad import ModenaLaunchPad
        wf, *_ = self._linear_wf()
        lp = self._lpad_with_wf(wf)
        ModenaLaunchPad.retrace_to_origin(lp, fw_id=3)
        out = capsys.readouterr().out
        assert 'EmptyFireTask' in out
        assert 'FitTask' in out

    def test_print_contains_states(self, capsys):
        from modena.Launchpad import ModenaLaunchPad
        wf, *_ = self._linear_wf()
        lp = self._lpad_with_wf(wf)
        ModenaLaunchPad.retrace_to_origin(lp, fw_id=3)
        out = capsys.readouterr().out
        assert 'COMPLETED' in out
