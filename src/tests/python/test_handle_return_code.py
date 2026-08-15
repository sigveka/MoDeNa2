"""
Tests for BackwardMappingScriptTask.handleReturnCode dispatch.

Covers every branch of the state machine that translates C-library exit
codes into Python exceptions consumed by ``executeAndCatchExceptions``:

    | rc  | Exception raised    | Precise (launch_id) vs fallback lookup |
    | 0   | none                | -                                       |
    | 200 | OutOfBounds         | precise via _pending_oob_launch_id      |
    |                           | fallback via SurrogateModel.loadFailing |
    | 201 | ParametersNotValid  | fallback via SurrogateModel.loadFromModule
    | 202 | ParametersNotValid  | precise via _pending_init_launch_id     |
    |                           | fallback via loadParametersNotValid     |
    | *   | TerminateWorkflow   | (unknown code)                          |

The precise paths must $unset their marker key after use so re-runs cannot
match stale markers.

None of these tests need MongoDB — the ``modena`` package stub in conftest
receives a mock SurrogateModel for each test.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest


def _install_mock_surrogate_model():
    """Replace ``modena.SurrogateModel`` with a MagicMock and return it +
    the original so the test can restore it in a finally block."""
    modena_stub = sys.modules['modena']
    original = getattr(modena_stub, 'SurrogateModel', None)
    mock_sm = MagicMock()
    modena_stub.SurrogateModel = mock_sm
    return original, mock_sm


def _restore(original):
    modena_stub = sys.modules['modena']
    if original is not None:
        modena_stub.SurrogateModel = original
    else:
        del modena_stub.SurrogateModel


def _make_task():
    from modena.Strategy import BackwardMappingScriptTask
    return BackwardMappingScriptTask({'script': 'echo hi'})


# ---------------------------------------------------------------------------
# Return code 0 — no exception
# ---------------------------------------------------------------------------

class TestReturnCodeZero:
    def test_rc_zero_raises_nothing(self):
        task = _make_task()
        # Should be a no-op — no MongoDB access, no exception
        assert task.handleReturnCode(0) is None
        assert task.handleReturnCode(0, launch_id='irrelevant') is None


# ---------------------------------------------------------------------------
# Return code 200 — OutOfBounds
# ---------------------------------------------------------------------------

class TestReturnCode200:
    """rc=200 must raise ``OutOfBounds`` carrying the failing model.

    The precise path uses ``SurrogateModel.objects(__raw__={'_pending_oob_launch_id': ...})``
    and unsets the marker on success.  The fallback path calls
    ``SurrogateModel.loadFailing()``.
    """

    def test_precise_path_via_launch_id(self):
        from modena.Strategy import OutOfBounds
        task = _make_task()
        original, mock_sm = _install_mock_surrogate_model()
        try:
            mock_model = MagicMock()
            mock_model._id = 'flowRate'
            # SurrogateModel.objects(__raw__=...).exclude('fitData').first()
            query = mock_sm.objects.return_value
            query.exclude.return_value.first.return_value = mock_model
            # update_one for unsetting the marker
            unset_query = mock_sm.objects.return_value.update_one

            with pytest.raises(OutOfBounds) as excinfo:
                task.handleReturnCode(200, launch_id='abc-123')

            assert excinfo.value.model is mock_model
            assert excinfo.value.returnCode == 200
            # First call was the query BY launch_id; second was the $unset
            first_call = mock_sm.objects.call_args_list[0]
            assert first_call.kwargs.get('__raw__') == {
                '_pending_oob_launch_id': 'abc-123',
            }
            # The $unset call happened
            assert unset_query.called
        finally:
            _restore(original)

    def test_fallback_when_launch_id_lookup_returns_none(self):
        """When the precise query returns None, loadFailing() is called."""
        from modena.Strategy import OutOfBounds
        task = _make_task()
        original, mock_sm = _install_mock_surrogate_model()
        try:
            mock_model = MagicMock()
            mock_model._id = 'flowRate'
            # Precise query returns None
            mock_sm.objects.return_value.exclude.return_value.first.return_value = None
            # loadFailing succeeds
            mock_sm.loadFailing.return_value = mock_model

            with pytest.raises(OutOfBounds) as excinfo:
                task.handleReturnCode(200, launch_id='no-match')
            assert excinfo.value.model is mock_model
            mock_sm.loadFailing.assert_called_once()
        finally:
            _restore(original)

    def test_fallback_when_no_launch_id(self):
        from modena.Strategy import OutOfBounds
        task = _make_task()
        original, mock_sm = _install_mock_surrogate_model()
        try:
            mock_model = MagicMock()
            mock_sm.loadFailing.return_value = mock_model
            with pytest.raises(OutOfBounds):
                task.handleReturnCode(200)  # no launch_id
            mock_sm.loadFailing.assert_called_once()
            # Precise-path objects() must not have been queried
            mock_sm.objects.assert_not_called()
        finally:
            _restore(original)

    def test_fallback_loadfailing_raises_becomes_terminate(self):
        from modena.Strategy import TerminateWorkflow
        task = _make_task()
        original, mock_sm = _install_mock_surrogate_model()
        try:
            mock_sm.loadFailing.side_effect = RuntimeError('db down')
            with pytest.raises(TerminateWorkflow) as excinfo:
                task.handleReturnCode(200)
            assert excinfo.value.args[-1] == 200
        finally:
            _restore(original)


# ---------------------------------------------------------------------------
# Return code 201 — model missing from database
# ---------------------------------------------------------------------------

class TestReturnCode201:

    def test_loadfrommodule_success(self):
        from modena.Strategy import ParametersNotValid
        task = _make_task()
        original, mock_sm = _install_mock_surrogate_model()
        try:
            mock_model = MagicMock()
            mock_sm.loadFromModule.return_value = mock_model
            with pytest.raises(ParametersNotValid) as excinfo:
                task.handleReturnCode(201)
            assert excinfo.value.returnCode == 201
            # ParametersNotValid stores models as a list; .model is the first
            assert excinfo.value.model is mock_model
        finally:
            _restore(original)

    def test_loadfrommodule_raises_becomes_terminate(self):
        from modena.Strategy import TerminateWorkflow
        task = _make_task()
        original, mock_sm = _install_mock_surrogate_model()
        try:
            mock_sm.loadFromModule.side_effect = ImportError('missing pkg')
            with pytest.raises(TerminateWorkflow) as excinfo:
                task.handleReturnCode(201)
            assert excinfo.value.args[-1] == 201
        finally:
            _restore(original)


# ---------------------------------------------------------------------------
# Return code 202 — parameters not fitted
# ---------------------------------------------------------------------------

class TestReturnCode202:

    def test_precise_path_via_launch_id(self):
        from modena.Strategy import ParametersNotValid
        task = _make_task()
        original, mock_sm = _install_mock_surrogate_model()
        try:
            mock_model = MagicMock()
            mock_model._id = 'coolProp'
            mock_sm.objects.return_value.exclude.return_value.first.return_value = mock_model

            with pytest.raises(ParametersNotValid) as excinfo:
                task.handleReturnCode(202, launch_id='launch-42')

            assert excinfo.value.model is mock_model
            first_call = mock_sm.objects.call_args_list[0]
            assert first_call.kwargs.get('__raw__') == {
                '_pending_init_launch_id': 'launch-42',
            }
            # $unset was called on success
            assert mock_sm.objects.return_value.update_one.called
        finally:
            _restore(original)

    def test_fallback_when_launch_id_lookup_returns_none(self):
        from modena.Strategy import ParametersNotValid
        task = _make_task()
        original, mock_sm = _install_mock_surrogate_model()
        try:
            mock_sm.objects.return_value.exclude.return_value.first.return_value = None
            fallback_model = MagicMock()
            mock_sm.loadParametersNotValid.return_value = [fallback_model]
            with pytest.raises(ParametersNotValid) as excinfo:
                task.handleReturnCode(202, launch_id='no-match')
            assert fallback_model in excinfo.value.models
        finally:
            _restore(original)

    def test_fallback_empty_becomes_terminate(self):
        from modena.Strategy import TerminateWorkflow
        task = _make_task()
        original, mock_sm = _install_mock_surrogate_model()
        try:
            mock_sm.loadParametersNotValid.return_value = []
            with pytest.raises(TerminateWorkflow) as excinfo:
                task.handleReturnCode(202)
            assert excinfo.value.args[-1] == 202
        finally:
            _restore(original)


# ---------------------------------------------------------------------------
# Unknown positive return code — TerminateWorkflow
# ---------------------------------------------------------------------------

class TestReturnCodeUnknown:

    @pytest.mark.parametrize('rc', [1, 42, 139, 255])
    def test_unknown_rc_terminates(self, rc):
        from modena.Strategy import TerminateWorkflow
        task = _make_task()
        with pytest.raises(TerminateWorkflow) as excinfo:
            task.handleReturnCode(rc)
        assert 'unknown' in str(excinfo.value).lower() or excinfo.value.args[-1] == rc

    def test_unknown_message_spelling(self):
        """Regression: 'An unknow error' -> 'An unknown error'."""
        from modena.Strategy import TerminateWorkflow
        task = _make_task()
        with pytest.raises(TerminateWorkflow) as excinfo:
            task.handleReturnCode(42)
        assert 'unknow ' not in str(excinfo.value)   # no misspelling
        assert 'unknown' in str(excinfo.value).lower()


# ---------------------------------------------------------------------------
# structured logging — 'return_code' event
# ---------------------------------------------------------------------------

class TestHandleReturnCodeLogging:

    def test_nonzero_rc_emits_return_code_event(self, caplog):
        import logging
        from modena.Strategy import TerminateWorkflow
        task = _make_task()
        with caplog.at_level(logging.ERROR, logger='modena.strategy'):
            with pytest.raises(TerminateWorkflow):
                task.handleReturnCode(42, launch_id='xyz')
        # The ERROR log carries structured extras
        rec = next(r for r in caplog.records if 'return code' in r.getMessage())
        assert getattr(rec, 'event', None) == 'return_code'
        assert getattr(rec, 'return_code', None) == 42
        assert getattr(rec, 'launch_id', None) == 'xyz'

    def test_zero_rc_emits_no_log(self, caplog):
        import logging
        task = _make_task()
        with caplog.at_level(logging.DEBUG, logger='modena.strategy'):
            task.handleReturnCode(0)
        # No 'return code = 0' log at any level
        assert not any('return code' in r.getMessage() for r in caplog.records)
