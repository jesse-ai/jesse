"""
Jesse General Tools

This module provides MCP tools for general Jesse operations.

The tools include:
- get_jesse_status: Get the current status of Jesse
- greet_user: Generate a greeting message for the user
"""

from jesse.mcp.tools.services.general import (
    get_jesse_status as get_jesse_status_service,
    greet_user as greet_user_service,
)


def register_general_tools(mcp):
    """
    Register the tools for the general operations.

    Args:
        mcp: The MCP server instance.

    Returns:
        None
    """
    # Tool: get jesse status
    @mcp.tool()
    def get_jesse_status():
        return get_jesse_status_service()

    # Tool: greet user
    @mcp.tool()
    def greet_user(name: str):
        return greet_user_service(name)

