"""Callbacks for the Model Detail page."""
from dash import Input, Output, State, callback, dcc, html, no_update
import dash_bootstrap_components as dbc

from modena_portal.components.fitdata_table import make_fitdata_table
from modena_portal.components.fitdata_plot import (
    build_scatter, default_axes, make_fitdata_plot,
)
from modena_portal.data.helpers import ordered_names, with_unit
from modena_portal.data.queries import get_fitdata, get_model, initial_design_size


def fitdata_layout(model, fitdata):
    """(column order, labels, n_initial) for a model's fit data.

    Inputs in argPos order, then outputs, then anything else stored --
    storage order put the output first.  Labels carry declared units.
    """
    inputs = ordered_names(model.inputs or {})
    outputs = ordered_names(model.outputs or {})
    columns = [c for c in inputs + outputs if c in fitdata]
    columns += [c for c in fitdata if c not in columns]
    entries = {**dict(model.inputs or {}), **dict(model.outputs or {})}
    labels = {c: with_unit(c, entries.get(c)) for c in columns}
    return columns, labels, inputs, outputs


# ---------------------------------------------------------------------------
# Lazy-load fit data on tab switch
# ---------------------------------------------------------------------------

@callback(
    Output('fitdata-content', 'children'),
    Input('detail-tabs', 'active_tab'),
    State('detail-model-id', 'data'),
    prevent_initial_call=True,
)
def load_fitdata_on_tab(active_tab, model_id):
    if active_tab != 'tab-fitdata' or not model_id:
        return no_update

    try:
        model = get_model(model_id)
        doc = get_fitdata(model_id)
        fitdata = dict(doc.fitData) if hasattr(doc, 'fitData') else {}
    except Exception as e:
        return dbc.Alert(f"Could not load fit data: {e}", color="danger")

    if not fitdata:
        return dbc.Alert("No fit data available for this model.", color="secondary")

    columns, labels, inputs, outputs = fitdata_layout(model, fitdata)
    n_initial = initial_design_size(model)
    x_col, y_col = default_axes(inputs, outputs, columns, fitdata)

    return html.Div([
        dcc.Store(id='fitdata-meta', data={'n_initial': n_initial, 'labels': labels}),
        make_fitdata_plot(fitdata, labels, x_col, y_col, n_initial),
        html.Hr(),
        make_fitdata_table(fitdata, columns, labels, n_initial),
    ])


# ---------------------------------------------------------------------------
# Fit data scatter plot update
# ---------------------------------------------------------------------------

@callback(
    Output('fitdata-graph', 'figure'),
    Input('fitdata-x-axis', 'value'),
    Input('fitdata-y-axis', 'value'),
    State('fitdata-meta', 'data'),
    State('detail-model-id', 'data'),
    prevent_initial_call=True,
)
def update_fitdata_plot(x_col, y_col, meta, model_id):
    if not model_id or not x_col or not y_col:
        return no_update
    meta = meta or {}
    try:
        doc = get_fitdata(model_id)
        fitdata = doc.fitData if hasattr(doc, 'fitData') else {}
        return build_scatter(fitdata, x_col, y_col, meta.get('n_initial'),
                             meta.get('labels'))
    except Exception:
        return no_update
