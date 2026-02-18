
"""
Jesse Candles Management Tools

This module provides MCP tools for managing Jesse candle data,
using the candle controller endpoints like the dashboard does.

The tools include:
- import_candles: Import historical candle data for a symbol
- cancel_candle_import: Cancel an ongoing candle import process
- clear_candle_cache: Clear the candles database cache
- get_candles: Retrieve candle data for analysis
- get_existing_candles: List all imported candle data
- delete_candles: Remove candle data from database

For real-time import progress monitoring, use get_candle_import_progress from events.py
All tools require authentication via Jesse admin password.
"""

from jesse.mcp.tools.services.candles import (
    import_candles_service,
    cancel_candle_import_service,
    clear_candle_cache_service,
    get_candles_service,
    get_existing_candles_service,
    delete_candles_service
)


def register_candles_tools(mcp):
    """
    Register the candle management tools with the MCP server.

    Args:
        mcp: The MCP server instance.

    Returns:
        None
    """

    @mcp.tool()
    def import_candles(
        exchange: str,
        symbol: str,
        start_date: str,
        blocking: bool = True,
        import_id: str = None,
    ) -> dict:
        """
        Import historical candle data for a specific exchange and symbol.

        Downloads historical candle data from the specified exchange starting from
        the given date. By default, this function blocks and waits for completion.

        Args:
            exchange: Exchange name (e.g., 'binance', 'bybit', 'coinbase')
            symbol: Trading symbol (e.g., 'BTC-USDT', 'ETH-USDT')
            start_date: Start date in YYYY-MM-DD format
            blocking: If True, wait for import completion. If False, return import_id immediately
            import_id: Optional import ID to reuse (for retries)

        Returns:
            Success confirmation with import results or error message
        """
        return import_candles_service(
            exchange=exchange,
            symbol=symbol,
            start_date=start_date,
            blocking=blocking,
            import_id=import_id
        )

    @mcp.tool()
    def cancel_candle_import(import_id: str) -> dict:
        """
        Cancel an ongoing candle import process.

        Stops the import process for the specified import ID.

        Args:
            import_id: The import process ID to cancel

        Returns:
            Success confirmation or error message
        """
        return cancel_candle_import_service(import_id)

    @mcp.tool()
    def clear_candle_cache() -> dict:
        """
        Clear the candles database cache.

        Flushes the cache to ensure fresh data is loaded from the database.

        Returns:
            Success confirmation or error message
        """
        return clear_candle_cache_service()

    @mcp.tool()
    def get_candles(exchange: str, symbol: str, timeframe: str) -> dict:
        """
        Retrieve candle data for analysis.

        Gets historical candle data for the specified exchange, symbol, and timeframe.

        Args:
            exchange: Exchange name (e.g., 'Binance', 'Bybit')
            symbol: Trading symbol (e.g., 'BTC-USDT', 'ETH-USDT')
            timeframe: Timeframe (e.g., '1m', '5m', '1h', '1D', '1W', '1M')

        Returns:
            Candle data or error message
        """
        return get_candles_service(exchange=exchange, symbol=symbol, timeframe=timeframe)

    @mcp.tool()
    def get_existing_candles() -> dict:
        """
        List all imported candle data in the database.

        Returns information about all candles that have been imported and stored.

        Returns:
            List of existing candle data or error message
        """
        return get_existing_candles_service()

    @mcp.tool()
    def delete_candles(exchange: str, symbol: str) -> dict:
        """
        Remove candle data from the database.

        Permanently deletes candle data for the specified exchange and symbol.

        Args:
            exchange: Exchange name (e.g., 'binance', 'bybit')
            symbol: Trading symbol (e.g., 'BTC-USDT', 'ETH-USDT')

        Returns:
            Success confirmation or error message
        """
        return delete_candles_service(exchange=exchange, symbol=symbol)

