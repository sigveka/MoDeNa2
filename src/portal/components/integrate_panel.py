"""Per-model integration snippets, one tab per language.

The quick-start docs already cover each language, worked through with
`flowRate`.  What they cannot do is fill in *this* model's id, inputs and
outputs -- or know which inputs a substitute model supplies, which the caller
must not claim.
"""
from dash import dcc, html
import dash_bootstrap_components as dbc

from modena.Integration import LANGUAGES

#: dcc.Markdown highlighter name per language key.
_HIGHLIGHT = {
    'c': 'c', 'cpp': 'cpp', 'fortran': 'fortran', 'python': 'python',
    'julia': 'julia', 'matlab': 'matlab', 'r': 'r',
}


def make_language_tabs(active: str = 'c'):
    return dbc.Tabs(
        [dbc.Tab(label=label, tab_id=f'lang-{key}')
         for key, (label, _ext, _fn) in LANGUAGES.items()],
        id='integrate-lang-tabs', active_tab=f'lang-{active}',
    )


def make_snippet_view(snippet: dict, model_id: str):
    """Code block + build command + any substitute-model warning."""
    lang_key = next(
        (k for k, (label, _e, _f) in LANGUAGES.items() if label == snippet['label']),
        'c',
    )

    blocks = []

    if snippet['supplied']:
        blocks.append(dbc.Alert(
            [
                html.Strong("Some inputs are supplied by substitute models. "),
                "The framework evaluates them first and writes the result "
                "straight into this model's input vector, so the application "
                "must not claim their argument positions — ",
                html.Code("modena_model_argPos_check()"),
                " calls ", html.Code("exit(1)"), " if it does. Omitted here: ",
                html.Span(', '.join(f'{k} ← {v}'
                                    for k, v in snippet['supplied'].items()),
                          className="font-monospace"),
            ],
            color="info", className="py-2",
        ))

    blocks.append(dcc.Markdown(
        f"```{_HIGHLIGHT.get(lang_key, '')}\n{snippet['code']}\n```",
        highlight_config={'theme': 'dark'},
    ))

    blocks.append(html.H6("Build and run", className="mt-3"))
    blocks.append(dcc.Markdown(f"```bash\n{snippet['build']}\n```"))
    blocks.append(html.P(
        [
            "Paths come from this installation. If you did not install to the "
            "default prefix, source ",
            html.Code("<prefix>/share/modena/modena-env.sh"),
            " first.",
        ],
        className="text-muted small",
    ))

    return html.Div(blocks)
