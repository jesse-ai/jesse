"""
Jesse Configuration Management Tools

This module provides MCP tools for managing Jesse configuration,
using the config controller endpoints like the dashboard does.

The configuration includes:
- Backtest settings (logging, warmup candles, exchanges)
- Live trading settings
- General Jesse settings
"""

from .services import (
    get_config_service,
    update_config_service,
    get_backtest_config_service,
    get_live_config_service,
    get_optimization_config_service
)


def register_config_tools(mcp):
    """
    Register the configuration management tools with the MCP server.

    Args:
        mcp: The MCP server instance.

    Returns:
        None
    """

    @mcp.tool()
    def get_config() -> dict:
        """
        Get the current Jesse configuration from the database.

        This loads the complete Jesse configuration that controls how
        backtests and live trading operate, using the same endpoint
        that the dashboard uses.

        Returns:
            Dictionary containing the current configuration
        """
        return get_config_service()

    @mcp.tool()
    def update_config(config: str) -> dict:
        """
        Update the Jesse configuration in the database.

        This saves the provided configuration to the database using the
        same endpoint that the dashboard uses for configuration updates.

        Args:
            config: JSON string of the complete configuration to save

        Returns:
            Success confirmation or error message
        """
        return update_config_service(config)

    @mcp.tool()
    def get_backtest_config() -> dict:
        """
        Get the backtest configuration section.

        This is a convenience method that loads the backtest-specific configuration
        including exchange settings, logging preferences, and warmup candles.

        Returns:
            Dictionary containing the backtest configuration
        """
        return get_backtest_config_service()

    @mcp.tool()
    def get_live_config() -> dict:
        """
        Get the live trading configuration section.

        This loads the live trading configuration including exchange settings
        and notification preferences.

        Returns:
            Dictionary containing the live trading configuration
        """
        return get_live_config_service()

    @mcp.tool()
    def get_optimization_config() -> dict:
        """
        Get the optimization configuration section.

        This loads the optimization settings including CPU cores, trials,
        and objective function configuration.

        Returns:
            Dictionary containing the optimization configuration
        """
        return get_optimization_config_service()
