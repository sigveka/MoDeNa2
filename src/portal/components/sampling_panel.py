"""Request additional training points for a model.

Distinct from the Refit tab in one way that governs the whole design: refit
re-reads data already in MongoDB and costs seconds, whereas each point here is
an *exact simulation* -- CFD, DEM, a quantum chemistry run -- costing minutes
to hours and, on HPC, real allocation.

So: the cost is shown before committing, the work is queued through FireWorks
rather than run in the request thread, and the sampler is the model's own.  A
model with a sum(x)=1 composition constraint declares a CASTRO variant
precisely because Latin Hypercube would generate invalid points -- which would
then be simulated at full price.  The user chooses how many, never how.
"""
from dash import dcc, html
import dash_bootstrap_components as dbc


def _humanise(seconds):
    if seconds is None:
        return None
    if seconds < 90:
        return f'{seconds:.0f} s'
    if seconds < 5400:
        return f'{seconds / 60:.0f} min'
    return f'{seconds / 3600:.1f} h'


def make_sampling_form(default_n: int = 5):
    return dbc.Card(dbc.CardBody([
        html.H5('Collect more training data', className='card-title'),
        html.P(
            'Runs the exact simulation at new points chosen by this model\'s '
            'own sampling strategy, then refits. Queued through FireWorks — '
            'watch progress on the Runs page.',
            className='text-muted small',
        ),
        dbc.Row([
            dbc.Col([
                dbc.Label('New points', html_for='sampling-n'),
                dbc.Input(id='sampling-n', type='number', value=default_n,
                          min=1, step=1, debounce=True),
            ], md=3),
            dbc.Col([
                dbc.Label(' '),
                dbc.Button('Estimate cost', id='sampling-estimate-btn',
                           color='secondary', className='w-100'),
            ], md=3),
            dbc.Col(html.Div(id='sampling-estimate'), md=6,
                    className='d-flex align-items-end'),
        ], className='g-2'),
        html.Hr(),
        html.Div(id='sampling-preview'),
        make_launch_controls(),
    ]), className='mb-3')


def make_cost_readout(cost: dict):
    each = _humanise(cost['seconds_each'])
    total = _humanise(cost['seconds_total'])
    if each is None:
        return dbc.Alert(
            'This model\'s exact simulation has not completed before, so there '
            'is no basis for an estimate. It may take anywhere from seconds to '
            'hours per point.',
            color='secondary', className='py-2 mb-0',
        )
    return dbc.Alert(
        [
            html.Strong(f"≈ {total} "),
            f"for {cost['n_points']} point(s) — {each} each, "
            f"averaged over {cost['basis']} previous run(s).",
        ],
        color='info', className='py-2 mb-0',
    )


def make_points_preview(points: dict):
    """Show what will be simulated, before anything is queued."""
    from dash import dash_table

    names = list(points)
    n = len(points[names[0]]) if names else 0
    rows = [{'#': i + 1, **{k: f'{points[k][i]:.6g}' for k in names}}
            for i in range(n)]
    return html.Div([
        html.H6(f'{n} point(s) to be simulated'),
        dash_table.DataTable(
            data=rows,
            columns=[{'name': c, 'id': c} for c in ['#'] + names],
            style_cell={'textAlign': 'left', 'fontFamily': 'monospace',
                        'fontSize': '0.85rem'},
            style_table={'overflowX': 'auto'},
            page_size=10,
        ),
    ])


def make_launch_controls():
    return html.Div([
        dbc.Alert(
            [
                html.Strong('This spends compute. '),
                'Each point runs the full exact simulation. On a cluster that '
                'is real allocation, and the work cannot be un-queued from '
                'here — use the Runs page to defuse it. Queued work does not '
                'start until a worker is running (modena fw launch).',
            ],
            color='warning', className='py-2 mt-3',
        ),
        dbc.Button('Queue simulations', id='sampling-run-btn',
                   color='danger', disabled=True),
        html.Span(id='sampling-status', className='ms-3'),
    ])
