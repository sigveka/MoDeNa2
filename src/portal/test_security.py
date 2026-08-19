"""
Tests for the portal's bind-address policy and Basic authentication.

The portal used to bind 0.0.0.0:8050 with no authentication.  That was
survivable while it was read-only; it now promotes fitted parameters and (with
the point-request flow) queues exact simulations that spend real compute, so
the one rule these tests pin is:

    binding anywhere other than loopback requires credentials.

No MongoDB and no libmodena -- the policy is pure logic.
"""
import base64

import pytest

from modena_portal.security import (
    InsecureConfiguration, _authorised, check_bind_policy, credentials,
    is_loopback,
)


class TestLoopbackDetection:

    @pytest.mark.parametrize('host', ['127.0.0.1', '::1', 'localhost', '127.0.0.5'])
    def test_loopback(self, host):
        assert is_loopback(host)

    @pytest.mark.parametrize('host', ['0.0.0.0', '192.168.1.5', '::', 'example.com'])
    def test_not_loopback(self, host):
        assert not is_loopback(host)


class TestBindPolicy:

    def test_loopback_needs_no_credentials(self):
        check_bind_policy('127.0.0.1', None)          # must not raise

    def test_public_bind_without_credentials_is_refused(self):
        """The whole point: no silent public listener."""
        with pytest.raises(InsecureConfiguration) as exc:
            check_bind_policy('0.0.0.0', None)
        message = str(exc.value)
        assert 'MODENA_PORTAL_USER' in message, 'must say how to fix it'
        assert 'MODENA_PORTAL_PASSWORD' in message

    def test_public_bind_with_credentials_is_allowed(self):
        check_bind_policy('0.0.0.0', ('alice', 's3cret'))

    def test_lan_address_is_also_refused(self):
        with pytest.raises(InsecureConfiguration):
            check_bind_policy('192.168.1.5', None)


class TestCredentials:

    def test_absent_by_default(self, monkeypatch):
        monkeypatch.delenv('MODENA_PORTAL_USER', raising=False)
        monkeypatch.delenv('MODENA_PORTAL_PASSWORD', raising=False)
        assert credentials() is None

    def test_both_required(self, monkeypatch):
        """A username with no password must not half-enable auth."""
        monkeypatch.setenv('MODENA_PORTAL_USER', 'alice')
        monkeypatch.delenv('MODENA_PORTAL_PASSWORD', raising=False)
        assert credentials() is None

    def test_read_from_environment(self, monkeypatch):
        monkeypatch.setenv('MODENA_PORTAL_USER', 'alice')
        monkeypatch.setenv('MODENA_PORTAL_PASSWORD', 's3cret')
        assert credentials() == ('alice', 's3cret')


def _header(user, password):
    token = base64.b64encode(f'{user}:{password}'.encode()).decode()
    return f'Basic {token}'


class TestBasicAuth:

    def test_correct_credentials(self):
        assert _authorised(_header('alice', 's3cret'), 'alice', 's3cret')

    @pytest.mark.parametrize('user,password', [
        ('alice', 'wrong'), ('bob', 's3cret'), ('', ''), ('alice', ''),
    ])
    def test_rejects_wrong_credentials(self, user, password):
        assert not _authorised(_header(user, password), 'alice', 's3cret')

    @pytest.mark.parametrize('header', ['', 'Bearer xyz', 'Basic !!!not-base64'])
    def test_rejects_malformed_header(self, header):
        assert not _authorised(header, 'alice', 's3cret')

    def test_password_containing_a_colon(self):
        """partition() splits on the first colon, so the password keeps the rest."""
        assert _authorised(_header('alice', 'a:b:c'), 'alice', 's3cret') is False
        assert _authorised(_header('alice', 'a:b:c'), 'alice', 'a:b:c')
