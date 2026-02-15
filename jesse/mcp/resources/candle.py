"""
Jesse MCP Candle Data Resources

This module provides comprehensive documentation and guidance for candle data
management in Jesse through the MCP (Model Context Protocol). It serves as the
complete reference for importing, managing, and working with historical market data.

The registered resource covers:
- Data import procedures and requirements
- Tool reference for all candle-related functions
- Supported exchanges, symbols, and timeframes
- Usage examples and retry mechanisms
- Success/failure response formats
- Best practices for data management

This resource is essential for ensuring strategies have access to required
historical data before backtesting or live trading.
"""

def register_data_resources(mcp):

    @mcp.resource("jesse://candle-management")
    def candle_management():
        """
        Get detailed reference for candle import and management procedures.

        This reference is used to help agents import and manage historical candle data.
        """
        return """
            # Candle Management Reference

            This reference covers candle import and management operations in Jesse.

            ## Data Requirements

            Historical candle data is required for backtesting strategies. Import data for all route exchanges, symbols, and timeframes before running backtests.

            ## Import Process

            1. Check existing data with `get_existing_candles()`
            2. Import missing data with `import_candles()` (blocking by default)
            3. Verify completion with `get_existing_candles()`

            ## Tool Reference

            ### get_existing_candles()

            Checks what candle data is currently available in the database.

            **Returns:** List of available candle datasets with exchange, symbol, timeframe, and date ranges.

            ### import_candles()

            Imports historical candle data from exchanges.

            **Parameters:**
            - `exchange`: Exchange name (e.g., "Binance Perpetual Futures")
            - `symbol`: Trading pair (e.g., "BTC-USDT")
            - `start_date`: Start date in YYYY-MM-DD format
            - `import_id` (optional): Import ID for retrying failed imports

            **Supported Timeframes:**
            1m, 3m, 5m, 15m, 30m, 45m, 1h, 2h, 3h, 4h, 6h, 8h, 12h, 1D, 3D, 1W, 1M

            **Returns:** Import result with status and import ID

            ## Usage Examples

            ### Basic Import
            ```python
            result = import_candles(
                exchange="Binance Spot",
                symbol="BTC-USDT",
                start_date="2024-01-01"
            )
            ```

            ### Retry Failed Import
            ```python
            # First attempt
            result = import_candles(
                exchange="Binance Spot",
                symbol="ETH-USDT",
                start_date="2024-01-01"
            )

            # If failed, retry with same import_id
            if result.get("status") != "success":
                import_id = result.get("import_id")
                retry_result = import_candles(
                    exchange="Binance Spot",
                    symbol="ETH-USDT",
                    start_date="2024-01-01",
                    import_id=import_id
                )
            ```

            ## Retry Behavior

            When retrying imports with the same `import_id`:

            - Previous events are automatically cleared
            - Import resumes from the failure point
            - Already-imported candles are skipped
            - Progress monitoring starts fresh but continues efficiently
            - WebSocket events are isolated per retry

            ## Success Response Format

            ```
            "Successfully imported candles since '2024-01-01' until today (2.1 days imported, 1.2 days already existed in the database)."
            ```

            The message shows both newly imported data and pre-existing data that was skipped.
            """