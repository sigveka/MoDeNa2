"""HTTP Basic authentication and bind-address policy for the portal.

The portal used to bind 0.0.0.0:8050 with no authentication.  That was
tolerable while it was strictly read-only, but it now has write actions --
promoting fitted parameters, and queueing exact simulations that spend real
compute -- so an unauthenticated listener on every interface is no longer a
tidiness issue.

The policy is one rule:

    binding anywhere other than loopback requires credentials.

A loopback bind is left open so the common case (`modena-portal` on your own
machine) needs no setup, and exposing it to a network without a password is
refused rather than warned about.  No new dependency: Dash already runs on
Flask, which is all Basic auth needs.
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
    """Attach Basic auth to the Flask server, if credentials are configured."""
    if creds is None:
        return
    user, password = creds

    @server.before_request
    def _require_auth():                                 # noqa: ANN202
        if _authorised(request.headers.get('Authorization', ''), user, password):
            return None
        return Response(
            'Authentication required.\n', 401,
            {'WWW-Authenticate': 'Basic realm="MoDeNa Portal"'},
        )

    _log.info('portal: HTTP Basic authentication enabled for user %r', user)
