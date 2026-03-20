"""Callbacks for the Model Detail page."""
from dash import Input, Output, State, callback, ctx, no_update
import dash_bootstrap_components as dbc

from modena_portal.components.fitdata_table import make_fitdata_table
from modena_portal.components.fitdata_plot import make_fitdata_plot, build_scatter
from modena_portal.data.queries import get_fitdata, save_documentation


# ---------------------------------------------------------------------------
# Live documentation preview
# ---------------------------------------------------------------------------

@callback(
    Output('doc-preview', 'children'),
    Input('doc-textarea', 'value'),
)
def update_doc_preview(text):
    return text or ''


# ---------------------------------------------------------------------------
# Save documentation
# ---------------------------------------------------------------------------

@callback(
    Output('doc-save-feedback', 'children'),
    Input('doc-save-btn', 'n_clicks'),
    State('doc-textarea', 'value'),
    State('detail-model-id', 'data'),
    prevent_initial_call=True,
)
def save_doc(n_clicks, text, model_id):
    if not n_clicks or not model_id:
        return no_update
    try:
        save_documentation(model_id, text or '')
        return dbc.Alert("Documentation saved.", color="success", duration=3000)
    except Exception as e:
        return dbc.Alert(f"Save failed: {e}", color="danger")


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
        doc = get_fitdata(model_id)
        fitdata = doc.fitData if hasattr(doc, 'fitData') else {}
    except Exception as e:
        return dbc.Alert(f"Could not load fit data: {e}", color="danger")

    if not fitdata:
        return dbc.Alert("No fit data available for this model.", color="secondary")

    table = make_fitdata_table(fitdata)
    plot_layout = make_fitdata_plot(fitdata)

    from dash import html
    return html.Div([
        plot_layout,
        html.Hr(),
        table,
    ])


# ---------------------------------------------------------------------------
# Fit data scatter plot update
# ---------------------------------------------------------------------------

@callback(
    Output('fitdata-graph', 'figure'),
    Input('fitdata-x-axis', 'value'),
    Input('fitdata-y-axis', 'value'),
    State('detail-model-id', 'data'),
    prevent_initial_call=True,
)
def update_fitdata_plot(x_col, y_col, model_id):
    if not model_id or not x_col or not y_col:
        return no_update
    try:
        doc = get_fitdata(model_id)
        fitdata = doc.fitData if hasattr(doc, 'fitData') else {}
        return build_scatter(fitdata, x_col, y_col)
    except Exception:
        return no_update
