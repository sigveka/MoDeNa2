"""Fit data DataTable component."""
from dash import dash_table
from modena_portal.data.helpers import transpose_fitdata


def make_fitdata_table(fitdata: dict):
    """Return a paginated DataTable from fitData {col: [vals]}."""
    rows = transpose_fitdata(fitdata)
    if not rows:
        return None

    columns = [{'name': k, 'id': k} for k in fitdata.keys()]
    return dash_table.DataTable(
        data=rows,
        columns=columns,
        page_size=50,
        style_table={'overflowX': 'auto'},
        style_cell={'textAlign': 'right', 'minWidth': '80px'},
        style_header={'fontWeight': 'bold'},
    )
