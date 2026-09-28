"""
Jesse MCP Worker Entry Point

jesse.mcp.manager launches this module as `python -m jesse.mcp.server`. It:
1. Parses the launch arguments (--api_url, --dashboard_url, and how the socket arrives)
2. Reads the dashboard PASSWORD from the environment (never from argv)
3. Takes over the listening loopback socket the manager reserved, and validates it
4. Creates the FastMCP server and registers all resources and tools
5. Wraps the Streamable HTTP app with static bearer-token authentication
6. Serves it on that socket

The worker never binds a port itself: the manager binds 127.0.0.1:0 and hands over the
listening socket, so the OS-assigned port stays owned from reservation until this process
exits. That is also why the worker is only started by the manager, not by hand.

MCP clients do not connect to this port directly. They use the authenticated /mcp route
on the dashboard origin, which streams requests to this worker; the worker still checks
the token itself so the loopback port is never an unauthenticated side door.

Nothing runs at import time, so tests can build the server and the ASGI app directly.
"""

import argparse
import errno
import logging
import os
import socket
import sys
import traceback
from typing import Optional, Sequence

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.types import ASGIApp

import jesse.mcp.mcp_config as mcp_config
from jesse.mcp.auth import McpTokenAuthMiddleware, dashboard_token
from jesse.services.dashboard_url import InvalidDashboardUrlError, mcp_endpoint_url, normalize_dashboard_url

logger = logging.getLogger("jesse.mcp.server")

# Advertise this workflow during initialization, including to clients without local agent rules.
INSTRUCTIONS = (
    "When asked to prepare, adapt, port, or deploy a strategy researched on traditional-market "
    "data for a 24/7 crypto exchange (including tokenized or stock-linked instruments), read "
    "jesse://strategy, especially Trading Hours and its adaptation workflow, before editing. "
    "Recognize equivalent requests even when the user does not mention trading hours. "
    "Research scripts are opt-in: only write or run files in research_scripts/ when the user "
    "specifically asks for a script, asks for machine-learning research that needs a script or "
    "Jesse's research module, or explicitly asks to use the research module. Generic requests to "
    "research, find, or improve strategies use the catalog, backtest, optimization, Monte Carlo, "
    "and significance-test tools instead; see jesse://research_scripts. "
    "Read stored session results, including live/paper sessions, with get_session_results "
    "(summary first). To analyze, compare, or chart results, use run_analysis, which runs in a "
    "temporary workspace and never needs research_scripts/; see jesse://session_analysis."
)


def _log_uncaught_exception(exc_type, exc_value, exc_tb):
    """Log uncaught exceptions with traceback for transport/session debugging."""
    logger.error("Uncaught exception in MCP server", exc_info=(exc_type, exc_value, exc_tb))


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse the worker's launch arguments. The password is intentionally not one of them."""
    parser = argparse.ArgumentParser(description='Jesse MCP Server')
    parser.add_argument('--api_url', type=str, required=True, help='Internal Jesse API URL used by the tools')
    parser.add_argument('--dashboard_url', type=str, required=True, help='Public dashboard origin used for links')
    handoff = parser.add_mutually_exclusive_group(required=True)
    handoff.add_argument(
        '--listen_fd', type=int, help='Inherited descriptor of the listening loopback socket (POSIX)',
    )
    handoff.add_argument(
        '--listen_share', action='store_true',
        help='Read socket.share() data for the listening loopback socket from stdin (Windows)',
    )
    return parser.parse_args(argv)


def _is_listening(sock: socket.socket) -> bool:
    """
    Report whether `sock` is listening, or True when the platform cannot tell.

    Linux answers SO_ACCEPTCONN. macOS defines it but rejects it in getsockopt with
    ENOPROTOOPT, and Windows may not define it at all. The manager always listens before
    handing the socket over, so this is a guard against a wrong descriptor, not a
    requirement.
    """
    accept_conn = getattr(socket, 'SO_ACCEPTCONN', None)
    if accept_conn is None:
        return True
    try:
        return bool(sock.getsockopt(socket.SOL_SOCKET, accept_conn))
    except OSError as e:
        if e.errno == errno.ENOPROTOOPT:
            return True
        raise


def adopt_listening_socket(listen_fd: Optional[int] = None, share_data: Optional[bytes] = None) -> socket.socket:
    """
    Take ownership of the listening socket handed over by the manager.

    Only a listening IPv4 TCP socket bound to the loopback worker host is accepted, so a
    wrong descriptor can never make the worker serve on another interface. Raises OSError
    or ValueError when the handed-over socket is unusable.
    """
    if share_data is not None:
        if sys.platform != 'win32':
            raise ValueError('Shared socket data is only supported on Windows.')
        sock = socket.fromshare(share_data)
    elif listen_fd is not None:
        # Family, type and protocol are detected from the descriptor itself.
        sock = socket.socket(fileno=listen_fd)
    else:
        raise ValueError('No listening socket was handed over.')
    try:
        # Tools spawn processes of their own; none of them may inherit the listener.
        sock.set_inheritable(False)
        if sock.family != socket.AF_INET or sock.type != socket.SOCK_STREAM:
            raise ValueError('The handed-over socket is not an IPv4 TCP socket.')
        host, port = sock.getsockname()[:2]
        if host != mcp_config.MCP_WORKER_HOST or not port:
            raise ValueError(f'The handed-over socket is bound to {host}:{port}, not {mcp_config.MCP_WORKER_HOST}.')
        if not _is_listening(sock):
            raise ValueError('The handed-over socket is not listening.')
    except BaseException:
        sock.close()
        raise
    return sock


def loopback_transport_security() -> TransportSecuritySettings:
    """
    Host/Origin validation for the loopback worker (DNS-rebinding protection).

    Set explicitly rather than relying on the SDK enabling it for loopback hosts, so the
    protection does not depend on SDK version. The /mcp proxy connects with a 127.0.0.1
    Host header and strips Origin, so proxied requests always pass these checks. Ports
    are wildcards because the OS assigns the worker's port at startup; only the host part
    guards against rebinding.
    """
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=['127.0.0.1:*', 'localhost:*', '[::1]:*'],
        allowed_origins=['http://127.0.0.1:*', 'http://localhost:*', 'http://[::1]:*'],
    )


def configure(api_url: str, dashboard_url: str, port: int, password: str) -> None:
    """Populate the shared runtime config that tools read at call time."""
    mcp_config.JESSE_API_URL = api_url
    mcp_config.JESSE_PASSWORD = password
    mcp_config.MCP_WORKER_PORT = port
    mcp_config.DASHBOARD_URL = dashboard_url
    mcp_config.MCP_URL = mcp_endpoint_url(dashboard_url)


def create_mcp_server(port: int) -> FastMCP:
    """Create the FastMCP server with every Jesse resource and tool registered."""
    mcp = FastMCP(
        "Jesse MCP Server",
        host=mcp_config.MCP_WORKER_HOST,
        port=port,
        json_response=True,
        instructions=INSTRUCTIONS,
        transport_security=loopback_transport_security(),
    )

    from jesse.mcp.resources import register_resources
    register_resources(mcp)

    from jesse.mcp.tools import register_tools
    register_tools(mcp)

    return mcp


def create_app(mcp: FastMCP, password: str) -> ASGIApp:
    """
    Return the worker's ASGI app: the Streamable HTTP transport behind token auth.

    Refuses to build without a password, so no caller can construct a worker whose
    expected token is the hash of an empty string.
    """
    if not password:
        raise ValueError('The MCP worker requires a non-empty PASSWORD.')
    return McpTokenAuthMiddleware(mcp.streamable_http_app(), dashboard_token(password))


def serve(app: ASGIApp, sock: socket.socket) -> None:
    """
    Serve `app` on the already-listening socket until the worker is stopped.

    uvicorn closes the socket on shutdown. Exits with uvicorn's own startup-failure code
    (3) when the server never started, e.g. because the app's lifespan startup failed.
    """
    port = sock.getsockname()[1]
    # host/port only label uvicorn's logs; the passed socket is what is served.
    config = uvicorn.Config(app, host=mcp_config.MCP_WORKER_HOST, port=port, log_level='info')
    server = uvicorn.Server(config)
    try:
        server.run(sockets=[sock])
    except KeyboardInterrupt:
        # uvicorn re-raises a captured Ctrl+C after its graceful shutdown.
        pass
    if not server.started:
        raise SystemExit(3)


def main(argv: Optional[Sequence[str]] = None) -> None:
    """Configure and serve the MCP worker until it is terminated."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )
    sys.excepthook = _log_uncaught_exception

    args = parse_args(argv)

    # Removed from the environment so processes the tools may spawn do not inherit it.
    password = os.environ.pop(mcp_config.WORKER_PASSWORD_ENV, '')
    if not password:
        logger.error("%s is not set; the MCP worker cannot authenticate requests.", mcp_config.WORKER_PASSWORD_ENV)
        raise SystemExit(2)

    try:
        dashboard_url = normalize_dashboard_url(args.dashboard_url)
    except InvalidDashboardUrlError as e:
        logger.error("%s", e)
        raise SystemExit(2)

    try:
        # The manager writes the share data and closes the pipe, so this read ends at EOF.
        share_data = sys.stdin.buffer.read() if args.listen_share else None
        sock = adopt_listening_socket(args.listen_fd, share_data)
    except (OSError, ValueError) as e:
        logger.error("The MCP worker cannot use the socket handed over by Jesse: %s", e)
        raise SystemExit(2)

    port = sock.getsockname()[1]
    configure(args.api_url, dashboard_url, port, password)
    app = create_app(create_mcp_server(port), password)

    try:
        # The port is internal. Only the dashboard's /mcp route is a client endpoint.
        logger.info(
            "MCP worker listening on internal loopback port %s; clients connect to %s",
            port, mcp_config.MCP_URL,
        )
        serve(app, sock)
    except Exception as exc:
        logger.error("MCP server runtime failure: %s", exc)
        logger.error("Traceback:\n%s", traceback.format_exc())
        raise


# Run the MCP worker when executed directly
if __name__ == "__main__":
    main()
