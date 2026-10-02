"""HTTP Basic authentication and bind-address policy for the portal.

The portal used to bind 0.0.0.0:8050 with no authentication.  That was
tolerable while it was strictly read-only, but it now has write actions --
promoting fitted parameters, and queueing exact simulations that spend real
compute -- so an unauthenticated listener on every interface is no longer a
tidiness issue.

The policy is one rule:

    serving anyone other than this machine requires credentials.

It is enforced twice.  Per request, in the app (install(), called from
app.py, so it holds under any WSGI server): with credentials every request
must carry them, without them only loopback clients are served.  And at
start-up, by `modena-portal` (check_bind_policy()), which refuses a public
bind without credentials rather than starting a listener that would answer
everyone with 403.

A loopback client needs no setup, so the common case (`modena-portal` on your
own machine) just works.  Basic auth sends the password with every request:
put anything beyond localhost behind HTTPS.  No new dependency: Dash already
runs on Flask, which is all Basic auth needs.
"""
import base64
import hmac
import ipaddress
import logging
import os

from flask import Response, request

_log = logging.getLogger('modena_portal.security')

#: Addresses that reach only this machine.
_LOOPBACK_HOSTS = {'127.0.0.1', '::1', 'localhost'}


class InsecureConfiguration(RuntimeError):
    """Raised when the portal is asked to listen publicly without credentials."""


def is_loopback(host: str) -> bool:
    if host in _LOOPBACK_HOSTS:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def credentials():
    """Return ``(user, password)`` from the environment, or ``None``.

    Environment rather than modena.toml by default: a password in a config
    file tends to end up committed, and this one guards the ability to spend
    compute.
    """
    user = os.environ.get('MODENA_PORTAL_USER')
    password = os.environ.get('MODENA_PORTAL_PASSWORD')
    if user and password:
        return user, password
    return None


def check_bind_policy(host: str, creds) -> None:
    """Refuse a non-loopback bind without credentials.

    Raises:
        InsecureConfiguration: with instructions, rather than starting a
        listener that anyone on the network can use to queue simulations.
    """
    if is_loopback(host) or creds is not None:
        return
    raise InsecureConfiguration(
        f"refusing to listen on {host} without authentication.\n"
        f"The portal can promote fitted parameters and queue exact "
        f"simulations, so a public bind needs credentials:\n\n"
        f"    export MODENA_PORTAL_USER=someone\n"
        f"    export MODENA_PORTAL_PASSWORD='...'\n\n"
        f"Or leave MODENA_PORTAL_HOST unset to listen on 127.0.0.1 only."
    )


def _authorised(header: str, user: str, password: str) -> bool:
    if not header or not header.startswith('Basic '):
        return False
    try:
        decoded = base64.b64decode(header[6:]).decode('utf-8')
        got_user, _, got_password = decoded.partition(':')
    except Exception:                                    # noqa: BLE001
        return False
    # compare_digest on both halves, and always evaluate both, so a wrong
    # username is not distinguishable from a wrong password by timing.
    ok_user = hmac.compare_digest(got_user, user)
    ok_password = hmac.compare_digest(got_password, password)
    return ok_user and ok_password


def install(server, creds) -> None:
    """Enforce the access policy on every request the Flask server handles.

    - credentials configured: every request needs HTTP Basic auth;
    - none configured: only requests from this machine are served.

    Enforced per request, in the app itself, because the bind address is not
    always ours to check.  This used to run only from `modena-portal`
    (run._serve), so the production recipe -- gunicorn "modena_portal.app:
    server" -- served everything to everyone even with MODENA_PORTAL_USER and
    MODENA_PORTAL_PASSWORD set.  app.py now calls this, so any WSGI server
    gets it.  Behind a reverse proxy on the same host the client address is
    loopback, and authentication is then the proxy's job.

    Idempotent: a second call on the same server is a no-op.
    """
    if server.config.get('MODENA_PORTAL_POLICY_INSTALLED'):
        return
    server.config['MODENA_PORTAL_POLICY_INSTALLED'] = True

    if creds is not None:
        user, password = creds

        @server.before_request
        def _require_auth():                             # noqa: ANN202
            if _authorised(request.headers.get('Authorization', ''), user, password):
                return None
            return Response(
                'Authentication required.\n', 401,
                {'WWW-Authenticate': 'Basic realm="MoDeNa Portal"'},
            )

        _log.info('portal: HTTP Basic authentication enabled for user %r', user)
        return

    @server.before_request
    def _loopback_only():                                # noqa: ANN202
        if is_loopback(request.remote_addr or ''):
            return None
        return Response(
            'This portal has no credentials configured, so it only serves '
            'requests from its own machine.\nSet MODENA_PORTAL_USER and '
            'MODENA_PORTAL_PASSWORD to serve the network.\n', 403,
        )

    _log.info('portal: no credentials configured; serving loopback clients only')
