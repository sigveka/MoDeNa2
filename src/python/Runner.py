"""
@file      MoDeNa workflow runner.
@details   Provides ``modena.run()`` — a high-level wrapper around FireWorks
           that handles launchpad setup, workflow construction, and progress
           reporting.  Supports three launcher backends:

           * ``'rapidfire'`` (default) — runs worker processes locally using
             ``fireworks.core.rocket_launcher.rapidfire``.  Parallel workers
             are spawned via ``multiprocessing``; ``njobs`` controls the count.

           * ``'qlaunch'`` — submits each Firework as a batch job to an HPC
             queue system (SLURM, PBS, SGE, …) via
             ``fireworks.queue.queue_launcher``.  Requires a configured
             ``qadapter``.  The queue scheduler manages parallelism; ``njobs``
             caps the number of jobs held in the queue simultaneously (0 =
             unlimited).

           * ``'auto'`` — starts local ``rapidfire`` workers AND a supervisor
             thread.  The supervisor watches the READY count; when it exceeds
             ``escalate_at``, it submits the overflow to the HPC queue.
             MongoDB's atomic claiming ensures each Firework is executed
             exactly once regardless of which backend claims it first.  Use
             this when a running macroscopic simulation (e.g. OpenFOAM) may
             suddenly queue hundreds of exact-simulation Fireworks at runtime
             (out-of-bounds expansion bursts).

@author    MoDeNa Project
@copyright 2014-2026, MoDeNa Project. GNU Public License.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from fireworks import Firework, Workflow
from fireworks.core.fworker import FWorker
from fireworks.core.rocket_launcher import rapidfire
from fireworks.fw_config import FWORKER_LOC, QUEUEADAPTER_LOC
from fireworks.queue.queue_launcher import launch_rocket_to_queue
from fireworks.utilities.fw_serializers import load_object_from_file as _fw_load_qadapter
from fireworks.queue.queue_launcher import rapidfire as queue_rapidfire

from modena.Launchpad import ModenaLaunchPad, _fw_strm_lvl
from modena.SurrogateModel import SurrogateModel, EmptyFireTask

_log = logging.getLogger('modena.runner')


# ------------------------------------------------------------------ #
# Worker helpers (module-level for multiprocessing pickling)          #
# ------------------------------------------------------------------ #

_SUPERVISOR_MAX_ERRORS = 5


def _auto_supervisor(lpad_dict: dict, fworker_dict: dict | None,
                     qadapter_path: str, launch_dir: str,
                     escalate_at: int, sleep_time: int, strm_lvl: str,
                     stop: threading.Event) -> None:
    """Background thread for ``launcher='auto'``.

    Polls the launchpad every ``sleep_time`` seconds.  Whenever the number of
    READY Fireworks exceeds ``escalate_at``, submits one HPC job per overflow
    Firework via ``launch_rocket_to_queue``.  Stops when ``stop`` is set.

    MongoDB's atomic claiming ensures that a Firework submitted to the HPC
    queue that has already been claimed by a local worker is simply skipped
    (FireWorks handles this transparently).

    After ``_SUPERVISOR_MAX_ERRORS`` consecutive failures the supervisor logs
    at ERROR level and exits, leaving local workers running.  A transient
    MongoDB blip resets the counter on the next successful poll.
    """
    lpad = ModenaLaunchPad.from_dict(lpad_dict)
    fworker = _resolve_fworker(fworker_dict)
    qadapter = _resolve_qadapter(qadapter_path)

    consecutive_errors = 0

    while not stop.is_set():
        try:
            n_ready = len(lpad.get_fw_ids(query={'state': 'READY'}))
            overflow = n_ready - escalate_at
            if overflow > 0:
                _log.info(
                    'auto: %d READY > threshold %d — submitting %d HPC job(s)',
                    n_ready, escalate_at, overflow,
                )
                for _ in range(overflow):
                    if stop.is_set():
                        break
                    launch_rocket_to_queue(
                        lpad, fworker, qadapter, launch_dir,
                        strm_lvl=strm_lvl,
                    )
            consecutive_errors = 0   # successful poll resets the counter

        except Exception as exc:
            consecutive_errors += 1
            if consecutive_errors >= _SUPERVISOR_MAX_ERRORS:
                _log.error(
                    'auto supervisor: %d consecutive errors — '
                    'disabling HPC submission, local workers will continue. '
                    'Last error: %s',
                    consecutive_errors, exc, exc_info=True,
                )
                return
            _log.warning(
                'auto supervisor error (%d/%d, will retry): %s',
                consecutive_errors, _SUPERVISOR_MAX_ERRORS, exc,
            )

        stop.wait(sleep_time)


# ------------------------------------------------------------------ #
# Resolver helpers                                                     #
# ------------------------------------------------------------------ #

def _resolve_fworker(fworker):
    """Return a ``FWorker`` from a path, dict, existing instance, or ``None``.

    Resolution order (mirrors FireWorks' own ``LaunchPad.auto_load`` pattern):

    1. Explicit argument — path string, dict, or ``FWorker`` instance.
    2. ``FWORKER_LOC`` from ``FW_config.yaml`` (FireWorks standard config).
    3. Default ``FWorker()`` — accepts any Firework.
    """
    if fworker is None:
        if FWORKER_LOC:
            return FWorker.from_file(FWORKER_LOC)
        return FWorker()
    if isinstance(fworker, dict):
        return FWorker.from_dict(fworker)
    if isinstance(fworker, (str, Path)):
        return FWorker.from_file(str(fworker))
    return fworker


def _resolve_qadapter(qadapter):
    """Return a ``QueueAdapterBase`` from a path, existing instance, or ``None``.

    Resolution order (mirrors FireWorks' own ``LaunchPad.auto_load`` pattern):

    1. Explicit argument — path string or ``QueueAdapterBase`` instance.
    2. ``QUEUEADAPTER_LOC`` from ``FW_config.yaml`` (FireWorks standard config).
    3. ``None`` — caller must check and raise if a qadapter is required.
    """
    if isinstance(qadapter, (str, Path)):
        return _fw_load_qadapter(str(qadapter))
    if qadapter is None:
        if QUEUEADAPTER_LOC:
            return _fw_load_qadapter(QUEUEADAPTER_LOC)
    return qadapter


# ------------------------------------------------------------------ #
# Public API                                                           #
# ------------------------------------------------------------------ #

def run(
    wf_or_models,
    *,
    lpad=None,
    reset: bool = True,
    sleep_time: int = 1,
    timeout: int | None = None,
    name: str = 'modena_workflow',
    njobs: int = 0,
    launcher: str = 'rapidfire',
    fworker=None,
    qadapter=None,
    launch_dir: str | Path = '.',
    escalate_at: int = 0,
):
    """Run a MoDeNa workflow.

    Accepts either a ready-made FireWorks ``Workflow`` (or ``Firework``) or a
    list of ``SurrogateModel`` instances.  In the latter case the method
    assembles the standard initialisation workflow automatically.

    Args:
        wf_or_models:
            A ``Workflow``, a ``Firework``, or an iterable of
            ``SurrogateModel`` instances.
        lpad:
            A ``ModenaLaunchPad`` instance.  ``None`` creates one from
            ``MODENA_URI``.
        reset:
            Reset the launchpad before adding the workflow.  Default ``True``.
        sleep_time:
            Seconds between polling cycles (all launchers).  Default 1.
            FireWorks treats 0 as falsy and substitutes its own 60-second
            default, which causes workers to hang for up to a minute after
            the workflow completes.  Values ≥ 1 are passed through directly.
        timeout:
            Wall-clock timeout in seconds (``rapidfire`` and ``auto`` local
            workers only).  ``None`` means no limit.
        name:
            Workflow name when ``wf_or_models`` is a model list.
        njobs:
            ``'qlaunch'`` only: max simultaneous HPC queue slots (0 =
            unlimited).  Ignored for ``'rapidfire'`` and ``'auto'`` — for
            local parallelism launch additional ``rapidfire`` workers externally
            against the same launchpad.
        launcher:
            ``'rapidfire'`` — single local worker (default).
            ``'qlaunch'``   — HPC queue only.
            ``'auto'``      — single local worker + HPC escalation supervisor.
        fworker:
            ``FWorker`` instance, path to ``fworker.yaml``, or ``None``
            (creates a default FWorker).  Used by ``'qlaunch'`` and ``'auto'``.
        qadapter:
            ``QueueAdapterBase`` instance or path to ``qadapter.yaml``.
            Required for ``'qlaunch'`` and ``'auto'``.
        launch_dir:
            Directory from which HPC batch scripts are written and submitted.
            Used by ``'qlaunch'`` and ``'auto'``.  Default: current directory.
        escalate_at:
            ``'auto'`` only.  Number of READY Fireworks that must be queued
            before the supervisor starts submitting to HPC.  For example,
            ``escalate_at=8`` means up to 8 jobs run locally; any beyond 8
            are off-loaded to the cluster.  Default 0 (escalate immediately
            for any overflow beyond local workers).

    Returns:
        The ``ModenaLaunchPad`` used.

    Raises:
        ValueError: unknown ``launcher``.
        ValueError: ``'qlaunch'`` or ``'auto'`` without a ``qadapter``.
    """
    if launcher not in ('rapidfire', 'qlaunch', 'auto'):
        raise ValueError(
            f"launcher must be 'rapidfire', 'qlaunch', or 'auto', got {launcher!r}"
        )

    # Resolve fworker and qadapter before validation so that values set in
    # FW_config.yaml (FWORKER_LOC / QUEUEADAPTER_LOC) are honoured.
    fworker  = _resolve_fworker(fworker)
    qadapter = _resolve_qadapter(qadapter)
    if launcher in ('qlaunch', 'auto') and qadapter is None:
        raise ValueError(
            f"launcher={launcher!r} requires a qadapter.  "
            "Pass qadapter='path/to/qadapter.yaml', a QueueAdapterBase "
            "instance, or set QUEUEADAPTER_LOC in FW_config.yaml."
        )

    # ------------------------------------------------------------------ #
    # Resolve launchpad                                                    #
    # ------------------------------------------------------------------ #
    if lpad is None:
        lpad = ModenaLaunchPad.from_modena_uri()

    # ------------------------------------------------------------------ #
    # Build workflow                                                       #
    # ------------------------------------------------------------------ #
    if isinstance(wf_or_models, Workflow):
        wf = wf_or_models
    elif isinstance(wf_or_models, Firework):
        wf = Workflow([wf_or_models])
    else:
        models = list(wf_or_models)
        if not models:
            _log.info('run: no models provided — nothing to do.')
            return lpad
        for m in models:
            m.save()
        model_ids = ', '.join(m._id for m in models)
        wf = Workflow(
            [Firework([EmptyFireTask()], name=f'init root — {model_ids}')],
            name=name,
        )
        for m in models:
            wf.append_wf(m.initialisationStrategy().workflow(m), wf.root_fw_ids)

    # ------------------------------------------------------------------ #
    # Reset and add                                                        #
    # ------------------------------------------------------------------ #
    if reset:
        lpad.reset('', require_password=False)
    lpad.add_wf(wf)

    n_ready   = len(lpad.get_fw_ids(query={'state': 'READY'}))
    n_waiting = len(lpad.get_fw_ids(query={'state': 'WAITING'}))
    strm_lvl  = _fw_strm_lvl()

    # ------------------------------------------------------------------ #
    # Launch                                                               #
    # ------------------------------------------------------------------ #
    if launcher == 'qlaunch':
        _log.info(
            'run: %d READY, %d WAITING — qlaunch (njobs_queue=%d, dir=%s)',
            n_ready, n_waiting, njobs, launch_dir,
        )
        queue_rapidfire(
            launchpad=lpad,
            fworker=fworker,
            qadapter=qadapter,
            launch_dir=str(launch_dir),
            nlaunches=0,
            njobs_queue=njobs,
            sleep_time=sleep_time,
            strm_lvl=strm_lvl,
        )

    elif launcher == 'auto':
        _log.info(
            'run: %d READY, %d WAITING — auto (escalate_at=%d, qadapter=%s)',
            n_ready, n_waiting, escalate_at, qadapter,
        )

        # Supervisor thread watches queue depth and submits HPC jobs on burst.
        # Serialise fworker to dict so the thread can reconstruct it cleanly
        # without sharing mutable state with the supervisor thread.
        fw_dict = fworker.to_dict()
        stop    = threading.Event()
        sv_sleep = max(sleep_time, 5)   # don't hammer MongoDB faster than 5 s
        supervisor = threading.Thread(
            target=_auto_supervisor,
            args=(lpad.to_dict(), fw_dict, qadapter, str(launch_dir),
                  escalate_at, sv_sleep, strm_lvl, stop),
            daemon=True,
            name='modena-auto-supervisor',
        )
        supervisor.start()

        try:
            _run_rapidfire(lpad, strm_lvl, sleep_time, timeout)
        finally:
            stop.set()
            supervisor.join(timeout=10)

    else:  # rapidfire
        _log.info(
            'run: %d READY, %d WAITING — rapidfire',
            n_ready, n_waiting,
        )
        _run_rapidfire(lpad, strm_lvl, sleep_time, timeout)

    # After all workers have joined, any firework still in RUNNING state has a
    # dead worker process (ping failed, worker crashed, or the launchpad was
    # reset concurrently).  Warn and automatically re-queue so the workflow can
    # continue without manual intervention.
    n_stuck = len(lpad.get_fw_ids(query={'state': 'RUNNING'}))
    if n_stuck:
        _log.warning(
            'run: %d firework(s) stuck in RUNNING after all workers exited '
            '(likely cause: launchpad was reset while a worker was finishing, '
            'or a worker crashed before sending the completion ping). '
            'Attempting automatic recovery via defuse_orphans()...',
            n_stuck,
        )
        recovered = lpad.defuse_orphans(max_age_seconds=0)
        if recovered:
            _log.warning(
                'run: %d firework(s) re-queued. '
                'Re-run modena.run() (with reset=False) to execute them.',
                recovered,
            )

    _log.info('run: done. %s', lpad.state_summary())
    return lpad


def _run_rapidfire(lpad, strm_lvl, sleep_time, timeout):
    """Run rapidfire in the current process until no READY fireworks remain."""
    rf_kwargs: dict = {'sleep_time': sleep_time, 'strm_lvl': strm_lvl}
    if timeout is not None:
        rf_kwargs['timeout'] = timeout
    rapidfire(lpad, **rf_kwargs)
