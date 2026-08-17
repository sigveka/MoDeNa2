"""
The OutOfBounds exception must carry the C layer's return code
---------------------------------------------------------------
``OutOfBounds`` has declared a ``returnCode`` attribute all along, and the
``Strategy.py`` raise sites populate it from a subprocess exit status.  The C
raise site in ``model.c`` did not: it built the exception with
``(message, model)`` only, so a pure-Python caller -- the audience
``callModel()`` stopped calling ``sys.exit(200)`` for -- received
``returnCode=None`` and had to hard-code 200 to know what had happened.

This is a Python<->C contract: ``model.c`` constructs the exception object, so
a change there silently degrades every caller.  Marked integration because it
needs the compiled library, a live MongoDB and an initialised model.
"""

import pytest


MODEL_ID = 'flowRate'


@pytest.fixture
def trained_model():
    modena = pytest.importorskip('modena')
    try:
        model = modena.load(MODEL_ID)
    except Exception as exc:                      # noqa: BLE001
        pytest.skip(f'{MODEL_ID} not available: {exc}')
    if not model.parameters:
        pytest.skip(f'{MODEL_ID} is untrained')
    return modena, model


def _midpoints(model):
    return {n: (v.min + v.max) / 2.0 for n, v in model.inputs.items()}


@pytest.mark.integration
def test_in_bounds_call_does_not_raise(trained_model):
    _modena, model = trained_model
    outputs = model(_midpoints(model))
    assert all(isinstance(v, float) for v in outputs.values())


@pytest.mark.integration
def test_out_of_bounds_carries_the_return_code(trained_model):
    """model.c must pass the code as the third constructor argument."""
    modena, model = trained_model
    inputs = _midpoints(model)
    first = next(iter(model.inputs))
    inputs[first] = model.inputs[first].max * 1e6      # far outside

    with pytest.raises(modena.OutOfBounds) as excinfo:
        model(inputs)

    exc = excinfo.value
    assert exc.returnCode == 200, (
        'OutOfBounds.returnCode is not populated — model.c built the '
        'exception without the code from modena_model_call()'
    )


@pytest.mark.integration
def test_out_of_bounds_identifies_the_model(trained_model):
    """The exception carries strictly more than an exit status does."""
    modena, model = trained_model
    inputs = _midpoints(model)
    first = next(iter(model.inputs))
    inputs[first] = model.inputs[first].max * 1e6

    with pytest.raises(modena.OutOfBounds) as excinfo:
        model(inputs)

    assert excinfo.value.model._id == MODEL_ID
    assert 'out-of-bounds' in excinfo.value.args[0]


@pytest.mark.integration
def test_parameters_not_valid_carries_the_return_code(trained_model):
    """The other exception model.c constructs, with the same defect.

    Both raise sites in modena_model_t_init built a 2-tuple (message, model),
    so returnCode was always None for a pure-Python caller -- which is what
    made the snippet's ``exc.returnCode or 202`` misleading: the fallback was
    not a fallback, it was the only branch that ever ran.

    Triggered by passing a parameter array of the wrong length, which is the
    second of the two conditions that raise it.
    """
    modena, model = trained_model
    n = len(model.parameter_names())
    if n < 2:
        pytest.skip('needs a model with at least two parameters')

    with pytest.raises(modena.ParametersNotValid) as excinfo:
        modena.libmodena.modena_model_t(model=model, parameters=[1.0] * (n - 1))

    exc = excinfo.value
    assert exc.returnCode == 202, (
        'ParametersNotValid.returnCode is not populated — model.c built the '
        'exception without the code'
    )
    assert exc.model._id == MODEL_ID
