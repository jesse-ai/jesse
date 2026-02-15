"""
Jesse MCP Resources Registration Module

This module serves as the central registry for all MCP (Model Context Protocol) resources
in the Jesse trading framework. It aggregates and registers all resource handlers that
provide documentation and reference materials for Jesse's various components.

Resources include:
- Strategy development guides and templates
- Indicator documentation and usage examples
- Position sizing and risk management references
- Utility functions and helper tools
- Exchange configurations and trading characteristics
- Backtesting tools and workflow guidance
- Market data handling procedures
- Configuration management references
- Backtest management best practices

Adding New Resources:
To add new MCP resources, create a new module in this directory following the pattern:

1. Create a new file: `your_resource.py`
2. Define a registration function: `register_your_resource_resources(mcp)`
3. Use the `@mcp.resource("jesse://your-resource-uri")` decorator
4. Return documentation strings from your resource functions
5. Import and call your registration function in this module's `register_resources()`

Example:
    def register_custom_resources(mcp):
        @mcp.resource("jesse://custom-guide")
        def custom_guide():
            return "Your custom documentation here"
"""

from jesse.mcp.resources.strategy import register_strategy_resources
from jesse.mcp.resources.indicator import register_indicator_resources
from jesse.mcp.resources.position import register_position_resources
from jesse.mcp.resources.backtest import register_backtest_resources
from jesse.mcp.resources.candle import register_data_resources
from jesse.mcp.resources.configuration import register_config_resources
from jesse.mcp.resources.backtest_management import register_backtest_management_resources
from jesse.mcp.resources.utils import register_utils_resources


def register_resources(mcp) -> None:
    """
    Register all Jesse MCP resources with the provided MCP server instance.

    This function serves as the single entry point for registering all MCP resources,
    ensuring that documentation and reference materials for all Jesse components
    are made available through the MCP protocol.

    Args:
        mcp: The MCP server instance to register resources with
    """
    register_strategy_resources(mcp)
    register_indicator_resources(mcp)
    register_position_resources(mcp)
    register_backtest_resources(mcp)
    register_data_resources(mcp)
    register_config_resources(mcp)
    register_backtest_management_resources(mcp)
    register_utils_resources(mcp)