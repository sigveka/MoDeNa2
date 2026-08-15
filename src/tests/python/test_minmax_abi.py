"""
ABI contract test for SurrogateModel.minMax().

The C code in src/src/model.c:modena_model_get_minMax() reads the returned
tuple by *raw integer index* via PyTuple_GET_ITEM(...).  Reordering,
renaming, or inserting elements before the last silently corrupts bounds
and/or segfaults the C application — no automated test previously caught
that.  This suite verifies the Python-side contract without requiring
libmodena or MongoDB to be built.

Current layout (indices 0..4) — must match model.c exactly:

    0  sequence of float   input minimums     (argPos-ordered)
    1  sequence of float   input maximums     (argPos-ordered)
    2  sequence of str     input names        (argPos-ordered)
    3  sequence of str     output names       (argPos-ordered)
    4  sequence of str     parameter names    (argPos-ordered)

The C code applies PySequence_Fast to each element, so the concrete type
may be list, tuple, or dict.keys() view.  A `set` would silently break
because iteration order is unspecified — the argPos-order tests below
would catch that.

New elements may only be appended (index 5 onward) and must land in the
same commit as the corresponding change to modena_model_get_minMax().
"""

from types import SimpleNamespace

import pytest


# ---------------------------------------------------------------------------
# Fixture — a mock model rich enough for SurrogateModel.minMax() to work
# ---------------------------------------------------------------------------

def _make_model(inputs, outputs, parameters):
    """Build a mock model with the attributes minMax() reaches for.

    ``inputs``, ``outputs``, ``parameters`` are ordered dicts mapping name →
    ``{'min': float, 'max': float, 'argPos': int}``.  For inputs, argPos is
    the position in the min/max arrays; for outputs and parameters, argPos
    is required for name ordering (though minMax itself just uses .keys()
    for those two — position is expected to match dict insertion order,
    which in Python 3.7+ is guaranteed for dict literals).
    """
    inputs_size = len(inputs)

    class MinMaxSlot:
        def __init__(self, spec):
            self.min = spec['min']
            self.max = spec['max']
            self.argPos = spec.get('argPos')
            self._spec = spec

        def __getitem__(self, key):
            return self._spec[key]

        def __contains__(self, key):
            return key in self._spec

    model_inputs = {k: MinMaxSlot(v) for k, v in inputs.items()}
    model_outputs = {k: MinMaxSlot(v) for k, v in outputs.items()}
    sf_parameters = {k: MinMaxSlot(v) for k, v in parameters.items()}

    sf = SimpleNamespace(
        inputs=model_inputs,       # for the fallback branch of inputs_argPos
        parameters=sf_parameters,
        inputs_size=lambda: inputs_size,
    )
    m = SimpleNamespace(
        inputs=model_inputs,
        outputs=model_outputs,
        surrogateFunction=sf,
    )
    # minMax() reaches for self.inputs_argPos(k); satisfy it directly from
    # the spec dict so the test doesn't depend on the real lookup path.
    m.inputs_argPos = lambda name: model_inputs[name].argPos
    return m


# ---------------------------------------------------------------------------
# ABI contract — tuple shape and element types
# ---------------------------------------------------------------------------

class TestMinMaxTupleShape:
    """Model.c reads exactly 5 elements from the returned tuple."""

    def _model(self):
        return _make_model(
            inputs={
                'D':      {'min': 0.0,  'max': 1.0,  'argPos': 0},
                'rho0':   {'min': 1.0,  'max': 10.0, 'argPos': 1},
                'p0':     {'min': 1e5,  'max': 5e5,  'argPos': 2},
            },
            outputs={
                'flowRate': {'min': -1e9, 'max': 1e9, 'argPos': 0},
            },
            parameters={
                'k0': {'min': -1.0, 'max': 1.0, 'argPos': 0},
                'k1': {'min': -1.0, 'max': 1.0, 'argPos': 1},
            },
        )

    def test_returns_tuple(self):
        from modena.SurrogateModel import SurrogateModel
        result = SurrogateModel.minMax(self._model())
        assert isinstance(result, tuple)

    def test_returns_exactly_five_elements(self):
        """Adding a 6th element without updating model.c is safe;
        removing to fewer than 5 is a segfault.  The C code reads
        indices 0..4 unconditionally."""
        from modena.SurrogateModel import SurrogateModel
        result = SurrogateModel.minMax(self._model())
        assert len(result) >= 5, (
            'minMax() returned fewer than 5 elements — model.c reads '
            'indices 0..4 unconditionally via PyTuple_GET_ITEM'
        )
        # Guard against silent expansion too — force a conscious update
        # to this test any time a new field is appended.
        assert len(result) == 5, (
            f'minMax() now returns {len(result)} elements; update model.c '
            'to consume the new fields and update this test to match'
        )

    def test_indices_zero_and_one_are_sequences_of_floats(self):
        """model.c calls PyFloat_AsDouble on each element of indices 0 and 1."""
        from modena.SurrogateModel import SurrogateModel
        result = SurrogateModel.minMax(self._model())
        for idx in (0, 1):
            elems = list(result[idx])
            assert all(isinstance(x, (int, float)) for x in elems), (
                f'minMax()[{idx}] contains a non-numeric element; '
                'PyFloat_AsDouble in model.c will fail'
            )

    def test_indices_two_three_four_are_sequences_of_strings(self):
        """model.c calls PyUnicode_AsEncodedString on each element of
        indices 2, 3, 4."""
        from modena.SurrogateModel import SurrogateModel
        result = SurrogateModel.minMax(self._model())
        for idx in (2, 3, 4):
            elems = list(result[idx])
            assert all(isinstance(x, str) for x in elems), (
                f'minMax()[{idx}] contains a non-str element; '
                'PyUnicode_AsEncodedString in model.c will fail'
            )

    def test_all_elements_support_pysequence_fast(self):
        """PySequence_Fast in model.c accepts list, tuple, or dict.keys();
        it does NOT accept sets, generators, or dict_values-of-non-strings.
        Sets are excluded because iteration order is unspecified — the C
        code would read names in arbitrary order."""
        from modena.SurrogateModel import SurrogateModel
        import collections.abc
        result = SurrogateModel.minMax(self._model())
        for idx, elem in enumerate(result[:5]):
            assert hasattr(elem, '__iter__'), f'minMax()[{idx}] not iterable'
            assert not isinstance(elem, (set, frozenset)), (
                f'minMax()[{idx}] is a set — order is unspecified; '
                'C code will read names in arbitrary order'
            )
            assert isinstance(elem, (list, tuple, collections.abc.KeysView)), (
                f'minMax()[{idx}] is {type(elem).__name__} — unexpected; '
                'only list, tuple, and dict.keys() are established as safe'
            )


# ---------------------------------------------------------------------------
# argPos ordering — the whole point of the tuple
# ---------------------------------------------------------------------------

class TestMinMaxArgPosOrdering:
    """C code reads the arrays by *position*.  Position i must correspond
    to argPos == i for every category."""

    def test_input_min_max_ordered_by_argpos(self):
        """Reverse the dict insertion order to make sure argPos wins."""
        from modena.SurrogateModel import SurrogateModel
        m = _make_model(
            inputs={
                # dict insertion order: rho0 first, then D — but argPos says D=0
                'rho0': {'min': 1.0,  'max': 10.0, 'argPos': 1},
                'D':    {'min': 0.01, 'max': 0.1,  'argPos': 0},
            },
            outputs={'out': {'min': 0, 'max': 1, 'argPos': 0}},
            parameters={'k': {'min': 0, 'max': 1, 'argPos': 0}},
        )
        mins, maxes, *_ = SurrogateModel.minMax(m)
        mins = list(mins); maxes = list(maxes)
        # Position 0 must be D (argPos=0), not rho0 (dict-first)
        assert mins[0] == 0.01 and maxes[0] == 0.1
        assert mins[1] == 1.0  and maxes[1] == 10.0

    def test_input_names_ordered_matches_min_max_positions(self):
        """Position i in the min/max arrays must correspond to position i
        in the names list (index 2)."""
        from modena.SurrogateModel import SurrogateModel
        m = _make_model(
            inputs={
                'rho0': {'min': 1.0,  'max': 10.0, 'argPos': 1},
                'D':    {'min': 0.01, 'max': 0.1,  'argPos': 0},
            },
            outputs={'out': {'min': 0, 'max': 1, 'argPos': 0}},
            parameters={},
        )
        result = SurrogateModel.minMax(m)
        mins, _, input_names, *_ = result
        input_names = list(input_names)
        mins = list(mins)
        # The current implementation returns names in dict insertion order,
        # NOT argPos order.  This is a latent bug worth surfacing: the C
        # code reads inputs_names[i] to name the input at slot i, but the
        # min/max at slot i comes from the argPos-indexed lookup, so if
        # dict insertion order != argPos order the C side reads
        # rho0's *name* for D's *value*.
        #
        # Assert the safe contract we want: names[i] belongs to the input
        # whose argPos is i.  If this fails, minMax() needs to sort keys
        # by argPos before returning them.
        for i, name in enumerate(input_names):
            slot = m.inputs[name]
            assert slot.argPos == i, (
                f'minMax()[2][{i}] = {name!r} has argPos={slot.argPos}; '
                f'C side will read the wrong input name for slot {i}. '
                'minMax() must sort input names by argPos before returning.'
            )


# ---------------------------------------------------------------------------
# Lengths match sizes — inputs_size / outputs_size / parameters_size
# ---------------------------------------------------------------------------

class TestMinMaxLengths:

    def test_min_and_max_same_length(self):
        from modena.SurrogateModel import SurrogateModel
        m = _make_model(
            inputs={
                'a': {'min': 0, 'max': 1, 'argPos': 0},
                'b': {'min': 0, 'max': 1, 'argPos': 1},
                'c': {'min': 0, 'max': 1, 'argPos': 2},
            },
            outputs={'o': {'min': 0, 'max': 1, 'argPos': 0}},
            parameters={'k': {'min': 0, 'max': 1, 'argPos': 0}},
        )
        mins, maxes, *_ = SurrogateModel.minMax(m)
        assert len(list(mins)) == len(list(maxes))

    def test_min_length_matches_inputs_size(self):
        """model.c stores len(minMax()[0]) as inputs_internal_size — this
        drives every subsequent malloc for input arrays.  Must equal what
        surrogateFunction.inputs_size() reports."""
        from modena.SurrogateModel import SurrogateModel
        m = _make_model(
            inputs={
                'a': {'min': 0, 'max': 1, 'argPos': 0},
                'b': {'min': 0, 'max': 1, 'argPos': 1},
                'c': {'min': 0, 'max': 1, 'argPos': 2},
            },
            outputs={'o': {'min': 0, 'max': 1, 'argPos': 0}},
            parameters={},
        )
        mins, _, _, _, _ = SurrogateModel.minMax(m)
        assert len(list(mins)) == m.surrogateFunction.inputs_size()

    def test_output_names_length_matches_outputs(self):
        from modena.SurrogateModel import SurrogateModel
        m = _make_model(
            inputs={'a': {'min': 0, 'max': 1, 'argPos': 0}},
            outputs={
                'o1': {'min': 0, 'max': 1, 'argPos': 0},
                'o2': {'min': 0, 'max': 1, 'argPos': 1},
            },
            parameters={},
        )
        _, _, _, output_names, _ = SurrogateModel.minMax(m)
        assert len(list(output_names)) == 2

    def test_parameter_names_length_matches_parameters(self):
        from modena.SurrogateModel import SurrogateModel
        m = _make_model(
            inputs={'a': {'min': 0, 'max': 1, 'argPos': 0}},
            outputs={'o': {'min': 0, 'max': 1, 'argPos': 0}},
            parameters={
                'k0': {'min': 0, 'max': 1, 'argPos': 0},
                'k1': {'min': 0, 'max': 1, 'argPos': 1},
                'k2': {'min': 0, 'max': 1, 'argPos': 2},
            },
        )
        *_, param_names = SurrogateModel.minMax(m)
        assert len(list(param_names)) == 3

    def test_empty_parameters_still_returns_sequence(self):
        """A ForwardMappingModel with no fitted parameters must still
        produce a valid (empty) sequence at index 4 — never None or
        missing."""
        from modena.SurrogateModel import SurrogateModel
        m = _make_model(
            inputs={'a': {'min': 0, 'max': 1, 'argPos': 0}},
            outputs={'o': {'min': 0, 'max': 1, 'argPos': 0}},
            parameters={},
        )
        result = SurrogateModel.minMax(m)
        assert result[4] is not None
        assert len(list(result[4])) == 0
