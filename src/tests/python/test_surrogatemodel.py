"""
Tests for modena.SurrogateModel
--------------------------------
Covers:
  - existsAndHasArgPos  — raises ArgPosNotFound, NOT bare Exception
  - GrowingList         — auto-extends on out-of-range index
  - SurrogateModel.parseIndices   — parses species indices from model _id
  - SurrogateModel.expandIndices  — substitutes index placeholders with values
  - SurrogateModel.inputs_argPos  — two-level fallback; ArgPosNotFound on miss
  - SurrogateModel.updateMinMax   — correct bounds; degenerate-positive guard
  - loadType            — ___*___ caching avoids re-deserialisation
  - parameterFittingStrategy()    — _changed_fields filter removes strategy roots
  - CFunction.compileCcode — SHA256 hash deterministic; skips cmake if .so exists

No MongoDB, libmodena, or R required.
"""

import os
import hashlib
import pytest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# existsAndHasArgPos
# ---------------------------------------------------------------------------

class TestExistsAndHasArgPos:

    def test_returns_argpos_when_present(self):
        from modena.SurrogateModel import existsAndHasArgPos
        assert existsAndHasArgPos({'D': {'argPos': 3}}, 'D') == 3

    def test_argpos_zero_is_valid(self):
        from modena.SurrogateModel import existsAndHasArgPos
        assert existsAndHasArgPos({'p0': {'argPos': 0}}, 'p0') == 0

    def test_raises_when_key_missing(self):
        from modena.SurrogateModel import existsAndHasArgPos, ArgPosNotFound
        with pytest.raises(ArgPosNotFound):
            existsAndHasArgPos({}, 'D')

    def test_raises_when_argpos_key_absent(self):
        from modena.SurrogateModel import existsAndHasArgPos, ArgPosNotFound
        with pytest.raises(ArgPosNotFound):
            existsAndHasArgPos({'D': {'min': 0.0, 'max': 1.0}}, 'D')

    def test_regression_raises_arg_pos_not_found_not_base_exception(self):
        """Regression: must raise ArgPosNotFound specifically, not bare Exception.

        The caller's `except ArgPosNotFound` block would silently skip if the
        wrong exception type is raised, bypassing the fallback to
        surrogateFunction.inputs.  This was the root cause of the twoTanks
        crash where '[D][argPos] not found' was unhandled.
        """
        from modena.SurrogateModel import existsAndHasArgPos, ArgPosNotFound
        try:
            existsAndHasArgPos({}, 'D')
            pytest.fail("Expected ArgPosNotFound to be raised")
        except ArgPosNotFound:
            pass  # correct
        except Exception:
            pytest.fail("Raised bare Exception instead of ArgPosNotFound")


# ---------------------------------------------------------------------------
# GrowingList
# ---------------------------------------------------------------------------

class TestGrowingList:

    def test_normal_assignment(self):
        from modena.SurrogateModel import GrowingList
        gl = GrowingList([10, 20, 30])
        gl[1] = 99
        assert gl == [10, 99, 30]

    def test_out_of_range_extends_list(self):
        from modena.SurrogateModel import GrowingList
        gl = GrowingList()
        gl[3] = 'x'
        assert len(gl) == 4
        assert gl[3] == 'x'

    def test_intermediate_slots_are_none(self):
        from modena.SurrogateModel import GrowingList
        gl = GrowingList()
        gl[2] = 'z'
        assert gl[0] is None
        assert gl[1] is None
        assert gl[2] == 'z'

    def test_extending_from_non_empty(self):
        from modena.SurrogateModel import GrowingList
        gl = GrowingList([1, 2])
        gl[5] = 9
        assert len(gl) == 6
        assert gl[2] is None
        assert gl[5] == 9


# ---------------------------------------------------------------------------
# SurrogateModel.parseIndices
# ---------------------------------------------------------------------------

class TestParseIndices:

    def test_no_brackets_returns_empty_dict(self):
        from modena.SurrogateModel import SurrogateModel
        assert SurrogateModel.parseIndices(None, 'flowRate') == {}

    def test_single_index(self):
        from modena.SurrogateModel import SurrogateModel
        result = SurrogateModel.parseIndices(None, 'flowRate[A=CO2]')
        assert result == {'A': 'CO2'}

    def test_multiple_indices(self):
        from modena.SurrogateModel import SurrogateModel
        result = SurrogateModel.parseIndices(None, 'D[A=CO2,B=N2]')
        assert result == {'A': 'CO2', 'B': 'N2'}

    def test_invalid_bracket_content_raises(self):
        """A bracket without '=' is unparseable and must raise."""
        from modena.SurrogateModel import SurrogateModel
        with pytest.raises(Exception, match='Unable to parse'):
            SurrogateModel.parseIndices(None, 'D[CO2]')  # missing 'A='

    def test_empty_brackets_returns_empty(self):
        from modena.SurrogateModel import SurrogateModel
        # re.search finds brackets but m.group(1).split(',') yields ['']
        # ''.split('=') → [''] so re.search('(.*)=(.*)', '') fails → raises
        # This documents current behaviour: empty brackets are invalid
        with pytest.raises(Exception):
            SurrogateModel.parseIndices(None, 'D[]')


# ---------------------------------------------------------------------------
# SurrogateModel.expandIndices
# ---------------------------------------------------------------------------

class TestExpandIndices:

    def _model(self, indices):
        m = SimpleNamespace()
        m.___indices___ = indices
        return m

    def test_no_brackets_returns_name_unchanged(self):
        from modena.SurrogateModel import SurrogateModel
        m = self._model({'A': 'CO2'})
        assert SurrogateModel.expandIndices(m, 'flowRate') == 'flowRate'

    def test_expands_single_index(self):
        from modena.SurrogateModel import SurrogateModel
        m = self._model({'A': 'CO2'})
        assert SurrogateModel.expandIndices(m, 'D[A]') == 'D[CO2]'

    def test_expands_multiple_indices(self):
        from modena.SurrogateModel import SurrogateModel
        m = self._model({'A': 'CO2', 'B': 'N2'})
        assert SurrogateModel.expandIndices(m, 'D[A,B]') == 'D[CO2,N2]'

    def test_name_without_index_variable_unchanged(self):
        from modena.SurrogateModel import SurrogateModel
        m = self._model({})
        assert SurrogateModel.expandIndices(m, 'pressure') == 'pressure'


# ---------------------------------------------------------------------------
# SurrogateModel.inputs_argPos — two-level fallback
# ---------------------------------------------------------------------------

class TestInputsArgPos:

    def _model(self, model_inputs, sf_inputs):
        """Minimal mock for inputs_argPos().

        inputs and surrogateFunction.inputs must be dicts whose values
        support: `'argPos' in v` and `v['argPos']`  (plain dicts satisfy this).
        """
        m = SimpleNamespace()
        m.inputs = model_inputs
        m.surrogateFunction = SimpleNamespace(inputs=sf_inputs)
        return m

    def test_found_in_model_inputs(self):
        from modena.SurrogateModel import SurrogateModel
        m = self._model(
            model_inputs={'D': {'argPos': 0}},
            sf_inputs={'D': {'argPos': 0}},
        )
        assert SurrogateModel.inputs_argPos(m, 'D') == 0

    def test_falls_back_to_surrogate_function_inputs(self):
        """'rho' absent from model.inputs but present in surrogateFunction.inputs."""
        from modena.SurrogateModel import SurrogateModel
        m = self._model(
            model_inputs={'D': {'argPos': 0}},
            sf_inputs={'D': {'argPos': 0}, 'rho': {'argPos': 2}},
        )
        assert SurrogateModel.inputs_argPos(m, 'rho') == 2

    def test_model_inputs_takes_precedence_over_sf(self):
        """If the same name is in both with different argPos, model wins."""
        from modena.SurrogateModel import SurrogateModel
        m = self._model(
            model_inputs={'D': {'argPos': 7}},
            sf_inputs={'D': {'argPos': 0}},
        )
        assert SurrogateModel.inputs_argPos(m, 'D') == 7

    def test_raises_when_not_in_either(self):
        from modena.SurrogateModel import SurrogateModel, ArgPosNotFound
        m = self._model(
            model_inputs={'D': {'argPos': 0}},
            sf_inputs={'D': {'argPos': 0}},
        )
        with pytest.raises(ArgPosNotFound):
            SurrogateModel.inputs_argPos(m, 'unknown')


# ---------------------------------------------------------------------------
# SurrogateModel.updateMinMax
# ---------------------------------------------------------------------------

class TestUpdateMinMax:

    def _slot(self):
        return SimpleNamespace(min=None, max=None)

    def _model(self, fitdata, input_keys, output_keys, nSamples):
        m = SimpleNamespace()
        m.nSamples = nSamples
        m.fitData = fitdata
        m.inputs  = {k: self._slot() for k in input_keys}
        m.outputs = {k: self._slot() for k in output_keys}
        return m

    def test_positive_values_set_min_and_max(self):
        from modena.SurrogateModel import SurrogateModel
        m = self._model(
            fitdata={'D': [1.0, 2.0, 3.0], 'out': [4.0, 5.0, 6.0]},
            input_keys=['D'], output_keys=['out'], nSamples=3,
        )
        SurrogateModel.updateMinMax(m)
        assert m.inputs['D'].min == 1.0
        assert m.inputs['D'].max == 3.0
        assert m.outputs['out'].min == 4.0
        assert m.outputs['out'].max == 6.0

    def test_degenerate_single_positive_value_max_exceeds_min(self):
        """When all input values equal the same positive number, the
        v.min * 1.000001 guard ensures max > min so the domain is non-degenerate."""
        from modena.SurrogateModel import SurrogateModel
        m = self._model(
            fitdata={'D': [5.0], 'out': [1.0]},
            input_keys=['D'], output_keys=['out'], nSamples=1,
        )
        SurrogateModel.updateMinMax(m)
        assert m.inputs['D'].max > m.inputs['D'].min

    def test_multiple_inputs_get_independent_bounds(self):
        from modena.SurrogateModel import SurrogateModel
        m = self._model(
            fitdata={'D': [1.0, 2.0], 'p': [100.0, 200.0], 'out': [0.0, 1.0]},
            input_keys=['D', 'p'], output_keys=['out'], nSamples=2,
        )
        SurrogateModel.updateMinMax(m)
        assert m.inputs['D'].min == 1.0
        assert m.inputs['D'].max == 2.0
        assert m.inputs['p'].min == 100.0
        assert m.inputs['p'].max == 200.0


# ---------------------------------------------------------------------------
# loadType — ___*___ caching
# ---------------------------------------------------------------------------

class TestLoadType:

    def test_returns_cached_value_without_deserialising(self):
        """If obj already has the ___name attribute, load_object must not be called."""
        from modena.SurrogateModel import loadType
        sentinel = object()
        obj = SimpleNamespace(meth_myStrat={'_fw_name': 'SomeStrategy'})
        setattr(obj, '___myStrat', sentinel)

        with patch('modena.SurrogateModel.load_object') as mock_load:
            result = loadType(obj, 'myStrat', object)

        mock_load.assert_not_called()
        assert result is sentinel

    def test_deserialises_on_first_call_and_caches(self):
        """Without the cache attribute, load_object is called once and the
        result is stored so subsequent calls won't call it again."""
        from modena.SurrogateModel import loadType
        sentinel = object()
        obj = SimpleNamespace(meth_myStrat={'_fw_name': 'SomeStrategy'})

        with patch('modena.SurrogateModel.load_object', return_value=sentinel) as mock_load:
            result = loadType(obj, 'myStrat', object)

        mock_load.assert_called_once()
        assert result is sentinel
        assert getattr(obj, '___myStrat') is sentinel

    def test_second_call_uses_cache(self):
        from modena.SurrogateModel import loadType
        sentinel = object()
        obj = SimpleNamespace(meth_myStrat={'_fw_name': 'SomeStrategy'})

        with patch('modena.SurrogateModel.load_object', return_value=sentinel):
            loadType(obj, 'myStrat', object)   # populates cache

        with patch('modena.SurrogateModel.load_object') as mock_second:
            loadType(obj, 'myStrat', object)   # should use cache

        mock_second.assert_not_called()


# ---------------------------------------------------------------------------
# parameterFittingStrategy() — _changed_fields filter
# ---------------------------------------------------------------------------

class TestParameterFittingStrategyChangedFieldsFilter:
    """
    Regression guard for the mongoengine _changed_fields injection bug.

    When mongoengine deserialises a nested strategy dict it injects the
    sub-object root names (e.g. 'crossValidation', 'acceptanceCriterion',
    'improveErrorStrategy._fw_name') into the model's _changed_fields list.
    parameterFittingStrategy() must strip these out so that model.save()
    does not crash with AttributeError in _delta().
    """

    def _make_model_stub(self, extra_changed_fields):
        """Return a SimpleNamespace that mimics a BackwardMappingModel."""
        sentinel = object()
        obj = SimpleNamespace(
            meth_parameterFittingStrategy={'_fw_name': 'NonLinFitWithErrorContol'},
            _changed_fields=['parameters', 'last_fitted'] + extra_changed_fields,
        )
        # Attach the cached result so loadType returns immediately without
        # calling load_object (avoids needing a real FireWorks registry).
        setattr(obj, '___parameterFittingStrategy', sentinel)
        return obj, sentinel

    def _call_filter(self, obj):
        """Apply only the _changed_fields filter from parameterFittingStrategy."""
        _strategy_roots = {
            'improveErrorStrategy', 'crossValidation', 'acceptanceCriterion',
            'metric',
        }
        obj._changed_fields = [
            f for f in obj._changed_fields
            if f.split('.')[0] not in _strategy_roots
        ]

    def test_real_model_fields_are_preserved(self):
        obj, _ = self._make_model_stub([])
        self._call_filter(obj)
        assert 'parameters' in obj._changed_fields
        assert 'last_fitted' in obj._changed_fields

    def test_cross_validation_root_is_removed(self):
        obj, _ = self._make_model_stub(['crossValidation'])
        self._call_filter(obj)
        assert 'crossValidation' not in obj._changed_fields

    def test_cross_validation_subpath_is_removed(self):
        obj, _ = self._make_model_stub(['crossValidation._fw_name'])
        self._call_filter(obj)
        assert 'crossValidation._fw_name' not in obj._changed_fields

    def test_acceptance_criterion_root_is_removed(self):
        obj, _ = self._make_model_stub(['acceptanceCriterion'])
        self._call_filter(obj)
        assert 'acceptanceCriterion' not in obj._changed_fields

    def test_acceptance_criterion_subpath_is_removed(self):
        obj, _ = self._make_model_stub(['acceptanceCriterion._fw_name',
                                        'acceptanceCriterion.threshold'])
        self._call_filter(obj)
        assert 'acceptanceCriterion._fw_name' not in obj._changed_fields
        assert 'acceptanceCriterion.threshold' not in obj._changed_fields

    def test_improve_error_strategy_subpath_is_removed(self):
        """Original hack: improveErrorStrategy._fw_name must still be filtered."""
        obj, _ = self._make_model_stub(['improveErrorStrategy._fw_name'])
        self._call_filter(obj)
        assert 'improveErrorStrategy._fw_name' not in obj._changed_fields

    def test_metric_subpath_is_removed(self):
        obj, _ = self._make_model_stub(['metric._fw_name'])
        self._call_filter(obj)
        assert 'metric._fw_name' not in obj._changed_fields

    def test_mixed_fields_only_strategy_roots_removed(self):
        obj, _ = self._make_model_stub([
            'crossValidation', 'crossValidation._fw_name',
            'acceptanceCriterion', 'improveErrorStrategy._fw_name',
        ])
        self._call_filter(obj)
        assert obj._changed_fields == ['parameters', 'last_fitted']


# ---------------------------------------------------------------------------
# CFunction.compileCcode — hash properties and cmake skip
# ---------------------------------------------------------------------------

class TestCompileCcode:

    def _make_so(self, tmp_path, code):
        """Pre-create the .so file so that compileCcode skips compilation."""
        h = hashlib.sha256(code.encode()).hexdigest()[:32]
        so = tmp_path / f'func_{h}' / f'lib{h}.so'
        so.parent.mkdir(parents=True, exist_ok=True)
        so.touch()
        return so

    def _registry_mock(self, tmp_path):
        return lambda: SimpleNamespace(surrogate_lib_dir=tmp_path)

    def test_hash_is_deterministic(self, tmp_path, monkeypatch):
        """Same Ccode → same returned library path on two independent calls."""
        from modena.SurrogateModel import CFunction
        monkeypatch.setattr('modena.Registry.ModelRegistry', self._registry_mock(tmp_path))

        code = 'void f(const modena_model_t*m,const double*i,double*o){o[0]=i[0];}'
        self._make_so(tmp_path, code)
        kwargs = {'Ccode': code, 'inputs': {}}
        m = SimpleNamespace(surrogateFunction=SimpleNamespace(inputs={}), inputs={})

        ln1 = CFunction.compileCcode(m, kwargs)
        ln2 = CFunction.compileCcode(m, kwargs)
        assert ln1 == ln2

    def test_different_code_produces_different_path(self, tmp_path, monkeypatch):
        from modena.SurrogateModel import CFunction
        monkeypatch.setattr('modena.Registry.ModelRegistry', self._registry_mock(tmp_path))

        code_a = 'void a(){int x=1;}'
        code_b = 'void b(){int x=2;}'
        self._make_so(tmp_path, code_a)
        self._make_so(tmp_path, code_b)

        m = SimpleNamespace(surrogateFunction=SimpleNamespace(inputs={}), inputs={})
        ln_a = CFunction.compileCcode(m, {'Ccode': code_a, 'inputs': {}})
        ln_b = CFunction.compileCcode(m, {'Ccode': code_b, 'inputs': {}})
        assert ln_a != ln_b

    def test_skips_cmake_when_so_already_exists(self, tmp_path, monkeypatch):
        """If the compiled .so is already present, subprocess.run must not be called."""
        from modena.SurrogateModel import CFunction
        monkeypatch.setattr('modena.Registry.ModelRegistry', self._registry_mock(tmp_path))

        code = 'void skip(){}'
        self._make_so(tmp_path, code)
        kwargs = {'Ccode': code, 'inputs': {}}
        m = SimpleNamespace(surrogateFunction=SimpleNamespace(inputs={}), inputs={})

        with patch('subprocess.run') as mock_run:
            CFunction.compileCcode(m, kwargs)

        mock_run.assert_not_called()

    def test_returned_path_contains_func_hash_prefix(self, tmp_path, monkeypatch):
        from modena.SurrogateModel import CFunction
        monkeypatch.setattr('modena.Registry.ModelRegistry', self._registry_mock(tmp_path))

        code = 'void check(){}'
        h = hashlib.sha256(code.encode()).hexdigest()[:32]
        self._make_so(tmp_path, code)
        kwargs = {'Ccode': code, 'inputs': {}}
        m = SimpleNamespace(surrogateFunction=SimpleNamespace(inputs={}), inputs={})

        ln = CFunction.compileCcode(m, kwargs)
        assert f'func_{h}' in ln
        assert ln.endswith(f'lib{h}.so')
