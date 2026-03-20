"""Parameter table component - joins model.parameters (positional) with
surrogateFunction.parameters (MapField with argPos)."""
import dash_bootstrap_components as dbc
from dash import dash_table
from modena_portal.data.helpers import get_parameter_table


def make_parameter_table(model):
    """Return a DataTable of model parameters (name, value, min, max)."""
    rows = get_parameter_table(model)
    if not rows:
        return dbc.Alert("No parameters fitted yet.", color="secondary")

    display = [
        {
            'Name': r['name'],
            'Value': f"{r['value']:.6g}" if r['value'] is not None else '-',
            'Min': f"{r['min']:.6g}" if r['min'] is not None else '-',
            'Max': f"{r['max']:.6g}" if r['max'] is not None else '-',
            'ArgPos': r['argPos'],
        }
        for r in rows
    ]

    return dash_table.DataTable(
        data=display,
        columns=[{'name': c, 'id': c} for c in ['Name', 'Value', 'Min', 'Max', 'ArgPos']],
        style_table={'overflowX': 'auto'},
        style_cell={'textAlign': 'left'},
    )
