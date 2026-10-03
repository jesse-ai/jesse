"""
Jesse MCP Configuration Store

This module provides a centralized configuration store for the MCP server.
All configuration values that need to be shared between the server and tools
are stored here to avoid circular imports.

The worker entry point (jesse.mcp.server) sets these values before registering tools.
"""

from typing import Optional
from urllib.parse import quote

# Internal Jesse API URL. Tools call the API on this machine through it (loopback or the
# concrete bind address); it is never the public DASHBOARD_URL.
JESSE_API_URL = None
JESSE_PASSWORD = None

# Public dashboard origin (DASHBOARD_URL or its localhost default). Dashboard links and
# the advertised MCP endpoint are derived from it.
DASHBOARD_URL = None

# The MCP worker listens on loopback only. Clients reach it through the authenticated
# /mcp route on the dashboard origin. The OS assigns the worker's port when Jesse starts
# it (see jesse.mcp.manager); MCP_WORKER_PORT holds that port once known, in both the
# Jesse process and the worker. It is an internal detail and never advertised to clients.
MCP_WORKER_HOST = '127.0.0.1'
MCP_WORKER_PORT: Optional[int] = None

# The .env key that used to fix the worker port. It is now ignored; Jesse only mentions
# it at startup so users know they can remove it.
LEGACY_PORT_ENV_KEY = 'MCP_PORT'

# Public MCP endpoint advertised to clients: DASHBOARD_URL + '/mcp'.
MCP_URL = None

# Environment variable used to hand the dashboard PASSWORD to the worker process.
# Command-line arguments are visible to every user on the machine (e.g. `ps`), so the
# password is never passed there.
WORKER_PASSWORD_ENV = 'JESSE_MCP_WORKER_PASSWORD'


# Dashboard routes per session category, plus the strategy editor keyed by strategy name.
# The Nuxt SPA is built into jesse/static/ and served from the root of the dashboard origin.
_DASHBOARD_PATHS = {
    'backtest': 'backtest',
    'optimization': 'optimization',
    'monte_carlo': 'monte-carlo',
    'significance_test': 'significance-test',
    # Opening a live/paper session link makes the dashboard load it into a Live tab.
    'live': 'live',
    'strategy': 'strategies',
}


def dashboard_page_url(path: str) -> str:
    """Build a dashboard link to a fixed page such as 'candles/manage'; '' without DASHBOARD_URL."""
    if not DASHBOARD_URL:
        return ''
    return f"{DASHBOARD_URL}/#/{path}"


def dashboard_url(category: str, session_id: str) -> str:
    """
    Build the dashboard URL for a given session or local strategy.

    Used by MCP tool responses so the agent can surface a clickable link
    to the user — they open the dashboard at the exact session page to
    inspect charts, trades, equity curves, etc. that aren't worth pulling
    over the wire.

    `category` is one of: 'backtest', 'optimization', 'monte_carlo',
    'significance_test', 'live', or 'strategy' (whose id is the local strategy name).

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
