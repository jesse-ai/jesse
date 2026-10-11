"""
End-to-end tests for the authenticated /mcp route and the loopback MCP worker.

The real Jesse FastAPI app (with its GZip/CORS middleware and static mount) and the real
MCP worker run as uvicorn servers on ephemeral loopback ports in background threads, so
streaming, disconnects and middleware behave as they do in production. A small recording
ASGI app stands in for the worker where exact header, status and disconnect behavior must
be observed.

Only initialize, tools/list and a packaged resource are exercised: nothing here calls a
tool, so no trading, backtest, database or license API is ever reached.
"""

import asyncio
import hashlib
import json
import socket
import threading
import time
from typing import List, Optional

import anyio
import httpx
import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import LATEST_PROTOCOL_VERSION

import jesse.mcp.manager as mcp_manager
import jesse.mcp.mcp_config as mcp_config
import jesse.mcp.server as mcp_server
from jesse.mcp.auth import dashboard_token
from jesse.services.env import ENV_VALUES
from jesse.services.web import fastapi_app

PASSWORD = 'integration-test-password'
TOKEN = dashboard_token(PASSWORD)
AUTH = {'Authorization': f'Bearer {TOKEN}'}
MCP_ACCEPT = 'application/json, text/event-stream'
# Generous upper bound for loopback operations; failures show up as timeouts, not hangs.
WAIT_SECONDS = 10


class _ThreadedServer:
    """Serve an ASGI app with uvicorn on an ephemeral loopback port in a daemon thread."""

    def __init__(self, app, lifespan: str) -> None:
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind(('127.0.0.1', 0))
        self.port = self._socket.getsockname()[1]
        self.url = f'http://127.0.0.1:{self.port}'
        config = uvicorn.Config(
            app, lifespan=lifespan, log_level='warning', access_log=False, timeout_graceful_shutdown=2,
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, kwargs={'sockets': [self._socket]}, daemon=True)

    def __enter__(self) -> '_ThreadedServer':
        self._thread.start()
        deadline = time.monotonic() + WAIT_SECONDS
        while not self._server.started:
            if not self._thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError('test server failed to start')
            time.sleep(0.01)
        return self

    def __exit__(self, *exc_info) -> None:
        self._server.should_exit = True
        self._thread.join(WAIT_SECONDS)
        self._socket.close()


def _closed_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class _UpstreamRecorder:
    """
    Stand-in for the MCP worker that records what the proxy sends and replies as told.

    `response` configures a plain reply; `sse` switches to a Server-Sent Events reply that
    withholds its first event until `release_event` is set; `hang` reads the request and
    never sends response headers, like a worker still running a long tool. In both of
    the latter modes the proxy closing the upstream connection is recorded in
    `disconnected`.
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.requests: List[dict] = []
        self.response = {'status': 200, 'headers': [(b'content-type', b'application/json')], 'body': b'{}'}
        self.sse = False
        self.hang = False
        self.release_event = threading.Event()
        self.disconnected = threading.Event()

    async def __call__(self, scope, receive, send) -> None:
        if scope['type'] != 'http':
            return
        body = b''
        while True:
            message = await receive()
            body += message.get('body', b'')
            if not message.get('more_body'):
                break
        self.requests.append({
            'method': scope['method'],
            'path': scope['path'],
            'headers': [(name.decode('latin-1'), value.decode('latin-1')) for name, value in scope['headers']],
            'body': body,
        })

        if self.hang:
            # The request body is fully read, so the next message is the disconnect.
            while True:
                message = await receive()
                if message['type'] == 'http.disconnect':
                    self.disconnected.set()
                    return

        if not self.sse:
            await send({'type': 'http.response.start', 'status': self.response['status'], 'headers': self.response['headers']})
            await send({'type': 'http.response.body', 'body': self.response['body']})
            return

        await send({
            'type': 'http.response.start',
            'status': 200,
            'headers': [(b'content-type', b'text/event-stream'), (b'cache-control', b'no-cache')],
        })
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(self._emit_first_event, send)
            while True:
                message = await receive()
                if message['type'] == 'http.disconnect':
                    self.disconnected.set()
                    task_group.cancel_scope.cancel()
                    return

    async def _emit_first_event(self, send) -> None:
        while not self.release_event.is_set():
            await anyio.sleep(0.01)
        try:
            await send({'type': 'http.response.body', 'body': b'data: first\n\n', 'more_body': True})
        except OSError:
            pass


_recorder = _UpstreamRecorder()


@pytest.fixture(scope='module')
def worker():
    app = mcp_server.create_app(mcp_server.create_mcp_server(0), PASSWORD)
    with _ThreadedServer(app, lifespan='on') as server:
        yield server


@pytest.fixture(scope='module')
def proxy():
    # Lifespan is off so shutdown does not close the shared test database or LSP state.
    with _ThreadedServer(fastapi_app, lifespan='off') as server:
        yield server


@pytest.fixture(scope='module')
def fake_upstream():
    with _ThreadedServer(_recorder, lifespan='off') as server:
        yield server


class _LiveProcess:
    """Stands in for a running worker process; the servers here run in threads instead."""

    def __init__(self) -> None:
        self.returncode: Optional[int] = None

    def poll(self) -> Optional[int]:
        return self.returncode


@pytest.fixture
def route_to(monkeypatch):
    """Publish a running worker on a given port, as run_mcp_server does, with the test password."""
    monkeypatch.setitem(ENV_VALUES, 'PASSWORD', PASSWORD)
    monkeypatch.setattr(mcp_manager, 'MCP_WORKER', None)
    monkeypatch.setattr(mcp_config, 'MCP_WORKER_PORT', None)

    def _route(port: int) -> mcp_manager.McpWorker:
        worker = mcp_manager.McpWorker(_LiveProcess(), port)  # type: ignore[arg-type]
        monkeypatch.setattr(mcp_manager, 'MCP_WORKER', worker)
        monkeypatch.setattr(mcp_config, 'MCP_WORKER_PORT', port)
        return worker

    return _route


@pytest.fixture
def recorder(fake_upstream, route_to):
    _recorder.reset()
    route_to(fake_upstream.port)
    return _recorder


@pytest.fixture
def http():
    # trust_env=False keeps a developer's proxy settings out of loopback test traffic.
    with httpx.Client(trust_env=False, timeout=WAIT_SECONDS) as client:
        yield client


def _initialize_payload(request_id: int = 1) -> dict:
    return {
        'jsonrpc': '2.0',
        'id': request_id,
        'method': 'initialize',
        'params': {
            'protocolVersion': LATEST_PROTOCOL_VERSION,
            'capabilities': {},
            'clientInfo': {'name': 'jesse-tests', 'version': '1.0'},
        },
    }


def _session_headers(session_id: str, authorization: Optional[str] = None) -> dict:
    headers = {
        'Accept': MCP_ACCEPT,
        'mcp-session-id': session_id,
        'mcp-protocol-version': LATEST_PROTOCOL_VERSION,
    }
    headers['Authorization'] = authorization if authorization is not None else AUTH['Authorization']
    return headers


def _initialize(http: httpx.Client, url: str) -> str:
    response = http.post(url, headers={**AUTH, 'Accept': MCP_ACCEPT}, json=_initialize_payload())
    assert response.status_code == 200, response.text
    assert response.json()['result']['serverInfo']['name'] == 'Jesse MCP Server'
    session_id = response.headers['mcp-session-id']
    initialized = http.post(
        url,
        headers=_session_headers(session_id),
        json={'jsonrpc': '2.0', 'method': 'notifications/initialized'},
    )
    assert initialized.status_code == 202, initialized.text
    return session_id


def test_sdk_client_handshake_lists_tools_and_reads_resource_through_proxy(proxy, worker, route_to, http):
    route_to(worker.port)

    async def scenario():
        async with httpx.AsyncClient(headers=AUTH, trust_env=False, timeout=WAIT_SECONDS) as http_client:
            async with streamable_http_client(f'{proxy.url}/mcp', http_client=http_client) as (read, write, get_session_id):
                async with ClientSession(read, write) as session:
                    initialized = await session.initialize()
                    tools = await session.list_tools()
                    resource = await session.read_resource('jesse://strategy')
                    return initialized, tools, resource, get_session_id()

    initialized, tools, resource, session_id = asyncio.run(scenario())

    assert initialized.serverInfo.name == 'Jesse MCP Server'
    assert 'get_backtest_session' in {tool.name for tool in tools.tools}
    assert 'jesse://charts' in resource.contents[0].text

    # Closing the SDK client sends DELETE for the session through the proxy.
    after_close = http.post(
        f'{proxy.url}/mcp',
        headers=_session_headers(session_id),
        json={'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
    )
    assert after_close.status_code == 404


def test_session_lifecycle_through_proxy(proxy, worker, route_to, http):
    route_to(worker.port)
    url = f'{proxy.url}/mcp'
    session_id = _initialize(http, url)

    listed = http.post(url, headers=_session_headers(session_id, TOKEN), json={'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'})
    assert listed.status_code == 200
    assert listed.json()['result']['tools']

    # A session ID never substitutes for the token, at either entrypoint.
    for entrypoint in (url, f'{worker.url}/mcp'):
        unauthenticated = http.post(
            entrypoint, headers=_session_headers(session_id, ''), json={'jsonrpc': '2.0', 'id': 3, 'method': 'tools/list'},
        )
        assert unauthenticated.status_code == 401

    # The standalone SSE stream opens (headers arrive although no event has been sent yet),
    # is not compressed, and closing it releases the worker's single GET-stream slot.
    for _ in range(2):
        with http.stream('GET', url, headers={**_session_headers(session_id), 'Accept': 'text/event-stream'}) as stream:
            assert stream.status_code == 200
            assert stream.headers['content-type'].startswith('text/event-stream')
            assert 'content-encoding' not in stream.headers
            assert stream.headers['mcp-session-id'] == session_id
        _wait_for_get_stream_release(http, url, session_id)

    deleted = http.delete(url, headers=_session_headers(session_id))
    assert deleted.status_code == 200

    after_delete = http.post(url, headers=_session_headers(session_id), json={'jsonrpc': '2.0', 'id': 4, 'method': 'tools/list'})
    assert after_delete.status_code == 404


def _wait_for_get_stream_release(http: httpx.Client, url: str, session_id: str) -> None:
    """Wait until the worker notices the closed GET stream (it answers 409 while one is open)."""
    deadline = time.monotonic() + WAIT_SECONDS
    while True:
        with http.stream('GET', url, headers={**_session_headers(session_id), 'Accept': 'text/event-stream'}) as probe:
            if probe.status_code == 200:
                return
            assert probe.status_code == 409
        assert time.monotonic() < deadline, 'closed SSE stream was never released upstream'
        time.sleep(0.05)


def test_trailing_slash_reaches_worker_without_redirect(proxy, worker, route_to, http):
    route_to(worker.port)

    response = http.post(f'{proxy.url}/mcp/', headers={**AUTH, 'Accept': MCP_ACCEPT}, json=_initialize_payload())

    assert response.status_code == 200
    assert 'mcp-session-id' in response.headers
    http.delete(f'{proxy.url}/mcp', headers=_session_headers(response.headers['mcp-session-id']))


def test_worker_accepts_direct_authenticated_loopback_clients(worker, http):
    session_id = _initialize(http, f'{worker.url}/mcp')

    assert http.delete(f'{worker.url}/mcp', headers=_session_headers(session_id)).status_code == 200


@pytest.mark.parametrize('entrypoint', ['proxy', 'worker'])
@pytest.mark.parametrize('method', ['GET', 'POST', 'DELETE'])
@pytest.mark.parametrize(
    'authorization',
    [None, 'Bearer wrong-token', f'Basic {TOKEN}', PASSWORD, f'Bearer {PASSWORD}'],
)
def test_both_entrypoints_reject_missing_or_wrong_token(
    proxy, worker, recorder, http, entrypoint, method, authorization,
):
    url = f'{proxy.url}/mcp' if entrypoint == 'proxy' else f'{worker.url}/mcp'
    headers = {'Accept': MCP_ACCEPT, 'mcp-session-id': 'any-session'}
    if authorization is not None:
        headers['Authorization'] = authorization
    body = json.dumps(_initialize_payload()) if method == 'POST' else None
    if body:
        headers['Content-Type'] = 'application/json'

    response = http.request(method, url, headers=headers, content=body)

    assert response.status_code == 401
    assert response.headers['www-authenticate'] == 'Bearer realm="Jesse MCP"'
    assert TOKEN not in response.text and PASSWORD not in response.text
    # The proxy authenticates before opening any upstream connection.
    assert recorder.requests == []


def test_proxy_rejects_duplicate_authorization_headers(proxy, recorder, http):
    response = http.post(
        f'{proxy.url}/mcp',
        headers=[('Authorization', f'Bearer {TOKEN}'), ('Authorization', f'Bearer {TOKEN}')],
        json=_initialize_payload(),
    )

    assert response.status_code == 401
    assert recorder.requests == []


def test_proxy_rejects_all_requests_when_password_is_unset(proxy, recorder, monkeypatch, http):
    monkeypatch.setitem(ENV_VALUES, 'PASSWORD', '')

    # Not even the token an empty password would hash to is accepted.
    empty_password_token = hashlib.sha256(b'').hexdigest()
    response = http.post(
        f'{proxy.url}/mcp', headers={'Authorization': f'Bearer {empty_password_token}'}, json=_initialize_payload(),
    )

    assert response.status_code == 401
    assert recorder.requests == []


@pytest.mark.parametrize(
    ('method', 'headers', 'content'),
    [
        ('PUT', {'Accept': MCP_ACCEPT}, b''),
        ('POST', {'Accept': 'text/plain', 'Content-Type': 'application/json'}, json.dumps(_initialize_payload()).encode()),
        ('POST', {'Accept': MCP_ACCEPT, 'Content-Type': 'text/plain'}, b'{}'),
        ('POST', {'Accept': MCP_ACCEPT, 'Content-Type': 'application/json'}, b'{not json'),
        ('POST', {'Accept': MCP_ACCEPT, 'Content-Type': 'application/json', 'mcp-session-id': 'missing'},
         json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}).encode()),
        ('GET', {'Accept': 'text/event-stream'}, b''),
        ('DELETE', {'Accept': MCP_ACCEPT}, b''),
    ],
)
def test_proxy_relays_worker_protocol_errors_unchanged(proxy, worker, route_to, http, method, headers, content):
    route_to(worker.port)
    headers = {**headers, **AUTH}

    direct = http.request(method, f'{worker.url}/mcp', headers=headers, content=content)
    proxied = http.request(method, f'{proxy.url}/mcp', headers=headers, content=content)

    assert direct.status_code >= 400
    assert proxied.status_code == direct.status_code
    assert proxied.content == direct.content
    assert proxied.headers.get('allow') == direct.headers.get('allow')
    if method == 'PUT':
        assert proxied.status_code == 405
        assert proxied.headers['allow'] == 'GET, POST, DELETE'


def test_proxy_returns_502_when_worker_is_unreachable(proxy, route_to, http):
    route_to(_closed_port())

    response = http.post(f'{proxy.url}/mcp', headers={**AUTH, 'Accept': MCP_ACCEPT}, json=_initialize_payload())

    assert response.status_code == 502
    assert 'not reachable' in response.json()['message']


def test_proxy_returns_502_when_no_worker_was_started(proxy, recorder, route_to, monkeypatch, http):
    monkeypatch.setattr(mcp_manager, 'MCP_WORKER', None)

    response = http.post(f'{proxy.url}/mcp', headers={**AUTH, 'Accept': MCP_ACCEPT}, json=_initialize_payload())

    assert response.status_code == 502
    assert 'not reachable' in response.json()['message']
    assert recorder.requests == []


def test_proxy_never_forwards_to_the_port_of_an_exited_worker(proxy, fake_upstream, recorder, route_to, http):
    # Something else listens on the port the exited worker had (here the recorder): the
    # client's token must not be sent there.
    worker = route_to(fake_upstream.port)
    worker.process.returncode = 1

    response = http.post(f'{proxy.url}/mcp', headers={**AUTH, 'Accept': MCP_ACCEPT}, json=_initialize_payload())

    assert response.status_code == 502
    assert recorder.requests == []
    # The stale address is forgotten, not retried.
    assert mcp_manager.MCP_WORKER is None
    assert mcp_config.MCP_WORKER_PORT is None


def test_proxy_ignores_legacy_mcp_port_setting(proxy, worker, fake_upstream, recorder, route_to, monkeypatch, http):
    route_to(worker.port)
    monkeypatch.setitem(ENV_VALUES, 'MCP_PORT', str(fake_upstream.port))

    response = http.post(f'{proxy.url}/mcp', headers={**AUTH, 'Accept': MCP_ACCEPT}, json=_initialize_payload())

    assert response.status_code == 200
    assert response.json()['result']['serverInfo']['name'] == 'Jesse MCP Server'
    assert recorder.requests == []
    http.delete(f'{proxy.url}/mcp', headers=_session_headers(response.headers['mcp-session-id']))


def test_proxy_forwards_only_protocol_headers_to_the_worker(proxy, fake_upstream, recorder, http):
    http.post(
        f'{proxy.url}/mcp/',
        headers={
            **AUTH,
            'Accept': MCP_ACCEPT,
            'Accept-Encoding': 'gzip',
            'Origin': 'https://evil.example',
            'Cookie': 'session=secret',
            'X-Custom': 'drop-me',
            'Proxy-Authorization': 'Basic abc',
            'mcp-session-id': 'session-1',
            'mcp-protocol-version': LATEST_PROTOCOL_VERSION,
            'last-event-id': 'event-7',
        },
        json={'jsonrpc': '2.0', 'id': 1, 'method': 'ping'},
    )

    [forwarded] = recorder.requests
    headers = dict(forwarded['headers'])
    assert forwarded['method'] == 'POST'
    assert forwarded['path'] == '/mcp'
    assert json.loads(forwarded['body']) == {'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}
    assert headers['host'] == f'127.0.0.1:{fake_upstream.port}'
    assert headers['authorization'] == AUTH['Authorization']
    assert headers['mcp-session-id'] == 'session-1'
    assert headers['mcp-protocol-version'] == LATEST_PROTOCOL_VERSION
    assert headers['last-event-id'] == 'event-7'
    assert headers['accept'] == MCP_ACCEPT
    assert headers['content-type'] == 'application/json'
    # The client's gzip offer is replaced so the worker answers uncompressed.
    assert headers['accept-encoding'] == 'identity'
    for dropped in ('origin', 'cookie', 'x-custom', 'proxy-authorization'):
        assert dropped not in headers


def test_proxy_drops_protocol_headers_nominated_by_connection(proxy, recorder, http):
    http.post(
        f'{proxy.url}/mcp',
        headers={
            **AUTH,
            'Accept': MCP_ACCEPT,
            'mcp-session-id': 'session-1',
            'mcp-protocol-version': LATEST_PROTOCOL_VERSION,
            'last-event-id': 'event-7',
            'Connection': 'keep-alive, Mcp-Session-Id,  MCP-PROTOCOL-VERSION',
        },
        json={'jsonrpc': '2.0', 'id': 1, 'method': 'ping'},
    )

    [forwarded] = recorder.requests
    headers = dict(forwarded['headers'])
    assert 'mcp-session-id' not in headers
    assert 'mcp-protocol-version' not in headers
    # Headers not nominated in Connection are still forwarded end to end.
    assert headers['last-event-id'] == 'event-7'
    assert headers['authorization'] == AUTH['Authorization']


def test_connection_nominated_authorization_is_consumed_by_proxy(proxy, worker, route_to, http):
    route_to(worker.port)

    # The proxy authenticates with the header meant for its hop, but must not forward it,
    # so the worker independently refuses the request.
    response = http.post(
        f'{proxy.url}/mcp',
        headers={**AUTH, 'Accept': MCP_ACCEPT, 'Connection': 'Authorization'},
        json=_initialize_payload(),
    )

    assert response.status_code == 401
    assert response.headers['www-authenticate'] == 'Bearer realm="Jesse MCP"'


def test_proxy_abandons_upstream_when_client_disconnects_before_response_headers(proxy, recorder):
    recorder.hang = True
    # A short read timeout makes the client give up and close its connection while the
    # worker is still withholding response headers.
    with httpx.Client(trust_env=False, timeout=httpx.Timeout(WAIT_SECONDS, read=0.5)) as client:
        with pytest.raises(httpx.ReadTimeout):
            client.post(f'{proxy.url}/mcp', headers={**AUTH, 'Accept': MCP_ACCEPT}, json={'jsonrpc': '2.0', 'id': 1, 'method': 'ping'})

    assert len(recorder.requests) == 1, 'the upstream request was never opened'
    assert recorder.disconnected.wait(WAIT_SECONDS), 'proxy kept the pending upstream request open'


@pytest.mark.parametrize('status', [401, 404, 405])
def test_proxy_relays_upstream_status_and_strips_hop_by_hop_headers(proxy, recorder, http, status):
    recorder.response = {
        'status': status,
        'headers': [
            (b'content-type', b'application/json'),
            (b'www-authenticate', b'Bearer realm="upstream"'),
            (b'allow', b'GET, POST, DELETE'),
            (b'mcp-session-id', b'session-1'),
            (b'x-keep', b'yes'),
            (b'connection', b'x-drop-me'),
            (b'x-drop-me', b'1'),
            (b'keep-alive', b'timeout=5'),
            (b'location', b'http://127.0.0.1:1/internal'),
        ],
        'body': b'{"from": "upstream"}',
    }

    response = http.post(f'{proxy.url}/mcp', headers={**AUTH, 'Accept': MCP_ACCEPT}, json={})

    assert response.status_code == status
    assert response.json() == {'from': 'upstream'}
    assert response.headers['www-authenticate'] == 'Bearer realm="upstream"'
    assert response.headers['allow'] == 'GET, POST, DELETE'
    assert response.headers['mcp-session-id'] == 'session-1'
    assert response.headers['x-keep'] == 'yes'
    for dropped in ('x-drop-me', 'keep-alive', 'location'):
        assert dropped not in response.headers


def test_proxy_compresses_large_json_responses(proxy, recorder, http):
    payload = {'jsonrpc': '2.0', 'id': 1, 'result': {'text': 'x' * 4096}}
    recorder.response = {'status': 200, 'headers': [(b'content-type', b'application/json')], 'body': json.dumps(payload).encode()}

    response = http.post(f'{proxy.url}/mcp', headers={**AUTH, 'Accept': MCP_ACCEPT, 'Accept-Encoding': 'gzip'}, json={})

    assert response.headers['content-encoding'] == 'gzip'
    assert response.json() == payload


def test_proxy_streams_sse_without_buffering_and_closes_upstream(proxy, recorder, http):
    recorder.sse = True

    with http.stream('GET', f'{proxy.url}/mcp', headers={**AUTH, 'Accept': 'text/event-stream', 'Accept-Encoding': 'gzip'}) as stream:
        # Headers arrive while the upstream is still withholding its first event.
        assert stream.status_code == 200
        assert stream.headers['content-type'].startswith('text/event-stream')
        assert 'content-encoding' not in stream.headers
        assert not recorder.release_event.is_set()

        recorder.release_event.set()
        received = b''
        for chunk in stream.iter_raw():
            received += chunk
            if b'data: first' in received:
                break
        assert b'data: first\n\n' in received

    assert recorder.disconnected.wait(WAIT_SECONDS), 'proxy kept the upstream SSE connection open'


def test_proxy_closes_upstream_when_client_disconnects_before_first_event(proxy, recorder, http):
    recorder.sse = True

    with http.stream('GET', f'{proxy.url}/mcp', headers={**AUTH, 'Accept': 'text/event-stream'}) as stream:
        assert stream.status_code == 200

    assert recorder.disconnected.wait(WAIT_SECONDS), 'proxy kept the upstream SSE connection open'
    recorder.release_event.set()
