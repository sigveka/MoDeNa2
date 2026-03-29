"""
@file      MoDeNa-aware LaunchPad wrapper.
@details   Provides ModenaLaunchPad — a thin subclass of FireWorks LaunchPad
           that adds safety checks, diagnostic helpers, and a status display
           tailored to MoDeNa workflows.
@author    MoDeNa Project
@copyright 2014-2026, MoDeNa Project. GNU Public License.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta

import logging

from fireworks import LaunchPad


def _fw_strm_lvl() -> str:
    """Return the FireWorks stream level that matches the modena log level.

    FireWorks loggers are outside the 'fireworks' hierarchy (they use names
    like 'launchpad', 'rocket.launcher') so setting logging.getLogger('fireworks')
    has no effect.  The only way to silence them is via the strm_lvl kwarg
    passed when the loggers are created.

    At DEBUG_VERBOSE (level 5) we expose full FireWorks output.  At any other
    level we clamp at WARNING to suppress routine INFO noise.
    """
    from modena._logging import DEBUG_VERBOSE
    modena_level = logging.getLogger('modena').level or logging.INFO
    if modena_level <= DEBUG_VERBOSE:
        return 'DEBUG'
    return 'WARNING'


class ModenaLaunchPad(LaunchPad):
    """FireWorks LaunchPad with MoDeNa-specific convenience methods.

    Use the factory ``modena.lpad()`` rather than constructing directly::

        import modena
        lp = modena.lpad()
        lp.status()
    """

    @classmethod
    def from_modena_uri(cls, server_selection_timeout_ms: int = 3000) -> 'ModenaLaunchPad':
        """Create a ModenaLaunchPad from the active MODENA_URI.

        Args:
            server_selection_timeout_ms: How long PyMongo waits for a server
                to become available before raising an error (ms). Default 3000.
                Set higher for slow networks; set lower for fast CI failure.

        Raises:
            pymongo.errors.ServerSelectionTimeoutError: if MongoDB is not
                reachable within ``server_selection_timeout_ms`` milliseconds.
        """
        from modena.SurrogateModel import MODENA_URI
        # FireWorks uri_mode=True passes the URI directly to MongoClient but
        # does NOT extract the database name from it — name= must be supplied
        # separately or LaunchPad.__init__ raises ValueError.
        _, database = MODENA_URI.rsplit('/', 1)
        # Use uri_mode=True so FireWorks passes the URI directly to MongoClient.
        # This avoids the FireWorks LaunchPad always injecting username=None and
        # authSource=<dbname> as explicit kwargs, which can trigger unintended
        # authentication handshakes in some PyMongo/MongoDB combinations.
        lp = cls(
            host=MODENA_URI,
            name=database,
            uri_mode=True,
            strm_lvl=_fw_strm_lvl(),
            mongoclient_kwargs={
                'serverSelectionTimeoutMS': server_selection_timeout_ms,
            },
        )
        _verify_connection(lp, MODENA_URI)
        return lp

    # ------------------------------------------------------------------ #
    # Diagnostics                                                          #
    # ------------------------------------------------------------------ #

    def status(self) -> None:
        """Print a table of all Firework ids, names, and states."""
        all_ids = self.get_fw_ids()
        if not all_ids:
            print('[modena] Launchpad is empty.')
            return

        rows = []
        for fw_id in sorted(all_ids):
            fw = self.get_fw_by_id(fw_id)
            rows.append({
                'fw_id':      fw_id,
                'name':       (fw.name or '')[:40],
                'state':      fw.state,
                'created':    str(fw.created_on)[:19] if fw.created_on else '',
                'updated':    str(fw.updated_on)[:19] if fw.updated_on else '',
            })

        cols = ['fw_id', 'name', 'state', 'created', 'updated']
        widths = {c: max(len(c), max(len(str(r[c])) for r in rows)) for c in cols}

        header = '  '.join(c.upper().ljust(widths[c]) for c in cols)
        sep    = '  '.join('-' * widths[c] for c in cols)
        print(header)
        print(sep)
        for r in rows:
            print('  '.join(str(r[c]).ljust(widths[c]) for c in cols))

    def state_counts(self) -> dict:
        """Return a dict mapping state name to count of fireworks in that state."""
        states = ['READY', 'RUNNING', 'WAITING', 'COMPLETED',
                  'RESERVED', 'FIZZLED', 'DEFUSED', 'PAUSED']
        return {s: len(self.get_fw_ids(query={'state': s})) for s in states}

    def state_summary(self) -> str:
        """Return a one-line summary of non-zero firework state counts."""
        counts = self.state_counts()
        parts = [f'{s}={n}' for s, n in counts.items() if n > 0]
        return ', '.join(parts) if parts else 'empty'

    # ------------------------------------------------------------------ #
    # Safe reset                                                           #
    # ------------------------------------------------------------------ #

    def reset(self, password: str = '', require_password: bool = False) -> None:
        """Reset the launchpad, with a warning if orphaned fireworks exist.

        Args:
            password:         Ignored when require_password is False.
            require_password: Passed through to FireWorks reset().
        """
        running  = self.get_fw_ids(query={'state': 'RUNNING'})
        reserved = self.get_fw_ids(query={'state': 'RESERVED'})
        if running or reserved:
            print(
                f'[modena] WARNING: resetting launchpad with '
                f'{len(running)} RUNNING and {len(reserved)} RESERVED '
                f'firework(s). Call defuse_orphans() first to recover them.'
            )
        super().reset(password, require_password=require_password)

    # ------------------------------------------------------------------ #
    # Orphan recovery                                                      #
    # ------------------------------------------------------------------ #

    def defuse_orphans(self, max_age_seconds: int = 3600) -> int:
        """Re-queue RUNNING/RESERVED fireworks whose process is no longer alive.

        A firework is considered orphaned if:
        - Its launch has been in RUNNING or RESERVED state for longer than
          ``max_age_seconds`` (default: 1 hour), OR
        - The launch host matches this machine and the recorded PID is no
          longer running (Linux/macOS only; falls back to age check).

        Args:
            max_age_seconds: Age threshold in seconds. Default 3600.

        Returns:
            Number of fireworks re-queued.
        """
        defused = 0
        now = datetime.now(timezone.utc)

        for state in ('RUNNING', 'RESERVED'):
            for fw_id in self.get_fw_ids(query={'state': state}):
                fw = self.get_fw_by_id(fw_id)

                # Determine age from the most recent launch
                orphaned = False
                launch_ids = getattr(fw, 'launches', [])
                if launch_ids:
                    launch = self.get_launch_by_id(launch_ids[-1])
                    t_start = getattr(launch, 'time_start', None)
                    if t_start:
                        # Ensure tz-aware comparison
                        if t_start.tzinfo is None:
                            t_start = t_start.replace(tzinfo=timezone.utc)
                        age = (now - t_start).total_seconds()
                        if age > max_age_seconds:
                            orphaned = True

                        # PID check (best-effort, Linux/macOS).
                        # Pass t_start as a Unix timestamp so _pid_alive can
                        # reject a reused PID that started after the launch.
                        pid = getattr(launch, 'pid', None)
                        host = getattr(launch, 'host', None)
                        if pid and host and host == _this_hostname():
                            ts = t_start.timestamp() if t_start else None
                            if not _pid_alive(pid, not_before=ts):
                                orphaned = True
                else:
                    # No launch record at all — definitely orphaned
                    orphaned = True

                if orphaned:
                    self.rerun_fw(fw_id)
                    print(
                        f'[modena] defuse_orphans: fw_id={fw_id} '
                        f'({state}) -> READY'
                    )
                    defused += 1

        if defused:
            print(f'[modena] defuse_orphans: {defused} firework(s) re-queued.')
        else:
            print('[modena] defuse_orphans: no orphans found.')
        return defused

    # ------------------------------------------------------------------ #
    # Graph tracing                                                        #
    # ------------------------------------------------------------------ #

    def retrace_to_origin(self, fw_id: int) -> list:
        """Trace and display all Fireworks that ran before fw_id.

        Walks the workflow graph backwards from fw_id, collecting every
        ancestor Firework (anything that had to complete first), then
        prints them in topological execution order — roots first, target
        last — grouped by depth level so branching and merging are visible.

        Args:
            fw_id: Target Firework ID to trace back from.

        Returns:
            List of Firework objects in topological order (roots first).
            The last entry is the Firework with fw_id.
        """
        wf = self.get_wf_by_fw_id(fw_id)

        # wf.links maps parent_id → [child_id, ...].
        # Normalise keys/values to int — FireWorks can use str keys.
        links: dict = {
            int(k): [int(c) for c in v]
            for k, v in wf.links.items()
        }
        all_ids = {int(k) for k in wf.id_fw}

        # Build child→parent inverse map.
        parents: dict = {fid: [] for fid in all_ids}
        for parent_id, children in links.items():
            for child_id in children:
                if child_id in parents:
                    parents[child_id].append(parent_id)

        # BFS backwards from fw_id to collect ancestors (inclusive).
        ancestors: set = set()
        queue = [fw_id]
        while queue:
            cur = queue.pop(0)
            if cur in ancestors:
                continue
            ancestors.add(cur)
            queue.extend(p for p in parents.get(cur, []) if p not in ancestors)

        # Topological sort of the ancestor subgraph (Kahn's algorithm).
        sub_children: dict = {fid: [] for fid in ancestors}
        in_degree:    dict = {fid: 0  for fid in ancestors}
        for fid in ancestors:
            for p in parents[fid]:
                if p in ancestors:
                    sub_children[p].append(fid)
                    in_degree[fid] += 1

        ready = sorted(fid for fid, d in in_degree.items() if d == 0)
        topo: list = []
        while ready:
            node = ready.pop(0)
            topo.append(node)
            for child in sorted(sub_children[node]):
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    ready.append(child)
                    ready.sort()

        # Compute depth: longest path from any root to each node.
        depth: dict = {fid: 0 for fid in ancestors}
        for fid in topo:
            for child in sub_children[fid]:
                depth[child] = max(depth[child], depth[fid] + 1)

        # Group by depth level.
        by_depth: dict = {}
        for fid in topo:
            by_depth.setdefault(depth[fid], []).append(fid)

        _print_retrace(wf, fw_id, by_depth, len(topo))
        return [wf.id_fw[fid] for fid in topo]

    # ------------------------------------------------------------------ #
    # Re-run                                                               #
    # ------------------------------------------------------------------ #

    def rerun(self, fw_id: int) -> None:
        """Re-queue a FIZZLED or COMPLETED firework for re-execution.

        Args:
            fw_id: The Firework id to re-run.
        """
        fw = self.get_fw_by_id(fw_id)
        print(
            f'[modena] rerun: fw_id={fw_id} '
            f'(was {fw.state}) -> READY'
        )
        self.rerun_fw(fw_id)


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #

def _print_retrace(wf, target_fw_id: int, by_depth: dict, n_total: int) -> None:
    """Print the depth-layered ancestor graph for retrace_to_origin."""
    target_fw   = wf.id_fw[target_fw_id]
    target_name = (target_fw.name or f'fw:{target_fw_id}')[:52]
    max_depth   = max(by_depth)
    W = 72

    print()
    print(f'  {"─" * W}')
    print(f'  Retrace to fw:{target_fw_id} "{target_name}"')
    print(f'  {"─" * W}')

    for level in sorted(by_depth):
        fids  = by_depth[level]
        n     = len(fids)
        label = f'  Depth {level}'
        if level == 0:
            label += '  (root)'
        if level == max_depth:
            label += '  ★ target' if n == 1 else '  (includes target ★)'
        label += f'  [{n} parallel]' if n > 1 else ''
        print(label)

        for fid in fids:
            fw    = wf.id_fw[fid]
            name  = (fw.name or '')[:46]
            state = (wf.fw_states or {}).get(fid, '?')
            star  = ' ★' if fid == target_fw_id else ''
            tasks = ', '.join(
                t.get('_fw_name', '?')
                for t in fw.spec.get('_tasks', [])
            )
            print(f'    [fw:{fid:<4}]  {name:<48}  {state}{star}')
            if tasks:
                print(f'             tasks: {tasks}')

        if level < max_depth:
            n_next = len(by_depth.get(level + 1, []))
            arrow  = f'↓ ({n} → {n_next})' if n != n_next else '↓'
            print(f'             {arrow}')
        print()

    print(f'  {"─" * W}')
    print(f'  {n_total} Firework(s) traced')
    print()


def _verify_connection(lp: ModenaLaunchPad, uri: str) -> None:
    """Raise a clear ModenaConnectionError if MongoDB is unreachable.

    Calls ``command('ping')`` on the connected database.  This triggers the
    first real network round-trip and honours the ``serverSelectionTimeoutMS``
    set on the underlying ``MongoClient``.
    """
    try:
        lp.db.command('ping')
    except Exception as exc:
        raise ModenaConnectionError(uri) from exc


class ModenaConnectionError(RuntimeError):
    """MongoDB is unreachable."""

    def __init__(self, uri: str) -> None:
        super().__init__(
            f'\n'
            f'  [modena] Cannot connect to MongoDB at: {uri}\n'
            f'\n'
            f'  Make sure MongoDB is running before using MoDeNa:\n'
            f'    sudo systemctl start mongod    # systemd\n'
            f'    mongod --dbpath /data/db       # manual\n'
            f'\n'
            f'  To use a different MongoDB instance set MODENA_URI, e.g.:\n'
            f'    export MODENA_URI=mongodb://myhost:27017/modena\n'
        )


def _this_hostname() -> str:
    import socket
    return socket.gethostname()


def _proc_start_epoch(pid: int) -> float | None:
    """Return the Unix timestamp at which ``pid`` started, or ``None``.

    Uses ``/proc/<pid>/stat`` (Linux only).  Returns ``None`` on any platform
    where the information is unavailable or unreadable.
    """
    import sys
    if not sys.platform.startswith('linux'):
        return None
    try:
        from pathlib import Path
        stat_text = Path(f'/proc/{pid}/stat').read_text()
        # The process name (field 2) is enclosed in parentheses and may itself
        # contain parentheses and spaces.  Use rfind to locate the end of it.
        idx = stat_text.rfind(')')
        if idx < 0:
            return None
        fields = stat_text[idx + 2:].split()
        # After the closing paren the fields are: state ppid pgrp session
        # tty_nr tpgid flags minflt cminflt majflt cmajflt utime stime cutime
        # cstime priority nice num_threads itrealvalue starttime …
        # starttime is the 20th field after ')' (0-indexed: 19).
        starttime_ticks = int(fields[19])
        clk_tck = os.sysconf('SC_CLK_TCK')

        btime = None
        for line in Path('/proc/stat').read_text().splitlines():
            if line.startswith('btime '):
                btime = int(line.split()[1])
                break
        if btime is None:
            return None

        return btime + starttime_ticks / clk_tck
    except (OSError, ValueError, IndexError):
        return None


def _pid_alive(pid: int, not_before: float | None = None) -> bool:
    """Return ``True`` if ``pid`` refers to the process that was running at
    ``not_before`` (Unix timestamp).

    ``os.kill(pid, 0)`` alone cannot distinguish the original process from an
    unrelated one that reused the same PID after the original died.  On Linux,
    we cross-check the process start time from ``/proc/<pid>/stat``: if the
    process started *after* ``not_before`` it is a different process and
    ``False`` is returned.  On other platforms (or if ``/proc`` is
    unreadable) the check degrades gracefully to the plain signal check.
    """
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, OSError):
        return False

    if not_before is not None:
        start = _proc_start_epoch(pid)
        if start is not None and start > not_before + 2.0:
            # Process started after the firework was launched — PID was reused.
            return False

    return True
