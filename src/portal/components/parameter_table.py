"""Parameter table component - joins model.parameters (by name) with
surrogateFunction.parameters (bounds, declaration order)."""
import dash_bootstrap_components as dbc
from dash import dash_table
from modena_portal.data.helpers import fmt, get_parameter_table


def make_parameter_table(model):
    """Return a DataTable of model parameters (name, value, min, max).

    Argument positions are in the Overview tab's fold-out, with the inputs'
    and outputs': only C and Fortran callers need them.
    """
    rows = get_parameter_table(model)
    if not rows:
        return dbc.Alert("No parameters fitted yet.", color="secondary")

    display = [
        {'Name': r['name'], 'Value': fmt(r['value']),
         'Min': fmt(r['min']), 'Max': fmt(r['max'])}
        for r in rows
    ]

    return dash_table.DataTable(
        data=display,
        columns=[{'name': c, 'id': c} for c in ['Name', 'Value', 'Min', 'Max']],
        style_table={'overflowX': 'auto'},
        style_cell={'textAlign': 'left'},
    )
