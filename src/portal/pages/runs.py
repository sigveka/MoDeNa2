"""Runs page - lists all FireWorks simulation workflows."""
import dash
from dash import html, dash_table, Input, Output, State, callback
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
        html.Div(id="runs-banner"),
        html.Div(id="runs-table-container", children=_build_table(rows)),
        html.Hr(),
        _make_actions(),
    ], fluid=True)


def _make_actions():
    """Actions ModenaLaunchPad has always implemented but the UI never exposed.

    Each maps to one launchpad method: rerun(), defuse_orphans() and
    retrace_to_origin().  Reset is deliberately absent -- it destroys every
    firework and its history, and `modena fw reset` already guards it behind a
    confirmation prompt.
    """
    return dbc.Row([
        dbc.Col(dbc.Card(dbc.CardBody([
            html.H6("Re-queue a firework"),
            html.P("A FIZZLED firework can be retried once the cause is fixed.",
                   className="text-muted small"),
            dbc.InputGroup([
                dbc.Input(id="runs-rerun-id", type="number", placeholder="fw id"),
                dbc.Button("Rerun", id="runs-rerun-btn", color="primary"),
            ]),
        ])), md=4),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.H6("Recover orphans"),
            html.P("Re-queues fireworks whose worker process died — they would "
                   "otherwise sit in RUNNING forever.",
                   className="text-muted small"),
            dbc.Button("Defuse orphans", id="runs-orphans-btn",
                       color="warning"),
        ])), md=4),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.H6("Trace ancestry"),
            html.P("Everything that had to finish before this firework — the "
                   "fastest way to see why a run took the shape it did.",
                   className="text-muted small"),
            dbc.InputGroup([
                dbc.Input(id="runs-trace-id", type="number", placeholder="fw id"),
                dbc.Button("Retrace", id="runs-trace-btn", color="secondary"),
            ]),
        ])), md=4),
    ], className="g-3")


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


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

@callback(
    Output("runs-banner", "children"),
    Output("runs-table-container", "children", allow_duplicate=True),
    Input("runs-rerun-btn", "n_clicks"),
    Input("runs-orphans-btn", "n_clicks"),
    State("runs-rerun-id", "value"),
    prevent_initial_call=True,
)
def run_action(rerun_clicks, orphan_clicks, fw_id):
    import dash

    from modena_portal.data.launchpad_queries import (
        defuse_orphans, list_workflows, rerun_firework,
    )

    trigger = dash.callback_context.triggered_id
    try:
        if trigger == "runs-rerun-btn":
            if fw_id is None:
                return dbc.Alert("Enter a firework id first.", color="warning",
                                 className="py-2"), dash.no_update
            rerun_firework(fw_id)
            msg = dbc.Alert(
                [f"Firework {int(fw_id)} re-queued. It stays READY until a "
                 f"worker runs it — ", html.Code("modena fw launch"), "."],
                color="success", className="py-2")
        else:
            n = defuse_orphans()
            msg = dbc.Alert(
                f"{n} orphaned firework(s) re-queued."
                if n else "No orphans found.",
                color="success" if n else "secondary", className="py-2")
        return msg, _build_table(list_workflows())
    except Exception as exc:                                   # noqa: BLE001
        return dbc.Alert(f"Failed: {exc}", color="danger",
                         className="py-2"), dash.no_update


@callback(
    Output("runs-banner", "children", allow_duplicate=True),
    Input("runs-trace-btn", "n_clicks"),
    State("runs-trace-id", "value"),
    prevent_initial_call=True,
)
def trace_action(_n, fw_id):
    from dash import dash_table

    from modena_portal.data.launchpad_queries import retrace

    if fw_id is None:
        return dbc.Alert("Enter a firework id first.", color="warning",
                         className="py-2")
    try:
        fws = retrace(fw_id)
    except Exception as exc:                                   # noqa: BLE001
        return dbc.Alert(f"Could not retrace: {exc}", color="danger",
                         className="py-2")

    rows = [{'fw_id': fw.fw_id, 'name': fw.name, 'state': fw.state}
            for fw in fws]
    return dbc.Card(dbc.CardBody([
        html.H6(f"{len(rows)} firework(s) leading to {int(fw_id)}"),
        dash_table.DataTable(
            data=rows,
            columns=[{'name': c, 'id': c} for c in ('fw_id', 'name', 'state')],
            style_cell={'textAlign': 'left', 'fontSize': '0.85rem'},
            style_table={'overflowX': 'auto'}, page_size=15,
        ),
    ]), className="mb-3")
