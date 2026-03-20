"""Runs page - lists all FireWorks simulation workflows."""
import dash
from dash import html, dash_table, Input, Output, callback
import dash_bootstrap_components as dbc

from modena_portal.components.navbar import make_navbar

dash.register_page(__name__, path="/runs", title="MoDeNa - Runs")

# Bootstrap colours mapped to CSS background colours for DataTable conditional styling.
_STATE_CSS = {
    'COMPLETED': ('#d1e7dd', '#0a3622'),   # green  (bg, text)
    'RUNNING':   ('#cfe2ff', '#052c65'),   # blue
    'WAITING':   ('#fff3cd', '#664d03'),   # yellow
    'READY':     ('#fff3cd', '#664d03'),
    'RESERVED':  ('#fff3cd', '#664d03'),
    'FIZZLED':   ('#f8d7da', '#58151c'),   # red
    'PAUSED':    ('#f8d7da', '#58151c'),
    'DEFUSED':   ('#f8d7da', '#58151c'),
}

_STATE_STYLE_CONDITIONS = [
    {
        'if': {'filter_query': f'{{state}} = "{state}"', 'column_id': 'state'},
        'backgroundColor': bg,
        'color': fg,
        'fontWeight': 'bold',
        'borderRadius': '4px',
    }
    for state, (bg, fg) in _STATE_CSS.items()
]


def _build_table(rows):
    if not rows:
        return dbc.Alert("No workflows found in the FireWorks launchpad.", color="secondary")

    table_rows = []
    for r in rows:
        created = r['created_on'].strftime('%Y-%m-%d %H:%M') if r['created_on'] else '—'
        updated = r['updated_on'].strftime('%Y-%m-%d %H:%M') if r['updated_on'] else '—'
        table_rows.append({
            'name':      r['name'],
            'state':     r['state'],
            'n_fw':      r['n_fw'],
            'completed': r['completed'],
            'running':   r['running'],
            'waiting':   r['waiting'],
            'fizzled':   r['fizzled'],
            'created':   created,
            'updated':   updated,
        })
    return dash_table.DataTable(
        id='runs-table',
        data=table_rows,
        columns=[
            {'name': 'Name',      'id': 'name'},
            {'name': 'State',     'id': 'state'},
            {'name': 'Total FWs', 'id': 'n_fw'},
            {'name': 'Completed', 'id': 'completed'},
            {'name': 'Running',   'id': 'running'},
            {'name': 'Waiting',   'id': 'waiting'},
            {'name': 'Fizzled',   'id': 'fizzled'},
            {'name': 'Created',   'id': 'created'},
            {'name': 'Updated',   'id': 'updated'},
        ],
        style_data_conditional=_STATE_STYLE_CONDITIONS,
        style_table={'overflowX': 'auto'},
        style_cell={'textAlign': 'left', 'padding': '8px'},
        style_header={'fontWeight': 'bold', 'backgroundColor': '#f8f9fa'},
        filter_action='native',
        sort_action='native',
        page_size=20,
    )


def layout():
    try:
        from modena_portal.data.launchpad_queries import list_workflows
        rows = list_workflows()
    except Exception as e:
        return dbc.Container([
            make_navbar(active='runs'),
            dbc.Alert(f"Could not connect to FireWorks launchpad: {e}", color="danger"),
        ])

    return dbc.Container([
        make_navbar(active='runs'),
        dbc.Row([
            dbc.Col(html.H2("Runs", className="mb-3")),
            dbc.Col(
                dbc.Button("Refresh", id="runs-refresh-btn", color="secondary",
                           size="sm", className="mb-3 float-end"),
                width="auto",
            ),
        ], align="center"),
        html.Div(id="runs-table-container", children=_build_table(rows)),
    ], fluid=True)


@callback(
    Output("runs-table-container", "children"),
    Input("runs-refresh-btn", "n_clicks"),
    prevent_initial_call=True,
)
def refresh_runs(_n):
    try:
        from modena_portal.data.launchpad_queries import list_workflows
        rows = list_workflows()
        return _build_table(rows)
    except Exception as e:
        return dbc.Alert(f"Could not connect to FireWorks launchpad: {e}", color="danger")
