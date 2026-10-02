"""The C Code tab: the source that was compiled, not the template.

A model declares its surrogate as a Jinja2 template whose
``{% block variables %}{% endblock %}`` CFunction.compileCcode() replaces
with the input and parameter bindings.  The tab used to show that template,
so the reader saw template syntax and a comment describing what the real code
would look like.  The rendered source is kept beside the compiled library
(func_<hash>/<hash>.c next to func_<hash>/lib<hash>.so), so show that.
"""
from pathlib import Path

from dash import html
import dash_bootstrap_components as dbc

from modena_portal.components.code_block import code_block


def rendered_source_path(library_name) -> Path | None:
    """func_<h>/<h>.c for the library func_<h>/lib<h>.so."""
    if not library_name:
        return None
    so = Path(library_name)
    return so.with_name(so.stem.removeprefix('lib') + '.c')


def make_ccode_view(sf):
    template = sf.Ccode if sf and sf.Ccode else None
    if template is None:
        return dbc.Alert("No C code stored for this model.", color="secondary",
                         className="mt-3")

    source = rendered_source_path(getattr(sf, 'libraryName', None))
    declared = html.Details([
        html.Summary("Template as declared in the model"),
        html.P(["MoDeNa replaces ", html.Code("{% block variables %}"),
                " with the bindings when it compiles."],
               className="text-muted small mt-2"),
        code_block(template, 'c'),
    ], className="mt-3")

    if source is not None and source.is_file():
        return html.Div([
            html.P(["The source compiled into ",
                    html.Code(str(Path(sf.libraryName).name)),
                    ": the model's template with its input and parameter "
                    "bindings filled in."],
                   className="text-muted small mt-3"),
            code_block(source.read_text(), 'c'),
            declared,
        ])

    return html.Div([
        dbc.Alert(
            ["The compiled source is not on this machine, so this is the "
             "template as declared. ", html.Code("{% block variables %}"),
             " is where MoDeNa inserts the input and parameter bindings when "
             "it compiles; loading the model compiles it."],
            color="secondary", className="mt-3 py-2"),
        code_block(template, 'c'),
    ])
