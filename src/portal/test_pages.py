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
        # Stored output-first, as real fitData often is.
        self.fitData = {'rho': [10.0, 12.0, 9.0], 'T': [300.0, 260.0, 340.0],
                        'p': [1e6, 0.010000003533967445, 2e6]}
        self.n_initial = 2
        self.last_fitted = None
        self.n_samples_fitted = 3
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


def _install(monkeypatch, fake, workflows=(), fireworks=()):
    for page in dash.page_registry.values():
        mod = sys.modules[page['module']]
        for name, value in (('get_model', lambda _id: fake),
                            ('list_models', lambda: [fake]),
                            ('list_model_sample_counts', lambda: {MODEL_ID: 3}),
                            ('get_sample_count', lambda _id: 3),
                            ('_mongo_status', lambda uri: (True, 'Connected'))):
            if hasattr(mod, name):
                monkeypatch.setattr(mod, name, value)
    for mod in ('evaluator_callbacks', 'detail_callbacks', 'diagnostics_callbacks'):
        monkeypatch.setattr(f'modena_portal.callbacks.{mod}.get_model', lambda _id: fake)
    monkeypatch.setattr('modena_portal.callbacks.detail_callbacks.get_fitdata',
                        lambda _id: fake)
    monkeypatch.setattr('modena_portal.callbacks.detail_callbacks.initial_design_size',
                        lambda _m: fake.n_initial)
    monkeypatch.setattr('modena_portal.data.launchpad_queries.list_workflows',
                        lambda: list(workflows))
    monkeypatch.setattr('modena_portal.data.launchpad_queries.list_fireworks',
                        lambda wf_id: list(fireworks))


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


def _page(name):
    """A page module, as Dash registered it.

    Never `import modena_portal.pages.<name>` in a test: executing a page
    module under a second name calls dash.register_page() again, and the
    duplicate -- registered with no layout yet -- answers later requests with
    an empty page.
    """
    return sys.modules[next(p['module'] for p in dash.page_registry.values()
                            if p['module'].rsplit('.', 1)[-1] == name)]


def _tree(component):
    """A component as the JSON tree the browser receives."""
    from plotly.utils import PlotlyJSONEncoder
    return json.loads(json.dumps(component, cls=PlotlyJSONEncoder))


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
    assert content, f'{path} rendered an empty page'
    assert not _alerts(content, 'danger'), _texts(_alerts(content, 'danger'))


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

def _evaluate(values, lib_ok=True):
    """Change the inputs the way the page does -- there is no button."""
    dep = _dep('eval-result.children')
    ids = [{'index': n, 'type': 'eval-input'} for n in values]
    inputs = [[{'id': i, 'property': 'value', 'value': v}
               for i, v in zip(ids, values.values())]]
    body = {'output': dep['output'], 'outputs': _outputs(dep), 'inputs': inputs,
            'state': [[{'id': i, 'property': 'id', 'value': i} for i in ids],
                      {'id': 'eval-model-id', 'property': 'data', 'value': MODEL_ID},
                      {'id': 'eval-lib-ok', 'property': 'data', 'value': lib_ok}],
            'changedPropIds': [json.dumps(ids[0], sort_keys=True, separators=(',', ':'))
                               + '.value']}
    return _updated(_CLIENT.post('/_dash-update-component', json=body),
                    'eval-result', 'children')


def _updated(r, component, prop):
    """The new value of component.prop, or None when the callback left it
    alone (no_update leaves the output out of the response)."""
    assert r.status_code in (200, 204), r.get_data(as_text=True)[:500]
    if r.status_code == 204:
        return None
    return r.get_json().get('response', {}).get(component, {}).get(prop)


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


def test_nothing_is_evaluated_without_a_compiled_library(model):
    assert _evaluate({'T': 300.0, 'p': 1e6}, lib_ok=False) is None
    assert model.calls == []


# ---------------------------------------------------------------------------
# Evaluator page: one box per input, live results, readable start values
# ---------------------------------------------------------------------------

def _props(tree, type_):
    return [c['props'] for c in _find(tree, lambda c: c.get('type') == type_)]


def test_the_evaluator_has_one_number_box_per_input_and_no_button(model):
    """Dash 4's slider adds its own input box; next to ours it showed a
    truncated copy of the same number.  Results follow the inputs, so the
    Evaluate button is gone."""
    _, page = _route(f'/evaluate/{MODEL_ID}')
    sliders = _props(page, 'Slider')
    assert len(sliders) == 2 and all(s['allow_direct_input'] is False for s in sliders)
    boxes = [p for p in _props(page, 'Input')
             if isinstance(p.get('id'), dict) and p['id'].get('type') == 'eval-input']
    assert len(boxes) == 2
    assert not _find(page, lambda c: c.get('props', {}).get('id') == 'eval-button')


def test_the_evaluator_labels_the_trained_range_and_starts_at_short_values(model):
    from modena.Integration import placeholder_value
    _, page = _route(f'/evaluate/{MODEL_ID}')
    t = next(s for s in _props(page, 'Slider') if s['id']['index'] == 'T')
    assert set(t['marks'].values()) == {'250', '350'}
    assert t['value'] == placeholder_value(250.0, 350.0) == 300.0


def test_a_fixed_input_is_shown_as_fixed_not_widened(monkeypatch):
    fake = _FakeModel()
    fake.inputs['T'] = _mm(300.0, 300.0, 0)
    _install(monkeypatch, fake)
    _, page = _route(f'/evaluate/{MODEL_ID}')
    t = next(s for s in _props(page, 'Slider') if s['id']['index'] == 'T')
    assert t['disabled'] is True
    assert 'fixed at 300' in _texts(page)


def test_dragging_rounds_the_box_but_a_typed_value_is_kept():
    from modena_portal.callbacks.evaluator_callbacks import sync_slider_to_input
    assert sync_slider_to_input([0.4165239571818414], [None]) == [0.416524]
    assert sync_slider_to_input([1.2345678], [1.2345678]) == [1.2345678]


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('path', [f'/model/{MODEL_ID}', f'/evaluate/{MODEL_ID}'])
def test_one_link_is_active_and_model_pages_have_a_breadcrumb(path, model):
    _, page = _route(path)
    active = [p for p in _props(page, 'NavLink') if p.get('active')]
    assert [p['children'] for p in active] == ['Library']
    crumbs = _props(page, 'Breadcrumb')
    assert crumbs and crumbs[0]['items'][1]['label'] == MODEL_ID
    assert ('Evaluate' in [i['label'] for i in crumbs[0]['items']]) == path.startswith('/evaluate')
    assert _props(page, 'NavbarToggler'), 'no menu button for narrow screens'


# ---------------------------------------------------------------------------
# Model page: overview, documentation, C code
# ---------------------------------------------------------------------------

def _tables(tree):
    return _props(tree, 'DataTable')


def test_a_range_that_prints_as_one_value_counts_as_fixed():
    from modena_portal.data.helpers import is_fixed
    assert is_fixed(0.01, 0.01000001)        # flowRate's D, as stored
    assert is_fixed(300.0, 300.0)
    assert not is_fixed(0.01, 0.0101) and not is_fixed(None, 1.0)


def test_the_selected_workflow_keeps_its_radio_button_across_refreshes():
    row_index = _page('runs').row_index
    rows = [{'id': 9}, {'id': 7}]            # a new workflow arrived on top
    assert row_index(rows, 7) == [1]
    assert row_index(rows, 3) == [] and row_index(rows, None) == []


def test_the_overview_flags_a_fixed_input_and_moves_argpos_aside(monkeypatch):
    fake = _FakeModel()
    fake.inputs['T'] = _mm(300.0, 300.0001, 0)
    _install(monkeypatch, fake)
    _, page = _route(f'/model/{MODEL_ID}')
    bounds = next(t for t in _tables(page) if any(c['id'] == 'Note' for c in t['columns']))
    assert {r['Variable']: r['Note'] for r in bounds['data']}['T'] == 'fixed at 300'
    params = next(t for t in _tables(page) if any(c['id'] == 'Value' for c in t['columns']))
    assert 'ArgPos' not in [c['id'] for c in params['columns']]
    assert 'Argument positions (for C and Fortran callers)' in _texts(page)


def test_units_show_when_declared_and_undeclared_is_said_once(monkeypatch):
    fake = _FakeModel()
    _install(monkeypatch, fake)
    _, page = _route(f'/model/{MODEL_ID}')
    assert any('No units declared' in t for t in _texts(page))

    fake.inputs['T'] = SimpleNamespace(min=250.0, max=350.0, argPos=0, unit='K',
                                       quantity='ThermodynamicTemperature')
    _, page = _route(f'/model/{MODEL_ID}')
    bounds = next(t for t in _tables(page) if any(c['id'] == 'Unit' for c in t['columns']))
    units = {r['Variable']: r['Unit'] for r in bounds['data']}
    assert units == {'T': 'K (ThermodynamicTemperature)', 'p': '—', 'rho': '—'}
    assert not any('No units declared' in t for t in _texts(page))


def test_missing_documentation_says_how_to_add_it(monkeypatch):
    fake = _FakeModel()
    fake.documentation = ''
    _install(monkeypatch, fake)
    _, page = _route(f'/model/{MODEL_ID}')
    shown = ' '.join(_texts(page))
    assert 'documentation=' in shown and 'initModels' not in shown


def test_the_c_code_tab_shows_the_compiled_source(tmp_path, monkeypatch):
    func = tmp_path / 'func_abc'
    func.mkdir()
    (func / 'libabc.so').write_bytes(b'')
    (func / 'abc.c').write_text('const double T = inputs[T_argPos];\n')
    fake = _FakeModel()
    fake.surrogateFunction.libraryName = str(func / 'libabc.so')
    fake.surrogateFunction.Ccode = '{% block variables %}{% endblock %}'
    _install(monkeypatch, fake)
    _, page = _route(f'/model/{MODEL_ID}')
    clips = [p['content'] for p in _props(page, 'Clipboard')]
    assert 'const double T = inputs[T_argPos];\n' in clips
    assert 'Template as declared in the model' in _texts(page)


def test_without_its_compiled_source_the_c_code_tab_says_so(model):
    _, page = _route(f'/model/{MODEL_ID}')
    assert any('compiled source is not on this machine' in t for t in _texts(page))


# ---------------------------------------------------------------------------
# Fit Data
# ---------------------------------------------------------------------------

def _load_tab(content_id, tab):
    resp = _post(_dep(f'{content_id}.children'),
                 [{'id': 'detail-tabs', 'property': 'active_tab', 'value': tab}],
                 state=[{'id': 'detail-model-id', 'property': 'data', 'value': MODEL_ID}])
    return resp[content_id]['children']


def test_fit_data_plots_the_first_input_against_the_output_by_origin(model):
    content = _load_tab('fitdata-content', 'tab-fitdata')
    x, y = (p['value'] for p in _props(content, 'Dropdown'))
    assert (x, y) == ('T', 'rho'), 'storage order put the output on the x axis'
    figure = _props(content, 'Graph')[0]['figure']
    assert [t['name'] for t in figure['data']] == ['initial design (2)', 'added later (1)']


def test_the_fit_data_table_rounds_but_keeps_full_precision_on_hover(model):
    content = _load_tab('fitdata-content', 'tab-fitdata')
    table = _tables(content)[0]
    assert [c['id'] for c in table['columns']] == ['#', 'origin', 'T', 'p', 'rho']
    assert table['columns'][3]['format']['specifier'] == '.6~g'
    assert table['tooltip_data'][1]['p']['value'] == '0.010000003533967445'
    assert [r['origin'] for r in table['data']] == ['initial', 'initial', 'later']


def test_the_default_x_axis_skips_an_input_sampled_at_one_value():
    from modena_portal.components.fitdata_plot import default_axes
    fitdata = {'D': [0.01, 0.010000004], 'rho0': [0.5, 3.5], 'y': [1, 2]}
    assert default_axes(['D', 'rho0'], ['y'], list(fitdata), fitdata) == ('rho0', 'y')


def test_without_a_known_initial_design_colour_shows_collection_order():
    from modena_portal.components.fitdata_plot import build_scatter
    fig = build_scatter({'x': [1, 2, 3], 'y': [4, 5, 6]}, 'x', 'y', None)
    assert len(fig.data) == 1 and list(fig.data[0].marker.color) == [0, 1, 2]


# ---------------------------------------------------------------------------
# Fit Quality and Refit
# ---------------------------------------------------------------------------

def test_residuals_map_back_to_their_sample():
    from modena_portal.data.helpers import residual_sample
    assert residual_sample(5, 2) == (2, 1)
    assert residual_sample(3, 1) == (3, 0)


def test_the_largest_residuals_are_listed_with_their_inputs():
    from modena_portal.components.fit_quality import make_worst_table
    block = make_worst_table({'residuals': [0.1, -0.5, 0.2]}, ['rho'],
                             {'T': [1.0, 2.0, 3.0]}, ['T'], k=2)
    rows = block.children[1].data
    assert [(r['sample'], r['residual'], r['T']) for r in rows] == \
        [(1, '-0.5', '2'), (2, '0.2', '3')]


def test_a_candidate_fit_is_shown_as_a_change_from_the_stored_one():
    from modena_portal.components.refit_panel import describe_change
    assert describe_change(0.539611, 0.539587) == '0.539611 (+0.00445%)'
    assert describe_change(2.0, 2.0) == '2 (unchanged)'
    assert describe_change(1.0, None) == '1'


# ---------------------------------------------------------------------------
# Runs: fireworks and their actions, polling
# ---------------------------------------------------------------------------

_WF = {'wf_id': 7, 'name': 'simulation', 'state': 'FIZZLED', 'n_fw': 2,
       'completed': 1, 'running': 0, 'waiting': 0, 'fizzled': 1,
       'created_on': None, 'updated_on': None}
_FWS = [{'fw_id': 7, 'name': 'exact sim', 'state': 'FIZZLED',
         'created_on': None, 'updated_on': None},
        {'fw_id': 8, 'name': 'fit', 'state': 'COMPLETED',
         'created_on': None, 'updated_on': None}]


def test_a_workflow_lists_its_fireworks_with_their_actions(monkeypatch):
    _install(monkeypatch, _FakeModel(), workflows=[_WF], fireworks=_FWS)
    _, page = _route('/runs')
    assert _tables(page), _texts(page)
    assert _tables(page)[0]['data'][0]['id'] == 7

    resp = _post(_dep('runs-fw-panel.children'), [
        {'id': 'runs-selected-wf', 'property': 'data', 'value': 7},
        {'id': 'runs-poll', 'property': 'n_intervals', 'value': None},
        {'id': 'runs-action-tick', 'property': 'data', 'value': 0},
        {'id': 'runs-refresh-btn', 'property': 'n_clicks', 'value': None},
    ])
    buttons = {(p['id']['type'], p['id']['index'])
               for p in _props(resp['runs-fw-panel']['children'], 'Button')}
    assert buttons == {('fw-rerun', 7), ('fw-trace', 7), ('fw-trace', 8)}


def _click_rerun(value):
    dep = _dep('runs-banner.children')
    rerun = {'index': 7, 'type': 'fw-rerun'}
    body = {'output': dep['output'], 'outputs': _outputs(dep),
            'inputs': [[{'id': rerun, 'property': 'n_clicks', 'value': value}], [],
                       {'id': 'runs-orphans-btn', 'property': 'n_clicks', 'value': None}],
            'state': [{'id': 'runs-action-tick', 'property': 'data', 'value': 0}],
            'changedPropIds': [json.dumps(rerun, sort_keys=True, separators=(',', ':'))
                               + '.n_clicks']}
    return _CLIENT.post('/_dash-update-component', json=body)


def test_rerun_requeues_that_firework_and_a_redrawn_button_does_not(monkeypatch):
    calls = []
    monkeypatch.setattr('modena_portal.data.launchpad_queries.rerun_firework', calls.append)
    redrawn = _click_rerun(None)
    assert _updated(redrawn, 'runs-banner', 'children') is None
    assert calls == [], 'a redrawn button counted as a click'
    clicked = _click_rerun(1)
    assert calls == [7]
    assert _updated(clicked, 'runs-action-tick', 'data') == 1


def test_firework_times_stored_as_strings_still_give_a_duration():
    """FireWorks stores firework times as ISO strings (workflow times are
    dates); subtracting two strings broke the fireworks panel."""
    from modena_portal.data.launchpad_queries import ACTIVE_STATES, as_datetime
    fw = dict(_FWS[1], created_on=as_datetime('2026-10-02T19:17:03.500000'),
              updated_on=as_datetime('2026-10-02T19:17:45.500000'))
    table = _page('runs').make_fireworks_table([fw], ACTIVE_STATES)
    assert '42 s' in _texts(_tree(table))


def test_list_fireworks_returns_dates_whatever_the_launchpad_stored(monkeypatch):
    import datetime
    import modena
    from modena_portal.data import launchpad_queries

    class _Cursor(list):
        def sort(self, *_):
            return self

    docs = [{'fw_id': 8, 'name': 'fit', 'state': 'COMPLETED',
             'created_on': '2026-10-02T19:17:03.500000',
             'updated_on': datetime.datetime(2026, 10, 2, 19, 17, 45, 500000)}]
    lpad = SimpleNamespace(
        workflows=SimpleNamespace(find_one=lambda q, p: {'nodes': [8]}),
        fireworks=SimpleNamespace(find=lambda q, p: _Cursor(docs)))
    monkeypatch.setattr(modena, 'lpad', lambda: lpad, raising=False)
    fw, = launchpad_queries.list_fireworks(8)
    assert (fw['updated_on'] - fw['created_on']).total_seconds() == 42
    assert launchpad_queries.as_datetime('not a date') is None
    assert launchpad_queries.as_datetime(None) is None


def test_the_runs_page_polls_only_while_work_can_change(monkeypatch):
    for state, polls in (('COMPLETED', False), ('RUNNING', True)):
        _install(monkeypatch, _FakeModel(), workflows=[dict(_WF, state=state)])
        _, page = _route('/runs')
        interval = _props(page, 'Interval')[0]
        assert interval['disabled'] is (not polls), state


# ---------------------------------------------------------------------------
# Library
# ---------------------------------------------------------------------------

def test_the_library_hides_the_case_toggle_and_reports_fit_freshness(model):
    _, page = _route('/library')
    table = _tables(page)[0]
    assert table['filter_options']['case'] == 'insensitive'
    assert {'selector': '.dash-filter--case', 'rule': 'display: none'} in table['css']
    assert table['data'][0]['freshness'] == 'up to date'

    assert _page('library').fit_freshness(model, 5) == '2 new samples since'


# ---------------------------------------------------------------------------
# Shared formatting
# ---------------------------------------------------------------------------

def test_numbers_plurals_and_durations_read_naturally():
    from modena_portal.data.helpers import duration, fmt, plural
    assert fmt(0.010000003533967445) == '0.01' and fmt(None) == '—'
    assert (plural(1, 'sample'), plural(3, 'sample')) == ('1 sample', '3 samples')
    assert (duration(0.2), duration(42), duration(600)) == ('< 1 s', '42 s', '10 min')


def test_code_blocks_copy_and_a_long_command_wraps():
    from modena_portal.components.code_block import code_block
    clip, pre = code_block('gcc -o x x.c', wrap=True).children
    assert clip.content == 'gcc -o x x.c'
    assert pre.style['whiteSpace'] == 'pre-wrap'
