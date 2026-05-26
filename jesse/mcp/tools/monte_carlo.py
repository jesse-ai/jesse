"""
Jesse Monte Carlo MCP Tools

Mirrors the backtest / significance_test tool surface so the agent can stage
and run Monte Carlo simulations with the same draft / run / poll workflow.

Tools exposed:
    create_monte_carlo_draft
    update_monte_carlo_draft
    update_monte_carlo_notes
    get_monte_carlo_session
    get_monte_carlo_sessions
    get_monte_carlo_equity_curves
    get_monte_carlo_logs
    run_monte_carlo
    resume_monte_carlo
    cancel_monte_carlo
    terminate_monte_carlo
    purge_monte_carlo_sessions
"""

from .services import (
    create_monte_carlo_draft_service,
    update_monte_carlo_draft_service,
    update_monte_carlo_notes_service,
    get_monte_carlo_session_service,
    get_monte_carlo_sessions_service,
    get_monte_carlo_equity_curves_service,
    get_monte_carlo_logs_service,
    run_monte_carlo_service,
    resume_monte_carlo_service,
    cancel_monte_carlo_service,
    terminate_monte_carlo_service,
    purge_monte_carlo_sessions_service,
)


def register_monte_carlo_tools(mcp):
    """Register all Monte Carlo tools on the MCP server."""

    @mcp.tool()
    def create_monte_carlo_draft(
        exchange: str = "Binance Perpetual Futures",
        routes: str = '[{"exchange": "Binance Perpetual Futures", "strategy": "ExampleStrategy", "symbol": "BTC-USDT", "timeframe": "4h"}]',
        data_routes: str = '[]',
        start_date: str = "2024-01-01",
        finish_date: str = "2024-03-01",
        num_scenarios: int = 200,
        run_trades: bool = False,
        run_candles: bool = True,
        fast_mode: bool = False,
        cpu_cores: int = None,
        pipeline_type: str = 'moving_block_bootstrap',
        pipeline_params: str = None,
        title: str = None,
        description: str = None,
        strategy_summary: str = None,
        hypothesis: str = None,
        rationale: str = None,
    ) -> dict:
        """
        Create a new Monte Carlo simulation draft session.

        Monte Carlo estimates the distribution of strategy outcomes by
        re-sampling either the trade sequence (`run_trades`) or the candle
        series (`run_candles`). Defaults to candles-only with 200 scenarios,
        which is the most informative variant for most strategies.

        Parameters:
            exchange: Exchange name (default "Binance Perpetual Futures").
            routes: JSON string array of route objects:
                [{"exchange": "...", "strategy": "...", "symbol": "...", "timeframe": "..."}]
            data_routes: JSON string array (default "[]").
            start_date / finish_date: YYYY-MM-DD.
            num_scenarios: How many Monte Carlo scenarios to run (default 200).
                200 is sufficient for stable percentile bands; increase to
                500-1000 when you need tighter tails.
            run_trades: Whether to run the trades resampler (default False).
                Trades MC is fast but lower signal — usually skip unless
                explicitly asked. Re-orders the executed trade sequence.
            run_candles: Whether to run the candles resampler (default True).
                Candles MC is the main mode — it resamples the underlying
                price series and re-runs the strategy on each variant.
            fast_mode: Skip charts/heavy outputs for speed (default False).
            cpu_cores: Worker count. Defaults to (cpu_count - 1, capped at 4).
            pipeline_type: Candle resampling pipeline. Default
                "moving_block_bootstrap". Other options depend on the
                installed pipelines.
            pipeline_params: Optional JSON object string of pipeline-specific
                parameters (e.g. block size).
            title: Optional human-readable note title.
            description: Optional markdown description; auto-generated if omitted.
            strategy_summary: One-sentence summary of the strategy.
            hypothesis: What the simulation is meant to test.
            rationale: Why this MC is being run.

        Returns:
            { "status": "success", "session_id": "<uuid>",
              "draft_state": {...}, "notes": {...}, "message": "..." }
        """
        return create_monte_carlo_draft_service(
            exchange=exchange,
            routes=routes,
            data_routes=data_routes,
            start_date=start_date,
            finish_date=finish_date,
            num_scenarios=num_scenarios,
            run_trades=run_trades,
            run_candles=run_candles,
            fast_mode=fast_mode,
            cpu_cores=cpu_cores,
            pipeline_type=pipeline_type,
            pipeline_params=pipeline_params,
            title=title,
            description=description,
            strategy_summary=strategy_summary,
            hypothesis=hypothesis,
            rationale=rationale,
        )

    @mcp.tool()
    def update_monte_carlo_draft(session_id: str, state: str) -> dict:
        """
        Replace the full state of a Monte Carlo draft.

        Workflow:
            1. session = get_monte_carlo_session(session_id)
            2. current_state = session["data"]["session"]["state"]
            3. modify current_state.form as needed
            4. update_monte_carlo_draft(session_id, json.dumps(current_state))

        Parameters:
            session_id: Draft session UUID.
            state: JSON string of the complete state object (form + results).
        """
        return update_monte_carlo_draft_service(session_id, state)

    @mcp.tool()
    def update_monte_carlo_notes(
        session_id: str,
        title: str = None,
        description: str = None,
        strategy_codes: str = None,
    ) -> dict:
        """
        Update title / description / strategy code snapshot on an existing session.

        Use this after a Monte Carlo run finishes to record the conclusion
        (e.g. "Median sharpe 1.4, worst-5% sharpe 0.6 — strategy is robust").

        Parameters:
            session_id: Session UUID.
            title: Short title shown in the sessions list.
            description: Markdown notes / conclusion.
            strategy_codes: Optional JSON object string of strategy code snapshots,
                keyed by "<exchange>-<symbol>".
        """
        return update_monte_carlo_notes_service(
            session_id=session_id,
            title=title,
            description=description,
            strategy_codes=strategy_codes,
        )

    @mcp.tool()
    def get_monte_carlo_session(session_id: str) -> dict:
        """
        Fetch full details of a Monte Carlo session.

        Returns:
            {
              "data": {
                "session": {
                  "id": "<uuid>",
                  "status": "draft|running|finished|stopped|terminated",
                  "trades_session": {                # null if run_trades=False
                    "status": "...",
                    "num_scenarios": int,
                    "completed_scenarios": int,
                    "summary_metrics": [
                      {"metric": "total_return", "original": float,
                       "worst_5": float, "median": float, "best_5": float},
                      ...
                    ],
                    "exception": str | null,
                    "traceback": str | null
                  },
                  "candles_session": {               # null if run_candles=False
                    "status": "...",
                    "num_scenarios": int,
                    "completed_scenarios": int,
                    "pipeline_type": str,
                    "pipeline_params": dict | null,
                    "summary_metrics": [
                      {"metric": "net_profit_percentage", "original": float,
                       "worst_5": float, "median": float, "best_5": float},
                      ...
                    ],
                    "exception": str | null,
                    "traceback": str | null
                  },
                  "state": {...},
                  "title": str,
                  "description": str
                }
              },
              "error": null | str,
              "message": str
            }

        Interpreting `summary_metrics` — the primary question is
        "is the strategy overfit?", answered by comparing `original` against
        the MC distribution:
            - `original`: metric from the unaltered strategy run
            - `best_5`: 95th-percentile MC scenario (the lucky tail)
            - `median`: 50th-percentile MC scenario
            - `worst_5`: 5th-percentile MC scenario (the unlucky tail)

        For higher-is-better metrics (sharpe, profit, win_rate, calmar):
            - `original > best_5`  → OVERFIT / suspect (beat 95% of MC paths)
            - `original > median`  → borderline (inside plausible range)
            - `original ≈ median`  → good (representative of typical MC)
            - `original < median`  → fantastic (conservative vs MC distribution)

        Separately, `worst_5` answers "how bad does the downside tail get?"
        — for max_drawdown this is the worst-case loss; for sharpe/profit
        it's whether the strategy survives an unlucky path.
        """
        result = get_monte_carlo_session_service(session_id)
        if result.get('error') is None:
            return {
                'data': result.get('data', {}),
                'dashboard_url': result.get('dashboard_url', ''),
                'error': None,
                'message': result.get('message', 'Session retrieved successfully'),
            }
        return {
            'data': None,
            'dashboard_url': result.get('dashboard_url', ''),
            'error': result.get('error'),
            'message': result.get('message', result.get('error', 'Unknown error')),
        }

    @mcp.tool()
    def get_monte_carlo_sessions(
        limit: int = 50,
        offset: int = 0,
        title_search: str = None,
        status_filter: str = None,
        date_filter: str = None,
    ) -> dict:
        """
        List Monte Carlo sessions (most recent first).

        Parameters:
            limit: Max sessions to return (default 50).
            offset: Pagination offset (default 0).
            title_search: Case-insensitive substring on title.
            status_filter: One of "draft", "running", "finished", "stopped", "terminated".
            date_filter: One of "7_days", "30_days", "90_days".
        """
        return get_monte_carlo_sessions_service(
            limit=limit,
            offset=offset,
            title_search=title_search,
            status_filter=status_filter,
            date_filter=date_filter,
        )

    @mcp.tool()
    def get_monte_carlo_equity_curves(session_id: str) -> dict:
        """
        Fetch equity curve data for a finished Monte Carlo session.

        Returns:
            {
              "status": "success",
              "session_id": "<uuid>",
              "trades": {                         # null if run_trades was False
                "original": { "name": "Portfolio", ... },
                "scenarios": [{ "name": "Portfolio", ... }, ...]
              },
              "candles": {                        # null if run_candles was False
                "original": { "name": "Portfolio", ... },
                "scenarios": [{ "name": "Portfolio", ... }, ...]
              }
            }

        Each curve is the Portfolio equity series. Use this to inspect
        dispersion visually or compute custom statistics across scenarios.
        """
        return get_monte_carlo_equity_curves_service(session_id)

    @mcp.tool()
    def get_monte_carlo_logs(session_id: str) -> dict:
        """
        Fetch the raw log file content for a Monte Carlo session.

        Useful for diagnosing failures (status == "stopped"/"terminated") or
        inspecting scenario-by-scenario progress.

        Returns:
            { "status": "success", "session_id": "<uuid>", "logs": "<string>" }
            or { "status": "error", "message": "Log file not found" }
        """
        return get_monte_carlo_logs_service(session_id)

    @mcp.tool()
    def run_monte_carlo(session_id: str) -> dict:
        """
        Fire a Monte Carlo simulation for a previously created draft and return immediately.

        Fire-and-poll: returns once the server acknowledges (202). Then poll
        get_monte_carlo_session(session_id) every few seconds until
        status == "finished" (or "stopped"/"terminated"). Summary metrics live
        in session.trades_session.summary_metrics and
        session.candles_session.summary_metrics once finished.

        Returns:
            { "status": "started", "session_id": "<uuid>", "message": "..." }
            or { "status": "error", "message": "..." }
        """
        return run_monte_carlo_service(session_id)

    @mcp.tool()
    def resume_monte_carlo(session_id: str) -> dict:
        """
        Resume a previously stopped or interrupted Monte Carlo session.

        Use this for sessions whose status is "stopped" or "terminated", or
        when a run was interrupted (server restart, conversation reset).
        For brand-new runs use run_monte_carlo instead.

        Same fire-and-poll semantics as run_monte_carlo.
        """
        return resume_monte_carlo_service(session_id)

    @mcp.tool()
    def cancel_monte_carlo(session_id: str) -> dict:
        """
        Cooperatively cancel a running Monte Carlo session.

        Requests termination but lets the worker complete its current scenario.
        For an immediate hard stop use terminate_monte_carlo.
        """
        return cancel_monte_carlo_service(session_id)

    @mcp.tool()
    def terminate_monte_carlo(session_id: str) -> dict:
        """
        Hard-terminate a running Monte Carlo session.

        Marks the session as "terminated" and force-cancels the worker process.
        Prefer cancel_monte_carlo unless the worker is stuck.
        """
        return terminate_monte_carlo_service(session_id)

    @mcp.tool()
    def purge_monte_carlo_sessions(days_old: int = None) -> dict:
        """
        Permanently delete Monte Carlo sessions.

        Parameters:
            days_old: If set, only sessions older than this many days are deleted.
                If None, ALL sessions are deleted (irreversible).
        """
        return purge_monte_carlo_sessions_service(days_old)
