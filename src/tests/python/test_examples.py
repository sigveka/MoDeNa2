"""
test_examples.py — static contract checks on every shipped model definition.

The named-parameter rework changed five things at once: outputs and parameters
lost ``argPos``, ``SurrogateModel.parameters`` became a dict, the Jinja2
template began synthesising ``const double <name> = parameters[<i>];`` for
every declared parameter, names had to become valid C identifiers, and the
config schema followed.  The reference example (``flowRate``) was updated;
four other shipped definitions were not, and each one surfaced only when
somebody ran into it:

  * ``idealGas``            hand-declared ``R``      -> gcc redefinition error
  * ``fullerEtAlDiffusion`` hand-declared 4 bindings -> gcc redefinition error
  * ``flowRate_idealGas``   hand-declared 2 bindings -> gcc redefinition error
  * ``fullerEtAlDiffusion`` named parameters ``W[A]`` -> not a C identifier
  * ``flowRate_idealGas``   declared ``param0`` while the code used ``P0``
  * ``idealGas``            ``parameters = [287.0]`` -> field is now a dict

Every one of those is detectable without MongoDB, without a compiler and
without CoolProp/LAMMPS/QE/Meep/NGSolve, by reading the config.toml and the
Ccode string out of the source.  That is what this module does, so the next
schema change fails here rather than in a user's terminal.
"""

import ast
import re
import tomllib
from pathlib import Path

import pytest

from modena.config_schema import ModelConfig

# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #

_REPO = Path(__file__).resolve().parents[3]

#: Installed copies and build trees are generated from the sources below;
#: checking them would double every failure and add stale ones.
_EXCLUDE = ('/models/', '/build/', '/.egg-info/', '/dist-packages/')


def _sources(pattern):
    return sorted(
        p for p in (_REPO / 'examples').rglob(pattern)
        if not any(x in str(p) for x in _EXCLUDE)
    ) + sorted(
        p for p in (_REPO / 'applications').rglob(pattern)
        if not any(x in str(p) for x in _EXCLUDE)
    )


def _model_configs():
    """config.toml files that describe a model (as opposed to a registry)."""
    out = []
    for p in _sources('config.toml'):
        try:
            raw = tomllib.loads(p.read_text())
        except tomllib.TOMLDecodeError:
            out.append((p, None))     # surfaced by test_config_toml_parses
            continue
        if 'surrogate' in raw or 'strategy' in raw:
            out.append((p, raw))
    return out


def _ccode_definitions():
    """``(path, ccode)`` for every literal ``CFunction(Ccode=...)`` in the tree.

    Read with ast rather than by importing: importing pulls in CoolProp,
    LAMMPS, Quantum ESPRESSO and a live MongoDB, none of which these checks
    need.
    """
    found = []
    for path in _sources('*.py'):
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and getattr(node.func, 'id', None) == 'CFunction'):
                continue
            for kw in node.keywords:
                if kw.arg == 'Ccode' and isinstance(kw.value, ast.Constant) \
                        and isinstance(kw.value.value, str):
                    found.append((path, kw.value.value))
    return found


_CONFIGS = _model_configs()
_CCODE   = _ccode_definitions()


def _rel(p):
    return str(p.relative_to(_REPO))


def _ids(pairs):
    return [_rel(p) for p, _ in pairs]


# --------------------------------------------------------------------------- #
# Sanity: discovery itself must not silently find nothing
# --------------------------------------------------------------------------- #

def test_discovery_finds_the_shipped_definitions():
    """A refactor that moves the examples must not turn this file into a no-op."""
    assert len(_CONFIGS) >= 10, f'only found {len(_CONFIGS)} model configs'
    assert len(_CCODE) >= 10, f'only found {len(_CCODE)} CFunction definitions'


# --------------------------------------------------------------------------- #
# config.toml
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize('path,raw', _CONFIGS, ids=_ids(_CONFIGS))
def test_config_toml_parses(path, raw):
    assert raw is not None, f'{_rel(path)} is not valid TOML'


@pytest.mark.parametrize('path,raw', _CONFIGS, ids=_ids(_CONFIGS))
def test_config_validates_against_the_schema(path, raw):
    """Catches the positional ``parameters = [...]`` form, among others."""
    if raw is None:
        pytest.skip('invalid TOML; reported by test_config_toml_parses')
    ModelConfig(**raw)


_C_IDENTIFIER = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


@pytest.mark.parametrize('path,raw', _CONFIGS, ids=_ids(_CONFIGS))
def test_declared_names_are_valid_c_identifiers(path, raw):
    """The Jinja2 template binds each name as ``const double <name> = ...``.

    ``W[A]`` is a perfectly good TOML key and a syntax error in C.
    """
    if raw is None:
        pytest.skip('invalid TOML; reported by test_config_toml_parses')
    surrogate = raw.get('surrogate') or {}
    bad = [
        f'{section}.{name}'
        for section in ('inputs', 'outputs', 'parameters')
        for name in (surrogate.get(section) or {})
        if not _C_IDENTIFIER.match(name)
    ]
    assert not bad, f'{_rel(path)}: not valid C identifiers: {bad}'


@pytest.mark.parametrize('path,raw', _CONFIGS, ids=_ids(_CONFIGS))
def test_parameter_values_match_declared_names(path, raw):
    """``[parameters]`` keys must name something declared under the surrogate."""
    if raw is None:
        pytest.skip('invalid TOML; reported by test_config_toml_parses')
    values  = raw.get('parameters') or {}
    if not isinstance(values, dict):
        pytest.skip('positional form; reported by the schema test')
    declared = set((raw.get('surrogate') or {}).get('parameters') or {})
    unknown  = set(values) - declared
    assert not unknown, (
        f'{_rel(path)}: [parameters] names nothing declared under '
        f'[surrogate.parameters]: {sorted(unknown)} (declared: {sorted(declared)})'
    )


# --------------------------------------------------------------------------- #
# Ccode
# --------------------------------------------------------------------------- #

def _strip_comments(code):
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.S)
    return '\n'.join(l for l in code.split('\n') if not l.strip().startswith('//'))


#: `const double NAME = parameters[0];` / `... = inputs[0];`
_HAND_BINDING = re.compile(
    r'\bconst\s+double\s+(\w+)\s*=\s*(parameters|inputs)\s*\[\s*\d+\s*\]')


@pytest.mark.parametrize('path,code', _CCODE, ids=_ids(_CCODE))
def test_ccode_does_not_hand_declare_bindings(path, code):
    """The variables block already emits a named binding for every declaration.

    Declaring one again is a C redefinition error, and it only shows up when
    the surrogate is compiled -- which happens lazily, so the model registers
    fine and then explodes the first time anything reads it.
    """
    hits = _HAND_BINDING.findall(_strip_comments(code))
    assert not hits, (
        f'{_rel(path)}: hand-declared binding(s) '
        f'{[f"{n} = {src}[...]" for n, src in hits]}; '
        f'the variables block already emits these by name'
    )


@pytest.mark.parametrize('path,code', _CCODE, ids=_ids(_CCODE))
def test_ccode_has_the_variables_block(path, code):
    """Without the placeholder no input or parameter is ever bound."""
    assert 'block variables' in code, (
        f'{_rel(path)}: Ccode is missing the '
        '{% block variables %}{% endblock %} placeholder'
    )


def _sibling_config(path):
    for cand in (path.parent / 'config.toml',):
        if cand.exists():
            try:
                return tomllib.loads(cand.read_text())
            except tomllib.TOMLDecodeError:
                return None
    return None


@pytest.mark.parametrize('path,code', _CCODE, ids=_ids(_CCODE))
def test_named_style_ccode_references_every_declared_parameter(path, code):
    """Catch a declared-name / used-name mismatch in named-binding style.

    Two styles are both legitimate.  A surrogate may index the raw array --
    ``outputs[0] = parameters[0] + parameters[1]*T`` -- or it may use the
    named bindings the variables block emits.  Only the second style can
    suffer a mismatch, and then it is fatal: ``flowRate_idealGas`` declared
    ``param0``/``param1`` while its code said ``P0``/``P1``, so the template
    bound two names nothing used and the code referenced two that did not
    exist.  gcc caught it; nothing before gcc did.

    So: if the code never indexes ``parameters[...]``, it must be using the
    named bindings, and every declared name has to appear.
    """
    raw = _sibling_config(path)
    if raw is None:
        pytest.skip('no sibling config.toml')
    declared = list(((raw.get('surrogate') or {}).get('parameters') or {}))
    if not declared:
        pytest.skip('no parameters declared in config.toml')

    body = _strip_comments(code)
    if re.search(r'\bparameters\s*\[', body):
        pytest.skip('indexed-array style; names are not required')

    missing = [n for n in declared
               if not re.search(rf'\b{re.escape(n)}\b', body)]
    assert not missing, (
        f'{_rel(path)}: parameter(s) {missing} are declared in config.toml but '
        f'the Ccode neither indexes parameters[...] nor references them by '
        f'name -- the declared and used names have diverged'
    )
