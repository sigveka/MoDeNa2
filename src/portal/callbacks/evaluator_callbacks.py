"""Callbacks for the Model Evaluator page.

The result follows the inputs: it is computed when the page opens and again
whenever an input changes (on slider release, or Enter / leaving a number
box).  An Evaluate button used to stand between changing a value and seeing
its effect, which is the one thing this page exists to show.
"""
from dash import ALL, Input, Output, State, callback, dash_table, html, no_update
import dash_bootstrap_components as dbc

from modena_portal.data.helpers import SIG_FIGS, fmt, ordered_names, unit_text
from modena_portal.data.queries import get_model


def _rounded(x):
    return None if x is None else float(f'{x:.{SIG_FIGS}g}')


# ---------------------------------------------------------------------------
# Sync: slider → number input
# ---------------------------------------------------------------------------

@callback(
    Output({'type': 'eval-input', 'index': ALL}, 'value'),
    Input({'type': 'eval-slider', 'index': ALL}, 'value'),
    State({'type': 'eval-input', 'index': ALL}, 'value'),
    prevent_initial_call=True,
)
def sync_slider_to_input(slider_values, input_values):
    # A slider step lands on values like 0.4165239571818414; the box shows
    # SIG_FIGS digits.  A value typed into the box is left exactly as typed:
    # when it already agrees with the slider at that precision, keep it.
    return [i if i is not None and _rounded(i) == _rounded(s) else _rounded(s)
            for s, i in zip(slider_values, input_values)]


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
    Input({'type': 'eval-input', 'index': ALL}, 'value'),
    State({'type': 'eval-input', 'index': ALL}, 'id'),
    State('eval-model-id', 'data'),
    State('eval-lib-ok', 'data'),
)
def run_evaluation(input_values, input_ids, model_id, lib_ok):
    if not model_id or not lib_ok or not input_ids:
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

    declared = getattr(model, 'outputs', None) or {}
    order = [n for n in ordered_names(declared) if n in outputs] + \
            [n for n in outputs if n not in declared]
    rows = [{'Output': k, 'Value': fmt(outputs[k]),
             'Unit': (unit_text(declared[k]) if k in declared else None) or '—'}
            for k in order]
    table = dash_table.DataTable(
        data=rows,
        columns=[{'name': c, 'id': c} for c in ['Output', 'Value', 'Unit']],
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
        html.Li(f"{n} = {fmt(x)}   (trained on {fmt(bounds[n][0])} … {fmt(bounds[n][1])})")
        for n, x in inputs.items()
        if n in bounds and not bounds[n][0] <= x <= bounds[n][1]
    ]
    return dbc.Alert([
        html.Strong("Outside the range this surrogate was trained on."),
        html.Ul(outside, className="mb-1 mt-2") if outside else None,
        html.Small("In a simulation, MoDeNa would run new exact simulations here "
                   "and refit; the portal only evaluates the existing fit."),
    ], color="warning")
