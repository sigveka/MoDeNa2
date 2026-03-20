"""Callbacks for the Model Evaluator page."""
from dash import Input, Output, State, callback, no_update, ALL, ctx
import dash_bootstrap_components as dbc
from dash import dash_table, html

from modena_portal.data.queries import get_model


# ---------------------------------------------------------------------------
# Sync: slider → number input
# ---------------------------------------------------------------------------

@callback(
    Output({'type': 'eval-input', 'index': ALL}, 'value'),
    Input({'type': 'eval-slider', 'index': ALL}, 'value'),
    prevent_initial_call=True,
)
def sync_slider_to_input(slider_values):
    return slider_values


# ---------------------------------------------------------------------------
# Sync: number input → slider
# ---------------------------------------------------------------------------

@callback(
    Output({'type': 'eval-slider', 'index': ALL}, 'value'),
    Input({'type': 'eval-input', 'index': ALL}, 'value'),
    prevent_initial_call=True,
)
def sync_input_to_slider(input_values):
    return input_values


# ---------------------------------------------------------------------------
# Evaluate model
# ---------------------------------------------------------------------------

@callback(
    Output('eval-result', 'children'),
    Input('eval-button', 'n_clicks'),
    State({'type': 'eval-input', 'index': ALL}, 'value'),
    State({'type': 'eval-input', 'index': ALL}, 'id'),
    State('eval-model-id', 'data'),
    prevent_initial_call=True,
)
def run_evaluation(n_clicks, input_values, input_ids, model_id):
    if not n_clicks or not model_id:
        return no_update

    # Build inputs dict from pattern-matched ids
    inputs_dict = {
        id_obj['index']: float(val) if val is not None else 0.0
        for id_obj, val in zip(input_ids, input_values)
    }

    try:
        model = get_model(model_id)
        outputs = model.callModel(inputs_dict)
    except Exception as e:
        return dbc.Alert(
            [html.Strong("Evaluation failed: "), str(e)],
            color="danger",
        )

    rows = [{'Output': k, 'Value': f"{v:.8g}"} for k, v in outputs.items()]
    table = dash_table.DataTable(
        data=rows,
        columns=[{'name': c, 'id': c} for c in ['Output', 'Value']],
        style_cell={'textAlign': 'left', 'padding': '8px'},
        style_header={'fontWeight': 'bold'},
    )

    return html.Div([
        html.H5("Results"),
        table,
    ])
