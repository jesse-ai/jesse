"""
Jesse Optimization Tools

MCP tools for hyperparameter optimization, mirroring the Monte Carlo tools so the
agent uses the same draft / run / poll workflow.

Workflow:
    1. create_optimization_draft(...)  -> returns session_id
    2. run_optimization(session_id)    -> fires the run, returns immediately
    3. poll get_optimization_session(session_id) until status == "finished"
       (or "stopped"/"terminated"); read best_candidates for the tuned params.

Requirements / gotchas:
    - The strategy MUST define a non-empty hyperparameters() list — otherwise there
      is nothing to optimize and the run stops with an error.
    - Candles must exist for BOTH the training and testing windows (plus warm-up
      before each). If they're missing the session stops with a clear message
      telling you what to import.
    - `trials` is PER hyperparameter: total trials = n_hyperparameters * trials.
    - Optimization is long-running; poll less frequently than a backtest.
"""

from .services import (
    create_optimization_draft_service,
    update_optimization_draft_service,
    update_optimization_notes_service,
    get_optimization_session_service,
    get_optimization_sessions_service,
    get_optimization_logs_service,
    run_optimization_service,
    rerun_optimization_service,
    cancel_optimization_service,
    terminate_optimization_service,
    purge_optimization_sessions_service,
)
from jesse.mcp.usage_limits import gated, CREDIT_WEIGHTS


def register_optimization_tools(mcp):
    """Register the optimization tools with the MCP server."""

    @mcp.tool()
    def create_optimization_draft(
        exchange: str = "Binance Perpetual Futures",
        routes: str = '[{"exchange": "Binance Perpetual Futures", "strategy": "ExampleStrategy", "symbol": "BTC-USDT", "timeframe": "4h"}]',
        data_routes: str = '[]',
        training_start_date: str = "2021-01-01",
        training_finish_date: str = "2022-06-01",
        testing_start_date: str = "2022-06-01",
        testing_finish_date: str = "2023-01-01",
        optimal_total: int = 50,
        objective_function: str = "sharpe",
        trials: int = 200,
        best_candidates_count: int = 20,
        warm_up_candles: int = 210,
        fast_mode: bool = True,
        cpu_cores: int = None,
        title: str = None,
        description: str = None,
        strategy_summary: str = None,
        hypothesis: str = None,
        rationale: str = None,
    ) -> dict:
        """
        Create a new hyperparameter Optimization draft session.

        Optimization tunes a strategy's hyperparameters() on a TRAINING window and
        reports out-of-sample performance on a separate TESTING window, so you can
        spot overfitting (great train metrics + poor test metrics).

        PRECONDITIONS:
            - The strategy in the route must already exist on disk (create it with
              create_strategy first) and must define a NON-EMPTY hyperparameters()
              method — that list is what gets optimized. With no hyperparameters
              there is nothing to optimize and the run will stop with an error.
            - Candles must exist for BOTH the training and testing windows (plus
              ~warm_up_candles before each start). If missing, the run stops with a
              message telling you exactly what to import; import then rerun.

        Parameters:
            exchange: Exchange name (default "Binance Perpetual Futures").
            routes: JSON string array with the trading route(s):
                [{"exchange": "...", "strategy": "...", "symbol": "...", "timeframe": "..."}]
            data_routes: JSON string array (default "[]").
            training_start_date / training_finish_date: YYYY-MM-DD — the in-sample
                window the optimizer tunes on.
            testing_start_date / testing_finish_date: YYYY-MM-DD — the out-of-sample
                window used to report each candidate's generalization. Conventionally
                testing_start_date == training_finish_date (contiguous), but they can
                be any non-overlapping ranges.
            optimal_total: Target number of best candidates to surface (default 50).
            objective_function: What to maximize. One of: "sharpe" (default),
                "calmar", "sortino", "omega", "serenity", "smart sharpe",
                "smart sortino".
            trials: Trials PER hyperparameter (default 200). Total trials =
                n_hyperparameters * trials. Lower it (e.g. 20-50) for a quick run.
            best_candidates_count: How many top candidates to keep (default 20).
            warm_up_candles: Warm-up candles before each window start (default 210).
            fast_mode: Faster, slightly less precise simulation (default True).
            cpu_cores: Worker count. Defaults to (cpu_count - 1, capped at 4).
            title / description: Optional notes; auto-generated if omitted.
            strategy_summary / hypothesis / rationale: Optional note context.

        Returns:
            { "status": "success", "session_id": "<uuid>", "draft_state": {...},
              "notes": {...}, "dashboard_url": "...", "message": "..." }
        """
        return create_optimization_draft_service(
            exchange=exchange,
            routes=routes,
            data_routes=data_routes,
            training_start_date=training_start_date,
            training_finish_date=training_finish_date,
            testing_start_date=testing_start_date,
            testing_finish_date=testing_finish_date,
            optimal_total=optimal_total,
            objective_function=objective_function,
            trials=trials,
            best_candidates_count=best_candidates_count,
            warm_up_candles=warm_up_candles,
            fast_mode=fast_mode,
            cpu_cores=cpu_cores,
            title=title,
            description=description,
            strategy_summary=strategy_summary,
            hypothesis=hypothesis,
            rationale=rationale,
        )

    @mcp.tool()
    def update_optimization_draft(session_id: str, state: str) -> dict:
        """
        Replace the full state of an optimization draft.

        Parameters:
            session_id: UUID of the optimization session.
            state: JSON string of the complete state object ({"form": {...}, "results": {...}}).
                Retrieve current state with get_optimization_session, modify, and send back.
        """
        return update_optimization_draft_service(session_id, state)

    @mcp.tool()
    def update_optimization_notes(
        session_id: str,
        title: str = None,
        description: str = None,
        strategy_codes: str = None,
    ) -> dict:
        """
        Update title / description / strategy-code snapshot on an optimization session.

        Parameters:
            session_id: UUID of the session.
            title / description: Optional note fields.
            strategy_codes: Optional JSON object string mapping "exchange-symbol" to
                strategy source.
        """
        return update_optimization_notes_service(
            session_id=session_id,
            title=title,
            description=description,
            strategy_codes=strategy_codes,
        )

    @mcp.tool()
    def get_optimization_session(session_id: str) -> dict:
        """
        Fetch full details of an optimization session — the primary polling tool.

        Returns (shape):
            {
              "data": { "session": {
                  "id": "<uuid>",
                  "status": "draft|running|paused|finished|stopped|terminated",
                  "completed_trials": int,
                  "total_trials": int,            # n_hyperparameters * trials
                  "best_candidates": [            # populated as trials complete
                    { "rank": "#1", "trial": "Trial N", "params": {...},
                      "fitness": float, "dna": "...",
                      "training_metrics": {...},   # in-sample
                      "testing_metrics": {...},    # out-of-sample
                      "objective_metric": "train / test" },
                    ...
                  ],
                  "objective_curve": [...],
                  "exception": str | null,
                  "traceback": str | null
              } },
              "error": null | str,
              "message": str
            }

        Polling: status == "running" → keep polling (every ~20-30s; optimization is
        slow). status == "finished" → read best_candidates (rank #1 is best by the
        objective). status == "stopped" → read `exception` (e.g. missing candles, or
        the strategy has no hyperparameters).

        Interpreting results: compare each candidate's training_metrics vs
        testing_metrics. A candidate that's strong in training but weak in testing is
        overfit; prefer candidates that hold up out-of-sample.
        """
        return get_optimization_session_service(session_id)

    @mcp.tool()
    def get_optimization_sessions(
        limit: int = 50,
        offset: int = 0,
        title_search: str = None,
        status_filter: str = None,
        date_filter: str = None,
    ) -> dict:
        """
        List optimization sessions (most recent first), with pagination/filtering.

        Parameters:
            limit (default 50), offset (default 0).
            title_search: case-insensitive title substring.
            status_filter: "running" | "paused" | "finished" | "stopped" | "terminated".
            date_filter: "today" | "this_week" | "this_month" | "this_year".
        """
        return get_optimization_sessions_service(
            limit=limit,
            offset=offset,
            title_search=title_search,
            status_filter=status_filter,
            date_filter=date_filter,
        )

    @mcp.tool()
    def get_optimization_logs(session_id: str) -> dict:
        """
        Fetch the raw log file content for an optimization session. Useful for
        diagnosing a stopped run beyond the `exception` field.
        """
        return get_optimization_logs_service(session_id)

    @mcp.tool()
    @gated(weight=CREDIT_WEIGHTS["run_optimization"])
    def run_optimization(session_id: str) -> dict:
        """
        Start a previously created optimization draft and return immediately.

        Fire-and-poll: returns once the server acknowledges. Then poll
        get_optimization_session(session_id) until status is "finished" (or
        "stopped"/"terminated"). Optimization is long-running — poll less frequently
        (every ~20-30s) and watch completed_trials / total_trials.

        Returns: { "status": "started", "session_id": "<uuid>", "message": "..." }
                 or { "status": "error", "message": "..." }
        """
        return run_optimization_service(session_id)

    @mcp.tool()
    def rerun_optimization(session_id: str) -> dict:
        """
        Reset and restart an existing optimization session, clearing its prior
        trials and results. Use this to run a finished or stopped session again
        (e.g. after importing missing candles or editing the strategy). Cancel a
        running session first before rerunning.
        """
        return rerun_optimization_service(session_id)

    @mcp.tool()
    def cancel_optimization(session_id: str) -> dict:
        """
        Cooperatively cancel a running optimization. The worker stops at the next
        trial checkpoint; partial results (completed trials) are preserved.
        """
        return cancel_optimization_service(session_id)

    @mcp.tool()
    def terminate_optimization(session_id: str) -> dict:
        """
        Hard-terminate a running optimization (marks it 'terminated' and forces the
        worker down). Prefer cancel_optimization for a graceful stop.
        """
        return terminate_optimization_service(session_id)

    @mcp.tool()
    def purge_optimization_sessions(days_old: int = None) -> dict:
        """
        Permanently delete optimization sessions. If days_old is given, only delete
        sessions older than that many days; otherwise delete all. Irreversible.
        """
        return purge_optimization_sessions_service(days_old)
