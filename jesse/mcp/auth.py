"""
Static bearer-token authentication for the Jesse MCP endpoint.

MCP clients authenticate with the same token the dashboard uses: the SHA-256 hex digest
of the project's PASSWORD. There is no OAuth flow; clients send the token themselves on
every request. Both the public /mcp route on the dashboard origin and the loopback MCP
worker check it independently, so neither entrypoint relies on the other for security.
"""

import hmac
from hashlib import sha256
from typing import List, Optional, Sequence

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

MCP_AUTH_REALM = 'Jesse MCP'


def dashboard_token(password: str) -> str:
    """
    Return the dashboard/MCP token derived from the project PASSWORD.

    An empty password is refused: its hash is a well-known constant, so deriving a token
    from it would let anyone authenticate. Callers must fail closed instead.
    """
    if not password:
        raise ValueError('A non-empty PASSWORD is required to derive the MCP token.')
    return sha256(password.encode('utf-8')).hexdigest()


def token_from_authorization(values: Sequence[str]) -> Optional[str]:
    """
    Extract the token from the request's Authorization header values.

    Accepts the standard ``Bearer <token>`` form (scheme is case-insensitive per RFC 6750)
    and the bare ``<token>`` form the dashboard already sends. Any other scheme, a missing
    header, or several Authorization headers (ambiguous) yields None.
    """
    if len(values) != 1:
        return None
    value = values[0].strip()
    scheme, _, credentials = value.partition(' ')
    if credentials:
        if scheme.lower() != 'bearer':
            return None
        value = credentials.strip()
    return value or None


def is_authorized(authorization_values: Sequence[str], expected_token: str) -> bool:
    """Check the Authorization header values against the expected token in constant time."""
    if not expected_token:
        return False
    token = token_from_authorization(authorization_values)
    if token is None:
        return False
    return hmac.compare_digest(token.encode('utf-8'), expected_token.encode('utf-8'))


def unauthorized_response() -> JSONResponse:
    """
    Return the 401 used by both MCP entrypoints.

    The challenge names only the Bearer scheme and a realm. It deliberately carries no
    ``resource_metadata`` parameter, so clients are not told to start OAuth discovery for
    a server that only accepts a static token.
    """
    return JSONResponse(
        {'message': 'Missing or invalid MCP token. Send the dashboard token as "Authorization: Bearer <token>".'},
        status_code=401,
        headers={'WWW-Authenticate': f'Bearer realm="{MCP_AUTH_REALM}"'},
    )


def _authorization_values(scope: Scope) -> List[str]:
    """Return every Authorization header value; ASGI delivers header bytes as latin-1."""
    return [value.decode('latin-1') for name, value in scope.get('headers', []) if name == b'authorization']


class McpTokenAuthMiddleware:
    """
    ASGI middleware that rejects every unauthenticated request to the wrapped MCP app.

    Each HTTP request is checked on its own, including requests that carry an existing
    ``Mcp-Session-Id``, so a session ID alone never grants access. Lifespan events pass
    through so the MCP session manager still starts and stops; WebSocket connections are
    refused because the MCP worker does not serve any.
    """

    def __init__(self, app: ASGIApp, expected_token: str) -> None:
        # Fail closed at construction rather than serving an app nobody can (or everybody
        # could) authenticate against.
        if not expected_token:
            raise ValueError('McpTokenAuthMiddleware requires a non-empty expected token.')
        self.app = app
        self.expected_token = expected_token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] == 'lifespan':
            await self.app(scope, receive, send)
            return
        if scope['type'] != 'http':
            await send({'type': 'websocket.close', 'code': 1008})
            return
        if not is_authorized(_authorization_values(scope), self.expected_token):
            await unauthorized_response()(scope, receive, send)
            return
        await self.app(scope, receive, send)
