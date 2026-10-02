"""
The portal's pages and callbacks, driven the way a browser drives them.

Nothing in this directory used to render a page or run a callback -- the
tests covered the security helpers and two pure functions.  That is how the
Evaluate page went unreachable: its template /model/<id>/evaluate was
captured by the detail page's /model/<model_id>, so every "Evaluate Model"
button led to "Model 'flowRate/evaluate' not found", and no test noticed.

These tests talk to the app over Dash's own protocol (/_dash-dependencies and
/_dash-update-component, through Flask's test client) with the data layer
replaced by an in-memory model, so they need no MongoDB and no libmodena.
"""
import json
import sys
from types import SimpleNamespace

import dash
import pytest

from modena_portal.app import app

MODEL_ID = 'twoParam[A=X]'      # brackets and '=' -- what real ids look like


# ---------------------------------------------------------------------------
# An in-memory model with the attributes the pages read
# ---------------------------------------------------------------------------

def _mm(lo, hi, arg_pos=None):
    return SimpleNamespace(min=lo, max=hi, argPos=arg_pos)


class _FakeModel:
    def __init__(self, raise_on_call=None):
        self._id = MODEL_ID
        self.inputs = {'T': _mm(250.0, 350.0, 0), 'p': _mm(1e5, 2e6, 1)}
        self.outputs = {'rho': _mm(0.0, 200.0)}
        self.parameters = {'a': 1.5, 'b': 0.25}
        self.substituteModels = []
        self.documentation = 'A fake model.'
        self.fitData = {'T': [300.0], 'p': [1e6], 'rho': [10.0]}
        self.surrogateFunction = SimpleNamespace(
            name='twoParam', Ccode='/* C */', libraryName=__file__,   # an existing file
            parameters={'a': _mm(0.0, 10.0), 'b': _mm(0.0, 10.0)})
        self._raise = raise_on_call
        self.calls = []

    def callModel(self, inputs):
        self.calls.append(dict(inputs))
        if self._raise is not None:
            raise self._raise
        return {'rho': inputs['p'] / (287.0 * inputs['T'])}


@pytest.fixture
def model(monkeypatch):
    """Patch the data layer of every page and callback module to one model."""
    fake = _FakeModel()
    _install(monkeypatch, fake)
    return fake


def _install(monkeypatch, fake):
    for page in dash.page_registry.values():
        mod = sys.modules[page['module']]
        for name, value in (('get_model', lambda _id: fake),
                            ('list_models', lambda: [fake]),
                            ('list_model_sample_counts', lambda: {MODEL_ID: 1}),
                            ('_mongo_status', lambda uri: (True, 'Connected'))):
            if hasattr(mod, name):
                monkeypatch.setattr(mod, name, value)
    monkeypatch.setattr('modena_portal.callbacks.evaluator_callbacks.get_model',
                        lambda _id: fake)
    monkeypatch.setattr('modena_portal.data.launchpad_queries.list_workflows', lambda: [])


# ---------------------------------------------------------------------------
# Talking to the app
# ---------------------------------------------------------------------------

_CLIENT = app.server.test_client()            # loopback client: no credentials needed
_DEPS = _CLIENT.get('/_dash-dependencies').get_json()


def _dep(output_fragment):
    return next(d for d in _DEPS if output_fragment in d['output'])


def _outputs(dep):
    out = dep['output']
    if not out.startswith('..'):
        ident, _, prop = out.rpartition('.')
        return {'id': ident, 'property': prop}
    res = []
    for part in out[2:-2].split('...'):
        ident, _, prop = part.rpartition('.')
        res.append({'id': ident, 'property': prop})
    return res


def _post(dep, inputs, state=(), changed=None):
    body = {'output': dep['output'], 'outputs': _outputs(dep),
            'inputs': list(inputs), 'state': list(state),
            'changedPropIds': changed or [f"{inputs[0]['id']}.{inputs[0]['property']}"]}
    r = _CLIENT.post('/_dash-update-component', json=body)
    assert r.status_code == 200, r.get_data(as_text=True)[:500]
    return r.get_json()['response']


def _route(path):
    """(page title, rendered content) for a URL path, via the pages router."""
    resp = _post(_dep('_pages_content'), [
        {'id': '_pages_location', 'property': 'pathname', 'value': path},
        {'id': '_pages_location', 'property': 'search', 'value': ''},
    ])
    return resp['_pages_store']['data'].get('title'), resp['_pages_content']['children']


def _texts(tree):
    """Every string in a rendered component tree."""
    if isinstance(tree, str):
        return [tree]
    if isinstance(tree, list):
        return [t for x in tree for t in _texts(x)]
    if isinstance(tree, dict):
        return [t for v in tree.values() for t in _texts(v)]
    return []


def _find(tree, pred):
    """Every component in a tree for which pred(component) holds."""
    out = []
    if isinstance(tree, dict):
        if 'type' in tree and pred(tree):
            out.append(tree)
        for v in tree.values():
            out += _find(v, pred)
    elif isinstance(tree, list):
        for x in tree:
            out += _find(x, pred)
    return out


def _alerts(tree, colour):
    return _find(tree, lambda c: c.get('type') == 'Alert'
                 and c.get('props', {}).get('color') == colour)


# ---------------------------------------------------------------------------
# Access policy on the app object itself -- the one gunicorn serves
# ---------------------------------------------------------------------------

def test_the_app_object_enforces_the_access_policy():
    """`gunicorn modena_portal.app:server` must not bypass security.install().

    It used to: only `modena-portal` installed the policy, so the documented
    production server answered everyone, credentials set or not.  With no
    credentials configured (as here) only this machine is served.
    """
    remote = _CLIENT.get('/', environ_base={'REMOTE_ADDR': '10.0.0.5'})
    local = _CLIENT.get('/', environ_base={'REMOTE_ADDR': '127.0.0.1'})
    assert (remote.status_code, local.status_code) == (403, 200)


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

_TEMPLATED = [p for p in dash.page_registry.values() if p.get('path_template')]


@pytest.mark.parametrize('page', _TEMPLATED, ids=[p['module'] for p in _TEMPLATED])
def test_every_page_template_routes_to_its_own_page(page, model):
    """A filled-in template must reach its own page, not one registered earlier.

    Dash tries templates in registration order, so a broad template such as
    /model/<model_id> silently swallows a narrower one registered after it.
    """
    path = page['path_template'].replace('<model_id>', 'someModel')
    title, _ = _route(path)
    assert title == page['title'], f'{path} rendered {title!r}, not {page["title"]!r}'


def test_evaluate_button_reaches_the_evaluator(model):
    from urllib.parse import quote
    _, content = _route(f"/model/{quote(MODEL_ID, safe='')}")
    links = [c['props']['href'] for c in _find(content, lambda c: 'href' in c.get('props', {}))
             if 'evaluate' in c['props']['href']]
    assert links, 'the detail page has no link to the evaluator'
    title, page = _route(links[0])
    assert title == 'MoDeNa - Evaluate'
    assert not _alerts(page, 'danger'), _texts(_alerts(page, 'danger'))


@pytest.mark.parametrize('path', ['/', '/library', '/runs', f'/model/{MODEL_ID}',
                                  f'/evaluate/{MODEL_ID}'])
def test_every_page_renders_without_an_error(path, model):
    _, content = _route(path)
    assert not _alerts(content, 'danger'), _texts(_alerts(content, 'danger'))


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

def _evaluate(values):
    dep = _dep('eval-result.children')
    ids = [{'index': n, 'type': 'eval-input'} for n in values]
    resp = _post(dep, [{'id': 'eval-button', 'property': 'n_clicks', 'value': 1}], state=[
        [{'id': i, 'property': 'value', 'value': v} for i, v in zip(ids, values.values())],
        [{'id': i, 'property': 'id', 'value': i} for i in ids],
        {'id': 'eval-model-id', 'property': 'data', 'value': MODEL_ID},
    ])
    return resp['eval-result']['children']


def test_evaluation_shows_the_outputs(model):
    shown = ' '.join(_texts(_evaluate({'T': 300.0, 'p': 1e6})))
    assert 'rho' in shown and model.calls == [{'T': 300.0, 'p': 1e6}]


def test_a_blank_input_is_refused_not_evaluated_as_zero(model):
    result = _evaluate({'T': None, 'p': 1e6})
    assert model.calls == [], 'evaluated although an input was blank'
    assert 'Enter a value for: T' in ' '.join(_texts(result))


def test_out_of_bounds_names_the_input_and_its_range(monkeypatch):
    from modena.Strategy import OutOfBounds
    fake = _FakeModel()
    fake._raise = OutOfBounds('Surrogate model is used out-of-bounds', fake, 200)
    _install(monkeypatch, fake)
    shown = ' '.join(_texts(_evaluate({'T': 500.0, 'p': 1e6})))
    assert 'Outside the range this surrogate was trained on' in shown
    assert 'T = 500' in shown and '250' in shown and '350' in shown
    assert 'p =' not in shown, 'an in-range input was reported as outside'
    assert 'BackwardMappingModel' not in shown and '(' not in shown.split('.')[0]
