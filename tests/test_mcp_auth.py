import hashlib
import json
import os
import socket
import subprocess
import sys
from types import SimpleNamespace

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


@pytest.mark.parametrize(
    ('listen_fd', 'handoff_args'),
    [(7, ['--listen_fd', '7']), (None, ['--listen_share'])],
)
def test_build_worker_launch_keeps_password_out_of_argv(listen_fd, handoff_args):
    argv, env = manager.build_worker_launch(
        'http://127.0.0.1:9000', 'https://jesse.example.com', PASSWORD, listen_fd, base_env={'PATH': '/bin'},
    )

    assert argv == [
        sys.executable, '-m', 'jesse.mcp.server',
        '--api_url', 'http://127.0.0.1:9000',
        '--dashboard_url', 'https://jesse.example.com',
        *handoff_args,
    ]
    assert all(PASSWORD not in arg and TOKEN not in arg for arg in argv)
    assert env == {'PATH': '/bin', mcp_config.WORKER_PASSWORD_ENV: PASSWORD}


class _FakeProcess:
    """A worker that stays up: it never exits during the startup check."""

    # Windows socket.share() needs a real recipient PID, even when Popen is a stand-in.
    pid = os.getpid()
    returncode = None

    def __init__(self):
        self.handoff = bytearray()
        self.stdin = SimpleNamespace(write=self.handoff.extend, close=lambda: None)

    def poll(self):
        return None

    def wait(self, timeout=None):
        raise subprocess.TimeoutExpired('jesse.mcp.server', timeout)

    def terminate(self):
        pass

    def kill(self):
        pass


@pytest.fixture
def isolated_manager(monkeypatch):
    """Keep run_mcp_server from touching real processes, signal handlers, or shared config."""
    launches = []

    def fake_popen(argv, **kwargs):
        launches.append((argv, kwargs))
        return _FakeProcess()

    monkeypatch.setattr(manager.subprocess, 'Popen', fake_popen)
    monkeypatch.setattr(manager.signal, 'signal', lambda *args: None)
    monkeypatch.setattr(manager, 'MCP_WORKER', None)
    for name in ('JESSE_API_URL', 'JESSE_PASSWORD', 'DASHBOARD_URL', 'MCP_WORKER_PORT', 'MCP_URL'):
        monkeypatch.setattr(mcp_config, name, getattr(mcp_config, name))
    monkeypatch.setitem(ENV_VALUES, 'PASSWORD', PASSWORD)
    monkeypatch.delitem(ENV_VALUES, 'MCP_PORT', raising=False)
    monkeypatch.setitem(ENV_VALUES, 'MCP_LOG_IN_TERMINAL', 'true')
    yield launches
    if manager.MCP_WORKER is not None:
        manager.MCP_WORKER.release_socket()


@pytest.mark.parametrize(
    ('bind_host', 'api_url'),
    [('0.0.0.0', 'http://127.0.0.1:9000'), ('::', 'http://[::1]:9000'), ('192.168.1.20', 'http://192.168.1.20:9000')],
)
def test_run_mcp_server_launches_loopback_worker_with_public_url(isolated_manager, capsys, bind_host, api_url):
    manager.run_mcp_server(bind_host, 9000, 'https://jesse.example.com')

    [(argv, kwargs)] = isolated_manager
    if sys.platform == 'win32':
        assert '--listen_share' in argv and 'pass_fds' not in kwargs
        assert kwargs['stdin'] == subprocess.PIPE
    else:
        listen_fd = int(argv[argv.index('--listen_fd') + 1])
        # Exactly the reserved listening socket is handed over; every other descriptor is closed.
        assert kwargs['pass_fds'] == (listen_fd,)
        assert kwargs.get('close_fds', True) is True
    assert '--port' not in argv
    assert argv[argv.index('--api_url') + 1] == api_url
    assert argv[argv.index('--dashboard_url') + 1] == 'https://jesse.example.com'
    assert '--password' not in argv
    assert all(PASSWORD not in arg for arg in argv)
    assert kwargs['shell'] is False
    assert kwargs['env'][mcp_config.WORKER_PASSWORD_ENV] == PASSWORD

    worker = manager.MCP_WORKER
    assert worker is not None
    assert mcp_config.MCP_WORKER_PORT == worker.port
    assert manager.running_worker_port() == worker.port
    if sys.platform == 'win32':
        # The parent keeps its handle while the worker adopts a Windows socket share.
        assert worker.held_socket is not None
        with socket.fromshare(bytes(worker.process.handoff)) as adopted:
            assert adopted.getsockname() == ('127.0.0.1', worker.port)
    else:
        assert worker.held_socket is None
        with pytest.raises(OSError):
            os.fstat(listen_fd)

    assert mcp_config.JESSE_API_URL == api_url
    assert mcp_config.MCP_URL == 'https://jesse.example.com/mcp'
    assert mcp_config.DASHBOARD_URL == 'https://jesse.example.com'

    output = capsys.readouterr().out
    assert 'https://jesse.example.com/mcp' in output
    # The internal port is never presented as an endpoint.
    assert str(worker.port) not in output
    assert 'MCP_PORT' not in output
    assert PASSWORD not in output
    assert TOKEN not in output


@pytest.mark.parametrize('legacy_value', ['9002', '9555', 'not-a-port', '0'])
def test_run_mcp_server_ignores_legacy_mcp_port(isolated_manager, capsys, monkeypatch, legacy_value):
    monkeypatch.setitem(ENV_VALUES, 'MCP_PORT', legacy_value)

    manager.run_mcp_server('0.0.0.0', 9000, 'http://localhost:9000')

    [(argv, _kwargs)] = isolated_manager
    assert legacy_value not in argv
    assert manager.MCP_WORKER is not None
    assert str(manager.MCP_WORKER.port) != legacy_value
    output = capsys.readouterr().out
    assert 'MCP_PORT in your .env file is no longer used and can be removed' in output
    assert 'http://localhost:9000/mcp' in output


@pytest.mark.parametrize('value', [None, '', '  '])
def test_run_mcp_server_does_not_mention_an_unset_legacy_port(isolated_manager, capsys, monkeypatch, value):
    if value is not None:
        monkeypatch.setitem(ENV_VALUES, 'MCP_PORT', value)

    manager.run_mcp_server('0.0.0.0', 9000, 'http://localhost:9000')

    assert 'MCP_PORT' not in capsys.readouterr().out


def test_run_mcp_server_does_not_start_a_second_worker(isolated_manager, capsys):
    manager.run_mcp_server('0.0.0.0', 9000, 'http://localhost:9000')
    first = manager.MCP_WORKER

    manager.run_mcp_server('0.0.0.0', 9000, 'http://localhost:9000')

    assert len(isolated_manager) == 1
    assert manager.MCP_WORKER is first
    assert 'already running' in capsys.readouterr().out


def test_run_mcp_server_requires_password(monkeypatch, isolated_manager):
    monkeypatch.setitem(ENV_VALUES, 'PASSWORD', '')

    with pytest.raises(Exception, match='PASSWORD'):
        manager.run_mcp_server('0.0.0.0', 9000, 'http://localhost:9000')

    assert isolated_manager == []


@pytest.mark.parametrize(
    'args',
    [
        # A password is never accepted on the command line.
        ['--listen_fd', '3', '--api_url', 'http://127.0.0.1:9000', '--dashboard_url', 'http://localhost:9000',
         '--password', PASSWORD],
        # The worker cannot choose a port of its own; it only serves the socket it is given.
        ['--port', '9555', '--api_url', 'http://127.0.0.1:9000', '--dashboard_url', 'http://localhost:9000'],
        ['--api_url', 'http://127.0.0.1:9000', '--dashboard_url', 'http://localhost:9000'],
        ['--listen_fd', '3', '--listen_share', '--api_url', 'http://127.0.0.1:9000',
         '--dashboard_url', 'http://localhost:9000'],
    ],
)
def test_worker_rejects_invalid_launch_arguments(args):
    with pytest.raises(SystemExit):
        mcp_server.parse_args(args)


class _HandedOverSocket:
    """A reserved loopback socket whose descriptor is handed to main() as the worker gets it."""

    def __init__(self) -> None:
        sock = manager.reserve_worker_socket()
        self.port = sock.getsockname()[1]
        # Ownership of the descriptor moves to main(), exactly as in the worker process.
        self.fd = sock.detach()
        self.adopted = None

    def close(self) -> None:
        # Close through whichever owner holds the descriptor, never twice: a second close
        # could hit an unrelated descriptor that reused the number.
        if self.adopted is not None:
            self.adopted.close()
        else:
            # Winsock handles must be closed as sockets, not CRT file descriptors.
            socket.close(self.fd)


@pytest.fixture
def isolated_worker_main(monkeypatch):
    """Run the worker's main() on a real handed-over socket without serving or leaking state."""
    served = []
    handed_over = _HandedOverSocket()

    def fake_serve(app, sock):
        handed_over.adopted = sock
        served.append((app, sock))

    monkeypatch.setattr(mcp_server, 'serve', fake_serve)
    monkeypatch.setattr(sys, 'excepthook', sys.excepthook)
    for name in ('JESSE_API_URL', 'JESSE_PASSWORD', 'DASHBOARD_URL', 'MCP_WORKER_PORT', 'MCP_URL'):
        monkeypatch.setattr(mcp_config, name, getattr(mcp_config, name))
    yield SimpleNamespace(
        served=served,
        port=handed_over.port,
        args=['--listen_fd', str(handed_over.fd), '--api_url', 'http://127.0.0.1:9000',
              '--dashboard_url', 'https://Jesse.Example.com/'],
    )
    handed_over.close()


def test_worker_main_serves_authenticated_app_on_handed_over_socket(monkeypatch, isolated_worker_main):
    monkeypatch.setenv(mcp_config.WORKER_PASSWORD_ENV, PASSWORD)

    mcp_server.main(isolated_worker_main.args)

    [(app, sock)] = isolated_worker_main.served
    assert isinstance(app, McpTokenAuthMiddleware)
    assert app.expected_token == TOKEN
    assert sock.getsockname() == ('127.0.0.1', isolated_worker_main.port)
    # Processes the tools spawn must not inherit the listener.
    assert sock.get_inheritable() is False
    # The password is removed from the environment so spawned processes do not inherit it.
    assert mcp_config.WORKER_PASSWORD_ENV not in os.environ
    assert mcp_config.JESSE_API_URL == 'http://127.0.0.1:9000'
    assert mcp_config.JESSE_PASSWORD == PASSWORD
    assert mcp_config.MCP_WORKER_PORT == isolated_worker_main.port
    assert mcp_config.DASHBOARD_URL == 'https://jesse.example.com'
    assert mcp_config.MCP_URL == 'https://jesse.example.com/mcp'


def test_worker_main_exits_without_password(monkeypatch, isolated_worker_main):
    monkeypatch.delenv(mcp_config.WORKER_PASSWORD_ENV, raising=False)

    with pytest.raises(SystemExit) as exc_info:
        mcp_server.main(isolated_worker_main.args)

    assert exc_info.value.code == 2
    assert isolated_worker_main.served == []


def test_worker_main_rejects_invalid_dashboard_url(monkeypatch, isolated_worker_main):
    monkeypatch.setenv(mcp_config.WORKER_PASSWORD_ENV, PASSWORD)
    args = isolated_worker_main.args
    args[args.index('--dashboard_url') + 1] = 'http://x/prefix'

    with pytest.raises(SystemExit) as exc_info:
        mcp_server.main(args)

    assert exc_info.value.code == 2
    assert isolated_worker_main.served == []


def test_worker_main_exits_when_the_descriptor_is_not_a_socket(monkeypatch, isolated_worker_main):
    monkeypatch.setenv(mcp_config.WORKER_PASSWORD_ENV, PASSWORD)
    read_end, write_end = os.pipe()
    try:
        args = isolated_worker_main.args
        args[args.index('--listen_fd') + 1] = str(read_end)

        with pytest.raises(SystemExit) as exc_info:
            mcp_server.main(args)
    finally:
        os.close(read_end)
        os.close(write_end)

    assert exc_info.value.code == 2
    assert isolated_worker_main.served == []
