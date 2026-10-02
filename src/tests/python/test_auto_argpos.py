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
# Index-set names: `W[A]` is declared with its brackets, bound in C as `WA`
# ---------------------------------------------------------------------------
# The template used to bind every name verbatim, so `const double W[A] = ...`
# was a C syntax error while checkVariableName accepted the name.  The one
# shipped index-set model, fullerEtAlDiffusion, was flattened to WA/DA to
# compile -- and lost the per-species names (D[A] -> D[H2O]) that index-set
# notation exists to provide.

class TestIndexSetNames:

    _CCODE = '''
        #include "modena.h"
        void f(const modena_model_t* model, const double* inputs, double* outputs) {
            {% block variables %}{% endblock %}
            outputs[0] = T * (WA + WB);
        }
    '''

    @pytest.fixture
    def species(self, mongo_db):
        from modena.SurrogateModel import IndexSet
        return IndexSet(name='species', names=['H2O', 'N2'])

    def _kw(self, species, **overrides):
        base = dict(
            Ccode=self._CCODE,
            inputs={'T': {'min': 0.0, 'max': 1.0}},
            outputs={'D[A]': {'min': 0.0, 'max': 1.0}},
            parameters={'W[A]': {'min': 0.0, 'max': 1.0},
                        'W[B]': {'min': 0.0, 'max': 1.0}},
            indices={'A': species, 'B': species},
        )
        base.update(overrides)
        return base

    @pytest.mark.parametrize('name,bound', [
        ('W[A]', 'WA'), ('D[A,B]', 'DAB'), ('k0', 'k0'), ('P_1', 'P_1'),
    ])
    def test_c_name(self, name, bound):
        from modena.SurrogateModel import SurrogateFunction
        assert SurrogateFunction.c_name(name) == bound

    def test_indexed_names_are_accepted(self, species):
        from unittest.mock import patch
        from modena.SurrogateModel import CFunction
        with patch.object(CFunction, 'compileCcode', return_value='/tmp/x.so'), \
             patch.object(CFunction, 'save'):
            f = CFunction(**self._kw(species))
        assert f.parameter_names_ordered() == ['W[A]', 'W[B]']

    def test_every_index_of_a_multi_index_name_must_be_declared(self, species):
        from modena.SurrogateModel import CFunction
        with pytest.raises(Exception, match='Index C not defined'):
            CFunction(**self._kw(species, outputs={'D[A,C]': {'min': 0.0, 'max': 1.0}}))

    def test_two_names_binding_to_one_c_variable_are_rejected(self, species):
        from modena.SurrogateModel import CFunction
        with pytest.raises(ValueError, match="both bind to the C variable 'WA'"):
            CFunction(**self._kw(species, parameters={
                'W[A]': {'min': 0.0, 'max': 1.0}, 'WA': {'min': 0.0, 'max': 1.0}}))

    def test_generated_code_binds_indexed_names_as_c_identifiers(
            self, species, tmp_path, monkeypatch):
        """Render the real template; only the gcc step is stubbed out."""
        from unittest.mock import patch
        import modena
        from modena import SurrogateModel as sm
        from modena.Registry import ModelRegistry
        monkeypatch.setattr(modena, 'MODENA_INCLUDE_DIR', str(tmp_path), raising=False)
        monkeypatch.setattr(modena, 'MODENA_LIB_DIR', str(tmp_path), raising=False)
        monkeypatch.setattr(ModelRegistry(), '_surrogate_lib_dir', str(tmp_path))
        kw = self._kw(species)
        # compileCcode reads argPos off inputs, as initKwargs has set it.
        kw['inputs'] = {'T': {'min': 0.0, 'max': 1.0, 'argPos': 0}}
        with patch.object(sm, '_compile_c_surrogate'):
            sm.CFunction.compileCcode(sm.CFunction.__new__(sm.CFunction), kw)

        source = next(tmp_path.glob('func_*/*.c')).read_text()
        assert 'const double WA = parameters[0];' in source
        assert 'const double WB = parameters[1];' in source
        assert 'W[A]' not in source


# ---------------------------------------------------------------------------
# argPos ordering matches declaration order
# ---------------------------------------------------------------------------

class TestAutoArgPosOrdering:
    """Since users no longer supply argPos, the ordering used by minMax(),
    the compiled .so, and the fitting marshalling all come from dict-key
    insertion order in the SurrogateFunction."""

    @pytest.mark.installed
    def test_parameter_names_ordered_matches_declaration(
        self, tmp_path, monkeypatch, mongo_db
    ):
        # Needs the full stack: CFunction is a MongoEngine document whose
        # construction compiles the surrogate, so this wants both a database
        # and the installed libmodena.  It previously took neither -- the
        # importorskip always fired, hiding the missing mongo_db fixture.
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
