"""Model Library page - lists all surrogate models."""
import dash
from dash import html, dash_table
import dash_bootstrap_components as dbc
from urllib.parse import quote

from modena_portal.components.navbar import make_navbar
from modena_portal.components.status_badge import STATUS_CSS, status_string
from modena_portal.data.helpers import plural
from modena_portal.data.queries import list_models, list_model_sample_counts

dash.register_page(__name__, path="/library", title="MoDeNa - Model Library")


def fit_freshness(model, n_samples) -> str:
    """Whether the stored parameters used every stored sample.

    Cheap -- two counts -- unlike the fit error, which means evaluating the
    surrogate at every sample (the Fit Quality tab does that on demand).
    """
    if not model.parameters or not isinstance(n_samples, int):
        return '—'
    new = n_samples - (getattr(model, 'n_samples_fitted', 0) or 0)
    return 'up to date' if new <= 0 else f"{plural(new, 'new sample')} since"


def layout():
    try:
        models = list_models()
        sample_counts = list_model_sample_counts()
    except Exception as e:
        return dbc.Container([
            make_navbar(active='library'),
            dbc.Alert(f"Could not connect to MongoDB: {e}", color="danger"),
        ])

    if not models:
        return dbc.Container([
            make_navbar(active='library'),
            html.H2("Model Library", className="mb-3"),
            dbc.Alert("No surrogate models found in the database.", color="secondary"),
        ], fluid=True)

    rows = []
    for m in models:
        sf = m.surrogateFunction
        n_samples = sample_counts.get(m._id, '-')
        last = getattr(m, 'last_fitted', None)
        rows.append({
            # A markdown link: DataTable renders the id column as one.
            '_id': f"[{m._id}](/model/{quote(m._id, safe='')})",
            'type': m.__class__.__name__,
            'function': sf.name if sf else '-',
            'inputs': len(m.inputs) if getattr(m, 'inputs', None) else 0,
            'outputs': len(m.outputs) if getattr(m, 'outputs', None) else 0,
            'samples': n_samples,
            'status': status_string(m),
            'last_fitted': last.strftime('%Y-%m-%d %H:%M') if last else '—',
            'freshness': fit_freshness(m, n_samples),
        })

    table = dash_table.DataTable(
        id='library-table',
        data=rows,
        columns=[
            {'name': 'ID', 'id': '_id', 'presentation': 'markdown'},
            {'name': 'Type', 'id': 'type'},
            {'name': 'Function', 'id': 'function'},
            {'name': 'Inputs', 'id': 'inputs'},
            {'name': 'Outputs', 'id': 'outputs'},
            {'name': 'Samples', 'id': 'samples'},
            {'name': 'Status', 'id': 'status'},
            {'name': 'Last fitted', 'id': 'last_fitted'},
            {'name': 'Fit', 'id': 'freshness'},
        ],
        markdown_options={'html': False},
        style_table={'overflowX': 'auto'},
        style_cell={'textAlign': 'left', 'padding': '8px'},
        style_header={'fontWeight': 'bold', 'backgroundColor': '#f8f9fa'},
        style_data_conditional=[
            {'if': {'filter_query': f'{{status}} = "{status}"', 'column_id': 'status'},
             'backgroundColor': bg, 'color': fg, 'fontWeight': 'bold'}
            for status, (bg, fg) in STATUS_CSS.items()
        ] + [
            {'if': {'filter_query': '{freshness} contains "since"', 'column_id': 'freshness'},
             'color': '#664d03', 'fontWeight': 'bold'},
        ],
        filter_action='native',
        # The case-sensitivity toggle DataTable puts in every filter cell
        # rendered as a stray pink "Aa" box under Bootstrap; matching is
        # case-insensitive instead and the toggle is hidden.
        filter_options={'case': 'insensitive', 'placeholder_text': 'filter…'},
        css=[{'selector': '.dash-filter--case', 'rule': 'display: none'}],
        sort_action='native',
        page_size=20,
    )

    return dbc.Container([
        make_navbar(active='library'),
        html.H2("Model Library", className="mb-3"),
        table,
        html.P("Fit: whether the stored parameters were fitted on every stored "
               "sample. Fit Quality on a model's page scores them.",
               className="text-muted small mt-2"),
    ], fluid=True)
