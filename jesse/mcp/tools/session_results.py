"""
Jesse Session Results Tools

Read-only, bounded access to stored results of backtests, optimizations, Monte Carlo runs,
rule significance tests, and live/paper sessions:
- get_session_results: a compact summary, or one page of a result section
- get_live_sessions: the live/paper session list (the other kinds have their own list tools)

Details and the snapshot format used by temporary analysis: jesse://session_analysis.

The tools are async and run their API call in a worker thread (see offload.py), so parsing a
large stored session does not stall other MCP requests on this worker.
"""
from typing import Optional

from .offload import run_blocking
from .services import get_live_sessions_service, get_session_results_service


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
            "next_offset", "has_more", "truncated_by_size"}. Values are exactly as stored;
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
            "has_error"}], "next_offset"} or an error with error_type
            "live_plugin_unavailable" or "invalid_request". Read one with
            get_session_results(session_type="live", session_id=...).
        """
        return await run_blocking(get_live_sessions_service, limit, offset, status_filter, mode_filter, title_search)
