"""
Authenticated same-origin route for the Jesse MCP server.

MCP clients connect to ``<dashboard origin>/mcp``. This route authenticates every request
with the dashboard token before any upstream connection is opened, then relays it to the
loopback-only MCP worker (jesse.mcp.server) and streams the response back unchanged:
status codes (including the worker's own 401/404/405 responses), protocol and session
headers, and Server-Sent Events are forwarded without buffering.

The worker runs in its own process and is reached over HTTP rather than mounted into this
app: MCP tools make blocking HTTP calls back to this API, so running them on this event
loop would deadlock the server.
"""

from typing import List, Optional, Set, Tuple

import anyio
import httpx
from fastapi import APIRouter, Request
from starlette.responses import JSONResponse, Response
from starlette.types import Receive, Scope, Send

import jesse.mcp.manager as mcp_manager
import jesse.mcp.mcp_config as mcp_config
from jesse.mcp.auth import dashboard_token, is_authorized, unauthorized_response
from jesse.services.dashboard_url import MCP_ENDPOINT_PATH
from jesse.services.env import ENV_VALUES

router = APIRouter(tags=['MCP'])

# Every method is relayed so the worker, not this route, decides what is allowed and its
# 405 response (with its Allow header) reaches the client unchanged.
_RELAYED_METHODS = ['GET', 'POST', 'DELETE', 'PUT', 'PATCH', 'HEAD', 'OPTIONS']

# Request headers the Streamable HTTP transport needs. Everything else is dropped:
# hop-by-hop headers, Cookie, and Origin (the worker's DNS-rebinding check only accepts
# loopback origins; the token already authenticates the caller). Accept-Encoding is also
# dropped so the worker answers uncompressed and this app's GZipMiddleware alone decides
# compression, which it never applies to event streams.
_FORWARDED_REQUEST_HEADERS = frozenset({
    'accept',
    'authorization',
    'content-type',
    'last-event-id',
    'mcp-protocol-version',
    'mcp-session-id',
    'user-agent',
})

# RFC 9110 hop-by-hop headers, which apply to a single connection and must not be relayed.
_HOP_BY_HOP_HEADERS = frozenset({
    'connection',
    'keep-alive',
    'proxy-authenticate',
    'proxy-authorization',
    'te',
    'trailer',
    'transfer-encoding',
    'upgrade',
})

# Response headers not relayed: this server sets its own Date and Server, and a Location
# from the worker would expose its internal loopback address.
_DROPPED_RESPONSE_HEADERS = _HOP_BY_HOP_HEADERS | {'date', 'server', 'location'}

# Loopback connects are immediate, so a short connect/pool timeout only guards against a
# wedged worker. Reads are unbounded: SSE streams stay open indefinitely and JSON
# responses wait for tools that can legitimately run for minutes (e.g. CSV imports).
_UPSTREAM_TIMEOUT = httpx.Timeout(connect=5.0, read=None, write=30.0, pool=5.0)


def _expected_token() -> str:
    """Derive the token from the current PASSWORD for each request (empty when unset)."""
    password = ENV_VALUES.get('PASSWORD') or ''
    return dashboard_token(password) if password else ''


def _worker_unreachable_response() -> JSONResponse:
    """Return the 502 used when no MCP worker is running or it cannot be reached."""
    return JSONResponse(
        {'message': 'The Jesse MCP server is not reachable. Check the Jesse terminal for MCP startup errors.'},
        status_code=502,
    )


def _connection_nominated(connection_values: List[str]) -> Set[str]:
    """Return the lower-cased header names a Connection header marks as hop-by-hop."""
    return {
        token.strip().lower()
        for value in connection_values
        for token in value.split(',')
        if token.strip()
    }


def _upstream_request_headers(request: Request) -> List[Tuple[str, str]]:
    """
    Return the allowlisted request headers that are end-to-end for this request.

    Headers the client nominates in Connection (RFC 9110 §7.6.1) apply only to this hop,
    even when they are protocol headers such as Mcp-Session-Id or Authorization, so they
    are consumed here and not forwarded. The worker then judges the request without
    them, e.g. answering 401 when Authorization was nominated.
    """
    connection_scoped = _connection_nominated(request.headers.getlist('connection'))
    return [
        (name, value) for name, value in request.headers.items()
        if name in _FORWARDED_REQUEST_HEADERS and name not in connection_scoped
    ]


def _relayed_response_headers(headers: httpx.Headers) -> List[Tuple[bytes, bytes]]:
    """Return upstream response headers minus hop-by-hop and connection-scoped ones."""
    connection_scoped = _connection_nominated(headers.get_list('connection'))
    dropped = _DROPPED_RESPONSE_HEADERS | connection_scoped
    # Raw header names are bytes; HTTP header octets map to latin-1 without loss.
    return [(name, value) for name, value in headers.raw if name.decode('latin-1').lower() not in dropped]


class _UpstreamStreamResponse(Response):
    """
    Relay an upstream MCP response chunk by chunk and always release the connection.

    A disconnect watcher runs alongside the relay; when the client goes away (for example
    closing a long-lived SSE stream) the relay is cancelled immediately and the upstream
    response and client are closed, so abandoned streams never keep a worker connection
    open.
    """

    def __init__(self, client: httpx.AsyncClient, upstream: httpx.Response) -> None:
        self._client = client
        self._upstream = upstream
        self.status_code = upstream.status_code
        # Response.__init__ is skipped (there is no body to render), but FastAPI reads
        # `background` on every returned Response to attach background tasks.
        self.background = None
        self.raw_headers = _relayed_response_headers(upstream.headers)
        self._is_event_stream = upstream.headers.get('content-type', '').startswith('text/event-stream')

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            async with anyio.create_task_group() as task_group:
                task_group.start_soon(self._cancel_on_disconnect, receive, task_group.cancel_scope)
                task_group.start_soon(self._relay, send, task_group.cancel_scope)
        finally:
            # Shielded so cleanup still runs while the surrounding request is being cancelled.
            with anyio.CancelScope(shield=True):
                await self._upstream.aclose()
                await self._client.aclose()

    async def _relay(self, send: Send, cancel_scope: anyio.CancelScope) -> None:
        try:
            await send({'type': 'http.response.start', 'status': self.status_code, 'headers': self.raw_headers})
            if self._is_event_stream:
                # GZipMiddleware holds the response start until the first body message.
                # An empty chunk releases the headers now, so the client sees the open SSE
                # stream before the worker emits its first event.
                await send({'type': 'http.response.body', 'body': b'', 'more_body': True})
            async for chunk in self._upstream.aiter_raw():
                await send({'type': 'http.response.body', 'body': chunk, 'more_body': True})
            await send({'type': 'http.response.body', 'body': b'', 'more_body': False})
        except httpx.TransportError:
            # The worker dropped the stream mid-response. The response is left incomplete
            # so the server aborts the client connection instead of presenting a truncated
            # body as complete.
            pass
        except OSError:
            # The client disconnected while a chunk was being sent.
            pass
        finally:
            cancel_scope.cancel()

    @staticmethod
    async def _cancel_on_disconnect(receive: Receive, cancel_scope: anyio.CancelScope) -> None:
        # The request body was already read, so the next message is the disconnect.
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                cancel_scope.cancel()
                return


async def _send_unless_client_disconnects(
    request: Request, client: httpx.AsyncClient, upstream_request: httpx.Request,
) -> Optional[httpx.Response]:
    """
    Send the upstream request and wait for its response headers, unless the client leaves.

    Reads are unbounded, so a worker that has not answered yet (for example a tool that is
    still running) would otherwise keep this request and its upstream connection alive
    forever after the client disconnected. Returns None when the client disconnected first;
    the in-flight upstream request is then cancelled, which closes its connection.
    Transport errors are re-raised for the caller; outside cancellation propagates.
    """
    upstream: Optional[httpx.Response] = None
    transport_error: Optional[httpx.TransportError] = None

    async with anyio.create_task_group() as task_group:
        async def send_upstream() -> None:
            nonlocal upstream, transport_error
            try:
                upstream = await client.send(upstream_request, stream=True)
            except httpx.TransportError as e:
                # Captured here so it is not wrapped in an exception group by the task group.
                transport_error = e
            finally:
                task_group.cancel_scope.cancel()

        async def watch_disconnect() -> None:
            # The request body was already read, so the next message is the disconnect.
            while True:
                message = await request.receive()
                if message['type'] == 'http.disconnect':
                    task_group.cancel_scope.cancel()
                    return

        task_group.start_soon(watch_disconnect)
        task_group.start_soon(send_upstream)

    if transport_error is not None:
        raise transport_error
    return upstream


async def _relay_to_worker(request: Request) -> Response:
    if not is_authorized(request.headers.getlist('authorization'), _expected_token()):
        return unauthorized_response()

    # Only a live worker's port is returned, so a port the OS may have handed to another
    # process after the worker exited never receives the client's token.
    port = mcp_manager.running_worker_port()
    if port is None:
        return _worker_unreachable_response()

    # MCP client messages are single JSON-RPC payloads, so the body is read up front; this
    # also leaves `receive` free to report the client's disconnect while waiting for and
    # streaming the worker's response.
    body = await request.body()
    # Both /mcp and /mcp/ map to the worker's exact endpoint path, so the worker never
    # issues a trailing-slash redirect pointing at its internal address.
    url = f'http://{mcp_config.MCP_WORKER_HOST}:{port}{MCP_ENDPOINT_PATH}'
    # trust_env=False keeps HTTP(S)_PROXY settings from routing loopback traffic elsewhere.
    # Accept-Encoding: identity replaces httpx's default gzip/deflate offer, so the worker
    # always answers uncompressed and relayed bytes never need decoding here.
    client = httpx.AsyncClient(
        timeout=_UPSTREAM_TIMEOUT, trust_env=False, headers={'Accept-Encoding': 'identity'},
    )
    try:
        upstream_request = client.build_request(
            request.method, url, headers=_upstream_request_headers(request), content=body,
        )
        upstream = await _send_unless_client_disconnects(request, client, upstream_request)
    except httpx.TransportError:
        await client.aclose()
        return _worker_unreachable_response()
    except BaseException:
        with anyio.CancelScope(shield=True):
            await client.aclose()
        raise

    if upstream is None:
        # The client left before the worker answered; the upstream request is already
        # cancelled. The server discards anything sent to a disconnected client, so this
        # placeholder (nginx's "client closed request" code) is never delivered.
        with anyio.CancelScope(shield=True):
            await client.aclose()
        return Response(status_code=499)

    return _UpstreamStreamResponse(client, upstream)


@router.api_route(MCP_ENDPOINT_PATH, methods=_RELAYED_METHODS, include_in_schema=False)
async def mcp_endpoint(request: Request) -> Response:
    return await _relay_to_worker(request)


@router.api_route(f'{MCP_ENDPOINT_PATH}/', methods=_RELAYED_METHODS, include_in_schema=False)
async def mcp_endpoint_trailing_slash(request: Request) -> Response:
    return await _relay_to_worker(request)
