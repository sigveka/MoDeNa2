"""Model Library page - lists all surrogate models."""
import dash
from dash import html, dash_table, dcc
import dash_bootstrap_components as dbc
from urllib.parse import quote

from modena_portal.components.navbar import make_navbar
from modena_portal.components.status_badge import status_string
from modena_portal.data.queries import list_models, list_model_sample_counts

dash.register_page(__name__, path="/", title="MoDeNa - Model Library")


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
        n_inputs = len(m.inputs) if hasattr(m, 'inputs') and m.inputs else 0
        n_outputs = len(m.outputs) if hasattr(m, 'outputs') and m.outputs else 0
        n_samples = sample_counts.get(m._id, '-')

        rows.append({
            '_id': m._id,
            'type': m.__class__.__name__,
            'function': sf.name if sf else '-',
            'inputs': n_inputs,
            'outputs': n_outputs,
            'samples': n_samples,
            'params': len(m.parameters),
            'status': status_string(m),
            '_link': f"/model/{quote(m._id, safe='')}",
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
            {'name': 'Params', 'id': 'params'},
            {'name': 'Status', 'id': 'status'},
        ],
        # Render _id as a markdown link
        markdown_options={'html': False},
        # We'll rewrite _id to markdown link below
        style_table={'overflowX': 'auto'},
        style_cell={'textAlign': 'left', 'padding': '8px'},
        style_header={'fontWeight': 'bold', 'backgroundColor': '#f8f9fa'},
        filter_action='native',
        sort_action='native',
        page_size=20,
    )

    # Rewrite _id to markdown links for the DataTable markdown column
    for row in rows:
        row['_id'] = f"[{row['_id']}]({row['_link']})"

    return dbc.Container([
        make_navbar(active='library'),
        html.H2("Model Library", className="mb-3"),
        table,
    ], fluid=True)
