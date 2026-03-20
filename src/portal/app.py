"""
MoDeNa Portal - Dash app factory.

Run in development:
    python src/portal/app.py

Run with gunicorn (production):
    gunicorn "modena_portal.app:server" --bind 0.0.0.0:8050 --workers 2

Requirements:
    - MODENA_URI env var (defaults to mongodb://localhost:27017/test)
    - LD_LIBRARY_PATH must include the directory containing libmodena.so
      so that callModel() can load the compiled surrogate libraries.
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

app.layout = dash.page_container

# Register all callbacks by importing the callback modules.
import modena_portal.callbacks.detail_callbacks      # noqa: F401, E402
import modena_portal.callbacks.evaluator_callbacks   # noqa: F401, E402

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8050)
