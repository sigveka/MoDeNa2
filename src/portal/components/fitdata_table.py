"""Fit data DataTable component.

Values show SIG_FIGS significant figures and stay numeric, so sorting is
by value; hovering a cell shows it at full precision.  The table used to
print raw floats, so 0.01 sat next to 0.010000003533967445.
"""
from dash import dash_table
from dash.dash_table.Format import Format, Scheme, Trim

from modena_portal.data.helpers import SIG_FIGS, transpose_fitdata


def make_fitdata_table(fitdata: dict, columns: list[str], labels: dict,
                       n_initial: int | None = None):
    """Return a paginated DataTable, columns in the given order.

    '#' is the sample number used by the plots' hover text and the Fit
    Quality tab; 'origin' appears when the initial design's size is known.
    """
    rows = transpose_fitdata({c: fitdata[c] for c in columns})
    if not rows:
        return None

    known = n_initial is not None and 0 < n_initial <= len(rows)
    for i, row in enumerate(rows):
        row['#'] = i
        if known:
            row['origin'] = 'initial' if i < n_initial else 'later'

    number = Format(precision=SIG_FIGS, scheme=Scheme.decimal_or_exponent, trim=Trim.yes)
    table_columns = [{'name': '#', 'id': '#', 'type': 'numeric'}]
    if known:
        table_columns.append({'name': 'origin', 'id': 'origin'})
    table_columns += [{'name': labels.get(c, c), 'id': c, 'type': 'numeric',
                       'format': number} for c in columns]

    return dash_table.DataTable(
        data=rows,
        columns=table_columns,
        tooltip_data=[{c: {'value': repr(row[c]), 'type': 'text'} for c in columns}
                      for row in rows],
        tooltip_delay=300,
        tooltip_duration=None,
        page_size=50,
        sort_action='native',
        style_table={'overflowX': 'auto'},
        style_cell={'textAlign': 'right', 'minWidth': '80px'},
        style_header={'fontWeight': 'bold'},
    )
