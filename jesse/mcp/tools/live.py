"""
Live and Paper Session Tools

MCP counterparts of the dashboard's Live page, through the same authenticated routes:
create/update/copy drafts, start, stop, notes, and delete. Reading sessions (status, orders,
closed trades, equity, logs, errors) stays with get_live_sessions and get_session_results.

All tools need the live trading plugin on the Jesse instance and run their API calls in a
worker thread (see offload.py). See jesse.mcp.tools.services.live for the exact checks.
"""

from typing import Annotated, Any, Optional

from pydantic import WithJsonSchema

from jesse.mcp.tools.offload import run_blocking
from jesse.mcp.tools.services.live import (
    copy_live_session_service,
    create_live_draft_service,
    delete_live_session_service,
    start_live_session_service,
    stop_live_session_service,
    update_live_draft_service,
    update_live_session_notes_service,
)


# FastMCP validates arguments with pydantic before a tool runs, and its errors quote the input: a
# missing required argument quotes every argument, and a wrong-typed one quotes its value. A secret
# pasted into a key ID field would come straight back that way (checked on SDK 1.28.1). So in the
# tools that take key IDs, those fields, the required fields, and the free-form JSON fields accept
# any value and default to None, and the services validate them with messages that never repeat a
# value, as the credential tools do. WithJsonSchema keeps the advertised types; the docstrings say
# which arguments are required.
#
# FastMCP also JSON-decodes a string argument unless its parameter is exactly `str`, so routes and
# config sent as JSON text usually arrive as a list or dict; the services accept both forms.
_AnyKeyId = Annotated[Any, WithJsonSchema({'anyOf': [{'type': 'string'}, {'type': 'null'}]})]
_AnyPaperMode = Annotated[Any, WithJsonSchema({'type': 'boolean'})]
_AnySessionId = Annotated[Any, WithJsonSchema({'type': 'string'})]
_AnyRoutes = Annotated[Any, WithJsonSchema({'anyOf': [
    {'type': 'string'}, {'type': 'array', 'items': {'type': 'object', 'additionalProperties': True}},
]})]
_AnyOptionalRoutes = Annotated[Any, WithJsonSchema({'anyOf': [
    {'type': 'string'}, {'type': 'array', 'items': {'type': 'object', 'additionalProperties': True}}, {'type': 'null'},
]})]
_AnyConfig = Annotated[Any, WithJsonSchema({'anyOf': [
    {'type': 'string'}, {'type': 'object', 'additionalProperties': True}, {'type': 'null'},
]})]


def register_live_tools(mcp):
    """Register the live/paper session management tools with the MCP server."""

    @mcp.tool()
    async def create_live_draft(
        paper_mode: _AnyPaperMode = None,
        routes: _AnyRoutes = None,
        exchange: Optional[str] = None,
        exchange_api_key_id: _AnyKeyId = None,
        data_routes: _AnyRoutes = '[]',
        notification_api_key_id: _AnyKeyId = None,
        debug_mode: bool = True,
        config: _AnyConfig = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
    ) -> dict:
        """Create a live or paper trading session draft (a new dashboard Live tab); nothing starts.

        `paper_mode` and `routes` are required. `paper_mode` decides what the session trades:
        - true: PAPER trading. Orders are simulated against live market data; no real funds and
          no exchange key. Pass `exchange` (a live-trading exchange name exactly as Jesse lists it).
        - false: LIVE trading with REAL funds. Pass `exchange_api_key_id` of a saved key
          (get_exchange_api_keys()); the session trades on that key's exchange, so `exchange` can
          be omitted. Keys are referenced by ID only; secrets are never read.

        `routes`: array (or JSON text) of {"strategy", "symbol", "timeframe"}; `data_routes`: array
        of {"symbol", "timeframe"}. The dashboard's route rules apply (unique symbols, one quote asset,
        no data route on a trading route's symbol and timeframe) and strategies must exist.
        `notification_api_key_id`: optional saved notification key ID.

        The draft gets its own configuration, resolved like a new dashboard tab from the saved
        defaults for that paper exchange or key; saved settings are not changed. `config` is an
        optional object (or JSON text) overriding any of: persistency, generate_candles_from_1m, logging,
        warm_up_candles, notifications, exchange {balance, fee, futures_leverage,
        futures_leverage_mode, simulation_model} (balance, fee, and market type are simulation
        values for paper sessions; real sessions use the venue's). The result shows the resolved
        config and a dashboard link. Start it with start_live_session only when the user asks.
        """
        return await run_blocking(
            create_live_draft_service,
            paper_mode=paper_mode,
            routes=routes,
            exchange=exchange,
            exchange_api_key_id=exchange_api_key_id,
            data_routes=data_routes,
            notification_api_key_id=notification_api_key_id,
            debug_mode=debug_mode,
            config=config,
            title=title,
            description=description,
        )

    @mcp.tool()
    async def update_live_draft(
        session_id: _AnySessionId = None,
        paper_mode: Optional[bool] = None,
        routes: _AnyOptionalRoutes = None,
        exchange: Optional[str] = None,
        exchange_api_key_id: _AnyKeyId = None,
        data_routes: _AnyOptionalRoutes = None,
        notification_api_key_id: _AnyKeyId = None,
        debug_mode: Optional[bool] = None,
        config: _AnyConfig = None,
    ) -> dict:
        """Change a live/paper draft before it starts; omitted fields keep their stored values.

        `session_id` is required. Only drafts can change (a started session is fixed; copy it with copy_live_session).
        Arguments mean the same as in create_live_draft and the whole form is validated again.
        Switching `paper_mode` changes whether the session trades real funds: false needs a saved
        key, true needs an exchange. `config` overrides are merged into the draft's own config.
        Pass "" to clear notification_api_key_id.
        """
        return await run_blocking(
            update_live_draft_service,
            session_id=session_id,
            paper_mode=paper_mode,
            routes=routes,
            exchange=exchange,
            exchange_api_key_id=exchange_api_key_id,
            data_routes=data_routes,
            notification_api_key_id=notification_api_key_id,
            debug_mode=debug_mode,
            config=config,
        )

    @mcp.tool()
    async def copy_live_session(session_id: str, title: Optional[str] = None) -> dict:
        """Create a new draft with the same mode, exchange, key, routes, and settings as a session.

        The dashboard's "New session" action: use it to run a stopped, failed, or finished
        session again (restart = copy_live_session, then start_live_session on the new ID), or to
        start from a draft's form. The source is unchanged and nothing starts. If the source's
        saved key or strategies no longer exist, the copy is refused with the reason.
        """
        return await run_blocking(copy_live_session_service, session_id=session_id, title=title)

    @mcp.tool()
    async def start_live_session(session_id: str) -> dict:
        """Start a live or paper draft, like the dashboard's Start button.

        Only start a session the user asked to start, and tell them whether it is PAPER
        (simulated) or LIVE (real funds); the result's `mode` says which. Only drafts can start;
        to run a finished session again, copy it first.

        The form is validated again and the session is started with the same request as the
        dashboard's Start. The session itself then checks the license and plan (allowed
        exchanges, routes, timeframes, paper trading), connects to the exchange, and loads
        warm-up candles; a failure there appears as the session's `error`, and a session the
        license or plan does not allow never trades. Check get_session_results("live",
        session_id) until `session_status` is `running`. Live and paper sessions do not use
        research credits.
        """
        return await run_blocking(start_live_session_service, session_id=session_id)

    @mcp.tool()
    async def stop_live_session(session_id: str) -> dict:
        """Stop a running live or paper session, like the dashboard's Stop button.

        Only stop a session the user asked to stop. Stopping ends the session process; it does
        not by itself mean positions are closed. While ending, a paper session, or a live session
        with persistency off, cancels its routes' open orders and closes their positions with
        market orders; a live session with persistency on leaves orders and positions on the
        exchange. The result's `on_stop` states this; confirm the outcome with
        get_session_results("live", session_id) (summary, orders, logs).
        """
        return await run_blocking(stop_live_session_service, session_id=session_id)

    @mcp.tool()
    async def update_live_session_notes(
        session_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
    ) -> dict:
        """Set the title and/or description of a live or paper session (the dashboard's notes).

        Works for drafts, running, and finished sessions; it changes nothing else.
        """
        return await run_blocking(
            update_live_session_notes_service, session_id=session_id, title=title, description=description,
        )

    @mcp.tool()
    async def delete_live_session(session_id: str) -> dict:
        """Permanently delete a stored live or paper session record (history or draft).

        Refused while the session is starting or running (stop it first) and while it is open
        in a dashboard Live tab (the dashboard asks to close the tab first). Deleting the record
        does not touch the exchange account. Only delete what the user asked to remove.
        """
        return await run_blocking(delete_live_session_service, session_id=session_id)
