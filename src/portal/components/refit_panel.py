"""Strategy comparison: refit stored fit data under different strategies.

Comparing cross-validation strategies previously meant editing the model's
Python source, re-running the fit, and keeping track of the results by hand --
with no record of what had already been tried.  Everything needed was already
in the framework (Holdout / KFold / LeaveOneOut / LeavePOut / Jackknife, three
optimizers, three error metrics); only a way to drive them was missing.

Results are candidates, not commitments.  Nothing reaches MongoDB until
"Promote" is pressed: the stored parameters are live, and a running C
application evaluates against them through modena_model_call.  So every
candidate is shown against what is stored -- the parameter change and the
stored parameters' error under the same metric.
"""
from dash import dcc, html, dash_table
import dash_bootstrap_components as dbc

from modena.Diagnostics import CV_STRATEGIES, OPTIMIZERS, METRICS
from modena_portal.data.helpers import fmt, plural


def _options(names):
    return [{'label': n, 'value': n} for n in names]


def make_refit_form():
    """Strategy pickers + the run button."""
    return dbc.Card(dbc.CardBody([
        html.H5("Refit on existing data", className="card-title"),
        html.P(
            "Re-runs parameter fitting against the fit data already in the "
            "database. No exact simulations are run and nothing is written "
            "until you promote a result.",
            className="text-muted small",
        ),
        dbc.Row([
            dbc.Col([
                dbc.Label("Cross-validation", html_for="refit-cv"),
                dcc.Dropdown(id="refit-cv", options=_options(CV_STRATEGIES),
                             value="Holdout", clearable=False),
            ], md=3),
            dbc.Col([
                dbc.Label("Strategy setting", html_for="refit-cv-param"),
                dbc.Input(id="refit-cv-param", type="number", value=0.2,
                          step="any", debounce=True),
                dbc.FormText(id="refit-cv-param-help",
                             children="Holdout: test fraction (0-1)"),
            ], md=2),
            dbc.Col([
                dbc.Label("Optimizer", html_for="refit-optimizer"),
                dcc.Dropdown(id="refit-optimizer", options=_options(OPTIMIZERS),
                             value="TrustRegionReflective", clearable=False),
            ], md=3),
            dbc.Col([
                dbc.Label("Error metric", html_for="refit-metric"),
                dcc.Dropdown(id="refit-metric", options=_options(METRICS),
                             value="AbsoluteError", clearable=False),
            ], md=2),
            dbc.Col([
                dbc.Label(" "),
                dbc.Button("Run fit", id="refit-run-btn", color="primary",
                           className="w-100"),
            ], md=2),
        ], className="g-2 align-items-start"),
    ]), className="mb-3")


def make_stored_line(model):
    """What a promotion would replace."""
    if not model.parameters:
        return html.Div("Nothing stored yet: this model has not been fitted.",
                        className="mb-2")
    last = getattr(model, 'last_fitted', None)
    when = f" · fitted {last.strftime('%Y-%m-%d %H:%M')} UTC" if last else ''
    n = getattr(model, 'n_samples_fitted', 0) or 0
    return html.Div([
        html.Strong("Stored now: "),
        html.Span(', '.join(f'{k} = {fmt(v)}' for k, v in model.parameters.items()),
                  className="font-monospace"),
        html.Span(f"{when} on {plural(n, 'sample')}", className="text-muted"),
    ], className="mb-2")


def describe_change(new: float, old) -> str:
    """'0.539611 (+0.0045%)' -- the new value and how far it moved."""
    if old is None:
        return fmt(new)
    if new == old:
        return f'{fmt(new)} (unchanged)'
    if old == 0:
        return f'{fmt(new)} (was 0)'
    return f'{fmt(new)} ({(new - old) / abs(old) * 100:+.3g}%)'


#: Column order for the comparison table.
_COLUMNS = [
    ('strategy',     'Cross-validation'),
    ('optimizer',    'Optimizer'),
    ('metric',       'Metric'),
    ('n_folds',      'Folds'),
    ('cv_error',     'CV error'),
    ('full_error',   'Full-fit error'),
    ('stored_error', 'Stored error'),
    ('parameters',   'Parameters (change from stored)'),
]

#: What the three error columns measure.  Side by side they are easy to
#: misread: the CV error is usually the *larger* one, because it scores each
#: fit on samples it never saw.
_LEGEND = [
    html.Strong("CV error"), " — the worst error on held-out samples, over "
    "all folds (the mean for Jackknife): how well the fit predicts points it "
    "was not fitted on. ",
    html.Strong("Full-fit error"), " — the worst error of a fit to all "
    "samples, on those same samples; these are the parameters Promote "
    "stores. ",
    html.Strong("Stored error"), " — the parameters stored now, scored the "
    "same way. All three use the row's metric.",
]


def make_results_table(rows):
    """Comparison table over every strategy run this session."""
    if not rows:
        return html.Div(
            "No fits run yet. Pick a strategy above and press Run fit.",
            className="text-muted",
        )

    return html.Div([
        dash_table.DataTable(
            id="refit-results-table",
            data=rows,
            columns=[{'name': label, 'id': key} for key, label in _COLUMNS],
            row_selectable="single",
            selected_rows=[],
            style_cell={'textAlign': 'left', 'fontFamily': 'monospace',
                        'fontSize': '0.85rem', 'whiteSpace': 'normal'},
            style_table={'overflowX': 'auto'},
            style_data_conditional=[{
                # Highlight the best CV error found so far.
                'if': {'filter_query': '{is_best} = 1'},
                'backgroundColor': '#e8f5e9',
            }],
            style_header={'fontWeight': 'bold'},
        ),
        html.P(_LEGEND, className="text-muted small mt-2"),
    ])


def make_promote_controls():
    """Explicit, guarded write path."""
    return html.Div([
        dbc.Alert(
            [
                html.Strong("Promoting overwrites the model's stored "
                            "parameters. "),
                "Any running simulation that evaluates this surrogate will "
                "pick up the new values on its next model load.",
            ],
            color="warning", className="py-2",
        ),
        dbc.Button("Promote selected fit", id="refit-promote-btn",
                   color="danger", disabled=True),
        html.Span("Select a fit in the table to promote it.",
                  id="refit-promote-hint", className="text-muted small ms-2"),
        html.Span(id="refit-promote-status", className="ms-3"),
    ], className="mt-3")
