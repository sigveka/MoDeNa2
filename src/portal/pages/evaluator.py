"""Model Evaluator page - /evaluate/<encoded_id>.

Not /model/<id>/evaluate: Dash matches path templates in registration order
and the detail page's /model/<model_id> captured "flowRate/evaluate" as the
model id, so this page was unreachable and every "Evaluate Model" button led
to "Model 'flowRate/evaluate' not found".  test_pages.py checks that every
page's template resolves to that page.
"""
from pathlib import Path
import dash
from dash import html, dcc
import dash_bootstrap_components as dbc
from urllib.parse import unquote, quote

from modena_portal.components.navbar import make_navbar
from modena_portal.components.evaluator_form import make_evaluator_form
from modena_portal.data.queries import get_model

dash.register_page(
    __name__,
    path_template="/evaluate/<model_id>",
    title="MoDeNa - Evaluate",
)


def layout(model_id: str = ""):
    decoded_id = unquote(model_id)

    try:
        model = get_model(decoded_id)
    except Exception as e:
        return dbc.Container([
            make_navbar(active='library'),
            dbc.Alert(f"Model '{decoded_id}' not found: {e}", color="danger"),
        ])

    sf = model.surrogateFunction
    lib_ok = sf and sf.libraryName and Path(sf.libraryName).is_file()

    encoded_id = quote(decoded_id, safe='')

    unavailable_banner = None
    if not lib_ok:
        unavailable_banner = dbc.Alert(
            "Evaluation unavailable - compiled library not found. "
            "Has the model been trained and the library compiled?",
            color="warning",
            className="mb-3",
        )

    return dbc.Container([
        make_navbar(model_id=decoded_id, page="evaluate", active='library'),
        html.H2(f"Evaluate: {decoded_id}", className="mb-1"),
        html.P("Results update when you release a slider or press Enter in a "
               "box. Slider ends are the trained range.",
               className="text-muted small"),
        dcc.Link(
            html.Small("← Back to model detail"),
            href=f"/model/{encoded_id}",
        ),
        html.Hr(),
        unavailable_banner,
        dcc.Store(id='eval-model-id', data=decoded_id),
        dcc.Store(id='eval-lib-ok', data=bool(lib_ok)),
        make_evaluator_form(model),
        html.Div(id='eval-result', className='mt-4'),
    ], fluid=True)
