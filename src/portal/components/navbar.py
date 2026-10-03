"""Top navigation bar, plus a breadcrumb row on model pages.

The navbar holds the same three links on every page, with exactly one
highlighted; where you are inside the library is the breadcrumb's job.  The
model id and "Evaluate" used to be appended to the navbar itself, so it grew
from page to page and highlighted two items at once.
"""
from urllib.parse import quote

import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, html


def make_navbar(model_id: str | None = None, page: str | None = None,
                active: str | None = None):
    """Return the navbar, followed by a breadcrumb when model_id is given.

    active: 'overview' | 'library' | 'runs' | None -- the highlighted link.
    page:   'evaluate' adds an Evaluate crumb after the model.
    """
    links = dbc.Nav([
        dbc.NavItem(dbc.NavLink("Overview", href="/",        active=active == 'overview')),
        dbc.NavItem(dbc.NavLink("Library",  href="/library", active=active == 'library')),
        dbc.NavItem(dbc.NavLink("Runs",     href="/runs",    active=active == 'runs')),
    ], navbar=True, className="ms-auto")

    navbar = dbc.Navbar(
        dbc.Container([
            dbc.NavbarBrand("MoDeNa Portal", href="/"),
            dbc.NavbarToggler(id="navbar-toggler", n_clicks=0),
            dbc.Collapse(links, id="navbar-collapse", is_open=False, navbar=True),
        ], fluid=True),
        color="dark",
        dark=True,
        expand="md",
        className="mb-3",
    )

    if not model_id:
        return html.Div(navbar, className="mb-3")

    # Encoded like every other model link: ids such as
    # fullerEtAlDiffusion[A=H2O,B=N2] carry brackets and commas.
    crumbs = [
        {'label': 'Library', 'href': '/library'},
        {'label': model_id, 'href': f"/model/{quote(model_id, safe='')}",
         'active': page != 'evaluate'},
    ]
    if page == 'evaluate':
        crumbs.append({'label': 'Evaluate', 'active': True})
    return html.Div([navbar, dbc.Breadcrumb(items=crumbs, className="mb-2")])


@callback(
    Output("navbar-collapse", "is_open"),
    Input("navbar-toggler", "n_clicks"),
    State("navbar-collapse", "is_open"),
    prevent_initial_call=True,
)
def toggle_navbar(n_clicks, is_open):
    """Open and close the links on narrow screens."""
    return not is_open if n_clicks else is_open
