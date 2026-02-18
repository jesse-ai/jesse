"""
Jesse Indicator Tools

This module provides MCP tools for working with Jesse's technical indicators.

The tools include:
- list_indicators: List all available technical indicators in Jesse
- get_indicator_details: Get detailed information about a specific indicator
"""

from .services import (
    list_indicators,
    get_indicator_details
)

def register_indicator_tools(mcp):
    """
    Register the indicator tools with the MCP server.

    Args:
        mcp: The MCP server instance.

    Returns:
        None
    """

    @mcp.tool()
    def list_indicators() -> dict:
        """
        List all available technical indicators in Jesse.

        Returns a comprehensive list of all indicators available through
        the jesse.indicators module, which can be used for technical analysis
        in trading strategies.

        Returns:
            dict: Contains status, count, and list of all available indicators
        """
        return list_indicators()

    @mcp.tool()
    def get_indicator_details(indicator_name: str) -> dict:
        """
        Get detailed information about a specific technical indicator.

        This tool provides comprehensive documentation for any Jesse indicator
        including parameters, return values, usage examples, and implementation details.

        Args:
            indicator_name: Name of the indicator (e.g., 'rsi', 'macd', 'sma')

        Returns:
            dict: Contains status, indicator details, or error information
        """
        return get_indicator_details(indicator_name)