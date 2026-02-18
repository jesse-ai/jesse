"""
Jesse Strategy Management Tools

This module provides MCP tools for managing Jesse trading strategies,
using the strategy controller endpoints like the dashboard does.

The tools include:
- create_strategy: Creates a new strategy with basic template code
- read_strategy: Reads the content of an existing strategy using Jesse's API
- write_strategy: Updates the content of an existing strategy using Jesse's API

All tools require authentication via Jesse admin password.
"""

from .services import (
    create_strategy_service,
    read_strategy_service,
    write_strategy_service
)


def register_strategy_tools(mcp):
    """
    Register the tools for the strategy related operations.

    This module provides MCP tools for managing Jesse trading strategies:
    - create_strategy: Creates a new strategy with basic template code
    - read_strategy: Reads the content of an existing strategy using Jesse's API
    - write_strategy: Updates the content of an existing strategy using Jesse's API

    All tools require authentication via Jesse admin password.

    Args:
        mcp: The MCP server instance.

    Returns:
        None
    """

    @mcp.tool()
    def create_strategy(name: str) -> dict:
        """
        Create a new trading strategy in Jesse.

        Args:
            name: Name of the new strategy to create

        Returns:
            Success or error message
        """
        return create_strategy_service(name)

    
    @mcp.tool()
    def read_strategy(name: str) -> dict:
        """
        Read the content of a trading strategy using Jesse's API.

        Args:
            name: Name of the strategy to read

        Returns:
            Dictionary containing strategy content or error message
        """
        return read_strategy_service(name)
    
    @mcp.tool()
    def write_strategy(name: str, content: str) -> dict:
        """
        Write content to a trading strategy using Jesse's API.

        Args:
            name: Name of the strategy to write to
            content: The Python code content to write to the strategy file

        Returns:
            Dictionary containing success confirmation or error message
        """
        return write_strategy_service(name, content)