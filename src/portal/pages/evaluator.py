"""Model Evaluator page - /model/<encoded_id>/evaluate."""
import os
import dash
from dash import html, dcc
import dash_bootstrap_components as dbc
from urllib.parse import unquote, quote

from modena_portal.components.navbar import make_navbar
from modena_portal.components.evaluator_form import make_evaluator_form
from modena_portal.data.queries import get_model

dash.register_page(
    __name__,
    path_template="/model/<model_id>/evaluate",
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
    lib_ok = sf and sf.libraryName and os.path.isfile(sf.libraryName)

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
        html.H2(f"Evaluate: {decoded_id}", className="mb-3"),
        dcc.Link(
            html.Small("← Back to model detail"),
            href=f"/model/{encoded_id}",
        ),
        html.Hr(),
        unavailable_banner,
        dcc.Store(id='eval-model-id', data=decoded_id),
        dcc.Store(id='eval-lib-ok', data=lib_ok),
        make_evaluator_form(model),
        dbc.Button(
            "Evaluate",
            id='eval-button',
            color='primary',
            className='mt-3',
            disabled=not lib_ok,
        ),
        html.Div(id='eval-result', className='mt-4'),
    ], fluid=True)
