"""Fit data scatter plot with X/Y axis dropdowns.

Defaults to the first input against the first output -- the plot a reader
wants first.  It used to plot whatever two columns came first and last in
storage order, which put the output on the x axis.

Points are coloured by where they came from.  The first samples are the
initial design; everything after arrived later, from out-of-bounds expansion
or error-driven sampling -- which is what makes a MoDeNa model's data
interesting.  When the initial design's size is unknown, colour shows the
order samples were collected in instead.
"""
from dash import dcc, html
import plotly.graph_objects as go

_INITIAL, _LATER = '#1f77b4', '#ff7f0e'


def default_axes(input_names, output_names, columns, fitdata=None):
    """(x, y): first input that varies against first output.

    An input sampled at one value only (flowRate's D) makes a useless x axis:
    every point in one vertical line, ticks reading 0.010000002.
    """
    from modena_portal.data.helpers import is_fixed

    def varies(n):
        col = (fitdata or {}).get(n) or []
        return not col or not is_fixed(min(col), max(col))

    candidates = [n for n in input_names if n in columns]
    x = next((n for n in candidates if varies(n)),
             candidates[0] if candidates else columns[0])
    y = next((n for n in output_names if n in columns),
             columns[-1] if len(columns) > 1 else columns[0])
    return x, y


def make_fitdata_plot(fitdata: dict, labels: dict, x_col: str, y_col: str,
                      n_initial: int | None, plot_id_prefix: str = "fitdata"):
    """X/Y dropdowns and the scatter.  labels maps column -> 'name [unit]'."""
    if not fitdata:
        return html.Div("No fit data available.")

    options = [{'label': labels.get(c, c), 'value': c} for c in fitdata]
    dropdown = {'clearable': False, 'style': {'minWidth': '220px'}}

    return html.Div([
        html.Div([
            html.Label("X axis:"),
            dcc.Dropdown(id=f"{plot_id_prefix}-x-axis", options=options,
                         value=x_col, **dropdown),
            html.Label("Y axis:", style={'marginLeft': '20px'}),
            dcc.Dropdown(id=f"{plot_id_prefix}-y-axis", options=options,
                         value=y_col, **dropdown),
        ], style={'display': 'flex', 'alignItems': 'center', 'gap': '8px',
                  'marginBottom': '10px', 'flexWrap': 'wrap'}),
        dcc.Graph(id=f"{plot_id_prefix}-graph",
                  figure=build_scatter(fitdata, x_col, y_col, n_initial, labels)),
    ])


def build_scatter(fitdata: dict, x_col: str, y_col: str,
                  n_initial: int | None = None, labels: dict | None = None) -> go.Figure:
    """Scatter of x_col against y_col, coloured by sample origin."""
    labels = labels or {}
    xs, ys = fitdata.get(x_col, []), fitdata.get(y_col, [])
    n = min(len(xs), len(ys))
    hover = (f'sample %{{customdata}}<br>{labels.get(x_col, x_col)} %{{x:.6g}}'
             f'<br>{labels.get(y_col, y_col)} %{{y:.6g}}<extra></extra>')

    fig = go.Figure()
    if n_initial is not None and 0 < n_initial <= n:
        for name, idx, colour in (
            (f'initial design ({n_initial})', range(n_initial), _INITIAL),
            (f'added later ({n - n_initial})', range(n_initial, n), _LATER),
        ):
            idx = list(idx)
            if idx:
                fig.add_trace(go.Scatter(
                    x=[xs[i] for i in idx], y=[ys[i] for i in idx],
                    customdata=idx, mode='markers', name=name,
                    marker={'size': 8, 'color': colour}, hovertemplate=hover))
        fig.update_layout(legend={'orientation': 'h', 'y': -0.2})
    else:
        fig.add_trace(go.Scatter(
            x=xs[:n], y=ys[:n], customdata=list(range(n)), mode='markers',
            marker={'size': 8, 'color': list(range(n)), 'colorscale': 'Viridis',
                    'colorbar': {'title': 'sample #'}, 'showscale': n > 1},
            hovertemplate=hover, showlegend=False))

    fig.update_layout(
        xaxis_title=labels.get(x_col, x_col),
        yaxis_title=labels.get(y_col, y_col),
        margin={'l': 60, 'r': 20, 't': 20, 'b': 50},
    )
    return fig
