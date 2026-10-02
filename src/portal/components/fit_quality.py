"""Fit-quality panel: how good are the parameters currently stored?

Before this, the portal reported training state as a three-value badge --
Untrained / Library missing / Trained -- derived only from "is `parameters`
non-empty and does the .so exist".  It never said whether the fit was any
good, even though SurrogateModel.error() and the n_samples_fitted field
already made both answerable.

Every point and bar names its sample and that sample's inputs, and the
largest residuals are listed: a bad fit is only actionable once you can see
*where* it is bad.
"""
from dash import dash_table, dcc, html
import dash_bootstrap_components as dbc
import plotly.graph_objects as go

from modena_portal.data.helpers import fmt, plural, residual_sample

_BAR, _WORST = '#636efa', '#dc3545'


def _stat(label, value, color=None):
    return dbc.Col(html.Div([
        html.Div(label, className="text-muted small"),
        html.Div(value, className=f"h4 mb-0 {color or ''}"),
    ]), width="auto", className="me-4")


def sample_descriptions(fitdata: dict, input_names: list[str]) -> list[str]:
    """'D = 0.01, rho0 = 3.5, ...' per sample, for hover text."""
    n = len(fitdata[input_names[0]]) if input_names else 0
    return [', '.join(f'{k} = {fmt(fitdata[k][i])}' for k in input_names)
            for i in range(n)]


def make_quality_summary(quality: dict):
    """Headline numbers: aggregated error, sample counts, staleness."""
    stale = quality['stale']

    staleness = dbc.Alert(
        [
            html.Strong("Parameters are stale. "),
            f"{plural(quality['n_new_samples'], 'sample')} collected since the "
            f"last fit ({quality['n_samples_fitted']} of "
            f"{quality['n_samples']} used). Refit to use all the data.",
        ],
        color="warning", className="py-2",
    ) if stale else dbc.Alert(
        f"Parameters reflect all {plural(quality['n_samples'], 'stored sample')}.",
        color="success", className="py-2",
    )

    return html.Div([
        dbc.Row([
            _stat(f"{quality['metric']} (max)", fmt(quality['error'])),
            _stat("Samples", str(quality['n_samples'])),
            _stat("Used in last fit", str(quality['n_samples_fitted']),
                  color="text-warning" if stale else None),
        ], className="mb-3"),
        staleness,
    ])


def make_parity_plot(preds: dict, samples: list[str] | None = None,
                     plot_id: str = "quality-parity"):
    """Measured vs predicted, one trace per output, with the y=x reference.

    A parity plot is the fastest read on fit quality: points off the diagonal
    are exactly the samples the surrogate gets wrong, and systematic curvature
    shows the functional form is wrong rather than the parameters.
    """
    fig = go.Figure()
    lo = hi = None

    for name, (measured, predicted) in preds.items():
        n = len(measured)
        fig.add_trace(go.Scatter(
            x=measured, y=predicted, mode='markers', name=name,
            marker={'size': 9, 'opacity': 0.8},
            customdata=[[i, (samples or [''] * n)[i]] for i in range(n)],
            hovertemplate=f'sample %{{customdata[0]}}: {name}<br>measured %{{x:.6g}}'
                          f'<br>predicted %{{y:.6g}}<br>%{{customdata[1]}}<extra></extra>',
        ))
        vals = list(measured) + list(predicted)
        if vals:
            lo = min(vals) if lo is None else min(lo, min(vals))
            hi = max(vals) if hi is None else max(hi, max(vals))

    if lo is not None and hi is not None:
        pad = (hi - lo) * 0.05 or 1.0
        fig.add_trace(go.Scatter(
            x=[lo - pad, hi + pad], y=[lo - pad, hi + pad],
            mode='lines', name='perfect fit',
            line={'dash': 'dash', 'width': 1, 'color': '#888'},
            hoverinfo='skip',
        ))

    fig.update_layout(
        xaxis_title='measured (exact simulation)',
        yaxis_title='predicted (surrogate)',
        margin={'l': 60, 'r': 20, 't': 30, 'b': 50},
        height=420, legend={'orientation': 'h', 'y': -0.2},
    )
    return dcc.Graph(id=plot_id, figure=fig)


def _worst(residuals):
    return max(range(len(residuals)), key=lambda i: abs(residuals[i]), default=None)


def make_residual_plot(quality: dict, output_names: list[str],
                       samples: list[str] | None = None,
                       plot_id: str = "quality-residuals"):
    """Residual per sample and output, the largest one in red."""
    residuals = quality['residuals']
    n_out = len(output_names)
    worst = _worst(residuals)
    custom, ticks = [], []
    for r in range(len(residuals)):
        s, o = residual_sample(r, n_out)
        label = f'{s}' if n_out == 1 else f'{s}:{output_names[o]}'
        ticks.append(label)
        custom.append([label, (samples[s] if samples and s < len(samples) else '')])

    fig = go.Figure(go.Bar(
        x=list(range(len(residuals))), y=residuals, customdata=custom,
        marker={'color': [_WORST if r == worst else _BAR for r in range(len(residuals))]},
        hovertemplate='sample %{customdata[0]}<br>residual %{y:.6g}'
                      '<br>%{customdata[1]}<extra></extra>',
    ))
    fig.add_hline(y=0, line={'width': 1, 'color': '#888'})
    fig.update_layout(
        xaxis={'title': 'sample' if n_out == 1 else 'sample:output',
               'tickmode': 'array', 'tickvals': list(range(len(residuals))),
               'ticktext': ticks} if len(residuals) <= 40 else
              {'title': 'sample' if n_out == 1 else 'sample × output'},
        yaxis_title=f"residual ({quality['metric']})",
        margin={'l': 60, 'r': 20, 't': 30, 'b': 50}, height=300,
        showlegend=False,
    )
    return dcc.Graph(id=plot_id, figure=fig)


def make_worst_table(quality: dict, output_names: list[str], fitdata: dict,
                     input_names: list[str], labels: dict | None = None, k: int = 5):
    """The k largest residuals with the inputs that produced them."""
    residuals = quality['residuals']
    labels = labels or {}
    order = sorted(range(len(residuals)), key=lambda i: -abs(residuals[i]))[:k]
    rows = []
    for r in order:
        s, o = residual_sample(r, len(output_names))
        row = {'sample': s, 'output': output_names[o] if output_names else '',
               'residual': fmt(residuals[r])}
        row.update({labels.get(n, n): fmt(fitdata[n][s]) for n in input_names
                    if n in fitdata and s < len(fitdata[n])})
        rows.append(row)
    columns = ['sample', 'output', 'residual'] + [labels.get(n, n) for n in input_names]
    return html.Div([
        html.H6(f"Largest residuals (top {len(rows)})"),
        dash_table.DataTable(
            data=rows, columns=[{'name': c, 'id': c} for c in columns],
            style_cell={'textAlign': 'left', 'fontFamily': 'monospace',
                        'fontSize': '0.85rem'},
            style_table={'overflowX': 'auto'},
            style_data_conditional=[{'if': {'row_index': 0}, 'color': _WORST,
                                     'fontWeight': 'bold'}],
        ),
        html.P("Sample numbers match the # column on the Fit Data tab.",
               className="text-muted small mt-1"),
    ], className="mt-3")
