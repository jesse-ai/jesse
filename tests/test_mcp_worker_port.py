"""
Real-process tests for the MCP worker's OS-assigned loopback port.

Each worker here is a real `python -m jesse.mcp.server` subprocess started by the manager
with its listening socket handed over, in a throwaway working directory that is not a
Jesse project, so no .env, key, or wallet file is ever read. The dashboard's /mcp route is
the real Jesse FastAPI app on a background thread. Only initialize, tools/list,
list_indicators (which reads the bundled indicator module), and a packaged resource are
exercised: nothing trades, touches the database, or reaches a license API.
"""

import asyncio
import errno
import os
import signal
import socket
import threading
from pathlib import Path
from typing import Dict, List, Optional

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

import jesse.mcp.manager as manager
import jesse.mcp.mcp_config as mcp_config
import jesse.mcp.server as mcp_server
from jesse.mcp.auth import dashboard_token
from jesse.services.env import ENV_VALUES
from jesse.services.web import fastapi_app
from tests.test_mcp_proxy import (
    MCP_ACCEPT,
    WAIT_SECONDS,
    _initialize_payload,
    _session_headers,
    _ThreadedServer,
)

PASSWORD = 'worker-port-test-password'
TOKEN = dashboard_token(PASSWORD)
AUTH = {'Authorization': f'Bearer {TOKEN}'}
# A worker needs a few seconds to import Jesse and register its tools before it answers.
WORKER_READY_SECONDS = 60

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Descriptor handoff is the POSIX code path.')


def _worker_env() -> Dict[str, str]:
    """This process's environment without pytest's markers, as `jesse run` would pass it."""
    return {key: value for key, value in os.environ.items() if not key.startswith('PYTEST')}


def _connection_refused(port: int) -> bool:
    """True when nothing listens on the loopback port any more."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        return probe.connect_ex((mcp_config.MCP_WORKER_HOST, port)) == errno.ECONNREFUSED


def _descriptors_bound_to(port: int) -> List[int]:
    """Return this process's descriptors for sockets bound to the loopback `port`."""
    fd_dir = '/proc/self/fd' if os.path.isdir('/proc/self/fd') else '/dev/fd'
    found = []
    for name in os.listdir(fd_dir):
        try:
            duplicate = os.dup(int(name))
        except OSError:
            continue  # The directory listing's own descriptor, already closed.
        try:
            sock = socket.socket(fileno=duplicate)
        except OSError:
            # Not a socket: socket() did not take ownership of the duplicate.
            os.close(duplicate)
            continue
        with sock:
            try:
                if sock.family == socket.AF_INET and sock.getsockname()[1] == port:
                    found.append(int(name))
            except OSError:
                pass
    return found


def _initialize(client: httpx.Client, url: str, headers: Optional[dict] = None) -> httpx.Response:
    return client.post(url, headers={**AUTH, 'Accept': MCP_ACCEPT, **(headers or {})}, json=_initialize_payload())


@pytest.fixture
def http():
    # trust_env=False keeps a developer's proxy settings out of loopback test traffic. The
    # read timeout covers a worker that is still loading while requests wait in its backlog.
    with httpx.Client(trust_env=False, timeout=WORKER_READY_SECONDS) as client:
        yield client


def _spawn_worker(directory: Path, log_name: str, password: str = PASSWORD) -> manager.McpWorker:
    """Start a real worker in `directory`, logging to `log_name`. Its API URL is a closed port."""
    log = open(directory / log_name, 'wb')
    try:
        return manager.start_worker(
            'http://127.0.0.1:9', 'http://localhost:9000', password,
            stdout=log, stderr=log, cwd=str(directory), base_env=_worker_env(),
        )
    finally:
        # The worker has its own copy of the descriptor.
        log.close()


@pytest.fixture
def start_worker(tmp_path):
    """Start real workers through the manager; every one is stopped at teardown."""
    workers: List[manager.McpWorker] = []

    def _start(password: str = PASSWORD) -> manager.McpWorker:
        worker = _spawn_worker(tmp_path, f'worker-{len(workers)}.log', password)
        workers.append(worker)
        return worker

    yield _start
    for worker in workers:
        worker.stop()


@pytest.fixture(scope='module')
def shared_worker(tmp_path_factory):
    worker = _spawn_worker(tmp_path_factory.mktemp('shared-worker'), 'worker.log')
    yield worker
    worker.stop()


@pytest.fixture(scope='module')
def proxy():
    # Lifespan is off so shutdown does not close the shared test database or LSP state.
    with _ThreadedServer(fastapi_app, lifespan='off') as server:
        yield server


@pytest.fixture
def jesse_run(monkeypatch, tmp_path):
    """
    Let run_mcp_server start a real worker as `jesse run` does, from a disposable directory,
    without installing signal handlers into pytest; stops it at teardown.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(manager.signal, 'signal', lambda *args: None)
    monkeypatch.setattr(manager, 'MCP_WORKER', None)
    for name in ('JESSE_API_URL', 'DASHBOARD_URL', 'MCP_WORKER_PORT', 'MCP_URL'):
        monkeypatch.setattr(mcp_config, name, getattr(mcp_config, name))
    monkeypatch.setitem(ENV_VALUES, 'PASSWORD', PASSWORD)
    monkeypatch.setitem(ENV_VALUES, 'MCP_LOG_IN_TERMINAL', 'false')
    monkeypatch.delitem(ENV_VALUES, 'MCP_PORT', raising=False)

    started: List[manager.McpWorker] = []
    real_start_worker = manager.start_worker

    def recording_start_worker(*args, **kwargs):
        worker = real_start_worker(*args, **kwargs)
        started.append(worker)
        return worker

    monkeypatch.setattr(manager, 'start_worker', recording_start_worker)
    yield started
    manager.terminate_mcp_server()
    for worker in started:
        worker.stop()


def test_reserved_socket_listens_on_loopback_with_an_os_assigned_port():
    sock = manager.reserve_worker_socket()
    try:
        host, port = sock.getsockname()
        assert (sock.family, sock.type) == (socket.AF_INET, socket.SOCK_STREAM)
        assert host == '127.0.0.1' and port > 0
        # Only a process it is explicitly handed to may inherit it.
        assert sock.get_inheritable() is False
        # Listening from the moment it is reserved: a connection is queued, not refused.
        with socket.create_connection((host, port), timeout=WAIT_SECONDS):
            pass
    finally:
        sock.close()
    assert _connection_refused(port)


def test_simultaneous_reservations_never_share_a_port():
    # Many threads released at once, as several Jesse instances starting together would
    # be, all ask the kernel for a port at the same moment.
    sockets: List[socket.socket] = []
    lock = threading.Lock()
    barrier = threading.Barrier(32)

    def reserve() -> None:
        barrier.wait()
        sock = manager.reserve_worker_socket()
        with lock:
            sockets.append(sock)

    threads = [threading.Thread(target=reserve) for _ in range(32)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(WAIT_SECONDS)
    try:
        ports = [sock.getsockname()[1] for sock in sockets]
        assert len(ports) == 32
        assert len(set(ports)) == 32
    finally:
        for sock in sockets:
            sock.close()


def test_worker_serves_on_the_handed_over_socket(start_worker, http, tmp_path):
    worker = start_worker()

    assert worker.held_socket is None
    # This process kept no descriptor for the listener...
    assert _descriptors_bound_to(worker.port) == []
    # ...yet the port is reserved while the worker is still loading: a request sent now
    # waits in the backlog and is answered once the worker serves.
    response = _initialize(http, f'http://127.0.0.1:{worker.port}/mcp')
    assert response.status_code == 200, response.text
    assert response.json()['result']['serverInfo']['name'] == 'Jesse MCP Server'

    log = (tmp_path / 'worker-0.log').read_text()
    assert f'MCP worker listening on internal loopback port {worker.port}; clients connect to http://localhost:9000/mcp' in log
    assert 'Uvicorn running on' not in log

    # Killed without any chance to clean up, the worker was the listener's only owner, so
    # the port is released immediately.
    worker.process.send_signal(signal.SIGKILL)
    worker.process.wait(WAIT_SECONDS)
    assert _connection_refused(worker.port)


def test_two_workers_run_side_by_side_with_their_own_ports_and_tokens(start_worker, http):
    other_password = 'second-instance-password'
    first = start_worker()
    second = start_worker(password=other_password)

    assert first.port != second.port
    for worker, own_token, foreign_token in (
        (first, TOKEN, dashboard_token(other_password)),
        (second, dashboard_token(other_password), TOKEN),
    ):
        url = f'http://127.0.0.1:{worker.port}/mcp'
        own = _initialize(http, url, {'Authorization': f'Bearer {own_token}'})
        assert own.status_code == 200, own.text
        foreign = _initialize(http, url, {'Authorization': f'Bearer {foreign_token}'})
        assert foreign.status_code == 401

    first.stop()
    assert _connection_refused(first.port)
    # Stopping one instance's worker leaves the other untouched.
    assert _initialize(http, f'http://127.0.0.1:{second.port}/mcp', {'Authorization': f'Bearer {dashboard_token(other_password)}'}).status_code == 200


@pytest.mark.parametrize(
    ('headers', 'status'),
    [
        ({}, 200),
        ({'Host': 'localhost:{port}'}, 200),
        ({'Origin': 'http://localhost:{port}'}, 200),
        ({'Origin': 'http://127.0.0.1:{port}'}, 200),
        ({'Host': 'evil.example'}, 421),
        ({'Host': 'evil.example:{port}'}, 421),
        ({'Host': '127.0.0.1.evil.example:{port}'}, 421),
        ({'Origin': 'http://evil.example'}, 403),
        ({'Origin': 'http://127.0.0.1.evil.example:{port}'}, 403),
        # Authentication comes first: an unauthenticated rebinding attempt learns nothing.
        ({'Host': 'evil.example', 'Authorization': 'Bearer wrong'}, 401),
    ],
)
def test_transport_security_holds_on_the_os_assigned_port(shared_worker, http, headers, status):
    port = shared_worker.port
    headers = {name: value.format(port=port) for name, value in headers.items()}

    response = _initialize(http, f'http://127.0.0.1:{port}/mcp', headers)

    assert response.status_code == status, response.text
    if status == 200:
        http.delete(f'http://127.0.0.1:{port}/mcp', headers=_session_headers(response.headers['mcp-session-id'], AUTH['Authorization']))


def test_run_mcp_server_serves_every_flow_through_the_dashboard_route(jesse_run, proxy, http, monkeypatch, capsys):
    from jesse.services.general_info import _get_mcp_info

    # An old .env pointing MCP_PORT at a port that is already taken must not matter.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
        occupied.bind(('127.0.0.1', 0))
        occupied.listen()
        legacy_port = occupied.getsockname()[1]
        monkeypatch.setitem(ENV_VALUES, 'MCP_PORT', str(legacy_port))

        manager.run_mcp_server('127.0.0.1', proxy.port, proxy.url)

    worker = manager.MCP_WORKER
    assert worker is not None and worker.port != legacy_port
    assert mcp_config.MCP_WORKER_PORT == worker.port
    assert _get_mcp_info() == {'configured_url': None, 'is_running': True}
    output = capsys.readouterr().out
    assert 'MCP_PORT in your .env file is no longer used' in output
    assert f'{proxy.url}/mcp' in output and str(worker.port) not in output

    url = f'{proxy.url}/mcp'

    async def sdk_scenario():
        async with httpx.AsyncClient(headers=AUTH, trust_env=False, timeout=WORKER_READY_SECONDS) as http_client:
            async with streamable_http_client(url, http_client=http_client) as (read, write, get_session_id):
                async with ClientSession(read, write) as session:
                    initialized = await session.initialize()
                    tools = await session.list_tools()
                    indicators = await session.call_tool('list_indicators', {})
                    resource = await session.read_resource('jesse://strategy')
                    return initialized, tools, indicators, resource, get_session_id()

    initialized, tools, indicators, resource, closed_session = asyncio.run(sdk_scenario())
    assert initialized.serverInfo.name == 'Jesse MCP Server'
    assert 'list_indicators' in {tool.name for tool in tools.tools}
    assert not indicators.isError and '"sma"' in indicators.content[0].text
    assert 'jesse://charts' in resource.contents[0].text
    # Closing the SDK client deleted its session through the route.
    assert http.post(url, headers=_session_headers(closed_session, AUTH['Authorization']),
                     json={'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'}).status_code == 404

    # The route strips a browser Origin, so the worker's rebinding check never blocks it.
    response = _initialize(http, url, {'Origin': 'https://jesse.example.com'})
    assert response.status_code == 200
    session_id = response.headers['mcp-session-id']
    assert http.post(url, headers=_session_headers(session_id, AUTH['Authorization']),
                     json={'jsonrpc': '2.0', 'method': 'notifications/initialized'}).status_code == 202

    with http.stream('GET', url, headers={**_session_headers(session_id, AUTH['Authorization']),
                                          'Accept': 'text/event-stream'}) as stream:
        assert stream.status_code == 200
        assert stream.headers['content-type'].startswith('text/event-stream')

    assert http.delete(url, headers=_session_headers(session_id, AUTH['Authorization'])).status_code == 200

    # Both entrypoints still refuse requests without the token.
    for entrypoint in (url, f'http://127.0.0.1:{worker.port}/mcp'):
        assert http.post(entrypoint, headers={'Accept': MCP_ACCEPT}, json=_initialize_payload()).status_code == 401

    manager.terminate_mcp_server()

    assert manager.MCP_WORKER is None and mcp_config.MCP_WORKER_PORT is None
    assert worker.process.poll() is not None
    assert _connection_refused(worker.port)
    assert _initialize(http, url).status_code == 502
    assert _get_mcp_info()['is_running'] is False


def test_a_worker_that_exits_later_is_forgotten(jesse_run, proxy, http):
    from jesse.services.general_info import _get_mcp_info

    manager.run_mcp_server('127.0.0.1', proxy.port, proxy.url)
    [worker] = jesse_run
    worker.process.send_signal(signal.SIGKILL)
    worker.process.wait(WAIT_SECONDS)

    assert _initialize(http, f'{proxy.url}/mcp').status_code == 502
    assert manager.MCP_WORKER is None and mcp_config.MCP_WORKER_PORT is None
    assert _get_mcp_info()['is_running'] is False
    assert _connection_refused(worker.port)


def test_startup_failure_releases_the_port_and_publishes_nothing(jesse_run, monkeypatch):
    # Long enough for the worker to load and reject its arguments; the wait returns as
    # soon as it exits.
    monkeypatch.setattr(manager, '_STARTUP_CHECK_SECONDS', WORKER_READY_SECONDS)

    # The worker refuses a dashboard URL with a path and exits with code 2.
    with pytest.raises(Exception, match='exited immediately with code 2'):
        manager.run_mcp_server('127.0.0.1', 9000, 'http://localhost:9000/prefix')

    [worker] = jesse_run
    assert worker.process.returncode == 2
    assert manager.MCP_WORKER is None and mcp_config.MCP_WORKER_PORT is None
    assert _connection_refused(worker.port)
    assert _descriptors_bound_to(worker.port) == []


def test_spawn_failure_closes_the_reserved_socket(jesse_run, monkeypatch):
    reserved: List[socket.socket] = []
    real_reserve = manager.reserve_worker_socket

    def recording_reserve() -> socket.socket:
        sock = real_reserve()
        reserved.append(sock)
        return sock

    def failing_popen(*_args, **_kwargs):
        raise OSError(errno.EAGAIN, 'Resource temporarily unavailable')

    monkeypatch.setattr(manager, 'reserve_worker_socket', recording_reserve)
    monkeypatch.setattr(manager.subprocess, 'Popen', failing_popen)

    with pytest.raises(Exception, match='Failed to start MCP server'):
        manager.run_mcp_server('127.0.0.1', 9000, 'http://localhost:9000')

    [sock] = reserved
    assert sock.fileno() == -1
    assert manager.MCP_WORKER is None and mcp_config.MCP_WORKER_PORT is None


def test_cancelling_startup_stops_the_worker_and_releases_the_port(jesse_run, monkeypatch):
    def interrupted(_process):
        raise KeyboardInterrupt

    monkeypatch.setattr(manager, '_wait_for_early_exit', interrupted)

    with pytest.raises(KeyboardInterrupt):
        manager.run_mcp_server('127.0.0.1', 9000, 'http://localhost:9000')

    [worker] = jesse_run
    assert worker.process.poll() is not None
    assert manager.MCP_WORKER is None and mcp_config.MCP_WORKER_PORT is None
    assert _connection_refused(worker.port)


def _handed_over(sock: socket.socket) -> int:
    """Detach `sock` so adopt_listening_socket owns its descriptor, as in the worker."""
    return sock.detach()


def test_adopt_listening_socket_accepts_the_reserved_socket_and_makes_it_private():
    reserved = manager.reserve_worker_socket()
    port = reserved.getsockname()[1]
    reserved.set_inheritable(True)  # As pass_fds leaves it in the worker.

    adopted = mcp_server.adopt_listening_socket(listen_fd=_handed_over(reserved))
    try:
        assert adopted.getsockname() == ('127.0.0.1', port)
        assert adopted.get_inheritable() is False
    finally:
        adopted.close()


def _wildcard_listener() -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('0.0.0.0', 0))
    sock.listen()
    return sock


def _udp_on_loopback() -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('127.0.0.1', 0))
    return sock


def _unbound_tcp() -> socket.socket:
    return socket.socket(socket.AF_INET, socket.SOCK_STREAM)


def _ipv6_loopback_listener() -> socket.socket:
    sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    try:
        sock.bind(('::1', 0))
    except OSError:
        sock.close()
        pytest.skip('IPv6 loopback is not available')
    sock.listen()
    return sock


@pytest.mark.parametrize('make_socket', [_wildcard_listener, _udp_on_loopback, _unbound_tcp, _ipv6_loopback_listener])
def test_adopt_listening_socket_refuses_sockets_it_must_not_serve(make_socket):
    fd = _handed_over(make_socket())

    with pytest.raises(ValueError):
        mcp_server.adopt_listening_socket(listen_fd=fd)

    # The refused socket was closed rather than leaked.
    with pytest.raises(OSError):
        os.fstat(fd)


@pytest.mark.skipif(not Path('/proc/self/fd').is_dir(), reason='Only Linux reports whether a socket listens.')
def test_adopt_listening_socket_refuses_a_bound_socket_that_is_not_listening():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('127.0.0.1', 0))

    with pytest.raises(ValueError, match='not listening'):
        mcp_server.adopt_listening_socket(listen_fd=_handed_over(sock))


def test_adopt_listening_socket_refuses_a_descriptor_that_is_not_a_socket():
    read_end, write_end = os.pipe()
    try:
        with pytest.raises(OSError):
            mcp_server.adopt_listening_socket(listen_fd=read_end)
    finally:
        os.close(read_end)
        os.close(write_end)


def test_adopt_listening_socket_refuses_shared_data_outside_windows():
    with pytest.raises(ValueError, match='only supported on Windows'):
        mcp_server.adopt_listening_socket(share_data=b'not-a-shared-socket')
