"""Strategy comparison: refit stored fit data under different strategies.

Comparing cross-validation strategies previously meant editing the model's
Python source, re-running the fit, and keeping track of the results by hand --
with no record of what had already been tried.  Everything needed was already
in the framework (Holdout / KFold / LeaveOneOut / LeavePOut / Jackknife, three
optimizers, three error metrics); only a way to drive them was missing.

Results are candidates, not commitments.  Nothing reaches MongoDB until
"Promote" is pressed: the stored parameters are live, and a running C
application evaluates against them through modena_model_call.
"""
from dash import dcc, html, dash_table
import dash_bootstrap_components as dbc

from modena.Diagnostics import CV_STRATEGIES, OPTIMIZERS, METRICS


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
                dbc.Label("Parameter", html_for="refit-cv-param"),
                dbc.Input(id="refit-cv-param", type="number", value=0.2,
                          step="any", debounce=True),
                dbc.FormText(id="refit-cv-param-help",
                             children="Holdout: test fraction"),
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
                dbc.Label(" "),
                dbc.Button("Run fit", id="refit-run-btn", color="primary",
                           className="w-100"),
            ], md=2),
        ], className="g-2 align-items-start"),
    ]), className="mb-3")


#: Column order for the comparison table.
_COLUMNS = [
    ('strategy',   'Cross-validation'),
    ('optimizer',  'Optimizer'),
    ('metric',     'Metric'),
    ('n_folds',    'Folds'),
    ('cv_error',   'CV error'),
    ('full_error', 'Full-fit error'),
    ('parameters', 'Parameters'),
]


def make_results_table(rows):
    """Comparison table over every strategy run this session."""
    if not rows:
        return html.Div(
            "No fits run yet. Pick a strategy above and press Run fit.",
            className="text-muted",
        )

    return dash_table.DataTable(
        id="refit-results-table",
        data=rows,
        columns=[{'name': label, 'id': key} for key, label in _COLUMNS],
        row_selectable="single",
        selected_rows=[],
        style_cell={'textAlign': 'left', 'fontFamily': 'monospace',
                    'fontSize': '0.85rem'},
        style_table={'overflowX': 'auto'},
        style_data_conditional=[{
            # Highlight the best CV error found so far.
            'if': {'filter_query': '{is_best} = 1'},
            'backgroundColor': '#e8f5e9',
        }],
        style_header={'fontWeight': 'bold'},
    )


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
        html.Span(id="refit-promote-status", className="ms-3"),
    ], className="mt-3")
