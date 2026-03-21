"""Overview page — environment, install locations, database, and model readiness."""
import os
import sys
from pathlib import Path

if sys.platform == 'darwin':
    _LIBMODENA_NAME  = 'libmodena.dylib'
    _LIBPATH_ENV_VAR = 'DYLD_LIBRARY_PATH'
elif sys.platform == 'win32':
    _LIBMODENA_NAME  = 'modena.dll'
    _LIBPATH_ENV_VAR = 'PATH'
else:
    _LIBMODENA_NAME  = 'libmodena.so'
    _LIBPATH_ENV_VAR = 'LD_LIBRARY_PATH'

import dash
import dash_bootstrap_components as dbc
from dash import html

from modena_portal.components.navbar import make_navbar
from modena_portal.components.status_badge import status_badge
from modena_portal.data.queries import list_models

dash.register_page(__name__, path="/", title="MoDeNa - Overview")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _env_row(name: str, description: str = "", secret: bool = False) -> dict:
    val = os.environ.get(name)
    set_ = val is not None
    display = ("•••" if secret else val) if set_ else None
    return {"name": name, "value": display, "description": description, "set": set_}


def _env_table(rows: list[dict]) -> dbc.Table:
    body = []
    for r in rows:
        if r["set"]:
            value_cell = html.Td(
                html.Code(r["value"]),
                style={"wordBreak": "break-all"},
            )
            icon = html.Td("✓", className="text-success", style={"textAlign": "center"})
        else:
            value_cell = html.Td(
                r["description"],
                className="text-muted fst-italic",
                style={"fontSize": "0.85em"},
            )
            icon = html.Td("—", className="text-muted", style={"textAlign": "center"})
        body.append(html.Tr([
            html.Td(html.Code(r["name"])),
            value_cell,
            icon,
        ]))
    return dbc.Table(
        [html.Thead(html.Tr([html.Th("Variable"), html.Th("Value / Description"), html.Th("Set")])),
         html.Tbody(body)],
        bordered=True, size="sm", hover=True, className="mb-0",
    )


def _kv_table(rows: list[tuple[str, str]]) -> dbc.Table:
    body = [html.Tr([html.Td(html.Strong(k)), html.Td(
        html.Code(v), style={"wordBreak": "break-all"}
    )]) for k, v in rows]
    return dbc.Table(html.Tbody(body), bordered=True, size="sm", className="mb-0")


def _find_libmodena() -> str:
    """Best-effort search for the modena shared library on the platform library path."""
    search_path = os.environ.get(_LIBPATH_ENV_VAR, "")
    for d in search_path.split(os.pathsep):
        candidate = Path(d) / _LIBMODENA_NAME
        if candidate.is_file():
            return str(candidate)
    return f"not found on {_LIBPATH_ENV_VAR}"


def _mongo_status(uri: str) -> tuple[bool, str]:
    """Ping MongoDB; return (ok, message)."""
    try:
        import pymongo
        client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=3000)
        client.admin.command("ping")
        return True, "Connected"
    except Exception as e:
        return False, str(e)


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

def layout():
    # ── Environment variables ────────────────────────────────────────────────
    env_rows = [
        _env_row("MODENA_URI",
                 "MongoDB connection URI. Default: mongodb://localhost:27017/test"),
        _env_row("MODENA_PATH",
                 "Colon-separated model prefix directories (highest priority, "
                 "appended after all config-file paths)."),
        _env_row("MODENA_BIN_PATH",
                 "Colon-separated directories for exact-simulation binaries. "
                 "Falls back to bin/ alongside the FireTask .py file when unset."),
        _env_row("MODENA_SURROGATE_LIB_DIR",
                 "Where compiled surrogate .so files are stored. "
                 "Default: ~/.modena/surrogate_functions"),
        _env_row("MODENA_LOG_LEVEL",
                 "Log verbosity: WARNING | INFO (default) | DEBUG | DEBUG_VERBOSE"),
        _env_row(_LIBPATH_ENV_VAR,
                 f"Must include the directory containing {_LIBMODENA_NAME} so that "
                 "compiled surrogate libraries can be loaded at runtime."),
    ]

    # ── Install locations ─────────────────────────────────────────────────────
    try:
        import modena
        python_lib = str(Path(modena.__file__).parent)
    except Exception:
        python_lib = "modena not importable"

    try:
        from modena.Registry import ModelRegistry
        reg = ModelRegistry()
        surrogate_lib_dir = reg.surrogate_lib_dir
    except Exception:
        surrogate_lib_dir = os.environ.get("MODENA_SURROGATE_LIB_DIR", "—")

    install_rows = [
        ("Python library", python_lib),
        (_LIBMODENA_NAME,          _find_libmodena()),
        ("Surrogate library cache", str(surrogate_lib_dir)),
        ("Python executable",   sys.executable),
    ]

    # ── Database ──────────────────────────────────────────────────────────────
    uri = os.environ.get("MODENA_URI", "mongodb://localhost:27017/test")
    db_ok, db_msg = _mongo_status(uri)
    db_name = uri.split("/")[-1] if "/" in uri else "—"
    host_part = uri.split("/")[2] if uri.count("/") >= 2 else uri

    db_rows = [
        ("URI",      uri),
        ("Host",     host_part),
        ("Database", db_name),
        ("Status",   db_msg),
    ]

    db_alert_color = "success" if db_ok else "danger"
    db_icon = "✓ Connected" if db_ok else f"✗ {db_msg}"

    # ── Model readiness ───────────────────────────────────────────────────────
    try:
        models = list_models()
        model_error = None
    except Exception as e:
        models = []
        model_error = str(e)

    trained = [m for m in models if _model_status(m) == "Trained"]
    library_missing = [m for m in models if _model_status(m) == "Library missing"]
    untrained = [m for m in models if _model_status(m) == "Untrained"]

    return dbc.Container([
        make_navbar(active="overview"),

        html.H2("MoDeNa Setup Overview", className="mb-4"),

        dbc.Row([
            # ── Left column ──────────────────────────────────────────────────
            dbc.Col([

                dbc.Card([
                    dbc.CardHeader(html.Strong("Environment Variables")),
                    dbc.CardBody(_env_table(env_rows)),
                ], className="mb-4"),

                dbc.Card([
                    dbc.CardHeader(html.Strong("Install Locations")),
                    dbc.CardBody(_kv_table(install_rows)),
                ], className="mb-4"),

            ], md=7),

            # ── Right column ─────────────────────────────────────────────────
            dbc.Col([

                dbc.Card([
                    dbc.CardHeader(html.Strong("Database")),
                    dbc.CardBody([
                        dbc.Alert(db_icon, color=db_alert_color,
                                  className="py-2 mb-3"),
                        _kv_table(db_rows),
                    ]),
                ], className="mb-4"),

                dbc.Card([
                    dbc.CardHeader(html.Strong("Model Readiness")),
                    dbc.CardBody(
                        _model_readiness_body(models, trained, library_missing,
                                              untrained, model_error)
                    ),
                ], className="mb-4"),

            ], md=5),
        ]),
    ], fluid=True)


# ---------------------------------------------------------------------------
# Helpers used inside layout()
# ---------------------------------------------------------------------------

def _model_status(model) -> str:
    if not model.parameters:
        return "Untrained"
    lib = getattr(model.surrogateFunction, "libraryName", None)
    if lib and Path(lib).is_file():
        return "Trained"
    return "Library missing"


def _model_readiness_body(models, trained, library_missing, untrained, error):
    if error:
        return dbc.Alert(f"Could not load models: {error}", color="danger")

    if not models:
        return dbc.Alert("No models found in the database.", color="secondary")

    summary = dbc.Row([
        dbc.Col(dbc.Card([
            dbc.CardBody([
                html.H3(len(trained), className="text-success mb-0"),
                html.Small("Ready to use"),
            ], className="text-center p-2"),
        ]), width=4),
        dbc.Col(dbc.Card([
            dbc.CardBody([
                html.H3(len(library_missing), className="text-warning mb-0"),
                html.Small("Library missing"),
            ], className="text-center p-2"),
        ]), width=4),
        dbc.Col(dbc.Card([
            dbc.CardBody([
                html.H3(len(untrained), className="text-danger mb-0"),
                html.Small("Untrained"),
            ], className="text-center p-2"),
        ]), width=4),
    ], className="mb-3 g-2")

    rows = []
    for m in sorted(models, key=lambda m: m._id):
        rows.append(html.Tr([
            html.Td(html.A(m._id, href=f"/model/{m._id}",
                           style={"fontFamily": "monospace"})),
            html.Td(status_badge(m)),
        ]))

    detail = dbc.Table(
        [html.Thead(html.Tr([html.Th("Model ID"), html.Th("Status")])),
         html.Tbody(rows)],
        bordered=True, size="sm", hover=True, className="mb-0",
    )

    note = None
    if library_missing:
        note = dbc.Alert(
            "Models marked \"Library missing\" have fitted parameters in the "
            "database but their compiled surrogate .so was not found on this "
            "machine. The .so will be recompiled automatically on first use if "
            "MoDeNa is installed and the C build tools are available.",
            color="warning", className="mt-3 mb-0 py-2",
        )

    return html.Div([summary, detail] + ([note] if note else []))
