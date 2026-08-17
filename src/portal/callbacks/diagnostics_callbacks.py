"""Callbacks for the Fit Quality and Refit tabs.

Fits run in the request thread rather than through FireWorks: they use only
stored fit data, take seconds, and the whole point is an immediate answer.
Anything that costs an *exact simulation* must not follow this pattern -- that
belongs in a queued workflow.
"""
import logging

from dash import Input, Output, State, callback, html, no_update
import dash_bootstrap_components as dbc

from modena_portal.components.fit_quality import (
    make_parity_plot, make_quality_summary, make_residual_plot,
)
from modena_portal.components.refit_panel import (
    make_promote_controls, make_refit_form, make_results_table,
)
from modena_portal.data.queries import get_model_full

_log = logging.getLogger('modena_portal.diagnostics')


#: Hint text per strategy for the single free parameter.
_CV_PARAM_HELP = {
    'Holdout':     'Holdout: test fraction (0-1)',
    'KFold':       'KFold: number of folds k',
    'LeavePOut':   'LeavePOut: samples held out per fold (p)',
    'LeaveOneOut': 'LeaveOneOut: no parameter',
    'Jackknife':   'Jackknife: no parameter',
}

_CV_PARAM_DEFAULT = {
    'Holdout': 0.2, 'KFold': 5, 'LeavePOut': 2,
    'LeaveOneOut': None, 'Jackknife': None,
}


def _build_cv(name, value):
    """Instantiate the chosen CV strategy with its single free parameter."""
    from modena.Diagnostics import CV_STRATEGIES
    cls, defaults = CV_STRATEGIES[name]
    if name == 'Holdout':
        return cls(testDataPercentage=float(value if value is not None else 0.2))
    if name == 'KFold':
        return cls(k=int(value if value is not None else 5))
    if name == 'LeavePOut':
        return cls(p=int(value if value is not None else 2))
    return cls(**defaults)


# ---------------------------------------------------------------------------
# Fit Quality tab
# ---------------------------------------------------------------------------

@callback(
    Output('quality-content', 'children'),
    Input('detail-tabs', 'active_tab'),
    State('detail-model-id', 'data'),
    prevent_initial_call=True,
)
def load_quality_on_tab(active_tab, model_id):
    if active_tab != 'tab-quality' or not model_id:
        return no_update

    from modena.Diagnostics import fit_quality, predictions

    try:
        model = get_model_full(model_id)
        quality = fit_quality(model)
        preds = predictions(model)
    except ValueError as exc:
        return dbc.Alert(str(exc), color="secondary")
    except Exception as exc:
        _log.exception('fit quality failed for %s', model_id)
        return dbc.Alert(f"Could not compute fit quality: {exc}", color="danger")

    return html.Div([
        make_quality_summary(quality),
        html.Hr(),
        html.H5("Measured vs predicted"),
        make_parity_plot(preds),
        html.Hr(),
        html.H5("Residuals"),
        make_residual_plot(quality),
    ])


# ---------------------------------------------------------------------------
# Refit tab — form scaffolding
# ---------------------------------------------------------------------------

@callback(
    Output('refit-content', 'children'),
    Input('detail-tabs', 'active_tab'),
    State('detail-model-id', 'data'),
    prevent_initial_call=True,
)
def load_refit_on_tab(active_tab, model_id):
    if active_tab != 'tab-refit' or not model_id:
        return no_update
    return html.Div([
        make_refit_form(),
        html.Div(id='refit-results', children=make_results_table([])),
        make_promote_controls(),
    ])


@callback(
    Output('refit-cv-param-help', 'children'),
    Output('refit-cv-param', 'value'),
    Output('refit-cv-param', 'disabled'),
    Input('refit-cv', 'value'),
    prevent_initial_call=True,
)
def update_cv_param(cv_name):
    default = _CV_PARAM_DEFAULT.get(cv_name)
    return (_CV_PARAM_HELP.get(cv_name, ''), default, default is None)


# ---------------------------------------------------------------------------
# Refit tab — run a fit, append to the comparison table
# ---------------------------------------------------------------------------

@callback(
    Output('refit-results', 'children'),
    Output('refit-store', 'data'),
    Output('refit-promote-btn', 'disabled', allow_duplicate=True),
    Input('refit-run-btn', 'n_clicks'),
    State('refit-cv', 'value'),
    State('refit-cv-param', 'value'),
    State('refit-optimizer', 'value'),
    State('refit-metric', 'value'),
    State('refit-store', 'data'),
    State('detail-model-id', 'data'),
    prevent_initial_call=True,
)
def run_refit(n_clicks, cv_name, cv_param, opt_name, metric_name,
              store, model_id):
    if not n_clicks or not model_id:
        return no_update, no_update, no_update

    from modena.Diagnostics import METRICS, OPTIMIZERS, cross_validate

    store = store or []
    try:
        model = get_model_full(model_id)
        result = cross_validate(
            model,
            crossValidation=_build_cv(cv_name, cv_param),
            optimizer=OPTIMIZERS[opt_name](),
            metric=METRICS[metric_name](),
        )
    except ValueError as exc:
        return dbc.Alert(str(exc), color="warning"), store, True
    except Exception as exc:
        _log.exception('refit failed for %s', model_id)
        return dbc.Alert(f"Fit failed: {exc}", color="danger"), store, True

    store.append({
        'strategy':   result['crossValidation'],
        'optimizer':  result['optimizer'],
        'metric':     result['metric'],
        'n_folds':    result['n_folds'],
        'cv_error':   f"{result['cv_error']:.6g}",
        'full_error': f"{result['full_fit_error']:.6g}",
        'parameters': ', '.join(f'{k}={v:.6g}'
                                for k, v in result['named_parameters'].items()),
        '_params':    result['full_fit_parameters'],
        '_cv_error':  result['cv_error'],
    })

    best = min(r['_cv_error'] for r in store)
    for row in store:
        row['is_best'] = 1 if row['_cv_error'] == best else 0

    return make_results_table(store), store, True


@callback(
    Output('refit-promote-btn', 'disabled'),
    Input('refit-results-table', 'selected_rows'),
    prevent_initial_call=True,
)
def toggle_promote(selected_rows):
    return not selected_rows


# ---------------------------------------------------------------------------
# Refit tab — the one write path
# ---------------------------------------------------------------------------

@callback(
    Output('refit-promote-status', 'children'),
    Input('refit-promote-btn', 'n_clicks'),
    State('refit-results-table', 'selected_rows'),
    State('refit-store', 'data'),
    State('detail-model-id', 'data'),
    prevent_initial_call=True,
)
def promote(n_clicks, selected_rows, store, model_id):
    if not n_clicks or not selected_rows or not store or not model_id:
        return no_update

    from modena.Diagnostics import promote_parameters

    row = store[selected_rows[0]]
    try:
        model = get_model_full(model_id)
        named = promote_parameters(model, row['_params'])
    except Exception as exc:
        _log.exception('promote failed for %s', model_id)
        return dbc.Badge(f"Promote failed: {exc}", color="danger")

    return dbc.Badge(
        f"Promoted {row['strategy']} fit: "
        + ', '.join(f'{k}={v:.6g}' for k, v in named.items()),
        color="success",
    )


# ---------------------------------------------------------------------------
# Integrate tab — per-model, per-language snippets
# ---------------------------------------------------------------------------

@callback(
    Output('integrate-content', 'children'),
    Input('detail-tabs', 'active_tab'),
    State('detail-model-id', 'data'),
    prevent_initial_call=True,
)
def load_integrate_on_tab(active_tab, model_id):
    if active_tab != 'tab-integrate' or not model_id:
        return no_update
    from modena_portal.components.integrate_panel import make_language_tabs
    return html.Div([
        make_language_tabs(),
        html.Div(id='integrate-snippet', className="mt-3"),
    ])


@callback(
    Output('integrate-snippet', 'children'),
    Input('integrate-lang-tabs', 'active_tab'),
    State('detail-model-id', 'data'),
)
def render_snippet(active_lang, model_id):
    if not active_lang or not model_id:
        return no_update

    from modena.Integration import snippet
    from modena_portal.components.integrate_panel import make_snippet_view

    language = active_lang.removeprefix('lang-')
    try:
        model = get_model_full(model_id)
        s = snippet(model, language)
    except Exception as exc:
        _log.exception('snippet generation failed for %s/%s', model_id, language)
        return dbc.Alert(f"Could not generate snippet: {exc}", color="danger")
    return make_snippet_view(s, model_id)
