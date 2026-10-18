
"""
Jesse Candles Management Tools

MCP counterparts of the dashboard's candle pages (Import Candles, Manage Candles, and the
Custom Data importer), calling the same authenticated candle routes:

- search_symbols: Find importable symbols on a candle source by ticker or instrument name
- import_candles / get_candle_import_status / cancel_candle_import: background imports
- get_existing_candles: List stored exchange/symbol pairs and their date coverage
- delete_candles / purge_candles: Delete one stored pair, or every pair of whole exchanges
- copy_candles: Duplicate (or move) a stored series under another exchange or symbol name
- export_candles: Write a stored series as CSV into the project's research_scripts/ folder
- preview_custom_candle_csv / clean_and_import_custom_candle_csv: Import a CSV as Custom Data
- get_candles: The small candle window the dashboard's live chart starts from
- clear_candle_cache: Clear the on-disk cache of candles loaded for backtests

Files: remote assistants exchange CSV files with Jesse through the project folders
(`project_path` under research_scripts/ or strategies/, see the project file tools); a
`file_path` is an absolute path on the Jesse host itself.

The tools are async and run their work in a worker thread (see offload.py): the API calls,
and for the custom CSV tools also reading and cleaning the file.
"""

from typing import List, Literal, Optional

from jesse.mcp.tools.offload import run_blocking
from jesse.mcp.tools.services.candles import (
    DEFAULT_CANDLE_SETS_LIMIT,
    DEFAULT_CHART_CANDLES_LIMIT,
    import_candles_service,
    cancel_candle_import_service,
    clear_candle_cache_service,
    get_candles_service,
    get_candle_import_status_service,
    get_existing_candles_service,
    delete_candles_service,
    purge_candles_service,
    export_candles_service,
    preview_custom_candle_csv_service,
    clean_and_import_custom_candle_csv_service,
    search_symbols_service,
    copy_candles_service,
)


def register_candles_tools(mcp):
    """
    Register the candle management tools with the MCP server.

    Args:
        mcp: The MCP server instance.

    Returns:
        None
    """

    @mcp.tool()
    async def preview_custom_candle_csv(
        symbol: str,
        project_path: Optional[str] = None,
        file_path: Optional[str] = None,
        timestamp_format: str = 'auto',
        timestamp_column: str = 'timestamp',
        open_column: str = 'open',
        close_column: str = 'close',
        high_column: str = 'high',
        low_column: str = 'low',
        volume_column: str = 'volume',
    ) -> dict:
        """Preview how a one-minute candle CSV would be cleaned and imported as Custom Data.

        Pass exactly one source:
        - `project_path`: a .csv inside the Jesse project, under research_scripts/ or strategies/
          (for example one you wrote with write_project_file or one export_candles produced).
          Use this when you are not running on the Jesse host.
        - `file_path`: an absolute path on the Jesse host. Only works when you run on that same
          machine; a path on your own computer does not exist there.

        The preview maps the named columns, converts timestamps (`auto`, `unix_ms`, `unix_s`,
        `iso8601` with an offset or Z) to Unix milliseconds, sorts rows, removes identical
        duplicate timestamps, and reports invalid or conflicting rows without importing anything.
        Missing minutes remain gaps. `symbol` must be BASE-QUOTE (e.g. SPY-USD).

        After reviewing `cleaning_report`, call clean_and_import_custom_candle_csv with the same
        source and explicitly choose `invalid_row_policy="reject"` or `"drop"`.
        """
        return await run_blocking(
            preview_custom_candle_csv_service,
            file_path=file_path,
            symbol=symbol,
            timestamp_format=timestamp_format,
            timestamp_column=timestamp_column,
            open_column=open_column,
            close_column=close_column,
            high_column=high_column,
            low_column=low_column,
            volume_column=volume_column,
            project_path=project_path,
        )

    @mcp.tool()
    async def clean_and_import_custom_candle_csv(
        symbol: str,
        invalid_row_policy: Literal['reject', 'drop'],
        project_path: Optional[str] = None,
        file_path: Optional[str] = None,
        timestamp_format: str = 'auto',
        timestamp_column: str = 'timestamp',
        open_column: str = 'open',
        close_column: str = 'close',
        high_column: str = 'high',
        low_column: str = 'low',
        volume_column: str = 'volume',
    ) -> dict:
        """Clean a CSV and import it atomically as `Custom Data / SYMBOL / 1m`.

        The source is `project_path` (a .csv in the Jesse project) or `file_path` (an absolute
        path on the Jesse host), exactly as in preview_custom_candle_csv.

        Use `reject` to fail when any row is invalid. Use `drop` only after reviewing the preview;
        malformed rows are omitted and reported. Both policies sort timestamps and remove identical
        duplicates. Conflicting candles at one timestamp always fail, and gaps are never filled.
        If the symbol already has Custom Data candles, new timestamps are added and timestamps
        already stored keep their existing values. The source file is never modified.
        """
        return await run_blocking(
            clean_and_import_custom_candle_csv_service,
            file_path=file_path,
            symbol=symbol,
            invalid_row_policy=invalid_row_policy,
            timestamp_format=timestamp_format,
            timestamp_column=timestamp_column,
            open_column=open_column,
            close_column=close_column,
            high_column=high_column,
            low_column=low_column,
            volume_column=volume_column,
            project_path=project_path,
        )

    @mcp.tool()
    async def import_candles(
        exchange: str,
        symbol: str,
        start_date: str,
        import_id: Optional[str] = None,
    ) -> dict:
        """Start a background candle import and return as soon as Jesse accepts it.

        `exchange` is a historical candle source exactly as Jesse lists it: the crypto
        exchanges (e.g. "Binance Perpetual Futures", "Binance Spot", "Bybit USDT Perpetual",
        "Coinbase Spot", "Kraken Pro Futures") and the Massive sources ("Massive Stocks",
        "Massive Currencies", "Massive Indices", "Massive Futures"; these need a saved Massive key,
        see jesse://credentials). `symbol` is BASE-QUOTE; when the user names an instrument, find
        the exact symbol with search_symbols first. `start_date` is YYYY-MM-DD and must be before
        today (UTC). An unsupported source, date, or symbol is rejected at once with Jesse's error.

        Only one-minute candles are imported and stored; every other timeframe is generated from them in
        backtests and the research modes, so there is no timeframe parameter. Candles already
        stored are kept and skipped. To update a stored series to today (the dashboard's Update
        button), import it again from its `start_date` as get_existing_candles shows it; Custom
        Data cannot be updated this way.

        After `status: "started"`, check get_candle_import_status(import_id) every few seconds
        until it is `finished`, `failed`, or `cancelled`. The dashboard runs one import per
        exchange at a time; wait for one to finish before starting another on the same exchange.
        `import_id` defaults to a new UUID; passing an earlier one reuses that ID for a new run.
        """
        return await run_blocking(
            import_candles_service,
            exchange=exchange,
            symbol=symbol,
            start_date=start_date,
            import_id=import_id
        )

    @mcp.tool()
    async def cancel_candle_import(import_id: str) -> dict:
        """Cancel a running candle import (the dashboard's Cancel button).

        Jesse marks the import as `cancelled` right away and the import process stops at its
        next check. Candles stored before that remain in the database. The status is set to
        `cancelled` even if the import had already ended, so only cancel imports you started and
        that get_candle_import_status still reports as `running`.
        """
        return await run_blocking(cancel_candle_import_service, import_id)

    @mcp.tool()
    async def get_candle_import_status(import_id: str) -> dict:
        """Check a candle import started with import_candles.

        A fast Redis lookup on the Jesse host. `status` is `running` (with `progress`: percent,
        date reached, estimated seconds left), `finished` (with `result.message`), `failed`
        (with `error` and `traceback`), or `cancelled`. An ID Jesse has no record of also reports
        `finished`, so only check IDs returned by import_candles.
        """
        return await run_blocking(get_candle_import_status_service, import_id)

    @mcp.tool()
    async def clear_candle_cache() -> dict:
        """Delete Jesse's on-disk cache of candles loaded for backtests and research runs.

        Stored candles are not touched. Use it only when a run keeps using stale data after
        candles were deleted, re-imported, or copied; the next run reloads from the database.
        """
        return await run_blocking(clear_candle_cache_service)

    @mcp.tool()
    async def get_candles(
        exchange: str,
        symbol: str,
        timeframe: str,
        limit: int = DEFAULT_CHART_CANDLES_LIMIT,
    ) -> dict:
        """Return the stored candles the dashboard's live chart starts from.

        This is NOT a historical reader: it returns at most the live `warm_up_candles` setting's
        number of `timeframe` candles ending now (built from one-minute rows when the live
        `generate_candles_from_1m` setting is on), so it is empty for data that ends in the past.
        Only the newest `limit` (1-1000) are returned; `truncated` says whether more existed.
        Each candle has `time` (Unix seconds), `open`, `close`, `high`, `low`, `volume`.

        For stored date coverage use get_existing_candles; to read a whole stored series, write
        it into the project with export_candles and read it with read_project_file.
        """
        return await run_blocking(
            get_candles_service, exchange=exchange, symbol=symbol, timeframe=timeframe, limit=limit,
        )

    @mcp.tool()
    async def get_existing_candles(
        exchange: Optional[str] = None,
        symbol: Optional[str] = None,
        availability: Literal['all', 'backtesting', 'live'] = 'all',
        offset: int = 0,
        limit: int = DEFAULT_CANDLE_SETS_LIMIT,
    ) -> dict:
        """List stored candles: one entry per exchange and symbol (the Manage Candles table).

        Each entry has `exchange`, `symbol`, `start_date` and `end_date` (first and last stored
        UTC day), `backtesting_supported` (the exchange can be used in backtests), and
        `updatable` (it is an import source, so import_candles can extend it). Coverage can have
        gaps between those dates; a backtest reports any missing range.

        Filters work like the dashboard's: `exchange` and `symbol` match case-insensitive
        substrings, and `availability` is `all`, `backtesting` (backtesting exchanges), or `live`
        (live-only exchanges). Results are sorted by exchange and symbol; page with `offset` and
        `limit` (1-1000) using `next_offset`. Listing scans the candle table and can take a while
        on large databases. Do not call this before a backtest to pre-check data (see
        jesse://candle); use it when the user asks what data exists or to verify an import.
        """
        return await run_blocking(
            get_existing_candles_service,
            exchange=exchange,
            symbol=symbol,
            availability=availability,
            offset=offset,
            limit=limit,
        )

    @mcp.tool()
    async def delete_candles(exchange: str, symbol: str) -> dict:
        """Permanently delete every stored candle of one exchange/symbol pair.

        Same scope as the dashboard's Delete on Manage Candles: all stored rows of that pair,
        every timeframe, across its whole date range. It cannot be undone. `exchange` and
        `symbol` must match get_existing_candles exactly; `deleted_count` 0 means nothing was
        stored under that name. Only delete what the user asked to remove.
        """
        return await run_blocking(delete_candles_service, exchange=exchange, symbol=symbol)

    @mcp.tool()
    async def purge_candles(exchanges: List[str]) -> dict:
        """Permanently delete every stored candle of whole exchanges (all their symbols).

        The dashboard's "Purge Candles by Exchange" action. Pass the exchange names exactly as
        get_existing_candles shows them. It cannot be undone and removes every symbol stored under
        each listed exchange, so only use it when the user asked to purge those exchanges; to
        remove one symbol use delete_candles.
        """
        return await run_blocking(purge_candles_service, exchanges=exchanges)

    @mcp.tool()
    async def export_candles(
        exchange: str,
        symbol: str,
        path: Optional[str] = None,
        overwrite: bool = False,
    ) -> dict:
        """Write a stored candle series as CSV into the Jesse project's research_scripts/ folder.

        The file is the same one the dashboard's Export button downloads: the complete stored
        one-minute series of the pair, oldest first, with columns timestamp (Unix ms), open,
        close, high, low, volume. It stays on the Jesse host inside the project; only a summary
        (path, row count, size, first and last candle) comes back. Use it to:
        - read the data in pages with read_project_file(path, start_line, max_lines),
        - feed a research script the user asked for, or
        - re-import it as Custom Data with clean_and_import_custom_candle_csv(project_path=path).
        To get the file onto the user's own computer, point them to Export on the dashboard's
        Manage Candles page (`dashboard_download_page`).

        `path` is a project-relative .csv under research_scripts/ (default
        research_scripts/candle_exports/<exchange>_<symbol>_1m.csv). An existing file is replaced
        only with `overwrite=True`. A series with no one-minute candles is `not_found`.
        """
        return await run_blocking(
            export_candles_service, exchange=exchange, symbol=symbol, path=path, overwrite=overwrite,
        )

    @mcp.tool()
    async def search_symbols(exchange: str, query: str, limit: int = 20) -> dict:
        """Find importable symbols on one candle source by ticker prefix or instrument name.

        Use this before import_candles() when the user names an instrument rather than an
        exact Jesse symbol, or when a Massive import fails with a symbol-not-found error.
        Ticker prefixes rank first, then symbols whose provider name contains the query.

        - Crypto exchanges (e.g. "Binance Perpetual Futures") match tickers only, such as "BTC".
        - Massive sources ("Massive Stocks", "Massive Currencies", "Massive Indices",
          "Massive Futures") also match names such as "microsoft" or "crude", and each match
          carries `name`, `kind` (Common Stock, ETF, Forex, Crypto, Index, Future), `venue`,
          and for futures `expiry`. Every source has its own catalogue: Microsoft the company
          lives on Massive Stocks as MSFT-USD, while Massive Futures lists CME stock futures
          on Microsoft such as SMSFTU6-USD. Pick the source that matches the user's intent.

        Pass the returned `symbol` value verbatim to import_candles().
        """
        return await run_blocking(search_symbols_service, exchange=exchange, query=query, limit=limit)

    @mcp.tool()
    async def copy_candles(
        exchange: str,
        symbol: str,
        target_exchange: str,
        target_symbol: Optional[str] = None,
        delete_source: bool = False,
    ) -> dict:
        """Duplicate stored candles under another exchange name (and optionally another symbol).

        Use this when the user wants to backtest data they already imported as if it belonged
        to a different market, for example run Massive Stocks "SPY-USD" under
        "Binance Perpetual Futures" as "SPY-USDT" to use that exchange's futures simulation.
        Every stored row of the pair is copied (backtests generate every other timeframe
        from the one-minute rows at run time, so they follow automatically). `target_exchange` must be a
        backtesting-capable exchange name exactly as Jesse lists it (the source exchange with a
        new symbol also works), and `target_symbol` defaults to `symbol`; set it when the target
        market quotes in another currency (USD vs USDT).

        The copy refuses to run if the target already has candles, so nothing is ever merged.
        With `delete_source=True` the original is removed once the copy completes (a rename);
        confirm with the user before doing that, and never do it for data that is still being
        updated from its provider, because updates only work under the original exchange name.
        A very large copy is written in chunks; if it is interrupted, delete the partial target
        before retrying.
        """
        return await run_blocking(
            copy_candles_service,
            exchange=exchange,
            symbol=symbol,
            target_exchange=target_exchange,
            target_symbol=target_symbol,
            delete_source=delete_source,
        )
