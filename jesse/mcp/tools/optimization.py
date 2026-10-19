"""
Jesse Optimization Tools

MCP tools for hyperparameter optimization, mirroring the Monte Carlo tools so the
agent uses the same draft / run / wait workflow.

Workflow:
    1. create_optimization_draft(...)  -> returns session_id
    2. run_optimization(session_id)    -> fires the run, returns immediately
    3. wait_for_sessions([session_id]) until done (call again while done=false),
       then read the best trials with get_session_results("optimization", session_id).

Requirements / gotchas:
    - The strategy MUST define a non-empty hyperparameters() list — otherwise there
      is nothing to optimize and the run stops with an error.
    - Candles must exist for BOTH the training and testing windows (plus warm-up
      before each). If they're missing the session stops with a clear message
      telling you what to import.
    - `trials` is PER hyperparameter: total trials = n_hyperparameters * trials.
    - Optimization is long-running; expect several wait_for_sessions calls.

The tools are async and run their API calls in a worker thread (see offload.py).
"""

from .offload import run_blocking
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
from .run_config_arguments import ConfigOverrides


def register_optimization_tools(mcp):
    """Register the optimization tools with the MCP server."""
    # The usage check and the run request happen in one worker-thread call, so a cancellation
    # never falls between them (a credit used without the run being attempted).
    gated_run_optimization = gated(weight=CREDIT_WEIGHTS["run_optimization"])(run_optimization_service)

    @mcp.tool()
    async def create_optimization_draft(
        exchange: str = "Binance Perpetual Futures",
        routes: str = '[{"exchange": "Binance Perpetual Futures", "strategy": "ExampleStrategy", "symbol": "BTC-USDT", "timeframe": "4h"}]',
        data_routes: str = '[]',
        training_start_date: str = "2021-01-01",
        training_finish_date: str = "2022-06-01",
        testing_start_date: str = "2022-06-01",
        testing_finish_date: str = "2023-01-01",
        optimal_total: int = 50,
        objective_function: str = None,
        trials: int = None,
        best_candidates_count: int = None,
        warm_up_candles: int = None,
        fast_mode: bool = True,
        cpu_cores: int = None,
        title: str = None,
        description: str = None,
        strategy_summary: str = None,
        hypothesis: str = None,
        rationale: str = None,
        fee: float = None,
        leverage: int = None,
        leverage_mode: str = None,
        balance: float = None,
        config_overrides: ConfigOverrides = None,
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
            objective_function: What to maximize. One of: "sharpe" (built-in default),
                "calmar", "sortino", "omega", "serenity", "smart sharpe",
                "smart sortino".
            trials: Trials PER hyperparameter (built-in default 200). Total trials =
                n_hyperparameters * trials. Lower it (e.g. 20-50) for a quick run.
            best_candidates_count: How many top candidates to keep (built-in default 20).
            fast_mode: Faster, slightly less precise simulation (default True).
            cpu_cores: Worker count. Defaults to (cpu_count - 1, capped at 4).
            title / description: Optional notes; auto-generated if omitted.
            strategy_summary / hypothesis / rationale: Optional note context.
            Built-in defaults apply only when nothing is saved for optimizations on this exchange;
            otherwise the saved values do. cpu_cores is the exception: unless passed, it is the
            MCP's own default for unattended runs.

        Run settings (all optional; omitted ones come from the saved optimization defaults for this
        exchange, else Jesse's built-in defaults):
            fee: Exchange fee as a fraction per side (0.0006 = 0.06%).
            leverage: Futures leverage, a whole number of 1 or more. Ignored on spot exchanges.
            leverage_mode: "cross" or "isolated" (futures only; must be supported by the exchange).
            balance: Starting balance.
            warm_up_candles: Candles loaded before the start date to warm up indicators.
            config_overrides: JSON object with any other run-config field: objective_function, trials, cpu_cores, best_candidates_count,
                e.g. {"exchange": {"fee": 0.0002, "futures_leverage": 20}}. Named arguments win over it.
        Set these here instead of editing the draft state afterwards. The response's `run_config` is
        exactly what the draft will run with, `config_source` says where each value came from
        (explicit / tool_default / saved_default / exchange_default / hard_default), and
        `config_warnings` flags a fee or leverage that is only Jesse's built-in default, saved
        defaults whose fee or leverage differ from this exchange's backtest defaults, or leverage
        ignored on a spot exchange. Pass fee and leverage explicitly when a warning appears.

        Returns:
            { "status": "success", "session_id": "<uuid>", "draft_state": {...},
              "run_config": {...}, "config_source": {...}, "config_warnings": [...] (when any),
              "notes": {...}, "dashboard_url": "...", "message": "..." }
        """
        return await run_blocking(
            create_optimization_draft_service,
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
            fee=fee,
            leverage=leverage,
            leverage_mode=leverage_mode,
            balance=balance,
            config_overrides=config_overrides,
        )

    @mcp.tool()
    async def update_optimization_draft(
        session_id: str,
        state: str = None,
        fee: float = None,
        leverage: int = None,
        leverage_mode: str = None,
        balance: float = None,
        warm_up_candles: int = None,
        config_overrides: ConfigOverrides = None,
    ) -> dict:
        """
        Update an optimization draft: replace its full state, or change only its run settings.

        Parameters:
            session_id: UUID of the optimization session.
            state: JSON string of the complete state object ({"form": {...}, "results": {...}}).
                Retrieve current state with get_optimization_session, modify, and send back.

        To change only run settings, omit `state` and pass any of fee, leverage, leverage_mode,
        balance, warm_up_candles or config_overrides (same meaning as in the create tool). The
        stored draft keeps everything else; only drafts can change. The response shows the new
        `run_config` and `config_source` ("explicit" for what this call set, "stored" for the rest).
        Do not combine `state` with run settings.
        """
        return await run_blocking(
            update_optimization_draft_service, session_id, state,
            fee=fee, leverage=leverage, leverage_mode=leverage_mode, balance=balance,
            warm_up_candles=warm_up_candles, config_overrides=config_overrides,
        )

    @mcp.tool()
    async def update_optimization_notes(
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
        return await run_blocking(
            update_optimization_notes_service,
            session_id=session_id,
            title=title,
            description=description,
            strategy_codes=strategy_codes,
        )

    @mcp.tool()
    async def get_optimization_session(session_id: str) -> dict:
        """
        Fetch full details of an optimization session. To wait for a run, use
        wait_for_sessions instead of calling this repeatedly.

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

        Status: "running" → wait with wait_for_sessions([session_id]) (optimization is
        slow). status == "finished" → read best_candidates (rank #1 is best by the
        objective). status == "stopped" → read `exception` (e.g. missing candles, or
        the strategy has no hyperparameters).

        Interpreting results: compare each candidate's training_metrics vs
        testing_metrics. A candidate that's strong in training but weak in testing is
        overfit; prefer candidates that hold up out-of-sample.
        """
        return await run_blocking(get_optimization_session_service, session_id)

    @mcp.tool()
    async def get_optimization_sessions(
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

        Each session row has "dashboard_url", its page on the dashboard: give the user that
        link, not the bare ID.
        """
        return await run_blocking(
            get_optimization_sessions_service,
            limit=limit,
            offset=offset,
            title_search=title_search,
            status_filter=status_filter,
            date_filter=date_filter,
        )

    @mcp.tool()
    async def get_optimization_logs(session_id: str) -> dict:
        """
        Fetch the raw log file content for an optimization session. Useful for
        diagnosing a stopped run beyond the `exception` field.
        """
        return await run_blocking(get_optimization_logs_service, session_id)

    @mcp.tool()
    async def run_optimization(session_id: str) -> dict:
        """
        Start a previously created optimization draft and return immediately.

        Returns once the server acknowledges. Then call wait_for_sessions([session_id])
        until it ends or stalls; optimization is long-running, so call it again while it
        returns done=false (its `progress` shows completed / total trials). Then read the
        best trials with get_session_results("optimization", session_id).

        Returns: { "status": "started", "session_id": "<uuid>", "message": "..." }
                 or { "status": "error", "message": "..." }
        """
        return await run_blocking(gated_run_optimization, session_id)

    @mcp.tool()
    async def rerun_optimization(session_id: str) -> dict:
        """
        Reset and restart an existing optimization session, clearing its prior
        trials and results. Use this to run a finished or stopped session again
        (e.g. after importing missing candles or editing the strategy). Cancel a
        running session first before rerunning. Wait for it with
        wait_for_sessions([session_id]), as after run_optimization.
        """
        return await run_blocking(rerun_optimization_service, session_id)

    @mcp.tool()
    async def cancel_optimization(session_id: str) -> dict:
        """
        Cooperatively cancel a running optimization. The worker stops at the next
        trial checkpoint; partial results (completed trials) are preserved.
        """
        return await run_blocking(cancel_optimization_service, session_id)

    @mcp.tool()
    async def terminate_optimization(session_id: str) -> dict:
        """
        Hard-terminate a running optimization (marks it 'terminated' and forces the
        worker down). Prefer cancel_optimization for a graceful stop.
        """
        return await run_blocking(terminate_optimization_service, session_id)

    @mcp.tool()
    async def purge_optimization_sessions(days_old: int = None) -> dict:
        """
        Permanently delete optimization sessions. If days_old is given, only delete
        sessions older than that many days; otherwise delete all. Irreversible.
        """
        return await run_blocking(purge_optimization_sessions_service, days_old)
