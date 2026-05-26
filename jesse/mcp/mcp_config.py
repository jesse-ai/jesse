"""
Jesse MCP Configuration Store

This module provides a centralized configuration store for the MCP server.
All configuration values that need to be shared between the server and tools
are stored here to avoid circular imports.

The server sets these values before registering tools.
"""

# Jesse API configuration
JESSE_API_URL = None
JESSE_PASSWORD = None

# MCP Server Port & URL
MCP_PORT = 9002
MCP_URL = f"http://localhost:{MCP_PORT}/mcp"


# Dashboard routes per session category. The dashboard is the Nuxt SPA
# built into jesse/static/ and is served from the same host:port as the
# Jesse API, so the dashboard base URL == JESSE_API_URL.
_DASHBOARD_PATHS = {
    'backtest': 'backtest',
    'monte_carlo': 'monte-carlo',
    'significance_test': 'significance-test',
}


def dashboard_url(category: str, session_id: str) -> str:
    """
    Build the dashboard URL for a given session.

    Used by MCP tool responses so the agent can surface a clickable link
    to the user — they open the dashboard at the exact session page to
    inspect charts, trades, equity curves, etc. that aren't worth pulling
    over the wire.

    `category` is one of: 'backtest', 'monte_carlo', 'significance_test'.

    Two quirks the URL has to handle:
    - The Nuxt SPA uses hash routing (nuxt.config.ts: `hashMode: true`),
      so session pages live at `/#/<path>/<id>`, not `/<path>/<id>`.
    - Jesse often binds to `0.0.0.0` (all interfaces) for the API server,
      but `0.0.0.0` is not a browser-routable address. We rewrite it to
      `127.0.0.1` so the link works when clicked from the user's machine.
    """
    if not JESSE_API_URL:
        return ''
    path = _DASHBOARD_PATHS.get(category)
    if not path or not session_id:
        return ''
    base = JESSE_API_URL.rstrip('/').replace('://0.0.0.0:', '://127.0.0.1:')
    return f"{base}/#/{path}/{session_id}"
