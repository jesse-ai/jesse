"""
Jesse Rule Significance Test MCP Tools

Mirrors the backtest MCP tool surface so the agent can stage and run rule
significance tests with the same draft / run / poll workflow it already knows.

Tools exposed:
    create_significance_test_draft
    update_significance_test_draft
    update_significance_test_notes
    get_significance_test_session
    get_significance_test_sessions
    run_significance_test
    cancel_significance_test
    purge_significance_test_sessions
"""

from .services import (
    create_significance_test_draft_service,
    update_significance_test_draft_service,
    update_significance_test_notes_service,
    get_significance_test_session_service,
    get_significance_test_sessions_service,
    run_significance_test_service,
    cancel_significance_test_service,
    purge_significance_test_sessions_service,
)


def register_significance_test_tools(mcp):
    """Register all rule-significance-test tools on the MCP server."""

    @mcp.tool()
    def create_significance_test_draft(
        exchange: str = "Binance Perpetual Futures",
        routes: str = '[{"exchange": "Binance Perpetual Futures", "strategy": "ExampleStrategy", "symbol": "BTC-USDT", "timeframe": "4h"}]',
        data_routes: str = '[]',
        start_date: str = "2021-01-01",
        finish_date: str = "2022-01-01",
        n_simulations: int = 2000,
        random_seed: int = None,
        title: str = None,
        description: str = None,
        strategy_summary: str = None,
        hypothesis: str = None,
        rationale: str = None,
    ) -> dict:
        """
        Create a new Rule Significance Test draft session.

        Rule Significance Testing (RST) statistically proves whether a strategy's
        entry signal has a genuine edge or is indistinguishable from luck. It runs
        the real strategy once, then runs `n_simulations` random-entry variants on
        the same candles and compares the distributions.

        Use this BEFORE writing a full strategy when prototyping an idea, or when
        the user explicitly asks to "validate an entry signal".

        Constraints:
            - Exactly ONE trading route is allowed (this is enforced server-side).
            - The strategy in the route must already exist on disk; create it with
              create_strategy() first if needed.
            - 2000+ simulations are recommended for stable p-values.

        Parameters:
            exchange: Exchange name (default "Binance Perpetual Futures").
            routes: JSON string array with EXACTLY one route object:
                [{"exchange": "...", "strategy": "...", "symbol": "...", "timeframe": "..."}]
            data_routes: JSON string array (default "[]").
            start_date / finish_date: YYYY-MM-DD.
            n_simulations: Number of random-entry simulations (default 2000).
            random_seed: Optional int for reproducibility.
            title: Optional human-readable note title.
            description: Optional markdown description; auto-generated if omitted.
            strategy_summary: One-sentence summary of the strategy.
            hypothesis: The trading hypothesis being validated.
            rationale: Why this rule is being significance-tested.

        Returns:
            {
              "status": "success",
              "session_id": "<uuid>",
              "draft_state": {...},
              "notes": {"title": ..., "description": ..., ...},
              "message": "..."
            }
        """
        return create_significance_test_draft_service(
            exchange=exchange,
            routes=routes,
            data_routes=data_routes,
            start_date=start_date,
            finish_date=finish_date,
            n_simulations=n_simulations,
            random_seed=random_seed,
            title=title,
            description=description,
            strategy_summary=strategy_summary,
            hypothesis=hypothesis,
            rationale=rationale,
        )

    @mcp.tool()
    def update_significance_test_draft(session_id: str, state: str) -> dict:
        """
        Replace the full state of a Rule Significance Test draft.

        Workflow:
            1. session = get_significance_test_session(session_id)
            2. current_state = session["data"]["session"]["state"]
            3. modify current_state.form as needed
            4. update_significance_test_draft(session_id, json.dumps(current_state))

        Parameters:
            session_id: Draft session UUID.
            state: JSON string of the complete state object (form + results).

        Returns:
            { "status": "success", "session_id": ..., "draft_state": ..., "message": ... }
        """
        return update_significance_test_draft_service(session_id, state)

    @mcp.tool()
    def update_significance_test_notes(
        session_id: str,
        title: str = None,
        description: str = None,
        strategy_codes: str = None,
    ) -> dict:
        """
        Update title / description / strategy code snapshot on an existing session.

        Use this after a test finishes to record the conclusion (e.g. "p_value=0.03,
        edge confirmed — proceeding to full strategy").

        Parameters:
            session_id: Session UUID.
            title: Short title shown in the sessions list.
            description: Markdown notes / conclusion.
            strategy_codes: Optional JSON object string of strategy code snapshots,
                keyed by "<exchange>-<symbol>".

        Returns:
            { "status": "success"|"error", "session_id": ..., ... }
        """
        return update_significance_test_notes_service(
            session_id=session_id,
            title=title,
            description=description,
            strategy_codes=strategy_codes,
        )

    @mcp.tool()
    def get_significance_test_session(session_id: str) -> dict:
        """
        Fetch full details of a significance test session.

        Returns:
            {
              "data": {
                "session": {
                  "id": "<uuid>",
                  "status": "draft|running|finished|stopped|terminated",
                  "state": {"form": {...}, "results": {...}},
                  "results": {                  # populated when finished
                    "observed_mean": float,
                    "annualized_return": float,
                    "p_value": float,           # < 0.05 = statistically significant
                    "n_simulations": int,
                    "n_observations": int
                  },
                  "exception": str | null,
                  "traceback": str | null
                }
              },
              "error": null | str,
              "message": str
            }
        """
        result = get_significance_test_session_service(session_id)
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
    def get_significance_test_sessions(
        limit: int = 50,
        offset: int = 0,
        title_search: str = None,
        status_filter: str = None,
        date_filter: str = None,
    ) -> dict:
        """
        List significance test sessions (most recent first).

        Parameters:
            limit: Max sessions to return (default 50).
            offset: Pagination offset (default 0).
            title_search: Case-insensitive substring on title.
            status_filter: One of "draft", "running", "finished", "stopped", "terminated".
            date_filter: One of "7_days", "30_days", "90_days".

        Returns:
            { "status": "success", "sessions": [...], "count": int, "message": ... }
        """
        return get_significance_test_sessions_service(
            limit=limit,
            offset=offset,
            title_search=title_search,
            status_filter=status_filter,
            date_filter=date_filter,
        )

    @mcp.tool()
    def run_significance_test(session_id: str) -> dict:
        """
        Fire a Rule Significance Test for a previously created draft and return immediately.

        Fire-and-poll: this returns once the server acknowledges (202). Then poll
        get_significance_test_session(session_id) every few seconds until
        status == "finished" (or "stopped"/"terminated"). Results live in
        session["results"] once finished.

        Returns:
            { "status": "started", "session_id": "<uuid>", "message": "..." }
            or { "status": "error", "message": "..." }

        Interpreting results:
            - p_value < 0.05         → entry signal has a statistically significant edge
            - 0.05 <= p_value <= 0.10 → borderline; flag as inconclusive to the user
            - p_value > 0.10         → HARD STOP. Indistinguishable from random;
              do not silently proceed to a full backtest
        """
        return run_significance_test_service(session_id)

    @mcp.tool()
    def cancel_significance_test(session_id: str) -> dict:
        """Cancel a running significance test."""
        return cancel_significance_test_service(session_id)

    @mcp.tool()
    def purge_significance_test_sessions(days_old: int = None) -> dict:
        """
        Permanently delete significance test sessions.

        Parameters:
            days_old: If set, only sessions older than this many days are deleted.
                If None, ALL sessions are deleted (irreversible).
        """
        return purge_significance_test_sessions_service(days_old)
