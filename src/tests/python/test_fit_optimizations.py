"""
Tests for the MongoDB fetch/write optimizations on the fit path:

  * ``SurrogateModel.n_samples_fitted`` — set at end of every fit; enables
    the no-op skip in ``ParameterFitting.run_task`` when the number of
    samples has not increased since the previous fit.
  * ``SurrogateModel.load(id, with_fit_data=False)`` — new fast-path
    variant that excludes the large ``fitData`` subdocument.
  * ``SurrogateModel.loadFailing()`` — now excludes ``fitData`` from
    the fallback OOB-lookup query.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Schema: new n_samples_fitted field
# ---------------------------------------------------------------------------

class TestNSamplesFittedField:

    def test_field_exists_and_defaults_to_zero(self):
        import mongoengine
        from modena.SurrogateModel import SurrogateModel
        field = SurrogateModel.n_samples_fitted
        assert isinstance(field, mongoengine.IntField)
        assert field.default == 0


# ---------------------------------------------------------------------------
# ParameterFitting.run_task skip semantics
# ---------------------------------------------------------------------------

class TestFitSkipWhenUnchanged:
    """When ``nSamples == n_samples_fitted`` and parameters are populated,
    ``ParameterFitting.run_task`` must return early without running scipy."""

    def _install_model_stub(self, parameters, n_samples, n_samples_fitted,
                             fitData=None):
        import sys
        modena_stub = sys.modules['modena']
        original = getattr(modena_stub, 'SurrogateModel', None)
        mock_sm = MagicMock()
        mock_model = MagicMock()
        mock_model._id = 'testModel'
        mock_model.parameters = parameters
        mock_model.n_samples_fitted = n_samples_fitted
        # nSamples is derived from fitData length; supply matching fitData
        if fitData is None:
            fitData = {'x': [0.0] * n_samples}
        mock_model.fitData = fitData
        mock_model.nSamples = n_samples
        # parameterFittingStrategy() is what would be called if we DON'T skip;
        # the skip test uses call_count on this MagicMock to prove we skipped.
        mock_model.parameterFittingStrategy = MagicMock()
        mock_sm.load.return_value = mock_model
        modena_stub.SurrogateModel = mock_sm
        return original, mock_sm, mock_model

    def _restore(self, original):
        import sys
        modena_stub = sys.modules['modena']
        if original is not None:
            modena_stub.SurrogateModel = original
        else:
            del modena_stub.SurrogateModel

    def test_skip_when_no_new_samples(self):
        """nSamples == n_samples_fitted → skip; no scipy call."""
        from modena.Strategy import ParameterFitting
        task = ParameterFitting({'surrogateModelId': 'testModel'})
        original, _, mock_model = self._install_model_stub(
            parameters={'P0': 1.0, 'P1': 2.0},
            n_samples=10,
            n_samples_fitted=10,
        )
        try:
            action = task.run_task({'_fw_env': {}})
        finally:
            self._restore(original)

        # The fitting strategy must NOT have been invoked
        mock_model.parameterFittingStrategy.assert_not_called()
        # But the freeze/lock spec must still be pushed so the caller
        # can identify which models were "fitted this run".
        assert action is not None
        assert action.mod_spec == [
            {'_push': {'_modena_fitted_models': 'testModel'}}
        ]

    def test_run_when_new_samples_arrived(self):
        """nSamples > n_samples_fitted → fit as normal."""
        from modena.Strategy import ParameterFitting
        from fireworks import FWAction
        task = ParameterFitting({'surrogateModelId': 'testModel'})
        original, _, mock_model = self._install_model_stub(
            parameters={'P0': 1.0, 'P1': 2.0},
            n_samples=15,          # 5 new samples
            n_samples_fitted=10,   # since last fit
        )
        # newPointsFWAction must return a FWAction (mocked)
        mock_model.parameterFittingStrategy.return_value.newPointsFWAction.return_value = FWAction()
        try:
            task.run_task({'_fw_env': {}})
        finally:
            self._restore(original)
        # We didn't skip — strategy was invoked
        mock_model.parameterFittingStrategy.assert_called_once()

    def test_run_when_no_parameters_yet(self):
        """Empty parameters (first fit) → always run, even if n_samples_fitted
        happens to equal nSamples (defensive)."""
        from modena.Strategy import ParameterFitting
        from fireworks import FWAction
        task = ParameterFitting({'surrogateModelId': 'testModel'})
        original, _, mock_model = self._install_model_stub(
            parameters={},                # never fitted
            n_samples=4,
            n_samples_fitted=4,           # matches, but no params
        )
        mock_model.parameterFittingStrategy.return_value.newPointsFWAction.return_value = FWAction()
        try:
            task.run_task({'_fw_env': {}})
        finally:
            self._restore(original)
        mock_model.parameterFittingStrategy.assert_called_once()

    def test_skip_emits_structured_log(self, caplog):
        """The skip decision must be visible as a structured event."""
        import logging
        from modena.Strategy import ParameterFitting
        task = ParameterFitting({'surrogateModelId': 'testModel'})
        original, _, _ = self._install_model_stub(
            parameters={'P0': 1.0}, n_samples=10, n_samples_fitted=10,
        )
        try:
            with caplog.at_level(logging.INFO, logger='modena.strategy'):
                task.run_task({'_fw_env': {}})
        finally:
            self._restore(original)
        # Find the skip record
        rec = next(
            (r for r in caplog.records
             if getattr(r, 'event', None) == 'parameter_fit_skipped'),
            None,
        )
        assert rec is not None, 'no parameter_fit_skipped event emitted'
        assert getattr(rec, 'model_id', None) == 'testModel'
        assert getattr(rec, 'reason', None) == 'no_new_samples'


# ---------------------------------------------------------------------------
# load(with_fit_data=False) fast path via mongomock
# ---------------------------------------------------------------------------

class TestLoadWithFitDataOption:

    def test_load_with_fit_data_false_excludes_fitdata(self, mongo_db):
        """The fast-path load must not populate model.fitData."""
        from modena.SurrogateModel import SurrogateModel
        coll = SurrogateModel._get_collection()
        # Populate with a substantial fitData subdocument to make the
        # exclusion visible.
        coll.replace_one(
            {'_id': 'test_exclude'},
            {
                '_id': 'test_exclude',
                '_cls': 'SurrogateModel.BackwardMappingModel',
                'parameters': {'P0': 0.5, 'P1': 0.6},
                'fitData': {'x': list(range(1000)), 'y': list(range(1000))},
            },
            upsert=True,
        )
        m_fast = SurrogateModel.load('test_exclude', with_fit_data=False)
        # fitData must be empty (excluded from projection)
        assert not m_fast.fitData

        # Parameters must still be present
        assert m_fast.parameters == {'P0': 0.5, 'P1': 0.6}

    def test_load_default_still_fetches_fitdata(self, mongo_db):
        """Default load() must be backward-compatible — full fetch."""
        from modena.SurrogateModel import SurrogateModel
        coll = SurrogateModel._get_collection()
        coll.replace_one(
            {'_id': 'test_default'},
            {
                '_id': 'test_default',
                '_cls': 'SurrogateModel.BackwardMappingModel',
                'parameters': {'P0': 0.5},
                'fitData': {'x': [1.0, 2.0, 3.0]},
            },
            upsert=True,
        )
        m = SurrogateModel.load('test_default')
        assert dict(m.fitData) == {'x': [1.0, 2.0, 3.0]}


# ---------------------------------------------------------------------------
# loadFailing excludes fitData
# ---------------------------------------------------------------------------

class TestLoadFailingExcludesFitData:

    def test_load_failing_returns_model_without_fitdata(self, mongo_db):
        """loadFailing() is a fallback OOB lookup that never touches
        fitData — the exclude must skip the large subdocument."""
        from modena.SurrogateModel import SurrogateModel
        coll = SurrogateModel._get_collection()
        coll.replace_one(
            {'_id': 'oob_test'},
            {
                '_id': 'oob_test',
                '_cls': 'SurrogateModel.BackwardMappingModel',
                'outsidePoint': {'D': 0.02},
                'fitData': {'D': list(range(1000))},
                'parameters': {'P0': 0.5},
            },
            upsert=True,
        )
        m = SurrogateModel.loadFailing()
        assert m is not None
        assert m._id == 'oob_test'
        # fitData is excluded from the projection
        assert not m.fitData

    def test_load_failing_returns_none_when_no_oob(self, mongo_db):
        """No model has an outsidePoint → None (unchanged behaviour)."""
        from modena.SurrogateModel import SurrogateModel
        coll = SurrogateModel._get_collection()
        coll.replace_one(
            {'_id': 'no_oob'},
            {
                '_id': 'no_oob',
                '_cls': 'SurrogateModel.BackwardMappingModel',
                'parameters': {},
            },
            upsert=True,
        )
        assert SurrogateModel.loadFailing() is None
