"""
Entry point for the MoDeNa Portal.

Development:
    python src/portal/run.py

Production (gunicorn):
    gunicorn "modena_portal.app:server" --bind 127.0.0.1:8050 --workers 2

Environment variables:
    MODENA_URI              MongoDB connection URI
                            (default: mongodb://localhost:27017/test)
    MODENA_PORTAL_HOST      Bind address (default: 127.0.0.1).  Any
                            non-loopback value requires credentials -- see
                            security.py.
    MODENA_PORTAL_PORT      Bind port (default: 8050)
    MODENA_PORTAL_USER      HTTP Basic username
    MODENA_PORTAL_PASSWORD  HTTP Basic password
    LD_LIBRARY_PATH         Must include the directory containing libmodena.so
                            and the per-model compiled surrogate libraries
                            (.so files) for callModel() to work.

Example -- serve on the network, with a password:
    export MODENA_PORTAL_HOST=0.0.0.0
    export MODENA_PORTAL_USER=alice MODENA_PORTAL_PASSWORD='...'
    modena-portal
"""
import logging
import os
import sys

from modena_portal.app import app, server
from modena_portal.security import (
    InsecureConfiguration, check_bind_policy, credentials, install,
)

_log = logging.getLogger('modena_portal')

#: Loopback, not 0.0.0.0.  The portal can promote fitted parameters and queue
#: exact simulations, so the default must not be reachable from the network.
DEFAULT_HOST = '127.0.0.1'
DEFAULT_PORT = 8050


def _settings():
    host = os.environ.get('MODENA_PORTAL_HOST', DEFAULT_HOST)
    try:
        port = int(os.environ.get('MODENA_PORTAL_PORT', DEFAULT_PORT))
    except ValueError:
        raise SystemExit(
            f"MODENA_PORTAL_PORT must be an integer, got "
            f"{os.environ['MODENA_PORTAL_PORT']!r}"
        )
    return host, port


def _serve(debug):
    host, port = _settings()
    creds = credentials()
    try:
        check_bind_policy(host, creds)
    except InsecureConfiguration as exc:
        print(f'[modena-portal] ERROR: {exc}', file=sys.stderr)
        raise SystemExit(1)

    install(server, creds)

    scope = 'this machine only' if host in ('127.0.0.1', '::1') else 'the network'
    auth = 'password-protected' if creds else 'no authentication'
    print(f'[modena-portal] http://{host}:{port}  ({scope}, {auth})')

    app.run(debug=debug, host=host, port=port)


def main():
    """Console script entry point installed by CMake."""
    _serve(debug=False)


if __name__ == '__main__':
    _serve(debug=True)
