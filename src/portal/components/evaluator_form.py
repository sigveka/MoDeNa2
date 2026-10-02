"""Slider + number input form per input variable for the evaluator page.

One number box per input.  Dash 4's slider adds its own direct-input box
(allow_direct_input), which sat next to ours too narrow to show its value --
two boxes for one number, one of them truncated.  The slider's is off.
"""
from dash import dcc, html
import dash_bootstrap_components as dbc

from modena.Integration import placeholder_value
from modena_portal.data.helpers import fmt, is_fixed, ordered_names, unit_text


def make_evaluator_form(model):
    """
    Return a form with one slider + synced number input per input variable.

    IDs follow the pattern:
      {"type": "eval-slider", "index": <input_name>}
      {"type": "eval-input",  "index": <input_name>}

    so that pattern-matching callbacks can handle them generically.
    """
    inputs = model.inputs  # MapField[name -> MinMaxArgPosOpt]

    if not inputs:
        return dbc.Alert("No inputs defined for this model.", color="warning")

    rows = []
    for name in ordered_names(inputs):
        entry = inputs[name]
        lo = entry.min if entry.min is not None else 0.0
        hi = entry.max if entry.max is not None else 1.0
        fixed = is_fixed(lo, hi)
        start = lo if fixed else placeholder_value(lo, hi)
        unit = unit_text(entry)

        label = html.Div([
            html.Label(name, style={'fontWeight': 'bold'}),
            html.Span(f' [{unit}]', className="text-muted") if unit else None,
            html.Div(f'fixed at {fmt(lo)}', className="small text-warning",
                     title="The model was only trained at this value.") if fixed else None,
        ])
        slider = dcc.Slider(
            id={'type': 'eval-slider', 'index': name},
            # A fixed input has no range to slide over; the slider stays as a
            # disabled marker and the number box still accepts other values
            # (which the evaluator reports as out of bounds).
            min=lo, max=hi if not fixed else lo + 1.0,
            step=None if fixed else (hi - lo) / 100.0,
            value=start,
            marks={lo: fmt(lo), hi: fmt(hi)} if not fixed else {lo: fmt(lo)},
            disabled=fixed,
            allow_direct_input=False,
            updatemode='mouseup',
            tooltip={'placement': 'bottom', 'always_visible': False},
        )
        rows.append(dbc.Row([
            dbc.Col(label, md=2),
            dbc.Col(slider, md=7),
            dbc.Col(dbc.Input(
                id={'type': 'eval-input', 'index': name},
                type='number', value=start, step='any', debounce=True,
            ), md=3),
        ], className="mb-3 align-items-center"))

    return html.Div(rows)
