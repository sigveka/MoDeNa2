"""Code shown for copying: a highlighted block with a copy button."""
from dash import dcc, html


def code_block(code: str, language: str = '', wrap: bool = False):
    """A code block with a copy button in its top-right corner.

    wrap=True is for one long line -- a compiler command -- that would
    otherwise run off the page; it is shown unhighlighted and wrapped.
    """
    copy = dcc.Clipboard(
        content=code, title="Copy",
        style={'position': 'absolute', 'top': '6px', 'right': '10px',
               'fontSize': '1.1rem', 'cursor': 'pointer', 'zIndex': 1,
               'color': '#6c757d'},
    )
    if wrap:
        body = html.Pre(code, style={
            'whiteSpace': 'pre-wrap', 'wordBreak': 'break-all',
            'backgroundColor': '#f8f9fa', 'padding': '12px 40px 12px 12px',
            'borderRadius': '4px', 'marginBottom': 0,
        })
    else:
        body = dcc.Markdown(f"```{language}\n{code}\n```",
                            highlight_config={'theme': 'dark'})
    return html.Div([copy, body], style={'position': 'relative'})
