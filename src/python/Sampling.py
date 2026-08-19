"""
@namespace  python.Sampling
@brief      Request additional training points for a surrogate, as a workflow.

Collecting a training point means running the model's *exact* simulation --
CFD, DEM, a quantum chemistry code -- which can take hours and, on HPC, real
allocation.  That makes this different in kind from ``Diagnostics``, which only
re-reads data already in MongoDB:

  * work is queued through FireWorks and watched on the Runs page, never run
    inside a request thread;
  * the caller is told the cost before committing;
  * the model's own sampling strategy decides *where* the points go.

That last point is a correctness constraint, not a preference.  Models with a
composition constraint (``sum(x) = 1``) declare ``ForbidOutOfBounds`` or
``ExtendSpaceExpandedCASTROSampling`` precisely because naive Latin Hypercube
sampling produces physically invalid points -- which would then be simulated at
full cost.  So a caller asks for *how many* points, never for *which sampler*.

@copyright  2014-2026, MoDeNa Project. GNU Public License.
"""

from __future__ import annotations

import getpass
import logging
import socket
from datetime import datetime, timezone

_log = logging.getLogger('modena.sampling')

__all__ = [
    'InFlight',
    'NotSamplable',
    'estimate_cost',
    'in_flight',
    'plan_points',
    'request_points',
]


class NotSamplable(Exception):
    """The model cannot have points added (no exact task, wrong type)."""


class InFlight(Exception):
    """Work is already queued for this model.

    Two concurrent fits on one model is the race documented in
    ``src/CLAUDE.md`` Phase 4 -- both workers read each other's markers and can
    handle the wrong model.  Refusing is cheaper than racing.
    """


def _require_samplable(model):
    from modena.SurrogateModel import BackwardMappingModel

    if not isinstance(model, BackwardMappingModel):
        raise NotSamplable(
            f"'{model._id}' is a {type(model).__name__}. Only a "
            f"BackwardMappingModel has an exact simulation to run -- a "
            f"ForwardMappingModel is the physics, there is nothing to sample."
        )
    # Stored as meth_exactTask (the serialised FireTask), not `exactTask` --
    # the constructor kwarg name and the persisted field name differ.
    if not getattr(model, 'meth_exactTask', None):
        raise NotSamplable(f"'{model._id}' declares no exactTask")
    return model


def in_flight(model, lpad=None) -> int:
    """Return the number of fireworks for this model that are not finished."""
    import modena

    lpad = lpad if lpad is not None else modena.lpad()
    busy = 0
    for state in ('READY', 'RESERVED', 'RUNNING', 'WAITING'):
        for fw_id in lpad.get_fw_ids(query={'state': state}):
            fw = lpad.get_fw_by_id(fw_id)
            if model._id in (fw.name or ''):
                busy += 1
    return busy


def estimate_cost(model, n_points: int, lpad=None) -> dict:
    """Estimate wall-clock cost from how long this model's points took before.

    Returns ``{'n_points', 'seconds_each', 'seconds_total', 'basis'}``.
    ``seconds_each`` is ``None`` when the exact task has never run -- say so
    rather than invent a number.
    """
    import modena

    lpad = lpad if lpad is not None else modena.lpad()
    durations = []
    try:
        for fw_id in lpad.get_fw_ids(query={'state': 'COMPLETED'}):
            fw = lpad.get_fw_by_id(fw_id)
            name = fw.name or ''
            # exactTasks() names these '<model> — sim i/n' (SurrogateModel.py).
            # Match that rather than the word "exact", which appears in no
            # firework name -- an earlier version of this filter matched
            # nothing and silently reported "no basis" after a full init.
            if not name.startswith(f'{model._id} — sim '):
                continue
            for launch in getattr(fw, 'launches', []):
                start, end = launch.time_start, launch.time_end
                if start and end:
                    durations.append((end - start).total_seconds())
    except Exception as exc:                                   # noqa: BLE001
        _log.debug('cost estimate unavailable for %s: %s', model._id, exc)

    if not durations:
        return {'n_points': n_points, 'seconds_each': None,
                'seconds_total': None, 'basis': 0}

    each = sum(durations) / len(durations)
    return {'n_points': n_points, 'seconds_each': each,
            'seconds_total': each * n_points, 'basis': len(durations)}


def plan_points(model, n_points: int) -> list:
    """Return the points the model's own strategy would collect. Runs nothing.

    Lets a UI show what it is about to simulate before committing to it.
    """
    import copy

    from modena.Strategy import ImproveErrorStrategy, StochasticSampling

    _require_samplable(model)
    if n_points < 1:
        raise ValueError(f'n_points must be at least 1, got {n_points}')
    if not getattr(model, 'fitData', None):
        raise NotSamplable(
            f"'{model._id}' has no fitData to sample around. Run "
            f"'modena init {model._id}' to collect the initial points first."
        )

    # improveErrorStrategy -- the model's declared answer to "the fit is not
    # good enough, get more data" -- lives inside the parameter fitting
    # strategy, not on the model.  Deep-copy it rather than rebuild it, so the
    # model's configured sampler (Halton, Sobol, a CASTRO variant for
    # composition-constrained models) survives; only the count is overridden.
    fitting = model.parameterFittingStrategy()
    declared = fitting.get('improveErrorStrategy') if fitting else None

    if declared is None:
        strategy = StochasticSampling(nNewPoints=n_points)
    else:
        if not isinstance(declared, ImproveErrorStrategy):
            # Real models exist in this state: flowRate named a
            # ParameterFittingStrategy here, whose newPoints() is the
            # unimplemented base method.  Say so, rather than let
            # NotImplementedError surface from four frames down -- and do not
            # silently substitute a sampler, which for a composition-
            # constrained model would generate invalid points.
            raise NotSamplable(
                f"'{model._id}' declares improveErrorStrategy as "
                f"{type(declared).__name__}, which is not an "
                f"ImproveErrorStrategy and cannot generate points. Fix the "
                f"model definition to use Strategy.StochasticSampling and "
                f"re-run 'modena init {model._id}'."
            )
        strategy = copy.deepcopy(declared)
        strategy['nNewPoints'] = n_points

    return strategy.newPoints(model)


def request_points(model, n_points: int, lpad=None, run=True,
                   source: str = 'api') -> dict:
    """Queue exact simulations for *n_points* new points, then a refit.

    Mirrors the out-of-bounds detour: exactTasks(points) fanned out, then
    ParameterFitting, so the surrogate is refitted on the enlarged dataset.

    Raises:
        NotSamplable: the model has no exact simulation to run.
        InFlight:     work is already queued for this model.
        ValueError:   n_points < 1.
    """
    import modena
    from fireworks import Firework, Workflow
    from modena.Strategy import ParameterFitting

    _require_samplable(model)
    lpad = lpad if lpad is not None else modena.lpad()

    busy = in_flight(model, lpad)
    if busy:
        raise InFlight(
            f"{busy} firework(s) for '{model._id}' are still queued or "
            f"running. Adding points now would fit the same model twice "
            f"concurrently -- wait for the Runs page to clear."
        )

    points = plan_points(model, n_points)
    model.save()          # the exact tasks load the model by id at run time

    wf = model.exactTasks(points)

    # Provenance.  Queued simulations spend real compute, and without this the
    # only record of a request is the firework names -- which cannot say who
    # asked, from where, or when.  Two batches appeared during development
    # that could not be attributed afterwards; that is the failure this
    # prevents.  Workflow.metadata is queryable, so `modena fw status` and the
    # Runs page can surface it.
    wf.metadata = {
        'modena_request': {
            'model_id': model._id,
            'n_points': n_points,
            'source': source,
            'user': getpass.getuser(),
            'host': socket.gethostname(),
            'requested_at': datetime.now(timezone.utc).isoformat(),
        }
    }

    wf.append_wf(
        Workflow([Firework(ParameterFitting(surrogateModelId=model._id),
                           name=f'{model._id} — fitting after sampling')],
                 name=f'{model._id} — fitting after sampling'),
        wf.leaf_fw_ids,
    )

    _log.info(
        'requested %d new point(s) for %s', n_points, model._id,
        extra={'event': 'points_requested', 'model_id': model._id,
               'n_points': n_points, 'source': source,
               'user': getpass.getuser()},
    )

    # Queue either way; `run` only decides whether local workers are started
    # here as well.  A CLI caller wants to sit and watch; a web request must
    # return immediately and let an external rlaunch/qlaunch worker pick the
    # work up.  modena.run() adds the workflow itself, so only the
    # queue-and-return path calls add_wf -- doing both would enqueue it twice.
    if run:
        modena.run(wf, lpad=lpad, reset=False)   # reset=False: keep other work
    else:
        lpad.add_wf(wf)

    return {
        'model_id': model._id,
        'n_points': n_points,
        'points': points,
        'launched': run,
        'source': source,
        'requested_at': datetime.now(timezone.utc),
    }
