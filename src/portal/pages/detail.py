"""Model Detail page - /model/<encoded_id>."""
import dash
from dash import html, dcc, dash_table
import dash_bootstrap_components as dbc
from urllib.parse import unquote, quote

from modena_portal.components.navbar import make_navbar
from modena_portal.components.status_badge import status_badge
from modena_portal.components.parameter_table import make_parameter_table
from modena_portal.components.dependency_graph import make_dependency_graph
from modena_portal.components.ccode_view import make_ccode_view
from modena_portal.data.helpers import fmt, is_fixed, ordered_names, plural, unit_text
from modena_portal.data.queries import get_model, get_sample_count

dash.register_page(__name__, path_template="/model/<model_id>", title="MoDeNa - Model Detail")


def _stat(label, value, note=None):
    return dbc.Col(html.Div([
        html.Div(label, className="text-muted small"),
        html.Div(value, className="h5 mb-0"),
        html.Div(note, className="small text-warning") if note else None,
    ]), width="auto", className="me-4 mb-2")


def make_summary(model, n_samples):
    """The facts a returning reader looks for first, in one line."""
    last = getattr(model, 'last_fitted', None)
    n_fitted = getattr(model, 'n_samples_fitted', 0) or 0
    new = n_samples - n_fitted if model.parameters else 0
    return dbc.Row([
        _stat("Status", status_badge(model)),
        _stat("Samples", str(n_samples),
              note=f"{plural(new, 'sample')} not yet in the fit" if new > 0 else None),
        _stat("Used in last fit", str(n_fitted) if model.parameters else '—'),
        _stat("Last fitted", last.strftime('%Y-%m-%d %H:%M') + ' UTC' if last else '—'),
    ], className="mb-1")


def bounds_rows(model):
    """Inputs then outputs, in argPos order, with units and fixed inputs flagged.

    min == max means the model was only ever sampled at one value -- the
    input is fixed, and the surrogate says nothing about other values.  The
    table used to show "0.01 0.01" and leave the reader to notice.
    """
    rows = []
    for kind, mapping in (('Input', model.inputs or {}), ('Output', model.outputs or {})):
        for name in ordered_names(mapping):
            entry = mapping[name]
            fixed = is_fixed(entry.min, entry.max)
            rows.append({
                'Variable': name,
                'Kind': kind,
                'Unit': unit_text(entry) or '—',
                'Min': fmt(entry.min),
                'Max': fmt(entry.max),
                'Note': f'fixed at {fmt(entry.min)}' if fixed else '',
            })
    return rows


def _argpos_details(model):
    """Argument positions: needed by C and Fortran callers, nobody else."""
    rows = []
    for kind, mapping in (('Input', model.inputs or {}), ('Output', model.outputs or {})):
        for name in ordered_names(mapping):
            rows.append({'Kind': kind, 'Name': name,
                         'argPos': getattr(mapping[name], 'argPos', None)})
    sf = model.surrogateFunction
    for pos, name in enumerate(sf.parameters.keys() if sf and sf.parameters else []):
        rows.append({'Kind': 'Parameter', 'Name': name, 'argPos': pos})
    return html.Details([
        html.Summary("Argument positions (for C and Fortran callers)"),
        html.P(["Indices into the ", html.Code("double[]"), " arrays libmodena "
                "exchanges. The Integrate tab looks them up by name, which is "
                "the safe way to use them."], className="text-muted small mt-2"),
        dash_table.DataTable(
            data=rows, columns=[{'name': c, 'id': c} for c in ('Kind', 'Name', 'argPos')],
            style_cell={'textAlign': 'left'}, style_table={'overflowX': 'auto'}),
    ], className="mt-3")


def _substitutes(model):
    subs = list(getattr(model, 'substituteModels', []) or [])
    if not subs:
        return html.Span("None — the caller supplies every input.",
                         className="text-muted")
    return html.Div([
        html.Div([dcc.Link(s._id, href=f"/model/{quote(s._id, safe='')}",
                           style={'marginRight': '12px'}) for s in subs]),
        make_dependency_graph(model),
    ])


def _documentation(doc_text):
    if doc_text:
        return dcc.Markdown(
            doc_text, mathjax=True,
            style={'border': '1px solid #dee2e6', 'padding': '16px',
                   'borderRadius': '4px', 'marginTop': '16px'},
        )
    return dbc.Alert([
        html.Strong("No documentation for this model. "),
        "Pass ", html.Code("documentation="), " where the model is declared "
        "in its Python package — Markdown text, or a ", html.Code("Path"),
        " to a Markdown file. It is stored with the model when the model is "
        "initialised (", html.Code("modena init <model>"), "), and shown here "
        "with LaTeX maths.",
    ], color="secondary", className="mt-3")


def _lazy_tab(label, tab_id, content_id, hint):
    return dbc.Tab(label=label, tab_id=tab_id, children=[
        html.Div(id=content_id, children=html.Span(hint, className="text-muted"),
                 className="mt-3"),
    ])


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
    encoded_id = quote(decoded_id, safe='')
    has_fitdata = hasattr(model, 'fitData')
    try:
        n_samples = get_sample_count(decoded_id) if has_fitdata else 0
    except Exception:                                          # noqa: BLE001
        n_samples = 0

    out_names = ordered_names(model.outputs) if model.outputs else ['?']
    in_names = ordered_names(model.inputs) if model.inputs else []
    param_names = list(sf.parameters.keys()) if sf and sf.parameters else []
    signature = (
        f"{', '.join(out_names)} = {sf.name if sf else '?'}"
        f"({', '.join(in_names)} ; {', '.join(param_names)})"
    )

    io_rows = bounds_rows(model)
    io_table = dash_table.DataTable(
        data=io_rows,
        columns=[{'name': c, 'id': c} for c in ['Variable', 'Kind', 'Unit', 'Min', 'Max', 'Note']],
        style_cell={'textAlign': 'left'},
        style_table={'overflowX': 'auto'},
        style_data_conditional=[{'if': {'filter_query': '{Note} != ""', 'column_id': 'Note'},
                                 'color': '#664d03', 'fontWeight': 'bold'}],
    )
    units_note = None
    if io_rows and all(r['Unit'] == '—' for r in io_rows):
        units_note = html.P("No units declared for this model. “—” means "
                            "undeclared, not dimensionless.",
                            className="text-muted small mt-1")

    overview_tab = dbc.Tab(label="Overview", tab_id="tab-overview", children=[
        html.Div([
            make_summary(model, n_samples),
            html.Hr(),
            html.H5("Function signature"),
            html.Code(signature, style={'fontSize': '1rem'}),
            html.Div("outputs = function(inputs ; parameters)",
                     className="text-muted small"),
            html.Hr(),
            html.H5("Parameters"),
            make_parameter_table(model),
            html.Hr(),
            html.H5("Inputs and outputs"),
            io_table,
            units_note,
            _argpos_details(model),
            html.Hr(),
            html.H5("Substitute models"),
            _substitutes(model),
        ], className="mt-3"),
    ])

    doc_tab = dbc.Tab(label="Documentation", tab_id="tab-docs",
                      children=_documentation(getattr(model, 'documentation', '') or ''))

    # Fit Data / Fit Quality / Refit / Collect Data need stored fitData
    # (BackwardMappingModel only).  Contents load on tab switch: computing fit
    # quality evaluates the surrogate once per sample, which is not something
    # to do on every page render.
    tabs = [overview_tab, doc_tab]
    if has_fitdata:
        tabs += [
            _lazy_tab("Fit Data", "tab-fitdata", 'fitdata-content',
                      "Switch to this tab to load fit data."),
            _lazy_tab("Fit Quality", "tab-quality", 'quality-content',
                      "Switch to this tab to score the stored parameters."),
            _lazy_tab("Refit", "tab-refit", 'refit-content',
                      "Switch to this tab to compare fitting strategies."),
            _lazy_tab("Collect Data", "tab-sampling", 'sampling-content',
                      "Switch to this tab to request more training points."),
        ]

    # Integration snippets work for any model -- they need only the schema.
    tabs.append(_lazy_tab("Integrate", "tab-integrate", 'integrate-content',
                          "Switch to this tab for ready-to-paste integration code."))
    tabs.append(dbc.Tab(label="C Code", tab_id="tab-ccode",
                        children=make_ccode_view(sf)))

    return dbc.Container([
        make_navbar(model_id=decoded_id, active='library'),
        html.H2(decoded_id, className="mb-1"),
        html.P(f"Type: {model.__class__.__name__}", className="text-muted"),
        dcc.Link(
            dbc.Button("Evaluate Model", color="success", size="sm"),
            href=f"/evaluate/{encoded_id}",
        ),
        html.Hr(),
        # Hidden store to pass model_id to callbacks
        dcc.Store(id='detail-model-id', data=decoded_id),
        # Candidate fits from the Refit tab.  Kept out of the tab body so the
        # comparison survives switching tabs; cleared on page reload, which is
        # correct -- these are unsaved experiments.
        dcc.Store(id='refit-store', data=[]),
        dbc.Tabs(tabs, id='detail-tabs', active_tab='tab-overview'),
    ], fluid=True)
