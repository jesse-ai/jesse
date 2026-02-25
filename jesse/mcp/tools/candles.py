
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
        Import historical candle data from exchanges for backtesting.

        Downloads historical candle (OHLCV) data from the specified exchange starting from
        the given date. Supports both blocking (waits for completion) and non-blocking modes.
        All supported timeframes are automatically imported: 1m, 3m, 5m, 15m, 30m, 45m,
        1h, 2h, 3h, 4h, 6h, 8h, 12h, 1D, 3D, 1W, 1M.

        Parameters:
            exchange (str): Exchange name for data import. Supported exchanges include:
                - "Binance Spot" - Most popular, reliable data
                - "Binance Perpetual Futures" - High leverage futures
                - "Bybit Spot" - Alternative data source
                - "Bybit USDT Perpetual" - Futures trading
                - "Bybit USDC Perpetual" - USDC settlement futures
                - "Coinbase Spot" - Low fees (0.03%)
                - "Bitfinex Spot" - Additional option
                - "Gate USDT Perpetual" - Additional futures option
                Shape: String matching supported exchange names
            symbol (str): Trading pair symbol (e.g., "BTC-USDT", "ETH-USDT", "DOGE-USDT")
                Shape: String in format "BASE-QUOTE" (e.g., "BTC-USDT")
            start_date (str): Import start date in YYYY-MM-DD format
                Data will be imported from this date until present
                Shape: String in "YYYY-MM-DD" format
            blocking (bool): Whether to wait for import completion or return immediately
                - True: Blocks and monitors progress until completion (default)
                - False: Returns immediately with import_id for async monitoring
                Shape: Boolean
            import_id (str, optional): UUID string to reuse for retrying failed imports
                If provided, resumes previous failed import
                If None, generates new unique import ID
                Shape: UUID format string or None

        Returns:
            dict: Import result with status and metadata:

            Blocking Mode Success Response:
            {
                "status": "completed",
                "action": "candle_import_completed",
                "import_id": "uuid-string",
                "exchange": "string",
                "symbol": "string",
                "start_date": "YYYY-MM-DD",
                "duration_seconds": int,
                "progress_events_count": int,
                "message": "Successfully imported BTC-USDT candles from Binance Spot in 45s"
            }

            Blocking Mode Error Response:
            {
                "status": "failed|timeout",
                "action": "candle_import_failed|candle_import_timeout",
                "import_id": "uuid-string",
                "exchange": "string",
                "symbol": "string",
                "start_date": "YYYY-MM-DD",
                "duration_seconds": int,
                "error_details": ["error_description"],
                "message": "Failed to import BTC-USDT candles from Binance Spot after 120s"
            }

            Non-Blocking Mode Success Response:
            {
                "status": "success",
                "action": "candle_import_started",
                "import_id": "uuid-string",
                "exchange": "string",
                "symbol": "string",
                "start_date": "YYYY-MM-DD",
                "message": "Started importing BTC-USDT candles from Binance Spot starting 2024-01-01"
            }

            Error Response (API/Configuration):
            {
                "status": "error",
                "action": "candle_import_failed|config_error",
                "exchange": "string",
                "symbol": "string",
                "error_type": "api_error|network_error",
                "message": "Failed to start candle import: [error details]"
            }

            Shape: {
                "status": "completed|failed|timeout|success|error",
                "action": string,
                "import_id": string,
                "exchange": string,
                "symbol": string,
                "start_date": string,
                "duration_seconds": int|undefined,
                "progress_events_count": int|undefined,
                "error_details": array[string]|undefined,
                "message": string
            }

        Raises:
            ValidationError: If exchange/symbol/start_date format is invalid
            NetworkError: If Jesse API is unreachable
            AuthenticationError: If Jesse password is incorrect

        Behavior:
            - Imports all supported timeframes automatically (no need to specify timeframe)
            - Blocking mode (default): Tool call blocks synchronously until import completes
            - WebSocket monitoring happens internally - agent just waits for final result
            - Non-blocking mode: Returns immediately with import_id for external monitoring
            - Retry with same import_id to resume failed imports efficiently

        Workflow:
            1. Call import_candles() with blocking=True (default)
            2. Tool handles all WebSocket monitoring internally
            3. Tool returns final result when import completes (success/failure/timeout)
            4. No additional monitoring or polling needed by the caller

        Example:
            >>> # Simple blocking import (recommended approach)
            >>> result = import_candles("Binance Spot", "BTC-USDT", "2024-01-01")
            >>> # Tool blocks here, monitoring WebSocket internally...
            >>> if result["status"] == "completed":
            ...     print(f"✅ Import successful! Duration: {result['duration_seconds']}s")
            ...     print(f"📊 Progress updates received: {result['progress_events_count']}")
            >>> elif result["status"] == "failed":
            ...     print(f"❌ Import failed: {result['message']}")
            >>> elif result["status"] == "timeout":
            ...     print(f"⏰ Import timed out after {result['duration_seconds']}s")

            >>> # Non-blocking import (advanced - returns immediately)
            >>> result = import_candles("Binance Spot", "ETH-USDT", "2024-01-01", blocking=False)
            >>> if result["status"] == "success":
            ...     import_id = result["import_id"]
            ...     print(f"🚀 Import started with ID: {import_id}")
            ...     # Import continues in background - you'd need external monitoring

            >>> # Retry failed import (same blocking behavior)
            >>> retry_result = import_candles("Binance Spot", "ETH-USDT", "2024-01-01",
            ...                               import_id=import_id)
            >>> # Blocks and waits for completion just like regular import
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

        Terminates a running candle import operation using its import ID.
        The import process will be stopped immediately. Any partially imported
        data will remain in the database, but the import operation itself ends.

        Parameters:
            import_id (str): UUID string of the import process to cancel
                This should be the import_id returned from import_candles()
                Shape: UUID format string (e.g., "550e8400-e29b-41d4-a716-446655440000")

        Returns:
            dict: Cancellation result with status:

            Success Response:
            {
                "status": "success",
                "action": "candle_import_cancelled",
                "import_id": "uuid-string",
                "message": "Candle import process 550e8400-e29b-41d4-a716-446655440000 has been requested for termination"
            }

            Error Response:
            {
                "status": "error",
                "action": "cancel_failed",
                "import_id": "uuid-string",
                "error_type": "api_error|network_error",
                "message": "Failed to cancel import: [error details]"
            }

            Shape: {
                "status": "success|error",
                "action": "candle_import_cancelled|cancel_failed",
                "import_id": string,
                "error_type": string|undefined,
                "message": string
            }

        Raises:
            ValidationError: If import_id format is invalid
            NetworkError: If Jesse API is unreachable
            NotFoundError: If import_id does not exist or is not running

        Behavior:
            - Immediately requests termination of the import process
            - Partially imported data remains in database
            - Cannot cancel already completed or failed imports
            - Operation is asynchronous - cancellation request is sent but may take time to process

        Example:
            >>> # Cancel a running import
            >>> result = cancel_candle_import("550e8400-e29b-41d4-a716-446655440000")
            >>> if result["status"] == "success":
            ...     print("Import cancellation requested")
            ... else:
            ...     print(f"Failed to cancel: {result['message']}")
        """
        return cancel_candle_import_service(import_id)

    @mcp.tool()
    def clear_candle_cache() -> dict:
        """
        Clear the candles database cache to ensure fresh data loading.

        Flushes the in-memory cache used by Jesse's candle data system.
        This forces subsequent candle queries to reload data directly from
        the database, ensuring you see the most recent imported data.

        Parameters:
            None

        Returns:
            dict: Cache clearing result:

            Success Response:
            {
                "status": "success",
                "action": "cache_cleared",
                "message": "Candles database cache cleared successfully"
            }

            Error Response:
            {
                "status": "error",
                "action": "cache_clear_failed",
                "error_type": "api_error|network_error",
                "message": "Failed to clear cache: [error details]"
            }

            Shape: {
                "status": "success|error",
                "action": "cache_cleared|cache_clear_failed",
                "error_type": string|undefined,
                "message": string
            }

        Raises:
            NetworkError: If Jesse API is unreachable
            AuthenticationError: If Jesse password is incorrect

        Behavior:
            - Clears all cached candle data from memory
            - Forces fresh database queries on next candle access
            - Useful after importing new data to ensure visibility
            - Does not affect stored data, only cache layer
            - Immediate effect on subsequent operations

        When to Use:
            - After importing new candle data to see it immediately
            - If experiencing stale data issues
            - Before critical backtests to ensure data freshness
            - When troubleshooting data visibility problems

        Example:
            >>> # Clear cache after importing new data
            >>> import_result = import_candles("Binance Spot", "BTC-USDT", "2024-01-01")
            >>> cache_result = clear_candle_cache()
            >>> if cache_result["status"] == "success":
            ...     print("Cache cleared - new data will be visible")
        """
        return clear_candle_cache_service()

    @mcp.tool()
    def get_candles(exchange: str, symbol: str, timeframe: str) -> dict:
        """
        Retrieve historical candle (OHLCV) data for technical analysis.

        Fetches candlestick data from the database for the specified exchange,
        symbol, and timeframe. Returns complete OHLCV (Open, High, Low, Close, Volume)
        data suitable for technical analysis and strategy development.

        Parameters:
            exchange (str): Exchange name where data was imported from. Must match
                the exchange used during import_candles(). Supported exchanges:
                - "Binance Spot", "Binance Perpetual Futures"
                - "Bybit Spot", "Bybit USDT Perpetual", "Bybit USDC Perpetual"
                - "Coinbase Spot", "Bitfinex Spot", "Gate USDT Perpetual"
                Shape: String matching import exchange name
            symbol (str): Trading pair symbol (e.g., "BTC-USDT", "ETH-USDT")
                Must match symbol used during import_candles()
                Shape: String in "BASE-QUOTE" format
            timeframe (str): Candle timeframe for analysis. Supported timeframes:
                - Minutes: "1m", "3m", "5m", "15m", "30m", "45m"
                - Hours: "1h", "2h", "3h", "4h", "6h", "8h", "12h"
                - Days: "1D", "3D"
                - Weeks: "1W"
                - Months: "1M"
                Shape: String from supported timeframe list

        Returns:
            dict: Candle data result with OHLCV arrays:

            Success Response:
            {
                "status": "success",
                "action": "candles_retrieved",
                "exchange": "Binance Spot",
                "symbol": "BTC-USDT",
                "timeframe": "1h",
                "candle_count": 1000,
                "candles": [
                    {
                        "timestamp": 1640995200000,  // Unix timestamp (ms)
                        "open": 46250.00,            // Opening price
                        "high": 46750.00,            // Highest price
                        "low": 46100.00,             // Lowest price
                        "close": 46500.00,           // Closing price
                        "volume": 123.45             // Trading volume
                    },
                    // ... more candles
                ],
                "message": "Retrieved 1000 candles for BTC-USDT on Binance Spot (1h)"
            }

            Error Response:
            {
                "status": "error",
                "action": "candles_retrieval_failed",
                "exchange": "string",
                "symbol": "string",
                "timeframe": "string",
                "error_type": "api_error|network_error",
                "message": "Failed to retrieve candles: [error details]"
            }

            Shape: {
                "status": "success|error",
                "action": "candles_retrieved|candles_retrieval_failed",
                "exchange": string,
                "symbol": string,
                "timeframe": string,
                "candle_count": int|undefined,
                "candles": array[object]|undefined,
                "error_type": string|undefined,
                "message": string
            }

            Candle Object Shape:
            {
                "timestamp": int,    // Unix timestamp in milliseconds
                "open": float,       // Opening price
                "high": float,       // Highest price in period
                "low": float,        // Lowest price in period
                "close": float,      // Closing price
                "volume": float      // Trading volume
            }

        Raises:
            ValidationError: If exchange/symbol/timeframe format is invalid
            NotFoundError: If requested data doesn't exist (not imported yet)
            NetworkError: If Jesse API is unreachable

        Prerequisites:
            - Candle data must be imported first using import_candles()
            - Exchange and symbol must match import parameters exactly
            - Timeframe must be one of the supported values

        Data Volume:
            - Returns all available candles for the specified parameters
            - Can return thousands of candles depending on import history
            - Consider timeframe for data density (1m returns more data than 1D)

        Example:
            >>> # Get hourly BTC data for analysis
            >>> candles = get_candles("Binance Spot", "BTC-USDT", "1h")
            >>> if candles["status"] == "success":
            ...     data = candles["candles"]
            ...     closes = [candle["close"] for candle in data]
            ...     print(f"Retrieved {len(closes)} price points")

            >>> # Get daily ETH data
            >>> daily_data = get_candles("Binance Spot", "ETH-USDT", "1D")
            >>> if daily_data["status"] == "success":
            ...     print(f"Latest close: ${daily_data['candles'][-1]['close']}")
        """
        return get_candles_service(exchange=exchange, symbol=symbol, timeframe=timeframe)

    @mcp.tool()
    def get_existing_candles() -> dict:
        """
        List all candle datasets available in the database.

        Retrieves metadata about all imported candle data including exchange,
        symbol, timeframe, and date ranges. Use this to check what data is
        available before running backtests or analysis.

        Parameters:
            None

        Returns:
            dict: Available candle datasets metadata:

            Success Response:
            {
                "status": "success",
                "action": "existing_candles_retrieved",
                "candle_sets_count": 5,
                "candle_sets": [
                    {
                        "exchange": "Binance Spot",
                        "symbol": "BTC-USDT",
                        "timeframe": "1h",
                        "count": 17520,           // Number of candles
                        "from_date": "2020-01-01",
                        "to_date": "2024-12-31"
                    },
                    {
                        "exchange": "Binance Spot",
                        "symbol": "ETH-USDT",
                        "timeframe": "4h",
                        "count": 4380,
                        "from_date": "2020-01-01",
                        "to_date": "2024-12-31"
                    },
                    // ... more datasets
                ],
                "message": "Found 5 candle datasets in database"
            }

            Error Response:
            {
                "status": "error",
                "action": "existing_candles_retrieval_failed",
                "error_type": "api_error|network_error",
                "message": "Failed to retrieve existing candles: [error details]"
            }

            Shape: {
                "status": "success|error",
                "action": "existing_candles_retrieved|existing_candles_retrieval_failed",
                "candle_sets_count": int|undefined,
                "candle_sets": array[object]|undefined,
                "error_type": string|undefined,
                "message": string
            }

            Candle Set Object Shape:
            {
                "exchange": string,     // Exchange name
                "symbol": string,       // Trading pair
                "timeframe": string,    // Candle timeframe
                "count": int,           // Number of candles available
                "from_date": string,    // Start date (YYYY-MM-DD)
                "to_date": string       // End date (YYYY-MM-DD)
            }

        Raises:
            NetworkError: If Jesse API is unreachable
            AuthenticationError: If Jesse password is incorrect

        Behavior:
            - Returns metadata only, not actual candle data
            - Shows all imported datasets across all exchanges/symbols/timeframes
            - Includes date ranges and candle counts for each dataset
            - Data is aggregated by exchange-symbol-timeframe combinations

        Use Cases:
            - Check what data is available before backtesting
            - Verify import completion
            - Plan data requirements for new strategies
            - Audit database contents

        Example:
            >>> # Check available data
            >>> available = get_existing_candles()
            >>> if available["status"] == "success":
            ...     datasets = available["candle_sets"]
            ...     print(f"Found {len(datasets)} datasets")
            ...
            ...     # Find BTC data
            ...     btc_datasets = [d for d in datasets if d["symbol"] == "BTC-USDT"]
            ...     for dataset in btc_datasets:
            ...         print(f"BTC-{dataset['timeframe']}: {dataset['count']} candles")
        """
        return get_existing_candles_service()

    @mcp.tool()
    def delete_candles(exchange: str, symbol: str) -> dict:
        """
        Permanently delete candle data from the database.

        Removes all candle data for the specified exchange and symbol across all timeframes.
        This operation is irreversible - deleted data cannot be recovered.
        Use with caution as it affects all timeframes for the exchange-symbol pair.

        Parameters:
            exchange (str): Exchange name whose data to delete. Must match
                the exchange name used during import. Supported exchanges:
                - "Binance Spot", "Binance Perpetual Futures"
                - "Bybit Spot", "Bybit USDT Perpetual", "Bybit USDC Perpetual"
                - "Coinbase Spot", "Bitfinex Spot", "Gate USDT Perpetual"
                Shape: String matching import exchange name exactly
            symbol (str): Trading pair symbol to delete (e.g., "BTC-USDT", "ETH-USDT")
                Must match symbol used during import exactly
                Shape: String in "BASE-QUOTE" format

        Returns:
            dict: Deletion result with confirmation:

            Success Response:
            {
                "status": "success",
                "action": "candles_deleted",
                "exchange": "Binance Spot",
                "symbol": "BTC-USDT",
                "message": "Candles for BTC-USDT on Binance Spot deleted successfully"
            }

            Error Response:
            {
                "status": "error",
                "action": "candles_deletion_failed",
                "exchange": "string",
                "symbol": "string",
                "error_type": "api_error|network_error",
                "message": "Failed to delete candles: [error details]"
            }

            Shape: {
                "status": "success|error",
                "action": "candles_deleted|candles_deletion_failed",
                "exchange": string,
                "symbol": string,
                "error_type": string|undefined,
                "message": string
            }

        Raises:
            ValidationError: If exchange/symbol format is invalid
            NotFoundError: If specified exchange/symbol data doesn't exist
            NetworkError: If Jesse API is unreachable

        Behavior:
            - Deletes ALL timeframes for the exchange-symbol pair
            - Operation is permanent and cannot be undone
            - Affects all imported timeframes (1m, 1h, 1D, etc.)
            - Immediately removes data from database
            - Cache is not automatically cleared (may need clear_candle_cache())

        Safety Considerations:
            - No confirmation prompt - deletion happens immediately
            - Consider backing up important data before deletion
            - Use get_existing_candles() first to verify what will be deleted
            - Deletion affects all timeframes for the pair

        When to Use:
            - Remove obsolete or incorrect data
            - Free up database space
            - Clean up test data
            - Re-import data with different parameters

        Example:
            >>> # Delete BTC data from Binance Spot
            >>> result = delete_candles("Binance Spot", "BTC-USDT")
            >>> if result["status"] == "success":
            ...     print("BTC data deleted from all timeframes")
            ... else:
            ...     print(f"Deletion failed: {result['message']}")

            >>> # Check what remains after deletion
            >>> remaining = get_existing_candles()
            >>> btc_data = [d for d in remaining["candle_sets"]
            ...             if d["exchange"] == "Binance Spot" and d["symbol"] == "BTC-USDT"]
            >>> print(f"BTC datasets remaining: {len(btc_data)}")  # Should be 0
        """
        return delete_candles_service(exchange=exchange, symbol=symbol)

