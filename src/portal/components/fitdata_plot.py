"""Fit data scatter plot with X/Y axis dropdowns."""
from dash import dcc, html
import plotly.graph_objects as go


def make_fitdata_plot(fitdata: dict, plot_id_prefix: str = "fitdata"):
    """
    Return a layout with X/Y axis dropdowns and a scatter plot.

    The actual figure update is handled by a callback in detail_callbacks.py.
    This component renders the initial static view with the first two columns.
    """
    if not fitdata:
        return html.Div("No fit data available.")

    cols = list(fitdata.keys())
    x_col = cols[0]
    y_col = cols[-1] if len(cols) > 1 else cols[0]

    options = [{'label': c, 'value': c} for c in cols]

    return html.Div([
        html.Div([
            html.Label("X axis:"),
            dcc.Dropdown(
                id=f"{plot_id_prefix}-x-axis",
                options=options,
                value=x_col,
                clearable=False,
                style={'width': '300px'},
            ),
            html.Label("Y axis:", style={'marginLeft': '20px'}),
            dcc.Dropdown(
                id=f"{plot_id_prefix}-y-axis",
                options=options,
                value=y_col,
                clearable=False,
                style={'width': '300px'},
            ),
        ], style={'display': 'flex', 'alignItems': 'center', 'gap': '8px', 'marginBottom': '10px'}),
        dcc.Graph(id=f"{plot_id_prefix}-graph", figure=build_scatter(fitdata, x_col, y_col)),
    ])


def build_scatter(fitdata: dict, x_col: str, y_col: str) -> go.Figure:
    """Build a Plotly scatter figure for the given x/y columns."""
    fig = go.Figure(go.Scatter(
        x=fitdata.get(x_col, []),
        y=fitdata.get(y_col, []),
        mode='markers',
        marker={'size': 6},
    ))
    fig.update_layout(
        xaxis_title=x_col,
        yaxis_title=y_col,
        margin={'l': 40, 'r': 20, 't': 20, 'b': 40},
    )
    return fig
