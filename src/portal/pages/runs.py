"""Runs page - lists all FireWorks simulation workflows.

Select a workflow to see its fireworks; each firework carries its own
actions.  The page used to ask for a "fw id" in free-text boxes while only
listing workflows, so the one number every action needed was nowhere on it.
"""
from datetime import datetime, timezone

import dash
from dash import ALL, Input, Output, State, callback, ctx, dcc, html, dash_table, no_update
import dash_bootstrap_components as dbc

from modena_portal.components.navbar import make_navbar
from modena_portal.data.helpers import duration, plural

dash.register_page(__name__, path="/runs", title="MoDeNa - Runs")

#: Poll interval while anything can still change.
POLL_MS = 5000

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

_STATE_BADGE = {
    'COMPLETED': 'success', 'RUNNING': 'primary', 'WAITING': 'warning',
    'READY': 'warning', 'RESERVED': 'warning', 'FIZZLED': 'danger',
    'PAUSED': 'danger', 'DEFUSED': 'danger',
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


def _now():
    # FireWorks stores naive UTC datetimes.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _elapsed(created, updated, active):
    """Run time: until now while active, until the last update otherwise."""
    if not created:
        return None
    end = _now() if active else updated
    return (end - created).total_seconds() if end else None


def _table_rows(workflows):
    from modena_portal.data.launchpad_queries import ACTIVE_STATES
    rows = []
    for r in workflows:
        active = r['state'] in ACTIVE_STATES
        took = duration(_elapsed(r['created_on'], r['updated_on'], active))
        rows.append({
            'id':        r.get('wf_id'),
            'name':      r['name'],
            'state':     r['state'],
            'n_fw':      r['n_fw'],
            'completed': r['completed'],
            'running':   r['running'],
            'waiting':   r['waiting'],
            'fizzled':   r['fizzled'],
            'created':   r['created_on'].strftime('%Y-%m-%d %H:%M') if r['created_on'] else '—',
            'duration':  f'{took} so far' if active and took != '—' else took,
        })
    return rows


def _any_active(workflows):
    from modena_portal.data.launchpad_queries import ACTIVE_STATES
    return any(r['state'] in ACTIVE_STATES for r in workflows)


def _build_table(rows):
    return dash_table.DataTable(
        id='runs-table',
        data=rows,
        columns=[
            {'name': 'Name',      'id': 'name'},
            {'name': 'State',     'id': 'state'},
            {'name': 'Fireworks', 'id': 'n_fw'},
            {'name': 'Completed', 'id': 'completed'},
            {'name': 'Running',   'id': 'running'},
            {'name': 'Waiting',   'id': 'waiting'},
            {'name': 'Fizzled',   'id': 'fizzled'},
            {'name': 'Created',   'id': 'created'},
            {'name': 'Duration',  'id': 'duration'},
        ],
        row_selectable='single',
        selected_rows=[],
        style_data_conditional=_STATE_STYLE_CONDITIONS + [
            {'if': {'state': 'active'}, 'backgroundColor': 'inherit',
             'border': '1px solid #dee2e6'},
        ],
        style_table={'overflowX': 'auto'},
        style_cell={'textAlign': 'left', 'padding': '8px', 'cursor': 'pointer'},
        style_header={'fontWeight': 'bold', 'backgroundColor': '#f8f9fa'},
        filter_action='native',
        filter_options={'case': 'insensitive', 'placeholder_text': 'filter…'},
        css=[{'selector': '.dash-filter--case', 'rule': 'display: none'}],
        sort_action='native',
        page_size=20,
    )


def _empty_message(rows):
    return (dbc.Alert("No workflows found in the FireWorks launchpad.", color="secondary")
            if not rows else None)


_PICK_HINT = html.Div("Select a workflow above to see its fireworks.",
                      className="text-muted")


def layout():
    try:
        from modena_portal.data.launchpad_queries import list_workflows
        workflows = list_workflows()
    except Exception as e:
        return dbc.Container([
            make_navbar(active='runs'),
            dbc.Alert(f"Could not connect to FireWorks launchpad: {e}", color="danger"),
        ])

    rows = _table_rows(workflows)
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
        dcc.Interval(id='runs-poll', interval=POLL_MS,
                     disabled=not _any_active(workflows)),
        dcc.Store(id='runs-selected-wf', data=None),
        dcc.Store(id='runs-action-tick', data=0),
        html.Div(id="runs-banner"),
        html.Div(id="runs-empty", children=_empty_message(rows)),
        _build_table(rows),
        html.Div(id="runs-poll-note", className="text-muted small mt-1",
                 children=_poll_note(_any_active(workflows))),
        html.Hr(),
        html.Div(id='runs-fw-panel', children=_PICK_HINT),
        html.Hr(),
        _make_orphans_card(),
    ], fluid=True)


def _poll_note(active):
    return (f"Updating every {POLL_MS // 1000} s while work is queued or running."
            if active else None)


def _make_orphans_card():
    """defuse_orphans() needs no firework id, so it stays a page-level action.

    Reset is deliberately absent -- it destroys every firework and its
    history, and `modena fw reset` already guards it behind a confirmation.
    """
    return dbc.Card(dbc.CardBody([
        html.H6("Recover orphans"),
        html.P("Re-queues fireworks whose worker process died — they would "
               "otherwise sit in RUNNING forever.",
               className="text-muted small"),
        dbc.Button("Defuse orphans", id="runs-orphans-btn", color="warning"),
    ]), style={'maxWidth': '32rem'})


# ---------------------------------------------------------------------------
# Workflow table: refresh on demand, after actions, and by polling
# ---------------------------------------------------------------------------

@callback(
    Output('runs-table', 'data'),
    Output('runs-table', 'selected_rows', allow_duplicate=True),
    Output('runs-empty', 'children'),
    Output('runs-poll', 'disabled'),
    Output('runs-poll-note', 'children'),
    Input('runs-refresh-btn', 'n_clicks'),
    Input('runs-poll', 'n_intervals'),
    Input('runs-action-tick', 'data'),
    State('runs-selected-wf', 'data'),
    prevent_initial_call=True,
)
def refresh_runs(_n, _tick, _action, wf_id):
    # Only the table's data is replaced, so sorting and filtering survive
    # every refresh; the selection is re-pointed at the same workflow, since
    # a new workflow at the top shifts every row index.
    try:
        from modena_portal.data.launchpad_queries import list_workflows
        workflows = list_workflows()
    except Exception as e:                                     # noqa: BLE001
        return (no_update, no_update,
                dbc.Alert(f"Could not connect to FireWorks launchpad: {e}", color="danger"),
                True, None)
    rows = _table_rows(workflows)
    active = _any_active(workflows)
    return rows, row_index(rows, wf_id), _empty_message(rows), not active, _poll_note(active)


def row_index(rows, wf_id):
    """selected_rows for a workflow: its index in the table's data.

    DataTable draws the radio button from selected_rows, which are indices
    into data -- so they must be recomputed whenever data is replaced.
    selected_row_ids looks writable but is derived; setting it shows nothing.
    """
    return [i for i, r in enumerate(rows or []) if r.get('id') == wf_id][:1]


@callback(
    Output('runs-selected-wf', 'data'),
    Output('runs-table', 'selected_rows'),
    Input('runs-table', 'selected_rows'),
    Input('runs-table', 'active_cell'),
    State('runs-table', 'data'),
    prevent_initial_call=True,
)
def select_workflow(selected_rows, active_cell, rows):
    """A click anywhere in a row selects it, not only on the radio button.

    One callback both records the workflow and moves the radio button.  Two
    callbacks -- selected_rows -> store, store -> selected_rows -- form a
    cycle, which Dash rejects ("Dependency Cycle Found") in debug mode; a
    callback may read and write the same property, two may not feed each
    other.
    """
    prop = ctx.triggered[0]['prop_id'] if ctx.triggered else ''
    if prop.endswith('.active_cell'):
        wf_id = (active_cell or {}).get('row_id')
    elif selected_rows and rows and selected_rows[0] < len(rows):
        wf_id = rows[selected_rows[0]].get('id')
    else:
        wf_id = None
    if wf_id is None:
        return no_update, no_update
    wanted = row_index(rows, wf_id)
    return wf_id, (no_update if (selected_rows or []) == wanted else wanted)


# ---------------------------------------------------------------------------
# Fireworks of the selected workflow
# ---------------------------------------------------------------------------

@callback(
    Output('runs-fw-panel', 'children'),
    Input('runs-selected-wf', 'data'),
    Input('runs-poll', 'n_intervals'),
    Input('runs-action-tick', 'data'),
    Input('runs-refresh-btn', 'n_clicks'),
    prevent_initial_call=True,
)
def show_fireworks(wf_id, _tick, _action, _refresh):
    if wf_id is None:
        return _PICK_HINT
    try:
        from modena_portal.data.launchpad_queries import ACTIVE_STATES, list_fireworks
        fireworks = list_fireworks(wf_id)
    except Exception as exc:                                   # noqa: BLE001
        return dbc.Alert(f"Could not load fireworks: {exc}", color="danger")
    if not fireworks:
        return dbc.Alert("This workflow no longer exists.", color="secondary")
    return make_fireworks_table(fireworks, ACTIVE_STATES)


def make_fireworks_table(fireworks, active_states):
    header = html.Thead(html.Tr([html.Th(h) for h in
                                 ('fw id', 'Name', 'State', 'Duration', '')]))
    body = []
    for fw in fireworks:
        active = fw['state'] in active_states
        actions = [dbc.Button("Trace", id={'type': 'fw-trace', 'index': fw['fw_id']},
                              color="secondary", size="sm", outline=True,
                              title="Everything that had to finish before this firework")]
        if fw['state'] == 'FIZZLED':
            actions.insert(0, dbc.Button(
                "Rerun", id={'type': 'fw-rerun', 'index': fw['fw_id']},
                color="primary", size="sm", className="me-2",
                title="Re-queue this firework once the cause is fixed"))
        body.append(html.Tr([
            html.Td(fw['fw_id'], className="font-monospace"),
            html.Td(fw['name']),
            html.Td(dbc.Badge(fw['state'], color=_STATE_BADGE.get(fw['state'], 'secondary'))),
            html.Td(duration(_elapsed(fw['created_on'], fw['updated_on'], active))),
            html.Td(actions, className="text-end text-nowrap"),
        ]))
    return html.Div([
        html.H5(plural(len(fireworks), 'firework') + " in this workflow"),
        dbc.Table([header, html.Tbody(body)], size="sm", hover=True,
                  responsive=True, className="align-middle"),
    ])


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

@callback(
    Output("runs-banner", "children"),
    Output("runs-action-tick", "data"),
    Input({'type': 'fw-rerun', 'index': ALL}, 'n_clicks'),
    Input({'type': 'fw-trace', 'index': ALL}, 'n_clicks'),
    Input("runs-orphans-btn", "n_clicks"),
    State("runs-action-tick", "data"),
    prevent_initial_call=True,
)
def run_action(_reruns, _traces, _orphans, tick):
    # Pattern-matched buttons are re-created whenever the fireworks panel
    # refreshes, which fires this callback with n_clicks None: not a click.
    if not ctx.triggered or not ctx.triggered[0]['value']:
        return no_update, no_update

    from modena_portal.data.launchpad_queries import (
        defuse_orphans, rerun_firework, retrace,
    )

    trigger = ctx.triggered_id
    tick = (tick or 0) + 1
    try:
        if trigger == "runs-orphans-btn":
            n = defuse_orphans()
            return dbc.Alert(
                f"{plural(n, 'orphaned firework')} re-queued." if n else "No orphans found.",
                color="success" if n else "secondary", className="py-2",
                dismissable=True), tick
        fw_id = int(trigger['index'])
        if trigger['type'] == 'fw-rerun':
            rerun_firework(fw_id)
            return dbc.Alert(
                [f"Firework {fw_id} re-queued. It stays READY until a "
                 f"worker runs it — ", html.Code("modena fw launch"), "."],
                color="success", className="py-2", dismissable=True), tick
        return _trace_card(fw_id, retrace(fw_id)), no_update
    except Exception as exc:                                   # noqa: BLE001
        return dbc.Alert(f"Failed: {exc}", color="danger", className="py-2",
                         dismissable=True), no_update


def _trace_card(fw_id, fws):
    rows = [{'fw id': fw.fw_id, 'name': fw.name, 'state': fw.state} for fw in fws]
    return dbc.Alert([
        html.H6(f"{plural(len(rows), 'firework')} leading to {fw_id}"),
        dash_table.DataTable(
            data=rows,
            columns=[{'name': c, 'id': c} for c in ('fw id', 'name', 'state')],
            style_cell={'textAlign': 'left', 'fontSize': '0.85rem'},
            style_table={'overflowX': 'auto'}, page_size=15,
        ),
    ], color="light", dismissable=True, className="mb-3")
