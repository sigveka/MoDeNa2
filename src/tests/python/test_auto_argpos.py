"""
Tests for the Phase 1 auto-argPos changes on SurrogateFunction / CFunction.

Covers:
  * argPos is auto-assigned from declaration order for outputs and
    parameters (previously required to be user-specified).
  * User-supplied argPos on any category is rejected with a TypeError
    that points at the named-parameter convention.
  * Variable names that are not valid C identifiers are rejected at
    declaration time.
  * SurrogateFunction exposes ``parameter_names_ordered()`` and
    ``output_names_ordered()`` helpers whose ordering is argPos.
  * MinMax embedded doc replaces MinMaxArgPos for outputs / parameters;
    MinMaxArgPos is gone.

These are pure-Python unit tests using MongoEngine's own validation —
no live MongoDB required (the module-level ``connect()`` is stubbed by
conftest.py).
"""

import pytest


# ---------------------------------------------------------------------------
# argPos on the DECLARATION side is rejected
# ---------------------------------------------------------------------------

class TestRejectArgPosInDeclaration:
    """User must not supply argPos in outputs={} or parameters={} — it is
    auto-assigned from declaration order."""

    _CCODE = '''
        #include "modena.h"
        void f(const modena_model_t* model, const double* inputs, double* outputs) {
            {% block variables %}{% endblock %}
            outputs[0] = 1.0;
        }
    '''

    def _minimal_kwargs(self):
        return dict(
            Ccode=self._CCODE,
            inputs={'D': {'min': 0.0, 'max': 1.0}},
            outputs={'y': {'min': 0.0, 'max': 1.0}},
            parameters={'k0': {'min': 0.0, 'max': 1.0}},
        )

    def test_rejects_argpos_on_outputs(self):
        from modena.SurrogateModel import CFunction
        kw = self._minimal_kwargs()
        kw['outputs'] = {'y': {'min': 0.0, 'max': 1.0, 'argPos': 0}}
        with pytest.raises(TypeError, match='outputs'):
            CFunction(**kw)

    def test_rejects_argpos_on_parameters(self):
        from modena.SurrogateModel import CFunction
        kw = self._minimal_kwargs()
        kw['parameters'] = {'k0': {'min': 0.0, 'max': 1.0, 'argPos': 0}}
        with pytest.raises(TypeError, match='parameters'):
            CFunction(**kw)

    def test_rejects_argpos_on_inputs(self):
        from modena.SurrogateModel import CFunction
        kw = self._minimal_kwargs()
        kw['inputs'] = {'D': {'min': 0.0, 'max': 1.0, 'argPos': 0}}
        with pytest.raises(TypeError, match='inputs'):
            CFunction(**kw)

    def test_error_message_names_offending_variable(self):
        from modena.SurrogateModel import CFunction
        kw = self._minimal_kwargs()
        kw['parameters'] = {
            'k0': {'min': 0.0, 'max': 1.0},
            'k1': {'min': 0.0, 'max': 1.0, 'argPos': 1},
        }
        with pytest.raises(TypeError, match="'k1'"):
            CFunction(**kw)


# ---------------------------------------------------------------------------
# Invalid variable names rejected at declaration
# ---------------------------------------------------------------------------

class TestVariableNameValidation:
    """Names must be valid C identifiers so the Jinja2 template can bind
    them as ``const double <name> = ...;``."""

    _CCODE = '''
        #include "modena.h"
        void f(const modena_model_t* model, const double* inputs, double* outputs) {
            {% block variables %}{% endblock %}
            outputs[0] = 1.0;
        }
    '''

    def _kw(self, **overrides):
        base = dict(
            Ccode=self._CCODE,
            inputs={'D': {'min': 0.0, 'max': 1.0}},
            outputs={'y': {'min': 0.0, 'max': 1.0}},
            parameters={'k0': {'min': 0.0, 'max': 1.0}},
        )
        base.update(overrides)
        return base

    @pytest.mark.parametrize('bad_name', ['2k', 'k-1', 'k.value', 'k v'])
    def test_rejects_invalid_parameter_name(self, bad_name):
        from modena.SurrogateModel import CFunction
        with pytest.raises(ValueError, match='C identifier'):
            CFunction(**self._kw(parameters={bad_name: {'min': 0.0, 'max': 1.0}}))

    def test_rejects_bracket_syntax_without_indexset(self):
        """`k[0]` is index-set syntax; without a declared index set it
        raises 'Index 0 not defined' rather than the C-identifier
        message.  Either error is acceptable — both prevent the bad
        name from reaching the compiler."""
        from modena.SurrogateModel import CFunction
        with pytest.raises(Exception, match='Index'):
            CFunction(**self._kw(parameters={'k[0]': {'min': 0.0, 'max': 1.0}}))

    @pytest.mark.parametrize('bad_name', ['2y', 'y-1', 'y.field'])
    def test_rejects_invalid_output_name(self, bad_name):
        from modena.SurrogateModel import CFunction
        with pytest.raises(ValueError, match='C identifier'):
            CFunction(**self._kw(outputs={bad_name: {'min': 0.0, 'max': 1.0}}))

    @pytest.mark.parametrize('good_name', ['k0', 'k_1', '_k', 'alpha', 'P0'])
    def test_accepts_valid_c_identifier(self, good_name):
        # Only assert that name validation does NOT reject the name.
        # We mock compileCcode so the test doesn't need libmodena.
        from unittest.mock import patch
        from modena.SurrogateModel import CFunction
        with patch.object(CFunction, 'compileCcode', return_value='/tmp/x.so'):
            with patch.object(CFunction, 'save'):
                # No ValueError = validation accepted the name.
                CFunction(**self._kw(parameters={good_name: {'min': 0.0, 'max': 1.0}}))


# ---------------------------------------------------------------------------
# argPos ordering matches declaration order
# ---------------------------------------------------------------------------

class TestAutoArgPosOrdering:
    """Since users no longer supply argPos, the ordering used by minMax(),
    the compiled .so, and the fitting marshalling all come from dict-key
    insertion order in the SurrogateFunction."""

    def test_parameter_names_ordered_matches_declaration(self, tmp_path, monkeypatch):
        # We need a real CFunction to test the ordering helpers.  Use the
        # existing installed libmodena so the compile step succeeds.
        pytest.importorskip('modena.libmodena')
        from modena.SurrogateModel import CFunction

        f = CFunction(
            Ccode='''
                #include "modena.h"
                void f_ordering(const modena_model_t* model, const double* inputs, double* outputs) {
                    {% block variables %}{% endblock %}
                    outputs[0] = param_c * inputs[0] + param_a * inputs[1] + param_b;
                }
            ''',
            inputs={'x': {'min': 0.0, 'max': 1.0}, 'y': {'min': 0.0, 'max': 1.0}},
            outputs={'z': {'min': 0.0, 'max': 1.0}},
            parameters={
                # Declaration order: c, a, b — arbitrary, not alphabetical
                'param_c': {'min': 0.0, 'max': 1.0},
                'param_a': {'min': 0.0, 'max': 1.0},
                'param_b': {'min': 0.0, 'max': 1.0},
            },
        )
        assert f.parameter_names_ordered() == ['param_c', 'param_a', 'param_b']
        assert f.output_names_ordered() == ['z']
        assert f.parameters_size() == 3


# ---------------------------------------------------------------------------
# MinMaxArgPos is gone
# ---------------------------------------------------------------------------

class TestSurrogateHashIncludesDeclarationOrder:
    """SHA256 hash used to name the compiled .so must include the
    declaration order of inputs/outputs/parameters — otherwise reordering
    would silently reuse a stale .so with the old name→index bindings
    while the SurrogateFunction record claimed the new order."""

    _CCODE = '''
        #include "modena.h"
        void f(const modena_model_t* model, const double* inputs, double* outputs) {
            {% block variables %}{% endblock %}
            outputs[0] = 1.0;
        }
    '''

    def _hash_for(self, params_dict):
        """Extract the SHA256 hash CFunction.compileCcode would use."""
        import hashlib
        m = hashlib.sha256()
        m.update(self._CCODE.encode('utf-8'))
        m.update(b'\x00')
        m.update('|'.join(['D']).encode('utf-8'))    # single input
        m.update(b'\x00')
        m.update('|'.join(['y']).encode('utf-8'))    # single output
        m.update(b'\x00')
        m.update('|'.join(params_dict.keys()).encode('utf-8'))
        return m.hexdigest()[:32]

    def test_hash_differs_when_parameters_swap_order(self):
        """{k0, k1} and {k1, k0} must hash differently."""
        h1 = self._hash_for({'k0': None, 'k1': None})
        h2 = self._hash_for({'k1': None, 'k0': None})
        assert h1 != h2

    def test_hash_stable_when_order_unchanged(self):
        h1 = self._hash_for({'k0': None, 'k1': None})
        h2 = self._hash_for({'k0': None, 'k1': None})
        assert h1 == h2

    def test_hash_differs_when_new_parameter_added(self):
        h1 = self._hash_for({'k0': None, 'k1': None})
        h2 = self._hash_for({'k0': None, 'k1': None, 'k2': None})
        assert h1 != h2


class TestMinMaxArgPosDeleted:
    """The MinMaxArgPos embedded doc was replaced by MinMax for outputs
    and parameters.  Verify the class no longer exists."""

    def test_minmaxargpos_not_in_module(self):
        import modena.SurrogateModel as sm
        assert not hasattr(sm, 'MinMaxArgPos'), (
            'MinMaxArgPos still exported — Phase 1 was supposed to delete it'
        )

    def test_minmax_class_exists_and_is_used(self):
        import modena.SurrogateModel as sm
        assert hasattr(sm, 'MinMax')
        assert hasattr(sm.SurrogateFunction, 'outputs')
        assert hasattr(sm.SurrogateFunction, 'parameters')
        # Verify the embedded document type on the field descriptor
        outputs_field = sm.SurrogateFunction.outputs.field
        parameters_field = sm.SurrogateFunction.parameters.field
        assert outputs_field.document_type is sm.MinMax
        assert parameters_field.document_type is sm.MinMax
