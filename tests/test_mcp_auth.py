import hashlib
import json
import os
import sys

import pytest
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

import jesse.mcp.manager as manager
import jesse.mcp.mcp_config as mcp_config
import jesse.mcp.server as mcp_server
from jesse.mcp.auth import (
    McpTokenAuthMiddleware,
    dashboard_token,
    is_authorized,
    token_from_authorization,
)
from jesse.services.auth import password_to_token
from jesse.services.env import ENV_VALUES

PASSWORD = 'unit-test-password'
TOKEN = dashboard_token(PASSWORD)


def test_dashboard_token_matches_dashboard_login_token(monkeypatch):
    monkeypatch.setitem(ENV_VALUES, 'PASSWORD', PASSWORD)

    body = json.loads(password_to_token(PASSWORD).body)

    assert body['auth_token'] == TOKEN


@pytest.mark.parametrize(
    ('values', 'expected'),
    [
        ([f'Bearer {TOKEN}'], TOKEN),
        ([f'bearer   {TOKEN}  '], TOKEN),
        ([TOKEN], TOKEN),
        ([], None),
        ([''], None),
        (['Bearer'], 'Bearer'),
        ([f'Basic {TOKEN}'], None),
        ([f'Bearer {TOKEN}', f'Bearer {TOKEN}'], None),
    ],
)
def test_token_from_authorization(values, expected):
    assert token_from_authorization(values) == expected


def test_dashboard_token_refuses_empty_password():
    with pytest.raises(ValueError):
        dashboard_token('')


def test_middleware_refuses_empty_expected_token():
    async def app(scope, receive, send):
        raise AssertionError('must not be reachable')

    with pytest.raises(ValueError):
        McpTokenAuthMiddleware(app, '')


@pytest.mark.parametrize('password', ['', None])
def test_worker_app_factory_refuses_empty_password(password):
    # The worker must never be built with the well-known SHA-256 of an empty string as
    # its token, even when create_app is called directly rather than through main().
    mcp = FastMCP('factory-test')

    with pytest.raises(ValueError, match='non-empty PASSWORD'):
        mcp_server.create_app(mcp, password)


def test_worker_app_factory_rejects_empty_password_hash_for_valid_app():
    app = mcp_server.create_app(FastMCP('factory-test'), PASSWORD)
    empty_password_token = hashlib.sha256(b'').hexdigest()

    response = TestClient(app).post('/mcp', headers={'Authorization': f'Bearer {empty_password_token}'}, json={})

    assert response.status_code == 401


def test_is_authorized_requires_the_exact_token():
    assert is_authorized([f'Bearer {TOKEN}'], TOKEN)
    assert is_authorized([TOKEN], TOKEN)
    assert not is_authorized([f'Bearer {TOKEN}x'], TOKEN)
    assert not is_authorized([f'Bearer {PASSWORD}'], TOKEN)
    assert not is_authorized([], TOKEN)
    # An unset PASSWORD must never authorize anything, including an empty token.
    assert not is_authorized([''], '')
    assert not is_authorized(['Bearer '], '')


def _protected_client() -> TestClient:
    async def endpoint(request):
        return PlainTextResponse('ok')

    app = Starlette(routes=[Route('/mcp', endpoint, methods=['GET', 'POST', 'DELETE'])])
    return TestClient(McpTokenAuthMiddleware(app, TOKEN))


@pytest.mark.parametrize('method', ['GET', 'POST', 'DELETE'])
@pytest.mark.parametrize(
    'headers',
    [{}, {'Authorization': 'Bearer wrong'}, {'Authorization': f'Basic {TOKEN}'}, {'Authorization': PASSWORD}],
)
def test_middleware_rejects_missing_or_wrong_token(method, headers):
    response = _protected_client().request(method, '/mcp', headers=headers)

    assert response.status_code == 401
    assert response.headers['www-authenticate'] == 'Bearer realm="Jesse MCP"'
    assert 'resource_metadata' not in response.headers['www-authenticate']
    assert TOKEN not in response.text
    assert PASSWORD not in response.text


@pytest.mark.parametrize('method', ['GET', 'POST', 'DELETE'])
@pytest.mark.parametrize('authorization', [f'Bearer {TOKEN}', TOKEN])
def test_middleware_accepts_bearer_and_bare_token(method, authorization):
    response = _protected_client().request(method, '/mcp', headers={'Authorization': authorization})

    assert response.status_code == 200
    assert response.text == 'ok'


def test_middleware_passes_lifespan_through():
    events = []

    async def app(scope, receive, send):
        if scope['type'] == 'lifespan':
            while True:
                message = await receive()
                events.append(message['type'])
                if message['type'] == 'lifespan.startup':
                    await send({'type': 'lifespan.startup.complete'})
                elif message['type'] == 'lifespan.shutdown':
                    await send({'type': 'lifespan.shutdown.complete'})
                    return

    with TestClient(McpTokenAuthMiddleware(app, TOKEN)):
        pass

    assert events == ['lifespan.startup', 'lifespan.shutdown']


def test_build_worker_launch_keeps_password_out_of_argv():
    argv, env = manager.build_worker_launch(
        'http://127.0.0.1:9000', 'https://jesse.example.com', 9555, PASSWORD, base_env={'PATH': '/bin'},
    )

    assert argv == [
        sys.executable, '-m', 'jesse.mcp.server',
        '--port', '9555',
        '--api_url', 'http://127.0.0.1:9000',
        '--dashboard_url', 'https://jesse.example.com',
    ]
    assert all(PASSWORD not in arg and TOKEN not in arg for arg in argv)
    assert env == {'PATH': '/bin', mcp_config.WORKER_PASSWORD_ENV: PASSWORD}


class _FakeProcess:
    def poll(self):
        return None


@pytest.fixture
def isolated_manager(monkeypatch):
    """Keep run_mcp_server from touching real processes, signal handlers, or shared config."""
    launches = []

    def fake_popen(argv, **kwargs):
        launches.append((argv, kwargs))
        return _FakeProcess()

    monkeypatch.setattr('subprocess.Popen', fake_popen)
    monkeypatch.setattr(manager.signal, 'signal', lambda *args: None)
    monkeypatch.setattr('time.sleep', lambda _seconds: None)
    monkeypatch.setattr(manager, 'MCP_PROCESS', None)
    for name in ('JESSE_API_URL', 'JESSE_PASSWORD', 'DASHBOARD_URL', 'MCP_PORT', 'MCP_URL'):
        monkeypatch.setattr(mcp_config, name, getattr(mcp_config, name))
    monkeypatch.setitem(ENV_VALUES, 'PASSWORD', PASSWORD)
    monkeypatch.setitem(ENV_VALUES, 'MCP_PORT', '9555')
    monkeypatch.setitem(ENV_VALUES, 'MCP_LOG_IN_TERMINAL', 'true')
    return launches


@pytest.mark.parametrize(
    ('bind_host', 'api_url'),
    [('0.0.0.0', 'http://127.0.0.1:9000'), ('::', 'http://[::1]:9000'), ('192.168.1.20', 'http://192.168.1.20:9000')],
)
def test_run_mcp_server_launches_loopback_worker_with_public_url(isolated_manager, capsys, bind_host, api_url):
    manager.run_mcp_server(bind_host, 9000, 'https://jesse.example.com')

    [(argv, kwargs)] = isolated_manager
    assert argv[argv.index('--port') + 1] == '9555'
    assert argv[argv.index('--api_url') + 1] == api_url
    assert argv[argv.index('--dashboard_url') + 1] == 'https://jesse.example.com'
    assert '--password' not in argv
    assert all(PASSWORD not in arg for arg in argv)
    assert kwargs['shell'] is False
    assert kwargs['env'][mcp_config.WORKER_PASSWORD_ENV] == PASSWORD

    assert mcp_config.JESSE_API_URL == api_url
    assert mcp_config.MCP_URL == 'https://jesse.example.com/mcp'
    assert mcp_config.DASHBOARD_URL == 'https://jesse.example.com'

    output = capsys.readouterr().out
    assert 'https://jesse.example.com/mcp' in output
    assert PASSWORD not in output
    assert TOKEN not in output


def test_run_mcp_server_requires_password(monkeypatch, isolated_manager):
    monkeypatch.setitem(ENV_VALUES, 'PASSWORD', '')

    with pytest.raises(Exception, match='PASSWORD'):
        manager.run_mcp_server('0.0.0.0', 9000, 'http://localhost:9000')

    assert isolated_manager == []


def test_worker_rejects_password_argument():
    with pytest.raises(SystemExit):
        mcp_server.parse_args([
            '--port', '9555', '--api_url', 'http://127.0.0.1:9000',
            '--dashboard_url', 'http://localhost:9000', '--password', PASSWORD,
        ])


@pytest.fixture
def isolated_worker_main(monkeypatch):
    """Run the worker's main() without binding a port or leaking global state."""
    served = []

    def fake_run(app, **kwargs):
        served.append((app, kwargs))

    monkeypatch.setattr(mcp_server.uvicorn, 'run', fake_run)
    monkeypatch.setattr(sys, 'excepthook', sys.excepthook)
    for name in ('JESSE_API_URL', 'JESSE_PASSWORD', 'DASHBOARD_URL', 'MCP_PORT', 'MCP_URL'):
        monkeypatch.setattr(mcp_config, name, getattr(mcp_config, name))
    return served


WORKER_ARGS = ['--port', '9555', '--api_url', 'http://127.0.0.1:9000', '--dashboard_url', 'https://Jesse.Example.com/']


def test_worker_main_serves_authenticated_app_on_loopback(monkeypatch, isolated_worker_main):
    monkeypatch.setenv(mcp_config.WORKER_PASSWORD_ENV, PASSWORD)

    mcp_server.main(WORKER_ARGS)

    [(app, kwargs)] = isolated_worker_main
    assert isinstance(app, McpTokenAuthMiddleware)
    assert app.expected_token == TOKEN
    assert kwargs['host'] == '127.0.0.1'
    assert kwargs['port'] == 9555
    # The password is removed from the environment so spawned processes do not inherit it.
    assert mcp_config.WORKER_PASSWORD_ENV not in os.environ
    assert mcp_config.JESSE_API_URL == 'http://127.0.0.1:9000'
    assert mcp_config.JESSE_PASSWORD == PASSWORD
    assert mcp_config.DASHBOARD_URL == 'https://jesse.example.com'
    assert mcp_config.MCP_URL == 'https://jesse.example.com/mcp'


def test_worker_main_exits_without_password(monkeypatch, isolated_worker_main):
    monkeypatch.delenv(mcp_config.WORKER_PASSWORD_ENV, raising=False)

    with pytest.raises(SystemExit) as exc_info:
        mcp_server.main(WORKER_ARGS)

    assert exc_info.value.code == 2
    assert isolated_worker_main == []


def test_worker_main_rejects_invalid_dashboard_url(monkeypatch, isolated_worker_main):
    monkeypatch.setenv(mcp_config.WORKER_PASSWORD_ENV, PASSWORD)

    with pytest.raises(SystemExit) as exc_info:
        mcp_server.main(['--port', '9555', '--api_url', 'http://127.0.0.1:9000', '--dashboard_url', 'http://x/prefix'])

    assert exc_info.value.code == 2
    assert isolated_worker_main == []
