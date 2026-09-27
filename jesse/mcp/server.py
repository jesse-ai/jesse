"""
Jesse MCP Worker Entry Point

jesse.mcp.manager launches this module as `python -m jesse.mcp.server`. It:
1. Parses the launch arguments (--port, --api_url, --dashboard_url)
2. Reads the dashboard PASSWORD from the environment (never from argv)
3. Creates the FastMCP server and registers all resources and tools
4. Wraps the Streamable HTTP app with static bearer-token authentication
5. Serves it on loopback only

MCP clients do not connect to this port directly. They use the authenticated /mcp route
on the dashboard origin, which streams requests to this worker; the worker still checks
the token itself so the loopback port is never an unauthenticated side door.

Nothing runs at import time, so tests can build the server and the ASGI app directly.

USAGE:
------
Normally started by manager.py. To run it by hand:
    JESSE_MCP_WORKER_PASSWORD=... python -m jesse.mcp.server --port 9002 \
        --api_url http://127.0.0.1:9000 --dashboard_url http://localhost:9000
"""

import argparse
import logging
import os
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
    "Recognize equivalent requests even when the user does not mention trading hours."
)


def _log_uncaught_exception(exc_type, exc_value, exc_tb):
    """Log uncaught exceptions with traceback for transport/session debugging."""
    logger.error("Uncaught exception in MCP server", exc_info=(exc_type, exc_value, exc_tb))


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse the worker's launch arguments. The password is intentionally not one of them."""
    parser = argparse.ArgumentParser(description='Jesse MCP Server')
    parser.add_argument('--port', type=int, required=True, help='Loopback port for the MCP worker')
    parser.add_argument('--api_url', type=str, required=True, help='Internal Jesse API URL used by the tools')
    parser.add_argument('--dashboard_url', type=str, required=True, help='Public dashboard origin used for links')
    return parser.parse_args(argv)


def loopback_transport_security() -> TransportSecuritySettings:
    """
    Host/Origin validation for the loopback worker (DNS-rebinding protection).

    Set explicitly rather than relying on the SDK enabling it for loopback hosts, so the
    protection does not depend on SDK version. The /mcp proxy connects with a 127.0.0.1
    Host header and strips Origin, so proxied requests always pass these checks.
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
    mcp_config.MCP_PORT = port
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

    configure(args.api_url, dashboard_url, args.port, password)
    app = create_app(create_mcp_server(args.port), password)

    try:
        logger.info(
            "Starting MCP worker on http://%s:%s/mcp (clients connect to %s)",
            mcp_config.MCP_WORKER_HOST, args.port, mcp_config.MCP_URL,
        )
        uvicorn.run(app, host=mcp_config.MCP_WORKER_HOST, port=args.port, log_level='info')
    except Exception as exc:
        logger.error("MCP server runtime failure: %s", exc)
        logger.error("Traceback:\n%s", traceback.format_exc())
        raise


# Run the MCP worker when executed directly
if __name__ == "__main__":
    main()
