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
Run directly: python -m jesse.mcp.server --port 9002 --api_url http://localhost:9000
Or via manager: manager.py handles subprocess creation with proper arguments

The server runs on 127.0.0.1 and accepts connections from MCP clients (like Cursor).
"""

import argparse
from mcp.server.fastmcp import FastMCP

# Parse command line arguments
parser = argparse.ArgumentParser(description='Jesse MCP Server')
parser.add_argument('--port', type=int, required=True, help='Port to run the MCP server on')
parser.add_argument('--api_url', type=str, required=True, help='Jesse API URL')
parser.add_argument('--password', type=str, required=True, help='Jesse admin password for WebSocket auth')
args = parser.parse_args()

# Create the MCP server instance
mcp = FastMCP("Jesse MCP Server", host="127.0.0.1", port=args.port, json_response=True)

# Set the global Jesse API URL for tools to access at runtime
import jesse.mcp.tools as tools_module
tools_module.JESSE_API_URL = args.api_url

# Set the global Jesse password for tools to access at runtime
tools_module.JESSE_PASSWORD = args.password

# Start WebSocket event listener for real-time updates
from jesse.mcp.ws_listener import start_listener
listener_started = start_listener(args.api_url, args.password)
if listener_started:
    print(f"🔌 Started WebSocket event listener for {args.api_url}")
else:
    print("⚠️  WebSocket listener already running")

# Register all available resources
from jesse.mcp.resources import register_resources
register_resources(mcp)

# Register all available tools
from jesse.mcp.tools import register_tools
register_tools(mcp)

def run():
    """Start the MCP server with streamable-http transport."""
    mcp.run(transport="streamable-http")

# Run the MCP server when executed directly
if __name__ == "__main__":
    run()
