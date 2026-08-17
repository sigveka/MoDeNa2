"""Fit-quality panel: how good are the parameters currently stored?

Before this, the portal reported training state as a three-value badge --
Untrained / Library missing / Trained -- derived only from "is `parameters`
non-empty and does the .so exist".  It never said whether the fit was any
good, even though SurrogateModel.error() and the n_samples_fitted field
already made both answerable.
"""
from dash import dcc, html
import dash_bootstrap_components as dbc
import plotly.graph_objects as go


def _stat(label, value, color=None):
    return dbc.Col(html.Div([
        html.Div(label, className="text-muted small"),
        html.Div(value, className=f"h4 mb-0 {color or ''}"),
    ]), width="auto", className="me-4")


def make_quality_summary(quality: dict):
    """Headline numbers: aggregated error, sample counts, staleness."""
    stale = quality['stale']

    staleness = dbc.Alert(
        [
            html.Strong("Parameters are stale. "),
            f"{quality['n_new_samples']} sample(s) have been collected since "
            f"the last fit ({quality['n_samples_fitted']} of "
            f"{quality['n_samples']} used).  Refit to use all the data.",
        ],
        color="warning", className="py-2",
    ) if stale else dbc.Alert(
        f"Parameters reflect all {quality['n_samples']} stored sample(s).",
        color="success", className="py-2",
    )

    return html.Div([
        dbc.Row([
            _stat(f"{quality['metric']} (max)", f"{quality['error']:.4g}"),
            _stat("Samples", str(quality['n_samples'])),
            _stat("Used in last fit", str(quality['n_samples_fitted']),
                  color="text-warning" if stale else None),
            _stat("Residuals", str(len(quality['residuals']))),
        ], className="mb-3"),
        staleness,
    ])


def make_parity_plot(preds: dict, plot_id: str = "quality-parity"):
    """Measured vs predicted, one trace per output, with the y=x reference.

    A parity plot is the fastest read on fit quality: points off the diagonal
    are exactly the samples the surrogate gets wrong, and systematic curvature
    shows the functional form is wrong rather than the parameters.
    """
    fig = go.Figure()
    lo = hi = None

    for name, (measured, predicted) in preds.items():
        fig.add_trace(go.Scatter(
            x=measured, y=predicted, mode='markers', name=name,
            marker={'size': 9, 'opacity': 0.8},
            hovertemplate=f'{name}<br>measured %{{x:.6g}}'
                          f'<br>predicted %{{y:.6g}}<extra></extra>',
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


def make_residual_plot(quality: dict, plot_id: str = "quality-residuals"):
    """Residual per sample, with a zero line."""
    residuals = quality['residuals']
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=list(range(len(residuals))), y=residuals, name='residual',
        hovertemplate='sample %{x}<br>residual %{y:.6g}<extra></extra>',
    ))
    fig.add_hline(y=0, line={'width': 1, 'color': '#888'})
    fig.update_layout(
        xaxis_title='sample × output', yaxis_title=f"residual ({quality['metric']})",
        margin={'l': 60, 'r': 20, 't': 30, 'b': 50}, height=300,
        showlegend=False,
    )
    return dcc.Graph(id=plot_id, figure=fig)
