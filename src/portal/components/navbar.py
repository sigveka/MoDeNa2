"""Top navigation / breadcrumb bar."""
import dash_bootstrap_components as dbc
from dash import html


def make_navbar(model_id: str | None = None, page: str | None = None,
               active: str | None = None):
    """Return a Bootstrap Navbar with breadcrumb links.

    active: 'library' | 'runs' | None — highlights the matching top-level link.
    """
    items = [
        dbc.NavItem(dbc.NavLink("Library", href="/",    active=active == 'library')),
        dbc.NavItem(dbc.NavLink("Runs",    href="/runs", active=active == 'runs')),
    ]

    if model_id:
        items.append(dbc.NavItem(
            dbc.NavLink(model_id, href=f"/model/{model_id}")
        ))

    if page == "evaluate":
        items.append(dbc.NavItem(
            dbc.NavLink("Evaluate", href="#", active=True)
        ))

    return dbc.Navbar(
        dbc.Container([
            dbc.NavbarBrand("MoDeNa Portal", href="/"),
            dbc.Nav(items, navbar=True),
        ]),
        color="dark",
        dark=True,
        className="mb-4",
    )
