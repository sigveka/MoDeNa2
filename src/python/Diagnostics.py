"""
@namespace  python.Diagnostics
@brief      Read-only fit diagnostics for surrogate models.

Answers two questions that the framework could compute but never surfaced:

  1. *How good is this model?*  ``fit_quality()`` scores the parameters
     currently stored in MongoDB against the stored ``fitData``.
  2. *Would a different fitting strategy do better?*  ``cross_validate()``
     runs a full CV fit for a given strategy and reports the error, without
     writing anything.

**Nothing in this module mutates the model or the database.**  That is the
point: ``NonLinFitWithErrorContol.newPointsFWAction()`` interleaves fitting
with ``model.save()``, ``updateMinMax()`` and ``FWAction`` detours, so it
cannot be used to ask "what if?".  These functions reuse the same public
pieces — ``CrossValidationStrategy.splits()``, ``ResidualsOptimizer.fit()``,
``SurrogateModel.error()`` — and stop before persisting.

Callers that want to keep a result apply it explicitly with
``promote_parameters()``.

@copyright  2014-2026, MoDeNa Project. GNU Public License.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import numpy as np

import modena
from modena.ErrorMetrics import AbsoluteError
from modena.Strategy import (
    Holdout,
    MaxError,
    TrustRegionReflective,
)

_log = logging.getLogger('modena.diagnostics')

__all__ = [
    'fit_quality',
    'cross_validate',
    'promote_parameters',
    'CV_STRATEGIES',
    'OPTIMIZERS',
    'METRICS',
]


def _cmodel(model, parameters):
    """Build a modena_model_t bound to *parameters* (not persisted)."""
    return modena.libmodena.modena_model_t(
        model=model, parameters=list(parameters)
    )


def _require_fit_data(model):
    """Return the sample count, deriving it from fitData when necessary.

    ``nSamples`` is not a stored field -- it is set as a side effect of
    ``updateFitDataFromFwSpec`` during fitting, so a document loaded straight
    from MongoDB does not carry it.  ``SurrogateModel.error()`` defaults its
    index range to ``self.nSamples``, so it has to exist before any scoring
    happens; derive it from the fit data and cache it on the instance.
    """
    n = getattr(model, 'nSamples', None)
    if not n:
        fit_data = getattr(model, 'fitData', None) or {}
        first = next(iter(fit_data.values()), None)
        n = len(first) if first is not None else 0
        model.nSamples = n
    if not n:
        raise ValueError(
            f"model '{model._id}' has no fit data — run 'modena init "
            f"{model._id}' to collect training samples first"
        )
    return n


# ------------------------------------------------------------------ #
# 1. How good is the model as it stands?                              #
# ------------------------------------------------------------------ #

def fit_quality(model, metric=None) -> dict:
    """Score the *stored* parameters against the *stored* fit data.

    Args:
        model:  a trained ``SurrogateModel`` (``fitData`` must be loaded).
        metric: an ``ErrorMetricBase``; defaults to ``AbsoluteError()``.

    Returns:
        dict with ``error`` (aggregated), ``residuals`` (per sample×output),
        ``n_samples``, ``n_samples_fitted``, ``stale`` and ``n_new_samples``.

    ``stale`` is the question the schema could already answer and nothing
    asked: ``n_samples_fitted`` records the sample count at the last fit, so
    ``nSamples > n_samples_fitted`` means points have arrived since — the
    stored parameters do not reflect all the data.
    """
    n_samples = _require_fit_data(model)
    metric = metric if metric is not None else AbsoluteError()

    if not model.parameters:
        raise ValueError(f"model '{model._id}' is untrained — no parameters to score")

    cModel = _cmodel(model, model.parameters_array())
    residuals = list(model.error(cModel, checkBounds=False, metric=metric))

    n_fitted = getattr(model, 'n_samples_fitted', 0) or 0
    return {
        'error':            metric.aggregate(residuals),
        'residuals':        residuals,
        'n_samples':        n_samples,
        'n_samples_fitted': n_fitted,
        'n_new_samples':    max(0, n_samples - n_fitted),
        'stale':            n_samples > n_fitted,
        'metric':           type(metric).__name__,
        'last_fitted':      getattr(model, 'last_fitted', None),
    }


def predictions(model, parameters=None) -> dict:
    """Return ``{output_name: (measured, predicted)}`` over the fit data.

    Used for parity / residual plots.  ``parameters`` defaults to the stored
    ones, so a candidate fit can be plotted before it is promoted.
    """
    n_samples = _require_fit_data(model)
    params = list(parameters) if parameters is not None else model.parameters_array()
    cModel = _cmodel(model, params)

    input_bindings = [(model.inputs_argPos(k), model.fitData[k]) for k in model.inputs]
    out_bindings = [(model.outputs_argPos(n), model.fitData[n], n)
                    for n in model.outputs]

    i = [0.0] * model.surrogateFunction.inputs_size()
    result = {name: ([], []) for _, _, name in out_bindings}

    for idx in range(n_samples):
        for pos, col in input_bindings:
            i[pos] = col[idx]
        out = cModel(i, checkBounds=False)
        for pos, col, name in out_bindings:
            result[name][0].append(col[idx])
            result[name][1].append(out[pos])
    return result


# ------------------------------------------------------------------ #
# 2. Would another strategy fit better?                               #
# ------------------------------------------------------------------ #

def cross_validate(model, crossValidation=None, optimizer=None,
                   metric=None) -> dict:
    """Run one cross-validated fit and report the error. Persists nothing.

    Mirrors the CV loop in ``NonLinFitWithErrorContol.newPointsFWAction()``:
    fit on each training split, score on the held-out split, aggregate per the
    strategy (``max`` for most, ``mean`` for ``Jackknife``).  Then refit on the
    full dataset — those are the parameters a caller would promote.

    Returns:
        dict with ``cv_error``, ``fold_errors``, ``n_folds``,
        ``full_fit_parameters`` (argPos-ordered), ``named_parameters``,
        ``full_fit_error`` and the strategy names used.

    Raises:
        ValueError: model has no fit data, or the strategy produces no folds.
    """
    n_samples = _require_fit_data(model)

    cv        = crossValidation if crossValidation is not None else Holdout(testDataPercentage=0.2)
    optimizer = optimizer       if optimizer       is not None else TrustRegionReflective()
    metric    = metric          if metric          is not None else AbsoluteError()

    sf_params = model.surrogateFunction.parameters
    init      = model.parameters_array()
    lo        = [v.min for v in sf_params.values()]
    hi        = [v.max for v in sf_params.values()]

    def _fit(train_idx):
        train = list(train_idx)
        cModel = _cmodel(model, init)

        def errorFit(parameters):
            cModel.parameters = list(parameters)
            return np.array(list(model.error(
                cModel, idxGenerator=iter(train),
                checkBounds=False, metric=metric,
            )))

        return list(optimizer.fit(
            errorFit, np.array(init, dtype=float), bounds=(lo, hi),
        ))

    # Deliberately serial: a portal request thread must not fork a
    # ProcessPoolExecutor, and these fits are seconds at most.
    folds = list(cv.splits(n_samples))
    if not folds:
        raise ValueError(
            f'{type(cv).__name__} produced no folds for {n_samples} sample(s)'
        )

    fold_errors = []
    cModel_eval = _cmodel(model, init)
    for train_idx, test_idx in folds:
        params = _fit(train_idx)
        cModel_eval.parameters = params
        residuals = list(model.error(
            cModel_eval, idxGenerator=iter(test_idx),
            checkBounds=False, metric=metric,
        ))
        fold_errors.append(metric.aggregate(residuals))

    full_params = _fit(range(n_samples))
    cModel_eval.parameters = full_params
    full_residuals = list(model.error(
        cModel_eval, checkBounds=False, metric=metric,
    ))

    result = {
        'cv_error':            cv.aggregate(fold_errors),
        'fold_errors':         fold_errors,
        'n_folds':             len(folds),
        'n_samples':           n_samples,
        'full_fit_parameters': full_params,
        'named_parameters':    dict(zip(model.parameter_names(), full_params)),
        'full_fit_error':      metric.aggregate(full_residuals),
        'crossValidation':     type(cv).__name__,
        'optimizer':           type(optimizer).__name__,
        'metric':              type(metric).__name__,
    }
    _log.info(
        'cross_validate %s: %s over %d fold(s) -> cv_error=%.4g',
        model._id, type(cv).__name__, len(folds), result['cv_error'],
        extra={'event': 'cross_validate', 'model_id': model._id,
               'crossValidation': type(cv).__name__,
               'cv_error': result['cv_error']},
    )
    return result


def promote_parameters(model, parameters) -> dict:
    """Write *parameters* to MongoDB as the model's fitted values.

    The only mutating function in this module, and it is never reached without
    an explicit caller decision.  Stored parameters are live: a running C
    application evaluates against them through ``modena_model_call``, so
    replacing them silently would change results under a running simulation.

    Returns the newly stored ``{name: value}`` mapping.
    """
    model.set_parameters_array(list(parameters))
    model.last_fitted = datetime.now(timezone.utc)
    model.n_samples_fitted = model.nSamples
    model.save()
    named = model.named_parameters()
    _log.info(
        'promoted parameters for %s: %s', model._id, named,
        extra={'event': 'parameters_promoted', 'model_id': model._id,
               'parameters': named},
    )
    return named


# ------------------------------------------------------------------ #
# Registries — what a UI can offer without hardcoding class names     #
# ------------------------------------------------------------------ #

def _cv_registry():
    from modena.Strategy import (
        Holdout, KFold, LeaveOneOut, LeavePOut, Jackknife,
    )
    return {
        'Holdout':     (Holdout,     {'testDataPercentage': 0.2}),
        'KFold':       (KFold,       {'k': 5}),
        'LeaveOneOut': (LeaveOneOut, {}),
        'LeavePOut':   (LeavePOut,   {'p': 2}),
        'Jackknife':   (Jackknife,   {}),
    }


def _optimizer_registry():
    from modena.Strategy import (
        TrustRegionReflective, LevenbergMarquardt, DogBox,
    )
    return {
        'TrustRegionReflective': TrustRegionReflective,
        'LevenbergMarquardt':    LevenbergMarquardt,
        'DogBox':                DogBox,
    }


def _metric_registry():
    from modena.ErrorMetrics import (
        AbsoluteError, RelativeError, NormalizedError,
    )
    return {
        'AbsoluteError':   AbsoluteError,
        'RelativeError':   RelativeError,
        'NormalizedError': NormalizedError,
    }


CV_STRATEGIES = _cv_registry()
OPTIMIZERS    = _optimizer_registry()
METRICS       = _metric_registry()
