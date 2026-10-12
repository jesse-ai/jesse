"""
Jesse Session Results Tools

Read-only, bounded access to stored results of backtests, optimizations, Monte Carlo runs,
rule significance tests, and live/paper sessions:
- get_session_results: a compact summary, or one page of a result section
- get_live_sessions: the live/paper session list (the other kinds have their own list tools)
- get_live_trades / get_live_orders: Jesse's recorded live/paper trades and orders of a date
  window across sessions (for example "my trades of the last 7 days")

Details and the snapshot format used by temporary analysis: jesse://session_analysis.

The tools are async and run their API call in a worker thread (see offload.py), so parsing a
large stored session does not stall other MCP requests on this worker.
"""
from typing import Annotated, Any, Optional

from pydantic import WithJsonSchema

from .offload import run_blocking
from .strict_arguments import keep_raw_argument_values, refuse_unknown_arguments
from .services import (
    get_live_orders_service,
    get_live_sessions_service,
    get_live_trades_service,
    get_session_results_service,
)

# The history tools take every argument as Any with the schema they advertise. FastMCP's pydantic
# validation would otherwise coerce (true -> 1, 7.9 -> 7, "5" -> 5) and its errors quote the given
# value; the arguments reach the Jesse API unchanged instead, which validates them strictly with
# messages that never repeat a value. The advertised types, enums, and defaults stay useful.
_OptionalText = Annotated[Any, WithJsonSchema({'anyOf': [{'type': 'string'}, {'type': 'null'}]})]
_RecentDays = Annotated[Any, WithJsonSchema({'anyOf': [{'type': 'integer', 'minimum': 1, 'maximum': 366},
                                                       {'type': 'null'}]})]
_Mode = Annotated[Any, WithJsonSchema({'type': 'string', 'enum': ['live', 'paper', 'all']})]
_Order = Annotated[Any, WithJsonSchema({'type': 'string', 'enum': ['newest_first', 'oldest_first']})]
_Limit = Annotated[Any, WithJsonSchema({'type': 'integer', 'minimum': 1, 'maximum': 500})]
_TimeField = Annotated[Any, WithJsonSchema({'type': 'string', 'enum': ['created_at', 'executed_at']})]
_Status = Annotated[Any, WithJsonSchema({'anyOf': [
    {'type': 'string', 'enum': ['ACTIVE', 'CANCELED', 'EXECUTED', 'PARTIALLY FILLED', 'QUEUED', 'LIQUIDATED',
                                'REJECTED']},
    {'type': 'null'},
]})]

_HISTORY_COMMON = """
        What this is: Jesse's own records of its live/paper sessions, across all sessions (or
        one). It is NOT the exchange account's history: trades or orders made outside Jesse, or
        while no session ran, are not here, and nothing contacts the exchange. Read-only.

        Window (UTC, start inclusive, end exclusive), one of:
            - nothing: the last 7 days up to now;
            - recent_days (1-366): the last N days up to now;
            - start (+ optional end): RFC 3339 date-times WITH an offset, e.g.
              "2026-09-21T00:00:00Z" or "2026-09-21T03:00:00+03:00" (end defaults to now).
        The response's "range" holds the exact bounds used ("start"/"end" and *_ms); a relative
        window is resolved once.

        Filters: mode "live" (default: real-money sessions only), "paper", or "all" (never
        mix paper results into real performance unless the user asks); exchange and symbol
        exactly as stored (e.g. "Bybit USDT Perpetual", "BTC-USDT"); session_id (UUID from
        get_live_sessions; a session of the other mode is refused with "mode_mismatch").
        Filters are applied before counting and paging.

        Paging: limit 1-500 (default 100); a page also stops before 128 KiB
        ("truncated_by_size") and, for trades, before loading more than 20,000 executed orders
        ("truncated_by_orders"). order "newest_first" (default) or "oldest_first", ties broken
        by record id. For the next page, call the tool again with exactly the arguments in
        "next_page" (it repeats the window, mode, filters, order, and limit, plus a cursor);
        a cursor used with other arguments is refused ("invalid_cursor"). Each page is one
        consistent database view; records changed between calls can still appear or
        disappear, so for one coherent dataset use run_analysis. "total" counts every
        matching record at this page's view; "all_records_returned" is true only when this
        first page holds all of them. Never compute totals, win rates, or other statistics
        from a partial page: use run_analysis with a {"dataset": ...} input built from the
        returned "range" and every non-null "filters" entry except "session_modes", which gives
        your code the complete selection on the Jesse host in its own database view.

        Each record carries session_id; "sessions" describes the sessions on this page (title,
        mode, exchange, status; {"exists": false} for a deleted one). To link a session for the
        user, replace {session_id} in "session_dashboard_url_template" with its ID ("" when
        no dashboard URL is known; a deleted session has no page). "is_active" and a
        stopped status for a session left marked running come from Jesse's worker registry at
        that moment, best effort, not from the page's database view. Saved key and
        notification credential values are redacted per record's session (every saved key's
        values for records of deleted sessions or sessions without a readable form); a failed
        key lookup or an unreadable session state returns an error, never unredacted data.
        Needs the live trading plugin ("live_plugin_unavailable").
"""


def register_session_results_tools(mcp):
    """
    Register the session results tools.

    Args:
        mcp: The MCP server instance.
    """

    @mcp.tool()
    async def get_session_results(session_type: str, session_id: str, section: str = "summary",
                            offset: int = 0, limit: int = 50) -> dict:
        """
        Read the stored results of a session in bounded pieces. Read-only: never starts,
        stops, or changes a session.

        Start with section "summary" (status, form, metrics, errors, and what each section
        holds), then page through a section only for the rows you need. For comparisons,
        statistics over many rows, or charts, use run_analysis instead of paging everything:
        it gives your code the complete data on the Jesse host.

        Parameters:
            session_type (str): "backtest", "optimization", "monte_carlo",
                "significance_test", or "live" (live and paper trading sessions).
            session_id (str): The session UUID (from the list tools or the run tools).
            section (str): "summary" (default) or, per type:
                backtest: "trades", "equity_curve", "hyperparameters", "logs"
                optimization: "best_trials" (best first, with training/testing metrics),
                    "objective_curve", "logs"
                monte_carlo: "confidence_analysis", "scenario_metrics" (original + each
                    scenario), "equity_curves" (Portfolio curve per scenario), "logs"
                significance_test: summary only
                live: "closed_trades", "orders", "equity_curve" (minute snapshots),
                    "logs" (info), "error_logs"
            offset (int): Items to skip. For logs it counts back from the newest line.
            limit (int): 1-500 items per page, default 50. Pages also stop at 128 KiB of
                JSON; continue from `next_offset`. For equity curves, items are points of
                each series.

        Returns:
            dict: For "summary", a session-type-specific object with "session_type",
            "session_id", "session_status", "status_note" (for unfinished runs), "title", "form",
            results, "error" (exception + traceback tail) and "sections"/"counts". For other
            sections: {"section", "items", "offset", "limit", "returned", "total",
            "next_offset", "has_more", "truncated_by_size"}. Every successful response, summary
            or section, also has "dashboard_url": the session's page on the dashboard. Give the
            user that link, not the bare session ID. Values are exactly as stored;
            NaN/infinite numbers are null. Errors: {"status": "error", "error_type", "message"}
            with error_type "not_found", "invalid_request", "item_too_large" (use
            run_analysis), "offset_too_large", "live_plugin_unavailable" (live sessions need
            the live trading plugin), "read_failed", "authentication_failed", or
            "connection_error".

        Live sessions: exact occurrences of the saved API key, secret, extra fields (such as
        a passphrase), and notification credential values (6+ characters) of the keys the
        session uses are replaced with "[redacted]". Other text a strategy logged is
        returned as stored.
        """
        return await run_blocking(get_session_results_service, session_type, session_id, section, offset, limit)

    @mcp.tool()
    async def get_live_sessions(limit: int = 20, offset: int = 0, status_filter: Optional[str] = None,
                          mode_filter: Optional[str] = None, title_search: Optional[str] = None) -> dict:
        """
        List live and paper trading sessions, most recently updated first (drafts excluded),
        without their bulky state. Read-only. Requires the live trading plugin.

        Parameters:
            limit (int): 1-100, default 20.
            offset (int): Sessions to skip; continue from `next_offset`.
            status_filter (str, optional): e.g. "running" or "stopped".
            mode_filter (str, optional): "livetrade" or "papertrade".
            title_search (str, optional): Case-insensitive title filter.

        Returns:
            dict: {"status": "success", "sessions": [{"id", "title", "status", "is_active",
            "session_mode", "exchange", "routes", "created_at", "updated_at", "finished_at",
            "has_error", "dashboard_url"}], "next_offset"} or an error with error_type
            "live_plugin_unavailable" or "invalid_request". "dashboard_url" opens that session
            on the dashboard: when the user asks for a session or its link, answer with it, not
            with the bare ID. Read one with get_session_results(session_type="live",
            session_id=...).
        """
        return await run_blocking(get_live_sessions_service, limit, offset, status_filter, mode_filter, title_search)

    # The two history tools share most of their description, so their docstrings are assembled
    # before registration (FastMCP reads the description when the tool is registered).
    async def get_live_trades(start: _OptionalText = None, end: _OptionalText = None, recent_days: _RecentDays = None,
                              mode: _Mode = "live", exchange: _OptionalText = None, symbol: _OptionalText = None,
                              session_id: _OptionalText = None, order: _Order = "newest_first",
                              cursor: _OptionalText = None, limit: _Limit = 100) -> dict:
        return await run_blocking(get_live_trades_service, start, end, recent_days, mode, exchange, symbol,
                                  session_id, order, cursor, limit)

    get_live_trades.__doc__ = """
        Closed live/paper trades whose closed_at falls in a date window, e.g. "my trades of the
        last 3 days": get_live_trades(recent_days=3).
        """ + _HISTORY_COMMON + """
        Trades: only CLOSED trades (selected by closed_at); open positions are never included,
        and "open_trades_not_included" counts the open trades in the same scope opened before
        the window's end. Trades Jesse discarded or merged into another trade are excluded.
        Each trade: id, session_id, session_mode, exchange, symbol, strategy_name, timeframe,
        type (long/short), leverage, opened_at/closed_at (ms), holding_period_seconds, qty,
        entry_price, exit_price, size, fee, pnl, pnl_percentage, executed_orders,
        orders_without_fee. pnl = price difference x qty minus the fees Jesse recorded on the
        trade's executed orders (the dashboard's value), in the symbol's quote currency: never
        add pnl across quote currencies or across live and paper. pnl is null when a trade has
        no executed exit or entry orders; count those, and compute no total or win rate for a
        group with any. If orders_without_fee > 0, fees are incomplete. There is no account
        balance or equity here.

        Returns:
            dict: {"status": "success", "dataset": "live_trades", "source", "range",
            "filters", "order", "items", "limit", "returned", "total", "has_more",
            "truncated_by_size", "truncated_by_orders", "all_records_returned", "next_page",
            "sessions", "session_dashboard_url_template", "open_trades_not_included", "note",
            "paging"} or an error with
            error_type "invalid_request", "invalid_cursor", "mode_mismatch",
            "too_many_orders" (a trade with over 10,000 executed orders), "item_too_large",
            "live_plugin_unavailable", "read_failed", "authentication_failed", or
            "connection_error". No trades in the window: "total": 0 and "items": [].
        """
    mcp.tool()(get_live_trades)

    async def get_live_orders(start: _OptionalText = None, end: _OptionalText = None, recent_days: _RecentDays = None,
                              mode: _Mode = "live", exchange: _OptionalText = None, symbol: _OptionalText = None,
                              session_id: _OptionalText = None, time_field: _TimeField = "created_at",
                              status: _Status = None, order: _Order = "newest_first", cursor: _OptionalText = None,
                              limit: _Limit = 100) -> dict:
        return await run_blocking(get_live_orders_service, start, end, recent_days, mode, exchange, symbol,
                                  session_id, time_field, status, order, cursor, limit)

    get_live_orders.__doc__ = """
        Live/paper orders in a date window, with their stored status, e.g. the orders of the
        last 7 days: get_live_orders(recent_days=7).
        """ + _HISTORY_COMMON + """
        Orders: time_field "created_at" (default: when Jesse created the order) or
        "executed_at" (when it filled; orders never executed do not match). status filters
        one of ACTIVE, CANCELED, EXECUTED, PARTIALLY FILLED, QUEUED, LIQUIDATED, REJECTED.
        "counts_by_status" counts the whole selection per status. Each order: id, trade_id,
        exchange_id, session_id, session_mode, exchange, symbol, side, type, qty, filled_qty,
        price, status, reduce_only, created_at, executed_at, canceled_at (ms or null),
        submitted_via, fee (null when not recorded), jesse_submitted (false for orders Jesse
        recorded to represent a position it found on the exchange).

        Returns:
            dict: {"status": "success", "dataset": "live_orders", "source", "range",
            "filters", "order", "items", "limit", "returned", "total", "has_more",
            "truncated_by_size", "truncated_by_orders" (always false), "all_records_returned",
            "next_page", "sessions", "session_dashboard_url_template", "counts_by_status",
            "note", "paging"} or an error like get_live_trades.
        """
    mcp.tool()(get_live_orders)
    # A misspelled filter must be refused, not dropped, and the text "null" must stay text: either
    # would silently widen the selection. All arguments of these two tools are scalars.
    keep_raw_argument_values(mcp, 'get_live_trades', 'get_live_orders')
    refuse_unknown_arguments(mcp, 'get_live_trades', 'get_live_orders')
