"""
MoDeNa Portal - Dash app factory.

Run in development, from a source checkout:
    ./run_portal

Run with gunicorn (production) -- see run.py for credentials and HTTPS:
    gunicorn "modena_portal.app:server" --bind 0.0.0.0:8050 --workers 2

Requirements:
    - MODENA_URI env var (defaults to mongodb://localhost:27017/test)
    - an installed MoDeNa: libmodena is found through MODENA_LIB_DIR, so
      LD_LIBRARY_PATH is not needed for a standard install.
"""
# config.py must be the very first modena-related import.
import modena_portal.config  # noqa: F401

import dash
import dash_bootstrap_components as dbc

app = dash.Dash(
    __name__,
    use_pages=True,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    suppress_callback_exceptions=True,
)

server = app.server  # Expose Flask server for gunicorn

# Access policy for every server that loads this module -- `modena-portal`,
# gunicorn or any other WSGI host: Basic auth when credentials are set, and
# loopback clients only when they are not.  See security.install().
from modena_portal.security import credentials as _credentials, install as _install  # noqa: E402
_install(server, _credentials())

app.layout = dash.page_container

# Register all callbacks by importing the callback modules.
import modena_portal.callbacks.detail_callbacks      # noqa: F401, E402
import modena_portal.callbacks.evaluator_callbacks   # noqa: F401, E402
import modena_portal.callbacks.diagnostics_callbacks # noqa: F401, E402

if __name__ == '__main__':
    # Same bind policy as the console script -- never 0.0.0.0 by default.
    from modena_portal.run import _serve
    _serve(debug=True)
