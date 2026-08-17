"""
Tests for modena.Integration (per-model integration snippets)
--------------------------------------------------------------
A generated snippet is worse than no snippet if it is wrong, because it looks
authoritative.  These tests therefore assert on the things that actually broke
while the templates were being written -- each one below is a bug that real
compilation or execution caught:

  - C++ ``operator[]`` takes a NAME, not a position
  - Fortran positions are ``integer(c_size_t)``, and ``300000_c_double`` is a
    syntax error because an integer literal cannot carry a real kind suffix
  - MATLAB's methods are ``set_input``/``get_output``; ``set`` is an Octave
    builtin and fails with a graphics-handle error
  - placeholder values must be inside the trained domain, or every snippet
    returns 200 (out of bounds) on its first call
  - substitute-supplied inputs must not be claimed, or argPos_check exits(1)

The compile tests live in tests/interface-tests/, which already has the
toolchain wiring; these are the pure-Python contracts.

No MongoDB and no compiled libmodena.
"""

import re

import pytest

from types import SimpleNamespace


def _model(inputs, outputs, model_id='demo', substitutes=()):
    """A SurrogateModel-shaped stub; inputs is {name: (min, max)}."""
    names = list(inputs)
    m = SimpleNamespace(
        _id=model_id,
        inputs={n: SimpleNamespace(min=lo, max=hi) for n, (lo, hi) in inputs.items()},
        outputs={n: SimpleNamespace(min=0.0, max=1.0) for n in outputs},
        substituteModels=list(substitutes),
    )
    m.inputs_argPos = lambda n: names.index(n)
    m.outputs_argPos = lambda n: list(outputs).index(n)
    return m


def _substitute(model_id, output_names):
    sm = SimpleNamespace(
        _id=model_id,
        outputs={n: SimpleNamespace(min=0.0, max=1.0) for n in output_names},
    )
    sm.expandIndices = lambda n: n
    return sm


_DEMO = {'D': (0.01, 0.02), 'p0': (2.8e5, 3.2e5)}


@pytest.fixture
def I():
    from modena import Integration
    return Integration


ALL_LANGUAGES = ['c', 'cpp', 'fortran', 'python', 'julia', 'matlab', 'r']


# ---------------------------------------------------------------------------
# Facts extraction
# ---------------------------------------------------------------------------

class TestFacts:

    def test_inputs_are_argpos_ordered(self, I):
        m = _model({'b': (0, 1), 'a': (0, 1)}, ['y'])
        assert I.model_facts(m)['inputs'] == ['b', 'a']

    def test_placeholder_values_are_inside_the_trained_domain(self, I):
        """0.0 is outside most trained ranges: a snippet using it returns 200."""
        facts = I.model_facts(_model(_DEMO, ['y']))
        for name, (lo, hi) in _DEMO.items():
            assert lo <= facts['values'][name] <= hi

    def test_substitute_supplied_inputs_are_identified(self, I):
        m = _model({'D': (0, 1), 'rho0': (0, 1)}, ['y'],
                   substitutes=[_substitute('idealGas', ['rho0'])])
        facts = I.model_facts(m)
        assert facts['supplied'] == {'rho0': 'idealGas'}
        assert facts['inputs'] == ['D']         # rho0 must not be claimed
        assert facts['all_inputs'] == ['D', 'rho0']


# ---------------------------------------------------------------------------
# Every language
# ---------------------------------------------------------------------------

class TestAllLanguages:

    @pytest.mark.parametrize('lang', ALL_LANGUAGES)
    def test_snippet_names_the_model_and_its_variables(self, I, lang):
        s = I.snippet(_model(_DEMO, ['mdot'], model_id='myModel'), lang)
        assert 'myModel' in s['code']
        for name in list(_DEMO) + ['mdot']:
            assert name in s['code'], f'{lang}: {name} missing'

    @pytest.mark.parametrize('lang', ALL_LANGUAGES)
    def test_substitute_inputs_are_omitted_and_explained(self, I, lang):
        """Claiming a substitute-supplied input makes argPos_check exit(1)."""
        m = _model({'D': (0.01, 0.02), 'rho0': (1.0, 5.0)}, ['mdot'],
                   substitutes=[_substitute('idealGas', ['rho0'])])
        code = I.snippet(m, lang)['code']
        # The provider is named in a comment...
        assert 'idealGas' in code
        # ...and rho0 is never set or queried as an application input.
        for forbidden in ('input_pos("rho0")', "input_pos('rho0')",
                          'inputs_argPos(model, "rho0")', 'pos_rho0'):
            assert forbidden not in code, f'{lang}: claimed rho0 via {forbidden}'

    @pytest.mark.parametrize('lang', ALL_LANGUAGES)
    def test_has_a_build_or_run_command(self, I, lang):
        assert I.snippet(_model(_DEMO, ['y']), lang)['build'].strip()

    def test_unknown_language_is_rejected(self, I):
        with pytest.raises(KeyError, match='unknown language'):
            I.snippet(_model(_DEMO, ['y']), 'cobol')

    @pytest.mark.parametrize('lang', ALL_LANGUAGES)
    def test_bracketed_model_ids_survive(self, I, lang):
        """Index-set model ids carry brackets and '='."""
        s = I.snippet(_model(_DEMO, ['y'], model_id='eps[material=Cu]'), lang)
        assert 'eps[material=Cu]' in s['code']


# ---------------------------------------------------------------------------
# Language-specific contracts -- each is a bug compilation actually caught
# ---------------------------------------------------------------------------

class TestLanguageContracts:

    def test_cpp_indexes_by_name_not_position(self, I):
        """model[pos] does not compile: operator[] takes const char*."""
        code = I.snippet(_model(_DEMO, ['y']), 'cpp')['code']
        assert 'model["D"] =' in code
        assert 'model[pos_D]' not in code

    def test_fortran_positions_are_c_size_t(self, I):
        code = I.snippet(_model(_DEMO, ['y']), 'fortran')['code']
        assert 'integer(c_size_t)' in code
        assert 'use iso_c_binding' in code

    def test_fortran_real_literals_carry_a_decimal_point(self, I):
        """`300000_c_double` is a syntax error -- an integer literal cannot
        take a real kind suffix."""
        code = I.snippet(_model({'p0': (3e5, 3e5)}, ['y']), 'fortran')['code']
        for literal in re.findall(r'(\S+)_c_double', code):
            assert '.' in literal, f'{literal}_c_double has no decimal point'

    def test_matlab_uses_set_input_not_set(self, I):
        """`set` is an Octave builtin; the wrapper method is set_input."""
        code = I.snippet(_model(_DEMO, ['y']), 'matlab')['code']
        assert 'set_input(model,' in code
        assert 'get_output(model,' in code
        assert not re.search(r'^\s+set\(model,', code, re.M)

    def test_python_dict_is_syntactically_valid(self, I):
        """The literal is built by string join -- a stray comma is easy."""
        code = I.snippet(_model(_DEMO, ['y']), 'python')['code']
        compile(code, 'example.py', 'exec')

    def test_r_uses_the_reference_class_and_set_then_call(self, I):
        """The exported class is Modena; call() takes no arguments."""
        code = I.snippet(_model(_DEMO, ['y']), 'r')['code']
        assert 'Modena$new(' in code
        assert 'm$call()' in code

    def test_c_checks_argpos_before_the_loop(self, I):
        code = I.snippet(_model(_DEMO, ['y']), 'c')['code']
        assert code.index('modena_model_argPos_check') < code.index('for (int step')

    def test_build_lines_carry_every_include_path(self, I):
        """modena.h is included as <modena.h> but lives in include/modena/,
        and it pulls in Python.h."""
        for lang in ('c', 'cpp'):
            build = I.snippet(_model(_DEMO, ['y']), lang)['build']
            assert '/include ' in build or '/include/' in build
            assert 'python' in build.lower()
            assert '-lmodena' in build


# ---------------------------------------------------------------------------
# Every snippet must handle the return-code protocol
# ---------------------------------------------------------------------------
# The out-of-bounds / retrain protocol is the framework's headline feature: a
# call can return 100 (retrained, retry), 200/201 (exit so FireWorks
# relaunches) or raise.  A snippet that ignores it silently produces wrong
# numbers, or drops a retraining signal on the floor.  The Python and Julia
# templates originally did exactly that -- they only *described* error
# handling in a comment.

#: language -> substrings that prove the snippet reacts to a failed call.
_ERROR_HANDLING = {
    'c':       ['if (ret != 0)'],
    'cpp':     ['catch', 'std::exception'],
    'fortran': ['if (ret /= 0)', 'call exit(ret)'],
    'python':  ['try:', 'except modena.OutOfBounds', 'sys.exit(exc.returnCode)'],
    'julia':   ['catch e', 'ParametersUpdated', 'ExitAndRestart', 'rethrow()'],
    'matlab':  ['if ret ~= 0', 'exit(ret)'],
    'r':       ['if (ret != 0)', 'quit(status = ret)'],
}


class TestErrorHandling:

    @pytest.mark.parametrize('lang', ALL_LANGUAGES)
    def test_snippet_reacts_to_a_failed_call(self, I, lang):
        code = I.snippet(_model(_DEMO, ['y']), lang)['code']
        for expected in _ERROR_HANDLING[lang]:
            assert expected in code, (
                f'{lang} snippet does not handle the return-code protocol: '
                f'{expected!r} missing'
            )

    def test_python_handles_both_exception_types(self, I):
        """callModel propagates OutOfBounds rather than exiting, so a
        standalone caller must react; ParametersNotValid means untrained."""
        code = I.snippet(_model(_DEMO, ['y']), 'python')['code']
        assert 'except modena.OutOfBounds' in code
        assert 'except modena.ParametersNotValid' in code
        compile(code, 'example.py', 'exec')

    def test_python_takes_the_code_from_the_exception(self, I):
        """OutOfBounds.returnCode carries what the C layer returned, so the
        snippet must not hard-code 200 -- and must say that exiting is only
        right when FireWorks is reading the exit status."""
        code = I.snippet(_model(_DEMO, ['y']), 'python')['code']
        assert 'sys.exit(exc.returnCode)' in code
        assert 'sys.exit(200)' not in code
        # No `or 202` fallback: both exceptions carry a real code now, and a
        # fallback that always fires reads as defensive while being the only
        # branch.
        assert 'or 202' not in code
        assert 'sys.exit(202)' not in code
        assert 'exc.model._id' in code, 'exception identifies the model'
        assert 'BackwardMappingScriptTask' in code, (
            'snippet must explain when exiting is the right response'
        )

    def test_julia_maps_each_exception_to_its_return_code(self, I):
        """call! throws typed exceptions instead of returning a code, and the
        three need different responses -- retry, exit, exit."""
        code = I.snippet(_model(_DEMO, ['y']), 'julia')['code']
        assert 'ParametersUpdated' in code and 'continue' in code
        assert 'ExitAndRestart' in code and 'exit(e.code)' in code
        assert 'ExitNoRestart' in code
        assert 'rethrow()' in code
