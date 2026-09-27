"""
Jesse MCP Configuration Store

This module provides a centralized configuration store for the MCP server.
All configuration values that need to be shared between the server and tools
are stored here to avoid circular imports.

The worker entry point (jesse.mcp.server) sets these values before registering tools.
"""

from typing import Mapping, Optional
from urllib.parse import quote

# Internal Jesse API URL. Tools call the API on this machine through it (loopback or the
# concrete bind address); it is never the public DASHBOARD_URL.
JESSE_API_URL = None
JESSE_PASSWORD = None

# Public dashboard origin (DASHBOARD_URL or its localhost default). Dashboard links and
# the advertised MCP endpoint are derived from it.
DASHBOARD_URL = None

# The MCP worker listens on loopback only. Clients reach it through the authenticated
# /mcp route on the dashboard origin; MCP_PORT is the worker's internal port.
MCP_WORKER_HOST = '127.0.0.1'
MCP_DEFAULT_PORT = 9002
MCP_PORT = MCP_DEFAULT_PORT

# Public MCP endpoint advertised to clients: DASHBOARD_URL + '/mcp'.
MCP_URL = None

# Environment variable used to hand the dashboard PASSWORD to the worker process.
# Command-line arguments are visible to every user on the machine (e.g. `ps`), so the
# password is never passed there.
WORKER_PASSWORD_ENV = 'JESSE_MCP_WORKER_PASSWORD'


# Dashboard routes per session category. The Nuxt SPA is built into jesse/static/ and
# served from the root of the dashboard origin.
_DASHBOARD_PATHS = {
    'backtest': 'backtest',
    'optimization': 'optimization',
    'monte_carlo': 'monte-carlo',
    'significance_test': 'significance-test',
}


def configured_worker_port(env_values: Mapping[str, Optional[str]]) -> int:
    """Return the MCP worker port from MCP_PORT, or the default when it is unset or blank."""
    raw = env_values.get('MCP_PORT')
    if raw is None or not str(raw).strip():
        return MCP_DEFAULT_PORT
    port = int(str(raw).strip())
    if not 1 <= port <= 65535:
        raise ValueError(f'MCP_PORT must be between 1 and 65535, got {port}')
    return port


def dashboard_url(category: str, session_id: str) -> str:
    """
    Build the dashboard URL for a given session.

    Used by MCP tool responses so the agent can surface a clickable link
    to the user — they open the dashboard at the exact session page to
    inspect charts, trades, equity curves, etc. that aren't worth pulling
    over the wire.

    `category` is one of: 'backtest', 'optimization', 'monte_carlo',
    'significance_test'.

    The Nuxt SPA uses hash routing (nuxt.config.ts: `hashMode: true`), so
    session pages live at `/#/<path>/<id>`, not `/<path>/<id>`. The base is
    the already-validated public DASHBOARD_URL origin, so the link works from
    the machine where the user clicks it rather than only on the Jesse host.
    """
    if not DASHBOARD_URL:
        return ''
    path = _DASHBOARD_PATHS.get(category)
    if not path or not session_id:
        return ''
    return f"{DASHBOARD_URL}/#/{path}/{quote(str(session_id), safe='')}"
