"""Slider + number input form per input variable for the evaluator page."""
from dash import dcc, html
import dash_bootstrap_components as dbc


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
    for name, entry in sorted(inputs.items(), key=lambda kv: (kv[1].argPos or 0)):
        lo = entry.min if entry.min is not None else 0.0
        hi = entry.max if entry.max is not None else 1.0
        mid = (lo + hi) / 2.0

        # Avoid zero-length range
        if lo >= hi:
            hi = lo + 1.0

        step = (hi - lo) / 100.0

        row = dbc.Row([
            dbc.Col(html.Label(name, style={'fontWeight': 'bold'}), width=2),
            dbc.Col(
                dcc.Slider(
                    id={'type': 'eval-slider', 'index': name},
                    min=lo,
                    max=hi,
                    step=step,
                    value=mid,
                    marks=None,
                    tooltip={'placement': 'bottom', 'always_visible': False},
                ),
                width=7,
            ),
            dbc.Col(
                dbc.Input(
                    id={'type': 'eval-input', 'index': name},
                    type='number',
                    value=mid,
                    min=lo,
                    max=hi,
                    step=step,
                    debounce=True,
                ),
                width=3,
            ),
        ], className="mb-3 align-items-center")

        rows.append(row)

    return html.Div(rows)
