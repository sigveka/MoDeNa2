"""Model Detail page - /model/<encoded_id>."""
import os
import dash
from dash import html, dcc, Input, Output, State, callback
import dash_bootstrap_components as dbc
from urllib.parse import unquote, quote

from modena_portal.components.navbar import make_navbar
from modena_portal.components.status_badge import status_badge
from modena_portal.components.parameter_table import make_parameter_table
from modena_portal.components.fitdata_table import make_fitdata_table
from modena_portal.components.fitdata_plot import make_fitdata_plot
from modena_portal.components.dependency_graph import make_dependency_graph
from modena_portal.data.queries import get_model, get_fitdata, save_documentation

dash.register_page(__name__, path_template="/model/<model_id>", title="MoDeNa - Model Detail")


def layout(model_id: str = ""):
    decoded_id = unquote(model_id)

    try:
        model = get_model(decoded_id)
    except Exception as e:
        return dbc.Container([
            make_navbar(active='library'),
            dbc.Alert(f"Model '{decoded_id}' not found: {e}", color="danger"),
        ])

    sf = model.surrogateFunction
    encoded_id = quote(decoded_id, safe='')

    # Function signature string
    out_names = list(model.outputs.keys()) if model.outputs else ['?']
    in_names = list(model.inputs.keys()) if model.inputs else []
    param_names = list(sf.parameters.keys()) if sf and sf.parameters else []
    signature = (
        f"{', '.join(out_names)} = {sf.name if sf else '?'}"
        f"({', '.join(in_names)} ; {', '.join(param_names)})"
    )

    # Inputs/outputs bounds table rows
    io_rows = []
    if model.inputs:
        for name, entry in model.inputs.items():
            io_rows.append({
                'Variable': name,
                'Kind': 'Input',
                'Min': f"{entry.min:.6g}" if entry.min is not None else '-',
                'Max': f"{entry.max:.6g}" if entry.max is not None else '-',
            })
    if model.outputs:
        for name, entry in model.outputs.items():
            io_rows.append({
                'Variable': name,
                'Kind': 'Output',
                'Min': f"{entry.min:.6g}" if entry.min is not None else '-',
                'Max': f"{entry.max:.6g}" if entry.max is not None else '-',
            })

    from dash import dash_table as dt
    io_table = dt.DataTable(
        data=io_rows,
        columns=[{'name': c, 'id': c} for c in ['Variable', 'Kind', 'Min', 'Max']],
        style_cell={'textAlign': 'left'},
        style_table={'overflowX': 'auto'},
    )

    # Substitute model links
    sub_links = []
    for sub in getattr(model, 'substituteModels', []):
        sub_enc = quote(sub._id, safe='')
        sub_links.append(dcc.Link(sub._id, href=f"/model/{sub_enc}",
                                  style={'marginRight': '12px'}))

    # Overview tab
    overview_tab = dbc.Tab(label="Overview", tab_id="tab-overview", children=[
        html.Div([
            html.H5("Status"),
            status_badge(model),
            html.Hr(),
            html.H5("Function Signature"),
            html.Code(signature, style={'fontSize': '1rem'}),
            html.Hr(),
            html.H5("Parameters"),
            make_parameter_table(model),
            html.Hr(),
            html.H5("Inputs / Outputs Bounds"),
            io_table,
            html.Hr(),
            html.H5("Substitute Models"),
            html.Div(sub_links if sub_links else html.Span("None", className="text-muted")),
            html.Hr(),
            html.H5("Dependency Graph"),
            make_dependency_graph(model),
        ], className="mt-3"),
    ])

    # Documentation tab
    doc_text = getattr(model, 'documentation', '') or ''
    doc_tab = dbc.Tab(label="Documentation", tab_id="tab-docs", children=[
        html.Div([
            dbc.Alert(
                "Documentation is defined in the model's Python package and "
                "synced to the database on initModels.",
                color="info", className="mt-3 py-2",
            ),
            dcc.Markdown(
                doc_text or '*No documentation provided.*',
                mathjax=True,
                style={'border': '1px solid #dee2e6', 'padding': '16px',
                       'minHeight': '200px', 'borderRadius': '4px',
                       'marginTop': '8px'},
            ),
        ]),
    ])

    # Fit Data tab (only for BackwardMappingModel)
    has_fitdata = hasattr(model, 'fitData')
    if has_fitdata:
        fitdata_tab = dbc.Tab(label="Fit Data", tab_id="tab-fitdata", children=[
            html.Div(id='fitdata-content', children=html.Span(
                "Switch to this tab to load fit data.",
                className="text-muted"
            ), className="mt-3"),
        ])
        tabs = [overview_tab, doc_tab, fitdata_tab]
    else:
        tabs = [overview_tab, doc_tab]

    # C Code tab
    ccode = sf.Ccode if sf and sf.Ccode else '# No C code stored.'
    ccode_tab = dbc.Tab(label="C Code", tab_id="tab-ccode", children=[
        dcc.Markdown(
            f"```c\n{ccode}\n```",
            highlight_config={"theme": "dark"},
            style={'marginTop': '16px'},
        ),
    ])
    tabs.append(ccode_tab)

    return dbc.Container([
        make_navbar(model_id=decoded_id, active='library'),
        html.H2(decoded_id, className="mb-1"),
        html.P(f"Type: {model.__class__.__name__}", className="text-muted"),
        dcc.Link(
            dbc.Button("Evaluate Model", color="success", size="sm"),
            href=f"/model/{encoded_id}/evaluate",
        ),
        html.Hr(),
        # Hidden store to pass model_id to callbacks
        dcc.Store(id='detail-model-id', data=decoded_id),
        dbc.Tabs(tabs, id='detail-tabs', active_tab='tab-overview'),
    ], fluid=True)
