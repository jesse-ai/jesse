from types import SimpleNamespace
from urllib.parse import SplitResult

import pytest

import jesse.mcp.mcp_config as mcp_config
import jesse.services.dashboard_url as dashboard_url_module
from jesse.mcp.tools.services import backtest as backtest_service
from jesse.mcp.tools.services import monte_carlo as monte_carlo_service
from jesse.mcp.tools.services import optimization as optimization_service
from jesse.mcp.tools.services import significance_test as significance_test_service
from jesse.services.dashboard_url import (
    InvalidDashboardUrlError,
    default_dashboard_url,
    internal_api_url,
    mcp_endpoint_url,
    normalize_dashboard_url,
    resolve_dashboard_url,
)


@pytest.mark.parametrize(
    ('env_values', 'bind_host', 'expected'),
    [
        ({}, '0.0.0.0', 'http://localhost:9000'),
        ({'DASHBOARD_URL': None}, '0.0.0.0', 'http://localhost:9000'),
        ({'DASHBOARD_URL': '   '}, '::', 'http://localhost:9000'),
        ({}, '', 'http://localhost:9000'),
        ({}, '192.168.1.20', 'http://192.168.1.20:9000'),
        ({}, 'fd00::10', 'http://[fd00::10]:9000'),
        ({'DASHBOARD_URL': 'http://mini.local:9000/'}, '0.0.0.0', 'http://mini.local:9000'),
    ],
)
def test_resolve_dashboard_url_defaults_and_overrides(env_values, bind_host, expected):
    assert resolve_dashboard_url(env_values, bind_host, 9000) == expected


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        ('http://192.168.1.20:9000', 'http://192.168.1.20:9000'),
        ('  HTTPS://Jesse.Example.COM/  ', 'https://jesse.example.com'),
        ('https://jesse.example.com:8443', 'https://jesse.example.com:8443'),
        ('http://[FD00::10]:9000/', 'http://[fd00::10]:9000'),
        ('http://[::1]:9000', 'http://[::1]:9000'),
        ('http://mac_mini.local:9000', 'http://mac_mini.local:9000'),
        ('http://xn--bcher-kva.example', 'http://xn--bcher-kva.example'),
        # Surrounding whitespace, such as a trailing newline from a pasted value, is trimmed.
        ('http://mini.local\n', 'http://mini.local'),
    ],
)
def test_normalize_dashboard_url_accepts_origins(value, expected):
    assert normalize_dashboard_url(value) == expected


@pytest.mark.parametrize(
    ('value', 'reason'),
    [
        ('', 'empty'),
        ('mini.local:9000', 'http:// or https://'),
        ('ftp://mini.local', 'http:// or https://'),
        ('http://', 'no host'),
        ('http://mini.local/jesse', 'without a path'),
        ('http://mini.local/jesse/', 'without a path'),
        ('http://mini.local//', 'without a path'),
        ('http://mini.local/?x=1', 'query or fragment'),
        ('http://mini.local/#/backtest', 'query or fragment'),
        ('http://mini.local?', 'query or fragment'),
        ('http://user:secret@mini.local', 'username or password'),
        ('http://user@mini.local', 'username or password'),
        ('http://0.0.0.0:9000', 'wildcard'),
        ('http://[::]:9000', 'wildcard'),
        ('http://mini.local:0', 'malformed host or port'),
        ('http://mini.local:70000', 'above 65535'),
        ('http://mini.local:abc', 'malformed host or port'),
        ('http://mini.local:', 'malformed host or port'),
        ('http://[::1]:', 'malformed host or port'),
        ('http://mini.local:080', 'malformed host or port'),
        ('http://mini.local:9000:9001', 'malformed host or port'),
        ('http://mini.local]:9000', 'not a valid URL|malformed host or port'),
        ('http://[::1]garbage:9000', 'not a valid URL|malformed host or port'),
        ('http://[::1]garbage', 'not a valid URL|malformed host or port'),
        ('http://[[::1]]:9000', 'not a valid URL|malformed host or port'),
        ('http://[fd00::10', 'not a valid URL'),
        ('http://[fe80::1%25en0]:9000', 'IPv6'),
        ('http://mini local:9000', 'whitespace'),
        ('http://bücher.example', 'ASCII'),
        ('http://mini.local\\evil', 'backslash'),
        ('http://-bad-.example', 'invalid host name'),
        ('http://192.168.1.020', 'invalid host name'),
        ('http://::1:9000', 'not a valid URL|malformed host or port'),
    ],
)
def test_normalize_dashboard_url_rejects_unsupported_values(value, reason):
    with pytest.raises(InvalidDashboardUrlError, match=reason):
        normalize_dashboard_url(value)


@pytest.mark.parametrize(
    'value',
    ['http://user:secret@mini.local:abc', 'user:secret@mini.local', 'ftp://user:secret@mini.local/x?y#z'],
)
def test_normalize_dashboard_url_never_echoes_credentials(value):
    with pytest.raises(InvalidDashboardUrlError) as exc_info:
        normalize_dashboard_url(value)

    assert 'username or password' in str(exc_info.value)
    assert 'secret' not in str(exc_info.value)


@pytest.mark.parametrize('netloc', ['[::1]garbage:9000', '[::1]garbage', 'mini.local:', '[::1]:'])
def test_malformed_authority_is_rejected_even_if_urlsplit_accepts_it(monkeypatch, netloc):
    # Older Pythons split some malformed bracketed authorities without raising; the
    # validator must not depend on urlsplit to catch them.
    lenient = SplitResult(scheme='http', netloc=netloc, path='', query='', fragment='')
    monkeypatch.setattr(dashboard_url_module, 'urlsplit', lambda _value: lenient)

    with pytest.raises(InvalidDashboardUrlError, match='malformed host or port'):
        normalize_dashboard_url('http://placeholder')


def test_resolve_dashboard_url_propagates_validation_errors():
    with pytest.raises(InvalidDashboardUrlError):
        resolve_dashboard_url({'DASHBOARD_URL': 'http://mini.local/jesse'}, '0.0.0.0', 9000)


@pytest.mark.parametrize(
    ('bind_host', 'expected'),
    [
        ('0.0.0.0', 'http://127.0.0.1:9000'),
        ('', 'http://127.0.0.1:9000'),
        (None, 'http://127.0.0.1:9000'),
        ('::', 'http://[::1]:9000'),
        ('[::]', 'http://[::1]:9000'),
        ('127.0.0.1', 'http://127.0.0.1:9000'),
        ('192.168.1.20', 'http://192.168.1.20:9000'),
        ('fd00::10', 'http://[fd00::10]:9000'),
    ],
)
def test_internal_api_url_uses_bind_address_not_public_url(bind_host, expected):
    assert internal_api_url(bind_host, 9000) == expected


def test_default_dashboard_url_matches_historical_localhost_link():
    assert default_dashboard_url('0.0.0.0', 9000) == 'http://localhost:9000'


def test_mcp_endpoint_is_derived_from_the_dashboard_origin():
    assert mcp_endpoint_url('https://jesse.example.com') == 'https://jesse.example.com/mcp'
    assert mcp_endpoint_url('http://[fd00::10]:9000') == 'http://[fd00::10]:9000/mcp'


@pytest.mark.parametrize(
    ('category', 'route'),
    [
        ('backtest', 'backtest'),
        ('optimization', 'optimization'),
        ('monte_carlo', 'monte-carlo'),
        ('significance_test', 'significance-test'),
        ('strategy', 'strategies'),
    ],
)
@pytest.mark.parametrize(
    'base',
    ['http://localhost:9000', 'https://jesse.example.com', 'http://[fd00::10]:9000'],
)
def test_dashboard_links_use_public_origin_for_every_session_category(monkeypatch, category, route, base):
    monkeypatch.setattr(mcp_config, 'DASHBOARD_URL', base)

    assert mcp_config.dashboard_url(category, 'abc-123') == f'{base}/#/{route}/abc-123'


def test_dashboard_link_is_empty_without_origin_category_or_id(monkeypatch):
    monkeypatch.setattr(mcp_config, 'DASHBOARD_URL', None)
    assert mcp_config.dashboard_url('backtest', 'abc') == ''

    monkeypatch.setattr(mcp_config, 'DASHBOARD_URL', 'http://localhost:9000')
    assert mcp_config.dashboard_url('unknown', 'abc') == ''
    assert mcp_config.dashboard_url('backtest', '') == ''


def test_dashboard_link_escapes_session_id(monkeypatch):
    monkeypatch.setattr(mcp_config, 'DASHBOARD_URL', 'http://localhost:9000')

    assert mcp_config.dashboard_url('backtest', 'a/b?c') == 'http://localhost:9000/#/backtest/a%2Fb%3Fc'


@pytest.mark.parametrize(
    ('service', 'function_name', 'api_path', 'route'),
    [
        (backtest_service, 'get_backtest_session_service', 'backtest', 'backtest'),
        (optimization_service, 'get_optimization_session_service', 'optimization', 'optimization'),
        (monte_carlo_service, 'get_monte_carlo_session_service', 'monte-carlo', 'monte-carlo'),
        (
            significance_test_service,
            'get_significance_test_session_service',
            'significance-test',
            'significance-test',
        ),
    ],
)
def test_session_tools_call_internal_api_but_link_to_public_dashboard(
    monkeypatch, service, function_name, api_path, route,
):
    requested_urls = []

    def fake_post(url, **_kwargs):
        requested_urls.append(url)
        return SimpleNamespace(status_code=200, text='', json=lambda: {'session': {'id': 'session-id'}})

    monkeypatch.setattr(mcp_config, 'JESSE_API_URL', 'http://127.0.0.1:9000')
    monkeypatch.setattr(mcp_config, 'JESSE_PASSWORD', 'test-password')
    monkeypatch.setattr(mcp_config, 'DASHBOARD_URL', 'https://jesse.example.com')
    monkeypatch.setattr(service.requests, 'post', fake_post)

    result = getattr(service, function_name)('session-id')

    assert requested_urls == [f'http://127.0.0.1:9000/{api_path}/sessions/session-id']
    assert result['dashboard_url'] == f'https://jesse.example.com/#/{route}/session-id'
