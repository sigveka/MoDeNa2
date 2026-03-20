"""
Entry point for the MoDeNa Portal.

Development:
    python src/portal/run.py

Production (gunicorn):
    gunicorn "modena_portal.app:server" --bind 0.0.0.0:8050 --workers 2

Environment variables:
    MODENA_URI          MongoDB connection URI (default: mongodb://localhost:27017/test)
    LD_LIBRARY_PATH     Must include the directory containing libmodena.so
                        and the per-model compiled surrogate libraries (.so files)
                        for callModel() to work.

Example:
    export MODENA_URI=mongodb://myserver:27017/modena
    export LD_LIBRARY_PATH=/opt/modena/lib:$LD_LIBRARY_PATH
    python src/portal/run.py
"""
from modena_portal.app import app


def main():
    """Console script entry point installed by setup.py."""
    app.run(debug=False, host='0.0.0.0', port=8050)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8050)
