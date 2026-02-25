"""
Jesse Backtest Management Tools

This module provides MCP tools for managing Jesse backtests,
using the backtest controller endpoints like the dashboard does.

The tools include:
- update_backtest_draft: Create or update a backtest draft configuration
- get_backtest_session: Get details of a specific backtest session by ID
- get_backtest_sessions: List backtest sessions with optional filters
- run_backtest: Execute a backtest using BacktestRequestJson configuration
- cancel_backtest: Cancel a running backtest
- purge_backtest_sessions: Purge old backtest sessions from the database
"""

from .services import (
    create_backtest_draft_service,
    update_backtest_draft_service,
    get_backtest_session_service,
    get_backtest_sessions_service,
    run_backtest_service,
    cancel_backtest_service,
    purge_backtest_sessions_service
)

def register_backtest_tools(mcp):
    """
    Register the backtest management tools with the MCP server.

    Args:
        mcp: The MCP server instance.

    Returns:
        None
    """


    @mcp.tool()
    def create_backtest_draft(
        exchange: str = "Binance Perpetual Futures",
        routes: str = '[{"exchange": "Binance Perpetual Futures", "strategy": "ExampleStrategy", "symbol": "BTC-USDT", "timeframe": "4h"}]',
        data_routes: str = '[]',
        start_date: str = "2024-01-01",
        finish_date: str = "2024-03-01",
        debug_mode: bool = False,
        export_csv: bool = False,
        export_json: bool = False,
        export_chart: bool = True,
        export_tradingview: bool = False,
        fast_mode: bool = False,
        benchmark: bool = True
    ) -> dict:
        """
        Create a new backtest draft session with specified parameters.

        Creates a new backtest session with the provided configuration parameters.
        This initializes a draft that can be modified using update_backtest_draft()
        before execution with run_backtest().

        Parameters:
            exchange (str): Exchange name for backtesting. Supported exchanges include:
                - "Binance Perpetual Futures" (default)
                - "Bybit USDT Perpetual"
                - "Bybit USDC Perpetual"
                - "Gate USDT Perpetual"
                - "Binance Spot"
                - "Bybit Spot"
                - "Coinbase Spot"
                - "Bitfinex Spot"
            routes (str): JSON string array of route configuration objects. Each route defines:
                - exchange: Exchange name (must match the main exchange parameter)
                - strategy: Strategy class name (e.g., "MyStrategy")
                - symbol: Trading pair (e.g., "BTC-USDT")
                - timeframe: Candle timeframe (e.g., "1h", "4h", "1D")
                Shape: Array of objects with required fields: exchange, strategy, symbol, timeframe
            data_routes (str): JSON string array of data route objects for additional data feeds.
                Each data route contains exchange, symbol, and timeframe fields.
                Shape: Array of objects with fields: exchange, symbol, timeframe
            start_date (str): Backtest start date in YYYY-MM-DD format
            finish_date (str): Backtest end date in YYYY-MM-DD format
            debug_mode (bool): Enable detailed debug logging during backtest execution
            export_csv (bool): Export backtest results as CSV file
            export_json (bool): Export backtest results as JSON file
            export_chart (bool): Export chart data for visualization
            export_tradingview (bool): Export TradingView Pine Script for chart analysis
            fast_mode (bool): Enable fast mode for quicker execution (reduced precision)
            benchmark (bool): Run benchmark comparison against buy-and-hold strategy

        Returns:
            dict: Session creation confirmation containing:
                - backtest_id: UUID string of the created session
                - message: Success confirmation message
                - Additional configuration metadata
                Shape: {"backtest_id": "uuid-string", "message": "string", ...}

        Raises:
            ValidationError: If route configuration is invalid or exchange is unsupported
            DatabaseError: If session creation fails in the database

        Example:
            >>> draft = create_backtest_draft(
            ...     exchange="Binance Spot",
            ...     routes='[{"exchange": "Binance Spot", "strategy": "MyStrategy", "symbol": "BTC-USDT", "timeframe": "4h"}]',
            ...     start_date="2024-01-01",
            ...     finish_date="2024-12-31"
            ... )
            >>> print(draft["backtest_id"])  # UUID of new session
        """
        return create_backtest_draft_service(
            exchange=exchange,
            routes=routes,
            data_routes=data_routes,
            start_date=start_date,
            finish_date=finish_date,
            debug_mode=debug_mode,
            export_csv=export_csv,
            export_json=export_json,
            export_chart=export_chart,
            export_tradingview=export_tradingview,
            fast_mode=fast_mode,
            benchmark=benchmark
        )

    @mcp.tool()
    def update_backtest_draft(backtest_id: str, state: str) -> dict:
        """
        Update an existing backtest draft configuration with complete state object.

        Replaces the entire state of an existing backtest session with new configuration.
        This is the primary method for modifying backtest parameters after creation.
        For complex modifications (adding routes, changing dates, etc.), first retrieve
        the current state with get_backtest_session(), perform your modifications,
        then update with the complete merged state.

        Parameters:
            backtest_id (str): UUID string of the backtest session to update
                Shape: UUID format string (e.g., "550e8400-e29b-41d4-a716-446655440000")
            state (str): JSON string containing complete state object with 'form' and 'results' sections.
                The state object must contain:
                - form: Configuration object with exchange, routes, dates, export options
                - results: Results object with showResults and executing flags
                Shape: JSON string representing {"form": {...}, "results": {...}}

        Returns:
            dict: Update confirmation containing:
                - success: Boolean indicating successful update
                - message: Status message string
                - backtest_id: The updated session ID (same as input)
                Shape: {"success": bool, "message": "string", "backtest_id": "uuid-string"}

        Raises:
            NotFoundError: If backtest_id does not exist
            ValidationError: If state JSON is malformed or invalid
            DatabaseError: If update fails in the database

        Workflow:
            1. Retrieve current state: session = get_backtest_session(backtest_id)
            2. Extract state object: current_state = session["data"]["session"]["state"]["state"]
            3. Modify the state object as needed (add routes, change dates, etc.)
            4. Convert modified state back to JSON string
            5. Call update_backtest_draft(backtest_id, json_string)

        Example:
            >>> # Add a new route to existing session
            >>> session = get_backtest_session("550e8400-e29b-41d4-a716-446655440000")
            >>> current_state = session["data"]["session"]["state"]["state"]
            >>> new_route = {"exchange": "Binance Spot", "strategy": "MyStrategy", "symbol": "ETH-USDT", "timeframe": "1h"}
            >>> current_state["form"]["routes"].append(new_route)
            >>> import json
            >>> updated_state = json.dumps(current_state)
            >>> result = update_backtest_draft("550e8400-e29b-41d4-a716-446655440000", updated_state)
        """
        return update_backtest_draft_service(backtest_id, state)

    @mcp.tool()
    def get_backtest_session(session_id: str) -> dict:
        """
        Retrieve detailed information about a specific backtest session by ID.

        Fetches complete session data from the database including configuration,
        execution status, performance metrics, trade history, and results.
        This is the primary method for inspecting backtest state and results.

        Parameters:
            session_id (str): UUID string of the backtest session to retrieve
                Shape: UUID format string (e.g., "550e8400-e29b-41d4-a716-446655440000")

        Returns:
            dict: Structured response with consistent format:

            Success Response:
            {
                "data": {
                    "session": {
                        "id": "uuid-string",
                        "state": {
                            "form": {
                                "exchange": "string",
                                "routes": [...],
                                "start_date": "YYYY-MM-DD",
                                "finish_date": "YYYY-MM-DD",
                                ...
                            },
                            "results": {
                                "showResults": bool,
                                "executing": bool,
                                ...
                            }
                        },
                        "metrics": {
                            "total_trades": int,
                            "winning_trades": int,
                            "losing_trades": int,
                            "net_profit": float,
                            "max_drawdown": float,
                            "sharpe_ratio": float,
                            ...
                        },
                        "trades": [
                            {
                                "id": int,
                                "type": "long|short",
                                "entry_price": float,
                                "exit_price": float,
                                "profit": float,
                                "entry_time": "datetime",
                                "exit_time": "datetime",
                                ...
                            }
                        ],
                        ...
                    }
                },
                "error": null,
                "message": "Backtest session retrieved successfully"
            }

            Error Response:
            {
                "data": null,
                "error": "error_description_string",
                "message": "error_description_string"
            }

            Shape: {"data": object|null, "error": string|null, "message": string}

        Raises:
            NotFoundError: If session_id does not exist (returns error in response dict)
            DatabaseError: If database query fails (returns error in response dict)

        Note:
            This function always returns a dict with 'data', 'error', and 'message' keys.
            Check if 'error' is None to determine success/failure.

        Example:
            >>> session = get_backtest_session("550e8400-e29b-41d4-a716-446655440000")
            >>> if session["error"] is None:
            ...     metrics = session["data"]["session"]["metrics"]
            ...     trades = session["data"]["session"]["trades"]
            ...     print(f"Total trades: {metrics['total_trades']}")
            ... else:
            ...     print(f"Error: {session['error']}")
        """
        result = get_backtest_session_service(session_id)

        # Ensure consistent return structure
        if result.get('error') is None:
            # Success case
            return {
                'data': result.get('data', {}),
                'error': None,
                'message': result.get('message', 'Session retrieved successfully')
            }
        else:
            # Error case
            return {
                'data': None,
                'error': result.get('error'),
                'message': result.get('message', result.get('error', 'Unknown error'))
            }

    @mcp.tool()
    def get_backtest_sessions(
        limit: int = 50,
        offset: int = 0,
        title_search: str = None,
        status_filter: str = None,
        date_filter: str = None
    ) -> dict:
        """
        Retrieve a paginated list of backtest sessions with optional filtering.

        Fetches multiple backtest sessions from the database with support for
        pagination and filtering by various criteria. Sessions are sorted by
        most recently updated first.

        Parameters:
            limit (int): Maximum number of sessions to return per page
                Range: 1-1000, Default: 50
                Shape: Positive integer
            offset (int): Number of sessions to skip for pagination (zero-based)
                Default: 0
                Shape: Non-negative integer
            title_search (str, optional): Text search filter for session titles
                Performs case-insensitive substring matching
                Shape: String or None
            status_filter (str, optional): Filter sessions by execution status
                Valid values: "finished", "running", "cancelled", "pending", "failed"
                Shape: String or None
            date_filter (str, optional): Filter sessions by creation/update date
                Valid values: "today", "this_week", "this_month", "this_year"
                Shape: String or None

        Returns:
            dict: Paginated session list with metadata:
            {
                "sessions": [
                    {
                        "id": "uuid-string",
                        "title": "string",
                        "status": "finished|running|cancelled|pending|failed",
                        "created_at": "datetime-string",
                        "updated_at": "datetime-string",
                        "exchange": "string",
                        "start_date": "YYYY-MM-DD",
                        "finish_date": "YYYY-MM-DD",
                        "total_trades": int,
                        "net_profit": float,
                        ...
                    }
                ],
                "total_count": int,  # Total sessions matching filters
                "limit": int,        # Requested limit
                "offset": int,       # Requested offset
                "has_more": bool     # True if more pages available
            }

            Shape: {
                "sessions": array[object],
                "total_count": int,
                "limit": int,
                "offset": int,
                "has_more": bool
            }

        Raises:
            ValidationError: If limit/offset parameters are out of valid range
            DatabaseError: If database query fails

        Pagination Notes:
            - Use offset + limit for next page (e.g., offset=50 for page 2 with limit=50)
            - Check 'has_more' to determine if additional pages exist
            - Maximum limit is 1000 to prevent excessive data transfer

        Example:
            >>> # Get first 20 finished sessions
            >>> result = get_backtest_sessions(limit=20, status_filter="finished")
            >>> sessions = result["sessions"]
            >>> print(f"Found {len(sessions)} finished sessions")

            >>> # Search for sessions with "BTC" in title
            >>> btc_sessions = get_backtest_sessions(title_search="BTC", limit=10)
            >>> print(f"BTC sessions: {len(btc_sessions['sessions'])}")
        """
        return get_backtest_sessions_service(
            limit=limit,
            offset=offset,
            title_search=title_search,
            status_filter=status_filter,
            date_filter=date_filter
        )

    @mcp.tool()
    def run_backtest(session_id: str, timeout_seconds: int = 24 * 60 * 60) -> dict:
        """
        Execute a backtest using stored session configuration and monitor completion.

        Executes a backtest session that was previously created with create_backtest_draft().
        The function monitors progress via WebSocket events (same as the dashboard) and
        returns completion status with results or error details.

        Uses WebSocket events exclusively for real-time monitoring, providing the same
        information and behavior as the dashboard interface. Jesse signals backtest
        completion by sending the 'backtest.equity_curve' event. Compressed equity_curve
        and trades data is automatically decompressed before returning.

        Parameters:
            session_id (str): UUID string of the backtest session to execute
                Shape: UUID format string (e.g., "550e8400-e29b-41d4-a716-446655440000")
            timeout_seconds (int): Maximum time to wait for completion in seconds
                Range: 60-604800 (1 minute to 7 days)
                Default: 86400 (24 hours)
                Shape: Positive integer

        Returns:
            dict: Execution result with status:

            Success Response:
            {
                "status": "success",
                "backtest_id": "uuid-string",
                "message": "Backtest completed successfully",
                "metrics": {
                    "total_trades": int,
                    "winning_trades": int,
                    "losing_trades": int,
                    "net_profit": float,
                    "net_profit_percentage": float,
                    "max_drawdown": float,
                    "max_drawdown_percentage": float,
                    "sharpe_ratio": float,
                    "sortino_ratio": float,
                    "calmar_ratio": float,
                    "win_rate": float,
                    "profit_factor": float,
                    "expectancy": float,
                    "expectancy_percentage": float,
                    "avg_win": float,
                    "avg_loss": float,
                    "largest_win": float,
                    "largest_loss": float,
                    "avg_holding_period": int,
                    "total_fees": float,
                    "total_volume": float,
                    "starting_balance": float,
                    "finishing_balance": float
                },
                "equity_curve": [
                    {
                        "timestamp": int,  // Unix timestamp
                        "balance": float   // Portfolio balance at this point
                    },
                    ...
                ],
                "trades": [
                    {
                        "id": str,
                        "symbol": str,          // e.g., "BTC-USDT"
                        "type": "long|short",
                        "entry_timestamp": int,
                        "exit_timestamp": int,
                        "entry_price": float,
                        "exit_price": float,
                        "qty": float,
                        "fee": float,
                        "pnl": float,          // Profit/Loss in base currency
                        "pnl_percentage": float
                    },
                    ...
                ]
            }

            Error Response:
            {
                "status": "error",
                "backtest_id": "uuid-string",
                "message": "Backtest failed",
                "error_details": {
                    "error": "CandlesNotFound: {'message': 'No candles found for BTC-USDT on Binance Spot between 2023-12-22 and 2023-12-31.', 'symbol': 'BTC-USDT', 'exchange': 'Binance Spot', 'start_date': '2024-01-01', 'type': 'missing_candles'}",
                    "traceback": "Traceback (most recent call last):\\n  File \"/home/king/jesse/jesse-ai/jesse/jesse/modes/backtest_mode.py\", line 142, in _execute_backtest\\n    _handle_sync_no_candles(e, start_date, exchange)\\n  [... full traceback ...]\\n  raise exceptions.CandlesNotFound({...})\\njesse.exceptions.CandlesNotFound: {'message': 'No candles found...', 'type': 'missing_candles'}"
                }
            }

            Cancelled Response:
            {
                "status": "cancelled",
                "backtest_id": "uuid-string",
                "message": "Backtest was cancelled"
            }

            Shape: {
                "status": "success|error|cancelled|unknown",
                "backtest_id": string,
                "message": string,
                "metrics": object|undefined,
                "equity_curve": array|undefined,
                "trades": array|undefined,
                "error_details": object|undefined
            }

        Raises:
            NotFoundError: If session_id does not exist
            ValidationError: If session configuration is invalid
            TimeoutError: If execution exceeds timeout_seconds
            DatabaseError: If configuration loading fails

        Workflow:
            1. create_backtest_draft() → creates session with configuration
            2. run_backtest(session_id) → executes and monitors via WebSocket
            3. Function returns completion status with results or error details

        Monitoring:
            - Uses WebSocket events for real-time completion detection
            - Same event-driven approach as the dashboard
            - Provides immediate error details for intelligent agent responses

        Example:
            >>> # Execute backtest and wait for completion
            >>> result = run_backtest("550e8400-e29b-41d4-a716-446655440000")
            >>> if result["status"] == "success":
            ...     print(f"Profit: ${result['metrics']['net_profit']:.2f}")
            ...     print(f"Win Rate: {result['metrics']['win_rate']:.1%}")
            ...     print(f"Total trades: {len(result['trades'])}")
            ...     print(f"Equity curve points: {len(result['equity_curve'])}")
            ...     # Access first trade
            ...     if result['trades']:
            ...         first_trade = result['trades'][0]
            ...         print(f"First trade P&L: ${first_trade['pnl']:.2f}")
            >>> elif result["status"] == "error":
            ...     error_details = result.get("error_details", {})
            ...     if "missing_candles" in error_details.get("error", ""):
            ...         print("Missing candles - importing data...")
            ...         # Agent can automatically call import_candles()
            ...     else:
            ...         print(f"Other error: {error_details.get('error', 'Unknown error')}")
            ...     else:
            ...         print(f"Backtest failed: {result['message']}")
            >>> elif result["status"] == "cancelled":
            ...     print("Backtest was cancelled")

            >>> # With custom timeout (2 hours)
            >>> result = run_backtest("550e8400-e29b-41d4-a716-446655440000", timeout_seconds=7200)
        """
        return run_backtest_service(session_id, timeout_seconds)

    @mcp.tool()
    def cancel_backtest(session_id: str) -> dict:
        """
        Cancel a currently running backtest process.

        Terminates an executing backtest session using the same endpoint as the dashboard.
        The backtest process is immediately stopped and the session status is updated
        to 'cancelled' in the database. Any partial results are preserved.

        Parameters:
            session_id (str): UUID string of the running backtest session to cancel
                Shape: UUID format string (e.g., "550e8400-e29b-41d4-a716-446655440000")

        Returns:
            dict: Cancellation result with status update:

            Success Response:
            {
                "success": true,
                "message": "Backtest cancelled successfully",
                "session_id": "uuid-string",
                "status": "cancelled",
                "cancelled_at": "datetime-string"
            }

            Error Response:
            {
                "success": false,
                "message": "Error description (e.g., session not found, not running)",
                "session_id": "uuid-string",
                "error": "detailed_error_message"
            }

            Shape: {
                "success": bool,
                "message": string,
                "session_id": string,
                "status": string|undefined,
                "cancelled_at": string|undefined,
                "error": string|undefined
            }

        Raises:
            NotFoundError: If session_id does not exist
            InvalidStateError: If session is not currently running
            DatabaseError: If cancellation update fails

        Behavior:
            - Only affects sessions with status "running"
            - Session status changes to "cancelled"
            - Partial results (if any) remain accessible via get_backtest_session()
            - No new trades or metrics are generated after cancellation
            - Process termination is immediate

        Example:
            >>> # Cancel a running backtest
            >>> result = cancel_backtest("550e8400-e29b-41d4-a716-446655440000")
            >>> if result["success"]:
            ...     print("Backtest cancelled successfully")
            ... else:
            ...     print(f"Cancellation failed: {result['message']}")

        Note:
            Cancellation is irreversible. Cancelled sessions cannot be resumed.
        """
        return cancel_backtest_service(session_id)

    @mcp.tool()
    def purge_backtest_sessions(days_old: int = None) -> dict:
        """
        Permanently delete old backtest sessions from the database.

        Removes backtest sessions using the same endpoint as the dashboard.
        Supports selective deletion by age or complete database cleanup.
        This operation is irreversible - deleted sessions cannot be recovered.

        Parameters:
            days_old (int, optional): Age threshold in days for selective deletion
                - If specified: Only sessions older than this many days are deleted
                - If None (default): All sessions in database are deleted
                Range: 1-3650 (1 day to 10 years)
                Shape: Positive integer or None

        Returns:
            dict: Deletion result with operation summary:

            Success Response:
            {
                "success": true,
                "message": "Successfully purged X backtest sessions",
                "deleted_count": int,      # Number of sessions deleted
                "days_old": int|null,      # Age filter used (null means all deleted)
                "deleted_sessions": [      # List of deleted session IDs
                    "uuid-string-1",
                    "uuid-string-2",
                    ...
                ]
            }

            Error Response:
            {
                "success": false,
                "message": "Error description",
                "error": "detailed_error_message",
                "deleted_count": 0
            }

            Shape: {
                "success": bool,
                "message": string,
                "deleted_count": int,
                "days_old": int|null,
                "deleted_sessions": array[string]|undefined,
                "error": string|undefined
            }

        Raises:
            ValidationError: If days_old is outside valid range
            DatabaseError: If deletion operation fails
            PermissionError: If user lacks deletion privileges

        Behavior:
            - Deletes sessions completely from database
            - Associated data (metrics, trades, configurations) also removed
            - No backup created - operation is permanent
            - Affects all sessions matching age criteria (or all if days_old=None)

        Safety Notes:
            - Use with caution - no undo capability
            - Consider exporting important results before purging
            - Test with small days_old values first
            - Regular purging helps maintain database performance

        Example:
            >>> # Delete sessions older than 30 days
            >>> result = purge_backtest_sessions(days_old=30)
            >>> print(f"Deleted {result['deleted_count']} old sessions")

            >>> # Delete ALL sessions (use with extreme caution)
            >>> result = purge_backtest_sessions()
            >>> print(f"Database cleared: {result['deleted_count']} sessions removed")

        Recommendation:
            Schedule regular purging (e.g., monthly) to maintain database performance
            while preserving recent results for analysis and comparison.
        """
        return purge_backtest_sessions_service(days_old)
