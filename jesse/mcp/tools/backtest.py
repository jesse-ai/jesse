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
        Create a new backtest draft with specified configuration.

        This creates a new backtest session with the provided parameters.
        Use update_backtest_draft for modifying existing sessions.

        Args:
            exchange: Exchange name (default: "Binance Perpetual Futures")
            routes: JSON string array of route objects
            data_routes: JSON string array of data route objects
            start_date: Start date in YYYY-MM-DD format
            finish_date: Finish date in YYYY-MM-DD format
            debug_mode: Enable debug mode logging
            export_csv: Export results as CSV
            export_json: Export results as JSON
            export_chart: Export chart data
            export_tradingview: Export TradingView pine script
            fast_mode: Enable fast mode
            benchmark: Run benchmark comparison

        Returns:
            Success confirmation with new session ID
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
        Update an existing backtest draft configuration with complete state.

        This replaces the entire state of an existing backtest session. For complex updates
        (like adding routes), use get_backtest_session first to retrieve current state,
        perform merging logic, then call this function with the complete new state.

        Args:
            backtest_id: ID of the backtest session to update (required)
            state: JSON string with complete state object containing 'form' and 'results'.
                Should match dashboard state format with complete data.

        Returns:
            Success confirmation with updated configuration
        """
        return update_backtest_draft_service(backtest_id, state)

    @mcp.tool()
    def get_backtest_session(session_id: str) -> dict:
        """
        Get details of a specific backtest session by ID.

        This retrieves a backtest session from the database, including its
        status, configuration, metrics, trades, and other details.

        Args:
            session_id: ID of the backtest session to retrieve

        Returns:
            Backtest session details including status, metrics, trades, etc.
        """
        return get_backtest_session_service(session_id)

    @mcp.tool()
    def get_backtest_sessions(
        limit: int = 50,
        offset: int = 0,
        title_search: str = None,
        status_filter: str = None,
        date_filter: str = None
    ) -> dict:
        """
        List backtest sessions with optional filters and pagination.

        This retrieves a list of backtest sessions from the database, sorted by
        most recently updated.

        Args:
            limit: Maximum number of sessions to return (default: 50)
            offset: Number of sessions to skip for pagination (default: 0)
            title_search: Optional text to search in session titles
            status_filter: Optional status filter (e.g., "finished", "running", "cancelled")
            date_filter: Optional date filter (e.g., "today", "this_week", "this_month")

        Returns:
            List of backtest sessions with their details
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
        Execute a backtest using a stored session configuration and monitor progress.

        This fetches the backtest form data from a session (created via
        create_backtest_draft or the dashboard), loads the current backtest
        config from the database, merges them, and runs the backtest.

        The function blocks and monitors progress via WebSocket events until
        the backtest completes with success or failure status.

        Workflow:
        1. use dashboard or create_backtest_draft() → creates session with form data, returns session_id
        2. (optional) use dashboard or update_backtest_draft() → modify the form data
        3. run_backtest(session_id) → automatically loads current config and runs backtest
        4. Monitor progress via WebSocket events until completion

        Args:
            session_id: ID of the backtest session to run
            timeout_seconds: Maximum time to wait for backtest completion (default: 86400 = 24 * 60 * 60 = 24 hours)

        Returns:
            Success message with results or error details
        """
        return run_backtest_service(session_id, timeout_seconds)

    @mcp.tool()
    def cancel_backtest(session_id: str) -> dict:
        """
        Cancel a running backtest process.

        This cancels a backtest using the same endpoint that the dashboard uses.
        The backtest process will be terminated and its status will be updated
        to 'cancelled' in the database.

        Args:
            session_id: ID of the backtest session to cancel

        Returns:
            Success message or error details
        """
        return cancel_backtest_service(session_id)

    @mcp.tool()
    def purge_backtest_sessions(days_old: int = None) -> dict:
        """
        Purge old backtest sessions from the database.

        This deletes backtest sessions using the same endpoint that the dashboard uses.
        If days_old is specified, only sessions older than that many days will be deleted.
        If days_old is None or not specified, all sessions will be deleted.

        Args:
            days_old: Optional number of days. Only sessions older than this will be deleted.
                     If None, all sessions will be purged.

        Returns:
            Number of deleted sessions and success/error message
        """
        return purge_backtest_sessions_service(days_old)
