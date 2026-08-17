"""
Tests for modena.Diagnostics
-----------------------------
The module exists so a caller can ask "how good is this fit?" and "would
another strategy do better?" without the answer costing a database write.
The tests that matter most are therefore the ones asserting that nothing is
persisted -- ``cross_validate`` reuses the same optimizer and error machinery
as the production fitting path, which *does* save.

Covers:
  - fit_quality: aggregation, staleness from n_samples_fitted, untrained guard
  - cross_validate: fold counts per strategy, non-destructiveness, guards
  - promote_parameters: the one mutating call, and that it stamps provenance
  - registries stay in step with the Strategy classes they advertise

No MongoDB and no compiled libmodena: the C layer is a linear model evaluated
in Python, so the optimizer has something real to converge on.
"""

import types
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# A fake model + fake C layer that together behave like y = a*x + b
# ---------------------------------------------------------------------------

class _FakeCModel:
    """Stands in for modena_model_t: outputs[0] = p[0]*x + p[1]."""

    def __init__(self, model=None, parameters=None):
        self.parameters = list(parameters or [0.0, 0.0])

    def __call__(self, inputs, checkBounds=True):
        return [self.parameters[0] * inputs[0] + self.parameters[1]]


def _fake_model(xs, ys, stored=(1.0, 0.0), n_fitted=None):
    """A SurrogateModel-shaped stub over the sample set (xs, ys)."""
    n = len(xs)
    sf = SimpleNamespace(
        parameters={'a': SimpleNamespace(min=-10.0, max=10.0),
                    'b': SimpleNamespace(min=-10.0, max=10.0)},
        inputs_size=lambda: 1,
    )
    lo_x, hi_x = (min(xs), max(xs)) if xs else (0.0, 1.0)
    lo_y, hi_y = (min(ys), max(ys)) if ys else (0.0, 1.0)
    m = SimpleNamespace(
        _id='fake',
        nSamples=n,
        fitData={'x': list(xs), 'y': list(ys)},
        inputs={'x': SimpleNamespace(min=lo_x, max=hi_x)},
        outputs={'y': SimpleNamespace(min=lo_y, max=hi_y)},
        surrogateFunction=sf,
        n_samples_fitted=n if n_fitted is None else n_fitted,
        last_fitted=None,
        parameters={'a': stored[0], 'b': stored[1]},
    )
    m.inputs_argPos = lambda name: 0
    m.outputs_argPos = lambda name: 0
    m.parameters_array = lambda: [m.parameters['a'], m.parameters['b']]
    m.parameter_names = lambda: ['a', 'b']
    m.named_parameters = lambda: dict(m.parameters)

    def _set_array(arr):
        m.parameters = {'a': arr[0], 'b': arr[1]}
    m.set_parameters_array = _set_array
    m.save = MagicMock()

    # Bind the real error() implementation to the stub.
    from modena.SurrogateModel import SurrogateModel
    m.error = lambda cModel, **kw: SurrogateModel.error(m, cModel, **kw)
    return m


@pytest.fixture
def diagnostics():
    """Import Diagnostics with a fake libmodena installed."""
    import modena
    lib = types.ModuleType('modena.libmodena')
    lib.modena_model_t = _FakeCModel
    with patch.object(modena, 'libmodena', lib, create=True):
        from modena import Diagnostics
        yield Diagnostics


# Perfectly linear data: y = 2x + 1
_XS = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
_YS = [1.0, 3.0, 5.0, 7.0, 9.0, 11.0]


# ---------------------------------------------------------------------------
# fit_quality
# ---------------------------------------------------------------------------

class TestFitQuality:

    def test_exact_parameters_give_zero_error(self, diagnostics):
        q = diagnostics.fit_quality(_fake_model(_XS, _YS, stored=(2.0, 1.0)))
        assert q['error'] == pytest.approx(0.0, abs=1e-12)
        assert q['n_samples'] == 6

    def test_wrong_parameters_give_nonzero_error(self, diagnostics):
        q = diagnostics.fit_quality(_fake_model(_XS, _YS, stored=(1.0, 0.0)))
        assert q['error'] > 1.0

    def test_reports_staleness_from_n_samples_fitted(self, diagnostics):
        """nSamples > n_samples_fitted means points arrived after the last fit."""
        q = diagnostics.fit_quality(
            _fake_model(_XS, _YS, stored=(2.0, 1.0), n_fitted=2))
        assert q['stale'] is True
        assert q['n_new_samples'] == 4

    def test_not_stale_when_counts_match(self, diagnostics):
        q = diagnostics.fit_quality(_fake_model(_XS, _YS, stored=(2.0, 1.0)))
        assert q['stale'] is False
        assert q['n_new_samples'] == 0

    def test_untrained_model_is_rejected(self, diagnostics):
        m = _fake_model(_XS, _YS)
        m.parameters = {}
        with pytest.raises(ValueError, match='untrained'):
            diagnostics.fit_quality(m)

    def test_model_without_fit_data_is_rejected(self, diagnostics):
        m = _fake_model([], [])
        with pytest.raises(ValueError, match='no fit data'):
            diagnostics.fit_quality(m)

    def test_sample_count_is_derived_when_nsamples_is_absent(self, diagnostics):
        """nSamples is not a stored field -- a doc loaded from MongoDB lacks
        it, and error() defaults its index range to it, so it must be
        recovered from fitData rather than trusted."""
        m = _fake_model(_XS, _YS, stored=(2.0, 1.0))
        del m.nSamples
        assert diagnostics.fit_quality(m)['n_samples'] == 6
        assert m.nSamples == 6

    def test_metric_is_reported(self, diagnostics):
        from modena.ErrorMetrics import RelativeError
        q = diagnostics.fit_quality(_fake_model(_XS, _YS, stored=(2.0, 1.0)),
                                    metric=RelativeError())
        assert q['metric'] == 'RelativeError'


# ---------------------------------------------------------------------------
# cross_validate
# ---------------------------------------------------------------------------

class TestCrossValidate:

    def test_recovers_the_underlying_relationship(self, diagnostics):
        r = diagnostics.cross_validate(_fake_model(_XS, _YS, stored=(0.0, 0.0)))
        assert r['named_parameters']['a'] == pytest.approx(2.0, abs=1e-4)
        assert r['named_parameters']['b'] == pytest.approx(1.0, abs=1e-4)
        assert r['full_fit_error'] == pytest.approx(0.0, abs=1e-6)

    @pytest.mark.parametrize('name,expected_folds', [
        ('Holdout', 1),
        ('KFold', 5),
        ('LeaveOneOut', 6),
        ('Jackknife', 6),
    ])
    def test_fold_counts_per_strategy(self, diagnostics, name, expected_folds):
        cls, kw = diagnostics.CV_STRATEGIES[name]
        r = diagnostics.cross_validate(_fake_model(_XS, _YS),
                                       crossValidation=cls(**kw))
        assert r['n_folds'] == expected_folds
        assert len(r['fold_errors']) == expected_folds

    def test_leave_p_out_holds_out_p_samples(self, diagnostics):
        from modena.Strategy import LeavePOut
        r = diagnostics.cross_validate(_fake_model(_XS, _YS),
                                       crossValidation=LeavePOut(p=2))
        assert r['n_folds'] == 15          # C(6,2)
        assert r['crossValidation'] == 'LeavePOut'

    def test_does_not_touch_the_model(self, diagnostics):
        """The whole point: asking 'what if' must not rewrite the model."""
        m = _fake_model(_XS, _YS, stored=(1.0, 0.0))
        before = dict(m.parameters)
        diagnostics.cross_validate(m)
        assert m.parameters == before
        m.save.assert_not_called()

    def test_reports_the_strategy_names_used(self, diagnostics):
        from modena.Strategy import KFold, DogBox
        from modena.ErrorMetrics import NormalizedError
        r = diagnostics.cross_validate(
            _fake_model(_XS, _YS),
            crossValidation=KFold(k=3), optimizer=DogBox(),
            metric=NormalizedError(),
        )
        assert (r['crossValidation'], r['optimizer'], r['metric']) == \
               ('KFold', 'DogBox', 'NormalizedError')

    def test_model_without_fit_data_is_rejected(self, diagnostics):
        m = _fake_model([], [])
        with pytest.raises(ValueError, match='no fit data'):
            diagnostics.cross_validate(m)


# ---------------------------------------------------------------------------
# promote_parameters
# ---------------------------------------------------------------------------

class TestPromote:

    def test_writes_parameters_and_saves(self, diagnostics):
        m = _fake_model(_XS, _YS, stored=(1.0, 0.0))
        named = diagnostics.promote_parameters(m, [2.0, 1.0])
        assert named == {'a': 2.0, 'b': 1.0}
        m.save.assert_called_once()

    def test_stamps_provenance(self, diagnostics):
        """last_fitted and n_samples_fitted are how staleness is judged later."""
        m = _fake_model(_XS, _YS, stored=(1.0, 0.0), n_fitted=2)
        diagnostics.promote_parameters(m, [2.0, 1.0])
        assert m.n_samples_fitted == 6
        assert isinstance(m.last_fitted, datetime)

    def test_promotion_clears_staleness(self, diagnostics):
        m = _fake_model(_XS, _YS, stored=(1.0, 0.0), n_fitted=2)
        assert diagnostics.fit_quality(m)['stale'] is True
        diagnostics.promote_parameters(m, [2.0, 1.0])
        assert diagnostics.fit_quality(m)['stale'] is False


# ---------------------------------------------------------------------------
# Registries
# ---------------------------------------------------------------------------

class TestRegistries:

    def test_cv_registry_entries_are_constructible(self, diagnostics):
        from modena.Strategy import CrossValidationStrategy
        for name, (cls, kw) in diagnostics.CV_STRATEGIES.items():
            inst = cls(**kw)
            assert isinstance(inst, CrossValidationStrategy), name

    def test_optimizer_registry_entries_are_constructible(self, diagnostics):
        from modena.Strategy import ResidualsOptimizer
        for name, cls in diagnostics.OPTIMIZERS.items():
            assert isinstance(cls(), ResidualsOptimizer), name

    def test_metric_registry_entries_are_constructible(self, diagnostics):
        from modena.ErrorMetrics import ErrorMetricBase
        for name, cls in diagnostics.METRICS.items():
            assert isinstance(cls(), ErrorMetricBase), name
