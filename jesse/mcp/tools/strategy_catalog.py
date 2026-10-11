"""
Jesse Strategy Catalog Tools

MCP tools for the jesse.trade strategy catalog, the community strategies the dashboard's
Strategies page lists. They are online strategies, separate from the strategies installed in
the Jesse project (those use create_strategy / read_strategy / write_strategy):

- browse_strategy_catalog: Rank, search, filter, and page through catalog strategies
- get_catalog_strategy_metrics: Backtest metrics of one catalog strategy for another
  symbol, timeframe, or period
- import_catalog_strategy: Copy one catalog strategy into the project as a local strategy

All tools require authentication via Jesse admin password. Signing in to jesse.trade uses the
project's LICENSE_API_TOKEN inside Jesse; no token is ever returned by these tools.

The tools are async and run their API calls in a worker thread (see offload.py).
"""

from typing import Optional

from jesse.mcp.tools.offload import run_blocking
from jesse.mcp.tools.services.locks import STRATEGY_FILES_LOCK, serialized
from jesse.mcp.tools.services.strategy_catalog import (
    DEFAULT_PAGE_SIZE,
    DEFAULT_SORT,
    browse_strategy_catalog_service,
    get_catalog_strategy_metrics_service,
    import_catalog_strategy_service,
)

# Imports create strategies/<local_name>, so they never overlap this worker's other
# strategy creation (see services/locks.py).
_import_catalog_strategy = serialized(STRATEGY_FILES_LOCK, import_catalog_strategy_service)


def register_strategy_catalog_tools(mcp):
    """Register the jesse.trade strategy catalog tools with the MCP server."""

    @mcp.tool()
    async def browse_strategy_catalog(
            period: Optional[str] = None,
            sort_by: str = DEFAULT_SORT,
            submitted_after: Optional[str] = None,
            submitted_before: Optional[str] = None,
            query: Optional[str] = None,
            strategy_type: Optional[str] = None,
            offset: int = 0,
            limit: int = DEFAULT_PAGE_SIZE,
    ) -> dict:
        """
        Browse the jesse.trade strategy catalog: community strategies published online, ranked
        by their backtest results. These are NOT the strategies installed in this Jesse project;
        a catalog strategy only becomes local after import_catalog_strategy.

        Workflow: browse (and page) here -> compare candidates, optionally with
        get_catalog_strategy_metrics on other symbols/timeframes/periods -> confirm the choice
        with the user -> import_catalog_strategy(slug) -> read_strategy(local_name) and backtest.

        Only approved strategies with completed metrics for the chosen period are listed, the
        same list the dashboard's Strategies page shows.

        Parameters (sent to jesse.trade, like the dashboard):
            period (str, optional): Trading period the ranking metrics cover, exactly as listed in
                the response's available_filters.periods, e.g. "Q1 of 2026" or "2024 - 2025".
                Omit to use available_filters.default_period, the dashboard's default.
            sort_by (str): "Sharpe Ratio" (default), "PNL", "Sortino Ratio", "Calmar Ratio",
                or "Win Rate". Always ranked best first.
            submitted_after / submitted_before (str, optional): Submission date bounds in
                YYYY-MM-DD. jesse.trade compares them with the submission time at 00:00 UTC of
                that date, so submitted_before excludes strategies submitted on that day.

        Parameters (applied by this tool to the ranked list, which jesse.trade returns whole):
            query (str, optional): Case-insensitive text matched against name, description,
                author username, and slug. Keeps the ranking order.
            strategy_type (str, optional): "free" or "premium".
            offset (int): Matches to skip, default 0. Use pagination.next_offset for the next page.
            limit (int): Page size, 1-25, default 10.

        Returns:
            dict: On success:
            {
                "status": "success",
                "source": "jesse.trade strategy catalog: ...",
                "message": "Showing 1-10 of 42 matching catalog strategies for Q1 of 2026.",
                "filters": {"period": ..., "sort_by": ..., "submitted_after": ..., "submitted_before": ...,
                            "query": ..., "strategy_type": ...},
                "available_filters": {"periods": [...], "default_period": "Q1 of 2026",
                                      "sort_by": [...], "strategy_type": ["free", "premium"]},
                "pagination": {"offset": 0, "limit": 10, "returned": 10, "total_matches": 42,
                               "total_ranked_in_period": 57, "has_more": true, "next_offset": 10},
                "jesse_trade_signed_in": true,
                "jesse_trade_auth": null,
                "strategies": [{
                    "slug": "trend-rider",            # the id import_catalog_strategy needs
                    "name": "Trend Rider",            # display name, not the local strategy name
                    "type": "free",
                    "author": "someone",
                    "description": "...",
                    "code_available": true,           # false = this account cannot import it
                    "submitted_at": "...",
                    "views": 120,
                    "default_symbol": "BTC-USDT", "default_timeframe": "4h",
                    "backtest_symbols": [...], "backtest_timeframes": [...],
                    "metrics": {"exchange", "symbol", "timeframe", "starting_date", "finishing_date",
                                "net_profit_percentage", "annual_return", "max_drawdown",
                                "sharpe_ratio", "sortino_ratio", "calmar_ratio", "win_rate",
                                "total_completed_trades"}  # for default_symbol/timeframe in period
                }]
            }

            When jesse.trade sign-in is unavailable, browsing still succeeds (as on the
            dashboard) with jesse_trade_signed_in false, every code_available false, and
            jesse_trade_auth = {"error_type": "license_token_missing" | "license_token_rejected"
            | "jesse_trade_unavailable", "message": ...}. Tell the user; imports need it fixed.

            An empty "strategies" list with status "success" means the catalog really has no
            match; "message" says whether the period or the query/strategy_type filters caused it.

            Errors: {"status": "error", "error_type": ..., "message": ...} with error_type
            "invalid_request" (bad argument), "invalid_period" (includes available_periods),
            "authentication_failed", "connection_error", "jesse_trade_unavailable",
            "jesse_trade_error", or "unexpected_response". Never present an error as an
            empty catalog.
        """
        return await run_blocking(
            browse_strategy_catalog_service,
            period, sort_by, submitted_after, submitted_before, query, strategy_type, offset, limit,
        )

    @mcp.tool()
    async def get_catalog_strategy_metrics(slug: str, period: str, symbol: str, timeframe: str) -> dict:
        """
        Get jesse.trade's backtest metrics for one catalog strategy on a specific symbol,
        timeframe, and period, to check how a candidate holds up beyond the default combination
        shown by browse_strategy_catalog. Read-only; it imports nothing.

        Parameters:
            slug (str): Catalog slug from browse_strategy_catalog, e.g. "trend-rider".
            period (str): A value from browse_strategy_catalog's available_filters.periods.
            symbol (str): One of the strategy's backtest_symbols, e.g. "ETH-USDT".
            timeframe (str): One of the strategy's backtest_timeframes, e.g. "1h".

        Returns:
            dict: {"status": "success", "slug", "period", "symbol", "timeframe", "metrics": {...}}
            where metrics holds jesse.trade's full metric set (net_profit_percentage,
            max_drawdown, sharpe_ratio, win_rate, total_completed_trades, expectancy, ...,
            "status") without the equity curve.

            Errors: error_type "not_found" when the slug is unknown or jesse.trade has no
            metrics for that combination, "invalid_request" for a malformed argument (symbols
            must look like "BTC-USDT"), or "authentication_failed", "connection_error",
            "jesse_trade_unavailable", "jesse_trade_error".
        """
        return await run_blocking(get_catalog_strategy_metrics_service, slug, period, symbol, timeframe)

    @mcp.tool()
    async def import_catalog_strategy(slug: str) -> dict:
        """
        Import one jesse.trade catalog strategy into this Jesse project as a local strategy,
        exactly like the dashboard's "Import Strategy" button. Only import a strategy the user
        chose or approved.

        Jesse downloads the code with the project's LICENSE_API_TOKEN and saves it on the
        machine running Jesse at strategies/<local_name>/__init__.py. The local name is the
        class name in the downloaded code, which usually differs from the catalog display name,
        so always continue with the returned local_name. An existing local strategy is never
        overwritten.

        Parameters:
            slug (str): Catalog slug from browse_strategy_catalog, e.g. "trend-rider".
                Import only strategies whose code_available is true; otherwise the account
                cannot access the code.

        Returns:
            dict: On success:
            {
                "status": "success",
                "action": "catalog_strategy_imported",
                "slug": "trend-rider",
                "local_name": "TrendRider",   # use with read_strategy, write_strategy, backtests
                "path": "strategies/TrendRider",
                "dashboard_url": "http://localhost:9000/#/strategies/TrendRider",
                "message": "..."
            }

            Errors: {"status": "error", "error_type": ..., "message": ..., "slug": ...}
            - "strategy_exists": a local strategy named local_name already exists; nothing
              changed. Ask the user whether to use the existing one or rename/delete it first.
            - "strategy_access_denied": premium strategy without an active Premium plan.
            - "license_token_missing" / "license_token_rejected": the project has no valid
              LICENSE_API_TOKEN; relay the message's setup steps to the user.
            - "catalog_strategy_not_found", "invalid_request" (bad slug, or code without a
              Python class), "authentication_failed", "connection_error",
              "jesse_trade_unavailable", "jesse_trade_error".
            Do not retry auth, access, or exists errors unchanged; they need the user.
        """
        return await run_blocking(_import_catalog_strategy, slug)
