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

    # A cleared field used to be evaluated as 0.0 -- outside most models'
    # trained range, so the answer was an out-of-bounds error naming no input,
    # or worse, a plausible number for a point nobody asked about.
    names = [id_obj['index'] for id_obj in input_ids]
    blank = [n for n, val in zip(names, input_values) if val is None]
    if blank:
        return dbc.Alert(f"Enter a value for: {', '.join(blank)}.", color="warning")
    inputs_dict = {n: float(val) for n, val in zip(names, input_values)}

    try:
        model = get_model(model_id)
        outputs = model.callModel(inputs_dict)
    except Exception as e:
        return _evaluation_error(e, model_id, inputs_dict)

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


def _evaluation_error(exc, model_id, inputs):
    """Explain a failed evaluation; out-of-bounds names the offending inputs.

    OutOfBounds used to reach the page as its raw argument tuple:
    "('Surrogate model is used out-of-bounds', <BackwardMappingModel ...>, 200)".
    """
    from modena.Strategy import OutOfBounds
    if not isinstance(exc, OutOfBounds):
        return dbc.Alert([html.Strong("Evaluation failed: "), str(exc)], color="danger")

    try:
        bounds = {n: (v.min, v.max) for n, v in get_model(model_id).inputs.items()}
    except Exception:                                          # noqa: BLE001
        bounds = {}
    outside = [
        html.Li(f"{n} = {x:.6g}   (trained on {bounds[n][0]:.6g} … {bounds[n][1]:.6g})")
        for n, x in inputs.items()
        if n in bounds and not bounds[n][0] <= x <= bounds[n][1]
    ]
    return dbc.Alert([
        html.Strong("Outside the range this surrogate was trained on."),
        html.Ul(outside, className="mb-1 mt-2") if outside else None,
        html.Small("In a simulation, MoDeNa would run new exact simulations here "
                   "and refit; the portal only evaluates the existing fit."),
    ], color="warning")
