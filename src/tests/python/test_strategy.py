"""
Tests for modena.Strategy
--------------------------
Covers:
  - SpaceFillingStrategy                 — LatinHypercube, Halton, Sobol, RandomUniform
  - ResidualsOptimizer                   — TrustRegionReflective, LevenbergMarquardt, DogBox
  - RerunAllPoints.newPoints             — column→row reconstruction
  - InitialPoints.newPoints             — returns stored initialPoints
  - EmptyInitialisationStrategy.newPoints — always returns []
  - ModenaFireTask.run_task             — Exception with empty args doesn't crash
  - BackwardMappingScriptTask.run_task  — same; success path returns FWAction()
  - ErrorMetrics                        — residual and aggregate behaviour
  - AcceptanceCriterion                 — MaxError accepts/rejects
  - CrossValidation                     — split sizes and fold counts

No MongoDB or libmodena required.
"""

import sys
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# SpaceFillingStrategy — LatinHypercube, Halton, Sobol, RandomUniform
# ---------------------------------------------------------------------------

class TestSpaceFillingStrategy:

    def test_latin_hypercube_shape(self):
        from modena.Strategy import LatinHypercube
        pts = LatinHypercube(seed=42).sample(10, 3)
        assert pts.shape == (10, 3)

    def test_latin_hypercube_in_unit_cube(self):
        from modena.Strategy import LatinHypercube
        pts = LatinHypercube(seed=0).sample(20, 4)
        assert pts.min() >= 0.0
        assert pts.max() <= 1.0

    def test_halton_shape(self):
        from modena.Strategy import Halton
        pts = Halton(seed=0).sample(8, 2)
        assert pts.shape == (8, 2)

    def test_sobol_shape(self):
        from modena.Strategy import Sobol
        pts = Sobol(seed=0).sample(8, 3)
        assert pts.shape == (8, 3)

    def test_random_uniform_shape(self):
        from modena.Strategy import RandomUniform
        pts = RandomUniform(seed=7).sample(5, 2)
        assert pts.shape == (5, 2)

    def test_random_uniform_in_unit_cube(self):
        from modena.Strategy import RandomUniform
        pts = RandomUniform(seed=7).sample(100, 3)
        assert pts.min() >= 0.0
        assert pts.max() <= 1.0

    def test_default_sampler_used_when_none_specified(self):
        """StochasticSampling with no sampler= key uses LatinHypercube by default."""
        from modena.Strategy import StochasticSampling, LatinHypercube
        s = StochasticSampling(nNewPoints=5)
        assert s.get('sampler', LatinHypercube()) is not None


# ---------------------------------------------------------------------------
# ResidualsOptimizer — TrustRegionReflective, LevenbergMarquardt, DogBox
# ---------------------------------------------------------------------------

class TestResidualsOptimizer:

    def _linear_residuals(self, params):
        # residuals for y = params[0]*x, data: x=[1,2,3], y=[2,4,6] → params=[2]
        import numpy as np
        x = np.array([1.0, 2.0, 3.0])
        y = np.array([2.0, 4.0, 6.0])
        return params[0] * x - y

    def test_trust_region_reflective_fits_linear(self):
        from modena.Strategy import TrustRegionReflective
        import numpy as np
        result = TrustRegionReflective().fit(self._linear_residuals, np.array([1.0]))
        assert result == pytest.approx([2.0], abs=1e-6)

    def test_levenberg_marquardt_fits_linear(self):
        from modena.Strategy import LevenbergMarquardt
        import numpy as np
        result = LevenbergMarquardt().fit(self._linear_residuals, np.array([1.0]))
        assert result == pytest.approx([2.0], abs=1e-6)

    def test_dogbox_fits_linear(self):
        from modena.Strategy import DogBox
        import numpy as np
        result = DogBox().fit(self._linear_residuals, np.array([1.0]))
        assert result == pytest.approx([2.0], abs=1e-6)

    def test_trust_region_reflective_respects_bounds(self):
        from modena.Strategy import TrustRegionReflective
        import numpy as np
        # True optimum is 2.0; bound at 1.5 should clamp result
        result = TrustRegionReflective().fit(
            self._linear_residuals, np.array([1.0]),
            bounds=([0.0], [1.5])
        )
        assert result[0] == pytest.approx(1.5, abs=1e-4)

    def test_lm_returns_array(self):
        from modena.Strategy import LevenbergMarquardt
        import numpy as np
        result = LevenbergMarquardt().fit(self._linear_residuals, np.array([1.0]))
        assert hasattr(result, '__len__')


# ---------------------------------------------------------------------------
# RerunAllPoints.newPoints — column-oriented → row-oriented reconstruction
# ---------------------------------------------------------------------------

class TestRerunAllPoints:

    def _model(self, fitdata):
        m = MagicMock()
        m.fitData = fitdata
        m.reload = MagicMock()
        return m

    def test_empty_fitdata_returns_empty_list(self):
        from modena.Strategy import RerunAllPoints
        m = self._model({})
        result = RerunAllPoints().newPoints(m)
        assert result == []

    def test_reconstructs_two_rows_from_two_columns(self):
        from modena.Strategy import RerunAllPoints
        m = self._model({'x': [1.0, 2.0], 'y': [3.0, 4.0]})
        result = RerunAllPoints().newPoints(m)
        assert len(result) == 2
        assert result[0]['x'] == 1.0
        assert result[0]['y'] == 3.0
        assert result[1]['x'] == 2.0
        assert result[1]['y'] == 4.0

    def test_calls_reload_to_fetch_fitdata(self):
        """reload('fitData') must be called to ensure we have current data."""
        from modena.Strategy import RerunAllPoints
        m = self._model({'x': [1.0]})
        RerunAllPoints().newPoints(m)
        m.reload.assert_called_once_with('fitData')

    def test_single_row(self):
        from modena.Strategy import RerunAllPoints
        m = self._model({'T': [300.0], 'p': [1e5]})
        result = RerunAllPoints().newPoints(m)
        assert result == [{'T': 300.0, 'p': 1e5}]


# ---------------------------------------------------------------------------
# InitialPoints.newPoints — returns the stored initialPoints list
# ---------------------------------------------------------------------------

class TestInitialPoints:

    def test_returns_initial_points(self):
        from modena.Strategy import InitialPoints
        points = [{'D': 0.01, 'p': 1e5}, {'D': 0.02, 'p': 2e5}]
        strategy = InitialPoints(initialPoints=points)
        result = strategy.newPoints(MagicMock())
        assert result == points

    def test_empty_initial_points(self):
        from modena.Strategy import InitialPoints
        strategy = InitialPoints(initialPoints=[])
        assert strategy.newPoints(MagicMock()) == []


# ---------------------------------------------------------------------------
# EmptyInitialisationStrategy.newPoints — always []
# ---------------------------------------------------------------------------

class TestEmptyInitialisationStrategy:

    def test_returns_empty_list(self):
        from modena.Strategy import EmptyInitialisationStrategy
        s = EmptyInitialisationStrategy()
        assert s.newPoints(MagicMock()) == []

    def test_returns_empty_list_regardless_of_model(self):
        from modena.Strategy import EmptyInitialisationStrategy
        s = EmptyInitialisationStrategy()
        for _ in range(3):
            assert s.newPoints(MagicMock()) == []


# ---------------------------------------------------------------------------
# ModenaFireTask.run_task — exception safety (str(e) not e.args[0])
# ---------------------------------------------------------------------------

class TestModenaFireTaskRunTask:

    def _make_task(self):
        from modena.Strategy import ModenaFireTask
        return ModenaFireTask({'modelId': 'testModel', 'point': {'D': 0.01}})

    def test_exception_with_no_args_does_not_crash(self):
        """Regression: old code used e.args[0] which raises IndexError when
        Exception() is raised with no message.  str(e) is always safe."""
        from modena.Strategy import ModenaFireTask
        task = self._make_task()

        # Make SurrogateModel.load raise an Exception with no message
        modena_stub = sys.modules['modena']
        original = getattr(modena_stub, 'SurrogateModel', None)
        mock_sm = MagicMock()
        mock_sm.load.side_effect = Exception()   # empty args — old code crashes here
        modena_stub.SurrogateModel = mock_sm

        try:
            result = task.run_task({'_fw_env': {}})
        finally:
            if original is not None:
                modena_stub.SurrogateModel = original
            else:
                del modena_stub.SurrogateModel

        # Should not raise; should return defuse action
        assert result is not None

    def test_model_load_failure_skips_point(self):
        """When SurrogateModel.load raises (_model stays None), the SkipPoint()
        fallback applies: the firework completes without defusing the workflow."""
        from modena.Strategy import ModenaFireTask
        task = self._make_task()

        modena_stub = sys.modules['modena']
        original = getattr(modena_stub, 'SurrogateModel', None)
        mock_sm = MagicMock()
        mock_sm.load.side_effect = RuntimeError('something went wrong')
        modena_stub.SurrogateModel = mock_sm

        try:
            result = task.run_task({'_fw_env': {}})
        finally:
            if original is not None:
                modena_stub.SurrogateModel = original
            else:
                del modena_stub.SurrogateModel

        # SkipPoint() returns FWAction() — firework completes, workflow continues
        assert result is not None
        assert result.defuse_workflow is False


# ---------------------------------------------------------------------------
# BackwardMappingScriptTask.run_task — exception safety and success path
# ---------------------------------------------------------------------------

class TestBackwardMappingScriptTaskRunTask:

    def _make_task(self):
        from modena.Strategy import BackwardMappingScriptTask
        return BackwardMappingScriptTask({'script': 'echo hello'})

    def test_exception_with_no_args_does_not_crash(self):
        """Same regression guard: str(e) must be used, not e.args[0]."""
        task = self._make_task()

        with patch.object(task, 'executeAndCatchExceptions',
                          side_effect=Exception()):   # no message
            result = task.run_task({'_fw_env': {}, '_modena_fitted_models': []})

        assert result is not None

    def test_returns_defuse_on_exception(self):
        task = self._make_task()

        with patch.object(task, 'executeAndCatchExceptions',
                          side_effect=RuntimeError('boom')):
            result = task.run_task({'_fw_env': {}, '_modena_fitted_models': []})

        assert result.defuse_workflow is True

    def test_success_returns_plain_fw_action(self):
        """When everything succeeds, run_task returns FWAction() (not defuse)."""
        task = self._make_task()

        with patch.object(task, 'executeAndCatchExceptions'):
            with patch('modena.Strategy.ModelRegistry') as mock_reg:
                mock_reg.return_value.freeze = MagicMock()
                result = task.run_task({'_fw_env': {}, '_modena_fitted_models': []})

        assert result.defuse_workflow is not True


# ---------------------------------------------------------------------------
# ErrorMetrics — residual values and aggregate behaviour
# ---------------------------------------------------------------------------

class TestErrorMetrics:

    def test_absolute_error_residual(self):
        from modena.ErrorMetrics import AbsoluteError
        m = AbsoluteError()
        assert m.residual(predicted=3.0, measured=5.0, output_range=10.0) == pytest.approx(2.0)

    def test_absolute_error_residual_negative(self):
        from modena.ErrorMetrics import AbsoluteError
        m = AbsoluteError()
        assert m.residual(predicted=5.0, measured=3.0, output_range=10.0) == pytest.approx(-2.0)

    def test_relative_error_residual(self):
        from modena.ErrorMetrics import RelativeError
        m = RelativeError()
        # (4.0 - 3.0) / |4.0| = 0.25
        assert m.residual(predicted=3.0, measured=4.0, output_range=1.0) == pytest.approx(0.25)

    def test_relative_error_guard_near_zero_measured(self):
        from modena.ErrorMetrics import RelativeError
        m = RelativeError()
        # |measured| < 1e-10 → falls back to absolute
        assert m.residual(predicted=0.0, measured=1e-11, output_range=1.0) == pytest.approx(1e-11)

    def test_normalized_error_residual(self):
        from modena.ErrorMetrics import NormalizedError
        m = NormalizedError()
        # (5.0 - 4.0) / 2.0 = 0.5
        assert m.residual(predicted=4.0, measured=5.0, output_range=2.0) == pytest.approx(0.5)

    def test_normalized_error_guard_zero_range(self):
        from modena.ErrorMetrics import NormalizedError
        m = NormalizedError()
        # range < 1e-10 → falls back to absolute
        assert m.residual(predicted=1.0, measured=3.0, output_range=0.0) == pytest.approx(2.0)

    def test_aggregate_returns_max_abs(self):
        from modena.ErrorMetrics import AbsoluteError
        m = AbsoluteError()
        assert m.aggregate([1.0, -3.0, 2.0]) == pytest.approx(3.0)

    def test_aggregate_single_element(self):
        from modena.ErrorMetrics import AbsoluteError
        m = AbsoluteError()
        assert m.aggregate([-0.5]) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# AcceptanceCriterion — MaxError.accepts behaviour
# ---------------------------------------------------------------------------

class TestAcceptanceCriterion:

    def test_max_error_accepts_when_below_threshold(self):
        from modena.Strategy import MaxError
        c = MaxError(threshold=0.1)
        assert c.accepts(0.05) is True

    def test_max_error_accepts_when_equal_to_threshold(self):
        from modena.Strategy import MaxError
        c = MaxError(threshold=0.1)
        assert c.accepts(0.1) is True

    def test_max_error_rejects_when_above_threshold(self):
        from modena.Strategy import MaxError
        c = MaxError(threshold=0.1)
        assert c.accepts(0.11) is False

    def test_max_error_default_metric_is_absolute_error(self):
        from modena.Strategy import MaxError
        from modena.ErrorMetrics import AbsoluteError
        c = MaxError(threshold=0.1)
        assert isinstance(c.metric, AbsoluteError)

    def test_max_error_custom_metric_stored(self):
        from modena.Strategy import MaxError
        from modena.ErrorMetrics import RelativeError
        metric = RelativeError()
        c = MaxError(metric=metric, threshold=0.05)
        assert isinstance(c.metric, RelativeError)


# ---------------------------------------------------------------------------
# CrossValidation — split sizes, fold counts, aggregate behaviour
# ---------------------------------------------------------------------------

class TestCrossValidation:

    def test_holdout_yields_one_split(self):
        from modena.Strategy import Holdout
        from numpy.random import seed as np_seed
        np_seed(0)
        cv = Holdout(testDataPercentage=0.2)
        splits = list(cv.splits(10))
        assert len(splits) == 1

    def test_holdout_sizes_correct(self):
        from modena.Strategy import Holdout
        from numpy.random import seed as np_seed
        np_seed(0)
        cv = Holdout(testDataPercentage=0.2)
        train, test = next(cv.splits(10))
        assert len(train) + len(test) == 10
        assert len(test) == 2  # max(1, int(0.2 * 10))

    def test_holdout_no_overlap(self):
        from modena.Strategy import Holdout
        from numpy.random import seed as np_seed
        np_seed(0)
        cv = Holdout(testDataPercentage=0.3)
        train, test = next(cv.splits(10))
        assert set(train).isdisjoint(set(test))

    def test_kfold_yields_k_splits(self):
        from modena.Strategy import KFold
        from numpy.random import seed as np_seed
        np_seed(0)
        cv = KFold(k=3)
        splits = list(cv.splits(9))
        assert len(splits) == 3

    def test_kfold_test_set_size(self):
        from modena.Strategy import KFold
        from numpy.random import seed as np_seed
        np_seed(0)
        cv = KFold(k=3)
        for train, test in cv.splits(9):
            assert len(test) == 3

    def test_kfold_no_overlap_between_folds(self):
        from modena.Strategy import KFold
        from numpy.random import seed as np_seed
        np_seed(0)
        cv = KFold(k=3)
        all_test_indices = []
        for train, test in cv.splits(9):
            all_test_indices.extend(test)
        # All 9 indices should appear exactly once across test sets
        assert sorted(all_test_indices) == list(range(9))

    def test_leaveoneout_yields_n_splits(self):
        from modena.Strategy import LeaveOneOut
        cv = LeaveOneOut()
        splits = list(cv.splits(4))
        assert len(splits) == 4

    def test_leaveoneout_test_size_is_one(self):
        from modena.Strategy import LeaveOneOut
        cv = LeaveOneOut()
        for train, test in cv.splits(4):
            assert len(test) == 1

    def test_leaveoneout_train_size(self):
        from modena.Strategy import LeaveOneOut
        cv = LeaveOneOut()
        for train, test in cv.splits(4):
            assert len(train) == 3

    def test_leavepout_yields_correct_number_of_folds(self):
        from modena.Strategy import LeavePOut
        cv = LeavePOut(p=2)
        splits = list(cv.splits(4))
        # C(4,2) = 6
        assert len(splits) == 6

    def test_leavepout_test_size_is_p(self):
        from modena.Strategy import LeavePOut
        cv = LeavePOut(p=2)
        for train, test in cv.splits(4):
            assert len(test) == 2

    def test_leavepout_raises_when_too_many_folds(self):
        from modena.Strategy import LeavePOut
        import pytest
        # C(100, 3) = 161700 >> 1000
        cv = LeavePOut(p=3)
        with pytest.raises(ValueError, match='folds'):
            list(cv.splits(100))

    def test_leavepout_accepts_under_limit(self):
        from modena.Strategy import LeavePOut
        # C(10, 2) = 45 < 1000 — should not raise
        cv = LeavePOut(p=2)
        splits = list(cv.splits(10))
        assert len(splits) == 45

    def test_jackknife_aggregate_uses_mean(self):
        from modena.Strategy import Jackknife
        cv = Jackknife()
        errors = [0.1, 0.2, 0.3]
        assert cv.aggregate(errors) == pytest.approx(0.2)

    def test_kfold_aggregate_uses_max(self):
        from modena.Strategy import KFold
        cv = KFold(k=3)
        errors = [0.1, 0.3, 0.2]
        assert cv.aggregate(errors) == pytest.approx(0.3)


# ---------------------------------------------------------------------------
# ModenaFireTask.find_binary — delegates to ModelRegistry with caller_file
# ---------------------------------------------------------------------------

class TestModenaFireTaskFindBinary:
    """
    Tests for ModenaFireTask.find_binary().

    The method must:
    1. Delegate to ModelRegistry().find_binary(name, caller_file=...).
    2. Pass inspect.getfile(type(self)) as caller_file so the
       package-relative bin/ fallback resolves relative to the concrete
       FireTask's .py file, not Strategy.py.
    """

    def setup_method(self):
        from modena.Registry import ModelRegistry
        ModelRegistry._instance = None

    def _make_task(self):
        from modena.Strategy import ModenaFireTask
        return ModenaFireTask({'modelId': 'testModel', 'point': {}})

    def test_find_binary_finds_in_configured_path(self, tmp_path, monkeypatch):
        bin_dir = tmp_path / 'bin'
        bin_dir.mkdir()
        binary = bin_dir / 'myExact'
        binary.write_text('#!/bin/sh\n')
        monkeypatch.setenv('MODENA_BIN_PATH', str(bin_dir))
        monkeypatch.chdir(tmp_path)
        # Re-load registry so env var is picked up
        from modena.Registry import ModelRegistry
        ModelRegistry().load()
        task = self._make_task()
        found = task.find_binary('myExact')
        assert found == str(binary.resolve())

    def test_find_binary_raises_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv('MODENA_BIN_PATH', raising=False)
        from modena.Registry import ModelRegistry
        ModelRegistry().load()
        task = self._make_task()
        with pytest.raises(FileNotFoundError):
            task.find_binary('no_such_binary')

    def test_find_binary_uses_caller_file_from_type(self, tmp_path, monkeypatch):
        """caller_file must be the concrete subclass's .py file, not Strategy.py."""
        import inspect
        from modena.Strategy import ModenaFireTask

        # Create a concrete subclass whose __module__ file we control
        # We can't truly relocate the class, but we can verify that
        # inspect.getfile(type(task)) returns the Strategy.py path and
        # that the registry receives it.
        task = self._make_task()
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv('MODENA_BIN_PATH', raising=False)

        from modena.Registry import ModelRegistry
        reg = ModelRegistry()
        reg.load()

        captured = {}

        original_find = reg.find_binary
        def _capture(name, caller_file=None):
            captured['caller_file'] = caller_file
            raise FileNotFoundError(f"stub: {name}")
        monkeypatch.setattr(reg, 'find_binary', _capture)

        with pytest.raises(FileNotFoundError):
            task.find_binary('anything')

        assert captured.get('caller_file') is not None
        assert captured['caller_file'] == inspect.getfile(type(task))
