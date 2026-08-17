"""
@namespace  python.Integration
@brief      Generate ready-to-paste integration code for a specific model.

``docs/quick-start-{c,cpp,fortran,julia,matlab,r}.md`` already explain how to
call MoDeNa from each language, worked through with ``flowRate``.  What they
cannot do is answer *"how do I call **this** model"* — the caller still has to
substitute the model id and every input and output name by hand, in argPos
order, for every language.

Two things make that more than a convenience:

* **The APIs differ per language in non-obvious ways.**  R is
  ``m$set(pos, v)`` then ``m$call()`` then ``m$output(pos)``; C++ is
  ``m["D"] = v`` with positions cached at construction; Python takes a dict.
* **Substitute-model inputs must NOT be queried.**  When a model lists
  substitute models, the framework fills those input slots itself by calling
  the substitute first.  A C application that calls
  ``modena_model_inputs_argPos()`` for one of them still passes, but the
  slot is then double-counted and ``modena_model_argPos_check()`` — which
  calls ``exit(1)`` — fails at runtime.  The rule is invisible from the input
  list alone; it needs ``substituteModels``, which this module reads.

Everything here is derived from the model document, so a model whose inputs
change produces a correspondingly changed snippet instead of a hand-written
example that silently goes stale.

@copyright  2014-2026, MoDeNa Project. GNU Public License.
"""

from __future__ import annotations

import os

__all__ = ['LANGUAGES', 'snippet', 'model_facts']


# ------------------------------------------------------------------ #
# Facts about the model that every template needs                     #
# ------------------------------------------------------------------ #

def _substitute_supplied(model) -> dict:
    """Return ``{input_name: providing_model_id}`` for substitute-filled slots.

    A substitute model's outputs are written straight into the outer model's
    input vector, so any outer input that matches a substitute's output name
    is supplied automatically and must not be claimed by the application.
    """
    supplied = {}
    for sm in getattr(model, 'substituteModels', []) or []:
        for out_name in sm.outputs.keys():
            expanded = sm.expandIndices(out_name) if hasattr(sm, 'expandIndices') else out_name
            names = expanded if isinstance(expanded, (list, tuple)) else [expanded]
            for name in names:
                if name in model.inputs:
                    supplied[name] = sm._id
    return supplied


def model_facts(model) -> dict:
    """Extract everything the templates render from, in argPos order."""
    inputs = sorted(model.inputs.keys(), key=lambda k: model.inputs_argPos(k))
    outputs = sorted(model.outputs.keys(), key=lambda k: model.outputs_argPos(k))
    supplied = _substitute_supplied(model)

    # Placeholder values are the midpoint of each input's trained range, not
    # 0.0.  Zero is outside the trained domain of most models, so a snippet
    # using it returns 200 (out of bounds) on the very first call -- which
    # looks like a broken example rather than a deliberate placeholder.
    values = {}
    for name in inputs:
        entry = model.inputs[name]
        lo = entry.min if entry.min is not None else 0.0
        hi = entry.max if entry.max is not None else 1.0
        values[name] = (lo + hi) / 2.0

    return {
        'model_id':   model._id,
        'inputs':     [n for n in inputs if n not in supplied],
        'all_inputs': inputs,
        'supplied':   supplied,
        'outputs':    outputs,
        'values':     values,
        'lib_dir':    os.environ.get('MODENA_LIB_DIR', ''),
    }


def _ident(name: str) -> str:
    """Make a name usable as a local variable in the generated code."""
    return name.replace('[', '_').replace(']', '').replace(',', '_') \
               .replace('=', '_').replace('.', '_').replace('-', '_')


def _supplied_note(facts, comment: str) -> list:
    """Comment lines explaining any inputs the application must not claim."""
    if not facts['supplied']:
        return []
    lines = [f'{comment} NOTE: these inputs are filled by substitute models and']
    lines.append(f'{comment} must NOT be queried here — doing so makes')
    lines.append(f'{comment} argPos_check() fail at runtime:')
    for name, provider in facts['supplied'].items():
        lines.append(f'{comment}   {name} <- {provider}')
    return lines


# ------------------------------------------------------------------ #
# Templates                                                           #
# ------------------------------------------------------------------ #

def _c(f) -> str:
    pos = '\n'.join(
        f'    const size_t pos_{_ident(n)} = modena_model_inputs_argPos(model, "{n}");'
        for n in f['inputs'])
    opos = '\n'.join(
        f'    const size_t pos_{_ident(n)} = modena_model_outputs_argPos(model, "{n}");'
        for n in f['outputs'])
    sets = '\n'.join(
        f'        modena_inputs_set(inputs, pos_{_ident(n)}, {f["values"][n]:.10g});'
        f'   /* {n} */'
        for n in f['inputs'])
    gets = '\n'.join(
        f'        const double {_ident(n)} = modena_outputs_get(outputs, pos_{_ident(n)});'
        for n in f['outputs'])
    note = '\n'.join(_supplied_note(f, '   '))
    note = f'\n{note}\n' if note else ''
    return f'''#include <modena.h>
#include <stdio.h>

int main(void)
{{
    /* 1. Load the surrogate.  Returns NULL and sets an error code if the
     *    model is missing or untrained — the 201/202 protocol lets FireWorks
     *    initialise it and relaunch this binary. */
    modena_model_t *model = modena_model_new("{f['model_id']}");
    if (modena_error_occurred()) {{ return modena_error(); }}

    modena_inputs_t  *inputs  = modena_inputs_new(model);
    modena_outputs_t *outputs = modena_outputs_new(model);

    /* 2. Cache argument positions ONCE, before any loop. */
{pos}
{opos}
{note}
    /* 3. Assert every declared input was claimed.  Calls exit(1) on failure. */
    modena_model_argPos_check(model);

    /* 4. Time-step loop. */
    for (int step = 0; step < 1; ++step)
    {{
{sets}

        const int ret = modena_model_call(model, inputs, outputs);
        if (ret != 0)
        {{
            /* 100 = surrogate retrained, retry this step.
             * 200/201 = exit so FireWorks can relaunch. */
            modena_inputs_destroy(inputs);
            modena_outputs_destroy(outputs);
            modena_model_destroy(model);
            return ret;
        }}

{gets}
        printf("{f['outputs'][0] if f['outputs'] else 'output'} = %g\\n", {_ident(f['outputs'][0]) if f['outputs'] else '0.0'});
    }}

    modena_inputs_destroy(inputs);
    modena_outputs_destroy(outputs);
    modena_model_destroy(model);
    return 0;
}}
'''


def _cpp(f) -> str:
    # operator[] takes a NAME, not a position: the constructor already caches
    # every argPos, so named access is a hash lookup with no Python call --
    # which is what makes it safe after check() has released the GIL.
    pos = '\n'.join(f'        model.input_pos("{n}");   // claim {n}'
                    for n in f['inputs'])
    sets = '\n'.join(f'            model["{n}"] = {f["values"][n]:.10g};'
                     for n in f['inputs'])
    gets = '\n'.join(f'            const double {_ident(n)} = model.output("{n}");'
                     for n in f['outputs'])
    note = '\n'.join(_supplied_note(f, '        //'))
    note = f'\n{note}\n' if note else ''
    return f'''#include <modena/modena.hpp>
#include <iostream>

int main()
{{
    try
    {{
        // 1. Construct — owns the model, inputs and outputs handles (RAII).
        //    Input and output positions are cached here, so named access
        //    stays valid after check() releases the GIL.
        modena::Model model("{f['model_id']}");

        // 2. Claim every input so check() can verify none was forgotten.
{pos}
{note}
        model.check();   // verify every declared input was queried

        // 3. Time-step loop.
        for (int step = 0; step < 1; ++step)
        {{
{sets}

            model.call();

{gets}
            std::cout << "{f['outputs'][0] if f['outputs'] else 'output'} = "
                      << {_ident(f['outputs'][0]) if f['outputs'] else '0.0'} << '\\n';
        }}
    }}
    catch (const std::exception &e)
    {{
        std::cerr << "modena: " << e.what() << '\\n';
        return 1;
    }}
    return 0;
}}
'''


def _fnum(v: float) -> str:
    """Format a Fortran real literal that always carries a kind suffix legally.

    ``%.10g`` renders 300000.0 as ``300000``, and an *integer* literal cannot
    take a real kind suffix -- ``300000_c_double`` is a syntax error.
    Exponent form always produces a decimal point, so it is always valid.
    """
    return f'{v:.10e}_c_double'


def _fortran(f) -> str:
    decl = ', '.join(f'pos_{_ident(n)}' for n in f['inputs'] + f['outputs']) or 'dummy'
    pos = '\n'.join(f'    pos_{_ident(n)} = m%input_pos("{n}")' for n in f['inputs'])
    opos = '\n'.join(f'    pos_{_ident(n)} = m%output_pos("{n}")' for n in f['outputs'])
    sets = '\n'.join(f'        call m%set(pos_{_ident(n)}, {_fnum(f["values"][n])})   ! {n}'
                     for n in f['inputs'])
    gets = '\n'.join(f'        {_ident(n)} = m%get_output(pos_{_ident(n)})'
                     for n in f['outputs'])
    outdecl = ', '.join(_ident(n) for n in f['outputs']) or 'dummy_out'
    note = '\n'.join(_supplied_note(f, '    !'))
    note = f'\n{note}\n' if note else ''
    return f'''program {_ident(f['model_id'])[:24]}_example
    use fmodena_oop
    use iso_c_binding
    implicit none

    ! Positions are integer(c_size_t) and outputs real(c_double): the bound
    ! procedures take those exact kinds, so a plain `integer` will not compile.
    type(modena_model) :: m
    integer(c_size_t)  :: {decl}
    integer(c_int)     :: ret
    integer            :: step
    real(c_double)     :: {outdecl}

    ! 1. Initialise once.
    call m%init("{f['model_id']}")

    ! 2. Cache argument positions once, before the loop.
{pos}
{opos}
{note}
    ! 3. Assert every declared input was claimed.
    call m%check()

    ! 4. Time-step loop.
    do step = 1, 1
{sets}

        ret = m%call()
        if (ret /= 0) then
            ! 100 = retrained, retry step.  200/201 = exit for FireWorks.
            call exit(ret)
        end if

{gets}
        print *, "{f['outputs'][0] if f['outputs'] else 'output'} = ", {_ident(f['outputs'][0]) if f['outputs'] else '0.0_c_double'}
    end do

end program {_ident(f['model_id'])[:24]}_example
'''


def _python(f) -> str:
    args = '\n'.join(f"    '{n}': {f['values'][n]:.10g}," for n in f['inputs'])
    note = '\n'.join(_supplied_note(f, '#'))
    note = f'\n{note}\n' if note else ''
    first_out = f['outputs'][0] if f['outputs'] else 'output'
    return f'''import sys

import modena

# 1. Load the surrogate.  Raises if the model is missing or untrained.
model = modena.load("{f['model_id']}")
{note}
# 2. Evaluate.  Inputs are passed by name — no argPos bookkeeping.
inputs = {{
{args}
}}

# 3. Handle the out-of-bounds protocol.  callModel() propagates OutOfBounds
#    rather than exiting, so the caller decides what to do.  The exception
#    carries everything needed: .returnCode is the code the C layer produced
#    (200 = out of bounds) and .model is the surrogate that went out of range.
#
#    Whether to exit depends on who launched this script:
#
#      * Launched by FireWorks as a BackwardMappingScriptTask subprocess --
#        exit with the code.  The process exit status is the only channel back
#        to handleReturnCode(), which queues a retraining detour and relaunches
#        this script.  That is what makes the surrogate expand its domain.
#
#      * Run standalone -- do not exit.  Nothing is reading the status, and
#        the exception already carries more than the code does.  Log it, clamp
#        the input, or re-raise.
try:
    outputs = model(inputs)
except modena.OutOfBounds as exc:
    print(f"{{exc.model._id}}: inputs left the trained domain "
          f"(code {{exc.returnCode}}); run 'modena init {f['model_id']}' "
          f"to extend it", file=sys.stderr)
    sys.exit(exc.returnCode)
except modena.ParametersNotValid as exc:
    print(f"{{exc.model._id}}: no valid parameters (code {{exc.returnCode}}); "
          f"run 'modena init {f['model_id']}' first", file=sys.stderr)
    sys.exit(exc.returnCode)

print(outputs["{first_out}"])
'''


def _julia(f) -> str:
    pos = '\n'.join(f'pos_{_ident(n)} = input_pos(model, "{n}")' for n in f['inputs'])
    opos = '\n'.join(f'pos_{_ident(n)} = output_pos(model, "{n}")' for n in f['outputs'])
    sets = '\n'.join(f'    set!(model, pos_{_ident(n)}, {f["values"][n]:.10g})   # {n}' for n in f['inputs'])
    gets = '\n'.join(f'    {_ident(n)} = output(model, pos_{_ident(n)})' for n in f['outputs'])
    note = '\n'.join(_supplied_note(f, '#'))
    note = f'\n{note}\n' if note else ''
    return f'''using Modena

# 1. Construct — the GC finaliser frees the C handles automatically.
model = Model("{f['model_id']}")

# 2. Cache argument positions once, before the loop.
{pos}
{opos}
{note}
# 3. Verify every declared input was queried.
check(model)

# 4. Time-step loop.
for step in 1:1
{sets}

    # call! throws instead of returning a code.  Each exception maps to one
    # of the framework's return codes, and they need different responses:
    try
        call!(model)
    catch e
        e isa ParametersUpdated && continue      # 100: retrained, retry step
        e isa ExitAndRestart    && exit(e.code)  # 200: FireWorks relaunches us
        e isa ExitAndInitialise     && exit(e.code)  # 201: model needs init
        rethrow()                                # ModenaError or anything else
    end

{gets}
    println("{f['outputs'][0] if f['outputs'] else 'output'} = ", {_ident(f['outputs'][0]) if f['outputs'] else '0.0'})
end
'''


def _matlab(f) -> str:
    pos = '\n'.join(f"pos_{_ident(n)} = input_pos(model, '{n}');" for n in f['inputs'])
    opos = '\n'.join(f"pos_{_ident(n)} = output_pos(model, '{n}');" for n in f['outputs'])
    sets = '\n'.join(f'    set_input(model, pos_{_ident(n)}, {f["values"][n]:.10g});   % {n}' for n in f['inputs'])
    gets = '\n'.join(f'    {_ident(n)} = get_output(model, pos_{_ident(n)});' for n in f['outputs'])
    note = '\n'.join(_supplied_note(f, '%'))
    note = f'\n{note}\n' if note else ''
    return f'''addpath(getenv('MODENA_MATLAB_DIR'));

% 1. Construct.
model = Modena('{f['model_id']}');

% 2. Cache argument positions once, before the loop.
{pos}
{opos}
{note}
% 3. Verify every declared input was queried.
check(model);

% 4. Time-step loop.
for step = 1:1
{sets}

    ret = call(model);
    if ret ~= 0
        % 100 = retrained, retry.  200/201 = exit for FireWorks.
        exit(ret);
    end

{gets}
    fprintf('{f['outputs'][0] if f['outputs'] else 'output'} = %g\\n', {_ident(f['outputs'][0]) if f['outputs'] else '0.0'});
end
'''


def _r(f) -> str:
    pos = '\n'.join(f'pos_{_ident(n)} <- m$input_pos("{n}")' for n in f['inputs'])
    opos = '\n'.join(f'pos_{_ident(n)} <- m$output_pos("{n}")' for n in f['outputs'])
    sets = '\n'.join(f'    m$set(pos_{_ident(n)}, {f["values"][n]:.10g})   # {n}' for n in f['inputs'])
    gets = '\n'.join(f'    {_ident(n)} <- m$output(pos_{_ident(n)})' for n in f['outputs'])
    note = '\n'.join(_supplied_note(f, '#'))
    note = f'\n{note}\n' if note else ''
    return f'''library(modena)

# 1. Construct.  The exported class is `Modena`; instances are reference
#    objects, so methods are called with $.
m <- Modena$new("{f['model_id']}")

# 2. Cache argument positions once, before the loop.
{pos}
{opos}
{note}
# 3. Verify every declared input was queried.
m$check()

# 4. Time-step loop.  Note the set -> call -> output sequence: m$call() takes
#    no arguments and returns a status code, not the outputs.
for (step in 1:1) {{
{sets}

    ret <- m$call()
    if (ret != 0) {{
        # 100 = retrained, retry.  200/201 = exit for FireWorks.
        quit(status = ret)
    }}

{gets}
    cat("{f['outputs'][0] if f['outputs'] else 'output'} =", {_ident(f['outputs'][0]) if f['outputs'] else '0.0'}, "\\n")
}}
'''


# ------------------------------------------------------------------ #
# Build / run instructions                                            #
# ------------------------------------------------------------------ #

def _build_line(language: str, facts: dict) -> str:
    """Compile/run command for the generated file.

    The include flags are not decorative.  ``modena.h`` lives in
    ``<prefix>/include/modena/`` but is included as ``<modena.h>``, so that
    directory must be on the search path in its own right; ``modena.hpp`` is
    included as ``<modena/modena.hpp>``, so the parent must be too.  And
    ``modena.h`` pulls in ``global.h``, which includes ``Python.h`` — every
    consumer of the public header needs the Python include directory, which
    is why the in-tree tests all set ``Python3_INCLUDE_DIRS``.
    """
    import sysconfig

    prefix = os.environ.get('MODENA_PREFIX') or os.path.expanduser('~')
    lib = facts['lib_dir'] or f'{prefix}/lib/modena'
    inc = f'{prefix}/include'
    py_inc = sysconfig.get_paths()['include']
    cflags = f'-I{inc} -I{inc}/modena -I{py_inc}'
    ldflags = f'-L{lib} -Wl,-rpath,{lib}'
    return {
        'c':       f'gcc -o example example.c {cflags} {ldflags} -lmodena',
        'cpp':     f'g++ -std=c++17 -o example example.cpp {cflags} {ldflags} -lmodena',
        'fortran': (f'gfortran -o example example.f90 -I{inc}/modena {ldflags} '
                    f'-lfmodena_oop -lfmodena -lmodena'),
        'python':  'python3 example.py',
        'julia':   'julia example.jl',
        'matlab':  'octave --path "$MODENA_MATLAB_DIR" example.m',
        'r':       'Rscript example.R',
    }[language]


#: language key -> (display label, file extension, renderer)
LANGUAGES = {
    'c':       ('C',             'c',    _c),
    'cpp':     ('C++',           'cpp',  _cpp),
    'fortran': ('Fortran',       'f90',  _fortran),
    'python':  ('Python',        'py',   _python),
    'julia':   ('Julia',         'jl',   _julia),
    'matlab':  ('MATLAB/Octave', 'm',    _matlab),
    'r':       ('R',             'R',    _r),
}


def snippet(model, language: str) -> dict:
    """Return ``{'code', 'build', 'label', 'extension', 'supplied'}``.

    Raises:
        KeyError: unknown language.
    """
    if language not in LANGUAGES:
        raise KeyError(
            f'unknown language {language!r}; expected one of '
            f'{", ".join(sorted(LANGUAGES))}'
        )
    label, ext, render = LANGUAGES[language]
    facts = model_facts(model)
    return {
        'code':      render(facts),
        'build':     _build_line(language, facts),
        'label':     label,
        'extension': ext,
        'supplied':  facts['supplied'],
    }
