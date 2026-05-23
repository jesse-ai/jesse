"""
Jesse MCP Server Entry Point

This module is the entry point for the Jesse MCP server. It:
1. Parses command line arguments (--port, --api_url)
2. Creates and configures the FastMCP server instance
3. Sets the Jesse API URL for tools to use
4. Registers all available MCP tools
5. Starts the server with streamable-http transport

USAGE:
------
Run directly: python -m jesse.mcp.server --port 9002 --api_url http://localhost:9000 --password your_password
Or via manager: manager.py handles subprocess creation with proper arguments

The server runs on 0.0.0.0 and accepts connections from MCP clients (like Cursor).
"""

import argparse
import logging
import sys
import traceback
from mcp.server.fastmcp import FastMCP
import jesse.mcp.mcp_config as mcp_config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("jesse.mcp.server")
MCP_HOST = "0.0.0.0"


def _log_uncaught_exception(exc_type, exc_value, exc_tb):
    """Log uncaught exceptions with traceback for transport/session debugging."""
    logger.error("Uncaught exception in MCP server", exc_info=(exc_type, exc_value, exc_tb))


sys.excepthook = _log_uncaught_exception

# Parse command line arguments
parser = argparse.ArgumentParser(description='Jesse MCP Server')
parser.add_argument('--port', type=int, required=True, help='Port to run the MCP server on')
parser.add_argument('--api_url', type=str, required=True, help='Jesse API URL')
parser.add_argument('--password', type=str, required=True, help='Jesse admin password for WebSocket auth')
args = parser.parse_args()

# Initialize shared runtime config for this subprocess.
# The manager process passes these values via CLI args.
mcp_config.JESSE_API_URL = args.api_url
mcp_config.JESSE_PASSWORD = args.password
mcp_config.MCP_PORT = args.port
mcp_config.MCP_URL = f"http://localhost:{args.port}/mcp"

# Create the MCP server instance
mcp = FastMCP("Jesse MCP Server", host=MCP_HOST, port=args.port, json_response=True)

# Start WebSocket event listener for real-time updates
from jesse.mcp.ws_listener import start_listener
try:
    listener_started = start_listener(args.api_url, args.password)
    if listener_started:
        logger.info("Started WebSocket event listener for %s", args.api_url)
    else:
        logger.warning("WebSocket listener already running")
except Exception:
    logger.exception("Failed to start WebSocket listener")

# Register all available resources
from jesse.mcp.resources import register_resources
register_resources(mcp)

# Register all available tools
from jesse.mcp.tools import register_tools
register_tools(mcp)

def run():
    """Start the MCP server with streamable-http transport."""
    try:
        logger.info("Starting MCP streamable-http server at %s", mcp_config.MCP_URL)
        mcp.run(transport="streamable-http")
    except Exception as exc:
        logger.error("MCP server runtime failure: %s", exc)
        logger.error("Traceback:\n%s", traceback.format_exc())
        raise

# Run the MCP server when executed directly
if __name__ == "__main__":
    run()
