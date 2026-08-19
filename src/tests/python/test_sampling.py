"""
Tests for modena.Sampling -- requesting additional training points.

Unlike Diagnostics, which only re-reads stored data, this queues *exact
simulations*: CFD or DEM runs that cost real wall-clock time and, on HPC, real
allocation.  The tests therefore concentrate on the refusals, because the
expensive mistake is starting work that should not have started.

Covers:
  - only BackwardMappingModels with an exactTask can be sampled
  - the model's own strategy decides where points go, never a caller-supplied
    sampler (composition-constrained models depend on this)
  - a mis-declared improveErrorStrategy is reported, not crashed on
  - work already in flight blocks a second request
  - cost is estimated from previous launches, and admits when it cannot

No MongoDB and no libmodena.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


class _Strategy(dict):
    """Stands in for a FWSerializable strategy (they subclass dict)."""
    def __init__(self, **kw):
        super().__init__(**kw)
        self.seen = None

    def newPoints(self, model):
        self.seen = self['nNewPoints']
        return {'x': [0.1] * self['nNewPoints']}


def _sampler(n=2):
    """A stand-in that passes the ImproveErrorStrategy isinstance check."""
    from modena.Strategy import ImproveErrorStrategy

    class _S(_Strategy, ImproveErrorStrategy):
        def __init__(self, **kw):
            _Strategy.__init__(self, **kw)
    return _S(nNewPoints=n)


# Instantiating a real mongoengine Document needs a live connection, so the
# model classes are swapped for plain stand-ins and the doubles inherit those.
class _Backward:
    pass


class _Forward:
    pass


@pytest.fixture(autouse=True)
def _patch_model_classes(monkeypatch):
    import modena.SurrogateModel as SM
    monkeypatch.setattr(SM, 'BackwardMappingModel', _Backward, raising=False)
    monkeypatch.setattr(SM, 'ForwardMappingModel', _Forward, raising=False)


def _model(backward=True, exact_task=True, improve=None, fit_data=None):
    m = (_Backward if backward else _Forward)()
    m._id = 'demo'
    m.meth_exactTask = {'_fw_name': 'x'} if exact_task else None
    m.fitData = fit_data if fit_data is not None else {'x': [0.0, 1.0]}
    fitting = {'improveErrorStrategy': improve} if improve is not None else {}
    m.parameterFittingStrategy = lambda: fitting
    m.save = MagicMock()
    m.exactTasks = MagicMock()
    return m


@pytest.fixture
def S():
    from modena import Sampling
    return Sampling


# ---------------------------------------------------------------------------
# What may be sampled at all
# ---------------------------------------------------------------------------

class TestSamplable:

    def test_forward_mapping_model_is_refused(self, S):
        """A ForwardMappingModel IS the physics -- there is nothing to run."""
        with pytest.raises(S.NotSamplable, match='_Forward'):
            S.plan_points(_model(backward=False), 2)

    def test_model_without_exact_task_is_refused(self, S):
        with pytest.raises(S.NotSamplable, match='exactTask'):
            S.plan_points(_model(exact_task=False), 2)

    def test_model_without_fitdata_is_refused(self, S):
        """Sampling densifies the region the existing points span."""
        with pytest.raises(S.NotSamplable, match='no fitData'):
            S.plan_points(_model(fit_data={}), 2)

    @pytest.mark.parametrize('n', [0, -1])
    def test_non_positive_count_is_refused(self, S, n):
        with pytest.raises(ValueError, match='at least 1'):
            S.plan_points(_model(improve=_sampler()), n)


# ---------------------------------------------------------------------------
# Which sampler is used
# ---------------------------------------------------------------------------

class TestStrategySelection:

    def test_uses_the_models_declared_strategy(self, S):
        """Not a caller-chosen sampler: models with a sum(x)=1 composition
        constraint declare CASTRO variants precisely because Latin Hypercube
        would produce physically invalid points."""
        declared = _sampler(n=2)
        points = S.plan_points(_model(improve=declared), 5)
        assert points == {'x': [0.1] * 5}

    def test_only_the_count_is_overridden(self, S):
        """The declared sampler keeps its other settings -- it is deep-copied,
        not rebuilt from the class."""
        declared = _sampler(n=2)
        declared['sampler'] = 'Halton-ish'
        S.plan_points(_model(improve=declared), 7)
        assert declared['nNewPoints'] == 2, 'the stored strategy must not mutate'

    def test_mis_declared_strategy_is_reported_not_crashed_on(self, S):
        """flowRate shipped with a ParameterFittingStrategy here, whose
        newPoints() is the unimplemented base method."""
        from modena.Strategy import NonLinFitWithErrorContol
        bad = NonLinFitWithErrorContol(nNewPoints=2)
        with pytest.raises(S.NotSamplable) as exc:
            S.plan_points(_model(improve=bad), 3)
        message = str(exc.value)
        assert 'NonLinFitWithErrorContol' in message
        assert 'StochasticSampling' in message, 'must name the fix'

    def test_falls_back_when_none_is_declared(self, S, monkeypatch):
        """No declared strategy -> plain StochasticSampling over the fitData
        range.  Stubbed here because the real one reaches into model.inputs."""
        import modena.Sampling as mod
        used = {}

        class _Fallback(_Strategy):
            def newPoints(self, model):
                used['n'] = self['nNewPoints']
                return {'x': [0.5] * self['nNewPoints']}

        monkeypatch.setattr('modena.Strategy.StochasticSampling', _Fallback)
        points = S.plan_points(_model(improve=None), 3)
        assert used['n'] == 3
        assert len(points['x']) == 3


# ---------------------------------------------------------------------------
# Concurrency and cost
# ---------------------------------------------------------------------------

class TestGuards:

    def test_in_flight_counts_only_this_model(self, S):
        lpad = MagicMock()
        lpad.get_fw_ids.side_effect = lambda query=None: (
            [1, 2] if query['state'] == 'READY' else [])
        lpad.get_fw_by_id.side_effect = lambda i: SimpleNamespace(
            name='demo — exact simulation' if i == 1 else 'other — fitting')
        assert S.in_flight(_model(), lpad) == 1

    def test_request_refuses_while_work_is_in_flight(self, S, monkeypatch):
        """Two concurrent fits on one model is the race in CLAUDE.md Phase 4."""
        monkeypatch.setattr(S, 'in_flight', lambda model, lpad=None: 3)
        with pytest.raises(S.InFlight, match='still queued'):
            S.request_points(_model(improve=_sampler()), 2, lpad=MagicMock())

    def test_cost_admits_when_it_cannot_estimate(self, S):
        lpad = MagicMock()
        lpad.get_fw_ids.return_value = []
        cost = S.estimate_cost(_model(), 4, lpad)
        assert cost['seconds_each'] is None and cost['basis'] == 0

    def test_cost_averages_previous_launches(self, S):
        from datetime import datetime, timedelta
        t0 = datetime(2026, 1, 1)
        launch = SimpleNamespace(time_start=t0, time_end=t0 + timedelta(seconds=60))
        lpad = MagicMock()
        lpad.get_fw_ids.side_effect = lambda query=None: (
            [1] if query['state'] == 'COMPLETED' else [])
        lpad.get_fw_by_id.return_value = SimpleNamespace(
            name='demo — exact simulation', launches=[launch])
        cost = S.estimate_cost(_model(), 5, lpad)
        assert cost['seconds_each'] == 60.0
        assert cost['seconds_total'] == 300.0
        assert cost['basis'] == 1
