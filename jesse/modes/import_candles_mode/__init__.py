import json
import math
import time
from typing import Dict, List, Any, Union

import arrow
import pydash

import jesse.helpers as jh
from jesse.exceptions import CandleNotFoundInExchange
from jesse.enums import live_session_modes
from jesse.models.Candle import Candle
from jesse.modes.import_candles_mode.drivers import (
    build_historical_provider_registry,
    historical_provider_names,
)
from jesse.modes.import_candles_mode.drivers.interface import CandleExchange
from jesse.config import config
from jesse.services.failure import register_custom_exception_handler
from jesse.services.redis import sync_publish, is_process_active, sync_redis
from jesse.services.env import ENV_VALUES
from jesse.store import store
from jesse import exceptions
from jesse.services.historical_data import (
    HistoricalCandleRange,
    HistoricalCandleRequest,
)
from jesse.services.historical_data.errors import ProviderPaginationError
from jesse.repositories import candle_repository


# Retained only for the inactive legacy fill helper; the shared importer never synthesizes gaps.
MAX_MISSING_EDGE_MINUTES = 50


def candle_import_progress_key(client_id: str) -> str:
    return f"{ENV_VALUES.get('APP_PORT', '9000')}|candle-import-progress|{client_id}"


def candle_import_outcome_key(client_id: str) -> str:
    return f"{ENV_VALUES.get('APP_PORT', '9000')}|candle-import-outcome|{client_id}"


def store_import_outcome(
    client_id: str,
    status: str,
    error: str = None,
    error_traceback: str = None,
    result: dict | None = None,
) -> None:
    """Persist a terminal import outcome so polling clients receive the real result."""
    payload = {'status': status}
    if error is not None:
        payload['error'] = error
    if error_traceback is not None:
        payload['traceback'] = error_traceback
    if result is not None:
        payload['result'] = result

    try:
        sync_redis.set(
            candle_import_outcome_key(client_id),
            json.dumps(payload),
            # Keep terminal details available for delayed MCP polling while
            # ensuring abandoned import IDs expire without manual cleanup.
            ex=86400,
        )
    except Exception:
        pass


def get_import_outcome(client_id: str) -> dict:
    """Return the persisted terminal outcome, or an empty mapping when unavailable."""
    try:
        raw = sync_redis.get(candle_import_outcome_key(client_id))
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def validate_import_request(exchange: str, symbol: str, start_date_str: str) -> tuple[int, str]:
    """Validate values that can be rejected before an import worker is started."""
    if exchange not in historical_provider_names:
        raise ValueError(
            f'{exchange} is not a supported historical provider. '
            f'Supported providers are: {historical_provider_names}'
        )

    try:
        start_timestamp = jh.arrow_to_timestamp(arrow.get(start_date_str, 'YYYY-MM-DD'))
    except Exception:
        raise ValueError(
            'start_date must be a string representing a date before today. '
            f'ex: 2020-01-17. You entered: {start_date_str}'
        )

    today = arrow.utcnow().floor('day').int_timestamp * 1000
    if start_timestamp == today:
        raise ValueError("Today's date is not accepted. start_date must represent a date BEFORE today.")
    if start_timestamp > today:
        raise ValueError("Future's date is not accepted. start_date must represent a date BEFORE today.")

    # quote_asset() enforces Jesse's BASE-QUOTE symbol contract.
    try:
        jh.quote_asset(symbol)
    except exceptions.InvalidRoutes as e:
        raise ValueError(str(e)) from None
    return start_timestamp, symbol.upper()


def _raise_if_cancelled(client_id: str, running_via_dashboard: bool) -> None:
    """Stop from the active import path when the API removes its process marker."""
    if running_via_dashboard and not is_process_active(client_id):
        raise exceptions.Termination


def _print_import_progressbar(exchange: str, symbol: str, percent: float, remaining_seconds: float,
                              reached_date: str) -> None:
    """
    Render a compact progress bar for CLI and research imports, including a
    human-readable ETA and the latest date reached.
    """
    width = 32
    filled = max(0, min(width, int(round(width * percent / 100))))
    bar = '█' * filled + '░' * (width - filled)

    secs = max(0, int(round(remaining_seconds)))
    if secs >= 3600:
        eta = f'{secs // 3600}h {secs % 3600 // 60:02d}m'
    elif secs >= 60:
        eta = f'{secs // 60}m {secs % 60:02d}s'
    else:
        eta = f'{secs}s'

    print(f'  Importing {symbol} on {exchange}')
    print(f'  [{bar}] {percent:5.1f}%')
    print(f'  reached {reached_date}  •  ETA {eta}')


def _store_import_progress(client_id: str, current, estimated_remaining_seconds, current_date: str) -> None:
    """
    Persist live import progress to Redis so /candles/import-status (and the MCP
    get_candle_import_status tool) can report real progress — percent complete,
    ETA, and the date reached so far — instead of only running/finished. Best-effort:
    a Redis hiccup must never break an import. The key carries a TTL so it self-cleans.
    """
    try:
        sync_redis.set(
            candle_import_progress_key(client_id),
            json.dumps({
                'current': current,
                'estimated_remaining_seconds': estimated_remaining_seconds,
                'current_date': current_date,
            }),
            ex=86400,
        )
    except Exception:
        pass


def _missing_import_ranges(
    requested_start: int,
    requested_end: int,
    first_stored: int | None,
    latest_stored: int | None,
    interval: int,
) -> list[tuple[int, int]]:
    """Return uncovered outer ranges while treating interior sparse gaps as intentional."""
    if first_stored is None or latest_stored is None:
        return [(requested_start, requested_end)]

    ranges = []
    prefix_end = min(first_stored, requested_end)
    if requested_start < prefix_end:
        ranges.append((requested_start, prefix_end))

    suffix_start = max(requested_start, latest_stored + interval)
    if suffix_start < requested_end:
        ranges.append((suffix_start, requested_end))
    return ranges


def _report_import_progress(
    client_id: str,
    exchange: str,
    symbol: str,
    completed_span: int,
    total_span: int,
    remaining_seconds: float,
    reached_timestamp: int,
    running_via_dashboard: bool,
    show_progressbar: bool,
) -> None:
    """Publish range-based progress because candle counts do not measure sparse coverage."""
    percent = round(min(max(completed_span / total_span * 100, 0), 100), 1)
    reached_date = jh.timestamp_to_date(reached_timestamp)
    _store_import_progress(client_id, percent, remaining_seconds, reached_date)
    if running_via_dashboard:
        sync_publish('progressbar', {
            'current': percent,
            'estimated_remaining_seconds': remaining_seconds,
        })
    if show_progressbar:
        jh.clear_output()
        _print_import_progressbar(exchange, symbol, percent, remaining_seconds, reached_date)


def _missing_live_candle_ranges(
    exchange: str, symbol: str, start: int, end: int, max_candles: int,
) -> list[tuple[int, int]]:
    """Cover absent live minutes with provider-sized pages, preserving sparse observations."""
    ranges = []
    cursor = start
    for candle in candle_repository.fetch_candles_from_db(exchange, symbol, '1m', start, end - 60_000):
        timestamp = int(candle[0])
        if timestamp > cursor:
            ranges.append((cursor, timestamp))
        cursor = timestamp + 60_000
    if cursor < end:
        ranges.append((cursor, end))

    # Thousands of isolated no-trade minutes must not cause thousands of requests
    # on every restart. Re-reading stored rows is safe because inserts retain them.
    page_span = max_candles * 60_000
    pages = []
    for missing_start, missing_end in ranges:
        if pages and missing_start <= pages[-1][1]:
            page_start, page_end = pages.pop()
            missing_end = max(missing_end, page_end)
        else:
            page_start = missing_start
        page_count = (missing_end - page_start + page_span - 1) // page_span
        pages.append((page_start, min(end, page_start + page_count * page_span)))
    return pages


def run(
        client_id: str,
        exchange: str,
        symbol: str,
        start_date_str: str,
        mode: str = 'candles',
        running_via_dashboard: bool = True,
        show_progressbar: bool = False,
):
    """Run an import and retain its terminal state for API and MCP polling."""
    if running_via_dashboard:
        store_import_outcome(client_id, 'running')

    try:
        result = _run(
            client_id,
            exchange,
            symbol,
            start_date_str,
            mode,
            running_via_dashboard,
            show_progressbar,
        )
    except exceptions.Termination:
        if running_via_dashboard:
            store_import_outcome(client_id, 'cancelled')
        raise
    except Exception as e:
        if running_via_dashboard:
            import traceback

            store_import_outcome(
                client_id,
                'failed',
                f'{type(e).__name__}: {e}',
                traceback.format_exc(),
            )
        raise
    else:
        if running_via_dashboard:
            store_import_outcome(client_id, 'finished', result=result)
        return result


def _run(
        client_id: str,
        exchange: str,
        symbol: str,
        start_date_str: str,
        mode: str = 'candles',
        running_via_dashboard: bool = True,
        show_progressbar: bool = False,
):
    start_timestamp, symbol = validate_import_request(exchange, symbol, start_date_str)

    if running_via_dashboard:
        config['app']['trading_mode'] = mode
        register_custom_exception_handler()
        store.app.set_session_id(client_id)

    _raise_if_cancelled(client_id, running_via_dashboard)

    # open database connection
    from jesse.services.db import database
    database.open_connection()

    provider = build_historical_provider_registry((exchange,)).get(exchange)
    # Crypto startup needs today's closed bars. Provider ranges are half-open, so the
    # current minute is excluded; traditional historical providers retain their daily cutoff.
    end_timestamp = arrow.utcnow().floor('minute' if isinstance(provider, CandleExchange) else 'day').int_timestamp * 1000
    max_candles = provider.capabilities.max_candles_per_request
    if max_candles is None:
        raise ValueError(f'Historical provider {exchange!r} does not declare a request range limit')

    # M3 persists the provider's native one-minute bars; higher timeframes are deferred to M4B.
    interval = 60_000
    first_timestamp, latest_timestamp = candle_repository.get_candle_timestamp_bounds(
        exchange,
        symbol,
        '1m',
    )
    effective_start_timestamp = start_timestamp
    if first_timestamp is None or start_timestamp < first_timestamp:
        # Provider data access can begin years after a symbol's listing date; probe the actual
        # entitled range once instead of issuing one empty page request per historical chunk.
        availability_request = HistoricalCandleRequest(
            symbol=symbol,
            timeframe='1m',
            requested_range=HistoricalCandleRange(start_timestamp, end_timestamp),
            adjustment_mode=provider.capabilities.default_adjustment_mode,
        )
        available_timestamp = provider.find_earliest_available_timestamp(availability_request)
        if available_timestamp is None:
            if first_timestamp is None:
                raise CandleNotFoundInExchange(
                    f'No observed candles were returned for {symbol} on {exchange} in the requested range'
                )
            effective_start_timestamp = first_timestamp
        else:
            effective_start_timestamp = max(start_timestamp, available_timestamp)

    import_ranges = _missing_import_ranges(
        effective_start_timestamp,
        end_timestamp,
        first_timestamp,
        latest_timestamp,
        interval,
    )
    if isinstance(provider, CandleExchange) and mode in (
        live_session_modes.LIVETRADE, live_session_modes.PAPERTRADE,
    ):
        # Stored endpoints do not prove live warm-up coverage: WebSocket writes may
        # bracket a downtime gap. Historical imports still preserve intentional sparse gaps.
        import_ranges = _missing_live_candle_ranges(
            exchange, symbol, effective_start_timestamp, end_timestamp, max_candles,
        )
    total_span = end_timestamp - effective_start_timestamp
    work_span = sum(range_end - range_start for range_start, range_end in import_ranges)
    completed_span = total_span - work_span
    completed_work = 0
    processed_candles = 0
    observed_first_timestamp = first_timestamp
    observed_latest_timestamp = latest_timestamp
    started_at = time.monotonic()

    if not import_ranges:
        _report_import_progress(
            client_id,
            exchange,
            symbol,
            completed_span,
            total_span,
            0,
            end_timestamp - interval,
            running_via_dashboard,
            show_progressbar,
        )

    for range_start, range_end in import_ranges:
        # Prefix backfills move toward older timestamps so each committed page extends the stored
        # boundary. A failed run therefore remains resumable instead of bracketing an interior hole.
        is_prefix_backfill = first_timestamp is not None and range_end <= first_timestamp
        cursor = range_end if is_prefix_backfill else range_start
        while (cursor > range_start if is_prefix_backfill else cursor < range_end):
            _raise_if_cancelled(client_id, running_via_dashboard)
            if is_prefix_backfill:
                page_start = max(range_start, cursor - max_candles * interval)
                page_end = cursor
            else:
                page_start = cursor
                page_end = min(range_end, cursor + max_candles * interval)
            request = HistoricalCandleRequest(
                symbol=symbol,
                timeframe='1m',
                requested_range=HistoricalCandleRange(page_start, page_end),
                adjustment_mode=provider.capabilities.default_adjustment_mode,
            )
            batch = provider.fetch_candles(request)
            if batch.continuation_token is not None:
                raise ProviderPaginationError(
                    f'Historical provider {exchange!r} returned more data than its declared request limit'
                )

            _raise_if_cancelled(client_id, running_via_dashboard)
            if (
                is_prefix_backfill
                and not batch.candles
                and batch.next_available_timestamp is not None
                and batch.next_available_timestamp >= page_end
            ):
                # The exchange answered a pre-listing page with its first real candle, so nothing
                # older exists: finish the prefix instead of paging through empty history.
                completed_work += page_end - range_start
                _report_import_progress(
                    client_id,
                    exchange,
                    symbol,
                    completed_span + completed_work,
                    total_span,
                    0,
                    range_start,
                    running_via_dashboard,
                    show_progressbar,
                )
                cursor = range_start
                continue
            candle_repository.store_observed_candles(exchange, symbol, '1m', batch.candles)
            processed_candles += len(batch.candles)
            if batch.candles:
                batch_first_timestamp = batch.candles[0].timestamp
                batch_latest_timestamp = batch.candles[-1].timestamp
                observed_first_timestamp = (
                    batch_first_timestamp
                    if observed_first_timestamp is None
                    else min(observed_first_timestamp, batch_first_timestamp)
                )
                observed_latest_timestamp = (
                    batch_latest_timestamp
                    if observed_latest_timestamp is None
                    else max(observed_latest_timestamp, batch_latest_timestamp)
                )
            _raise_if_cancelled(client_id, running_via_dashboard)

            covered_end = page_end
            if (
                not is_prefix_backfill
                and batch.next_available_timestamp is not None
                and batch.next_available_timestamp > covered_end
            ):
                # This hint comes from an actual returned candle, not an inferred listing calendar.
                covered_end = min(batch.next_available_timestamp, range_end)

            completed_work += covered_end - page_start
            completed = completed_span + completed_work
            elapsed = time.monotonic() - started_at
            remaining_work = work_span - completed_work
            remaining_seconds = elapsed / completed_work * remaining_work if completed_work else 0
            _report_import_progress(
                client_id,
                exchange,
                symbol,
                completed,
                total_span,
                remaining_seconds,
                page_start if is_prefix_backfill else covered_end - interval,
                running_via_dashboard,
                show_progressbar,
            )
            cursor = page_start if is_prefix_backfill else covered_end

            if completed_work < work_span and provider.capabilities.request_delay_seconds:
                time.sleep(provider.capabilities.request_delay_seconds)

    if (
        observed_first_timestamp is None
        or observed_latest_timestamp is None
        or observed_latest_timestamp < effective_start_timestamp
        or observed_first_timestamp >= end_timestamp
    ):
        raise CandleNotFoundInExchange(
            f'No observed candles were returned for {symbol} on {exchange} in the requested range'
        )
    actual_start_timestamp = max(start_timestamp, observed_first_timestamp)
    actual_end_timestamp = min(end_timestamp - interval, observed_latest_timestamp)
    requested_start_date = jh.timestamp_to_date(start_timestamp)
    actual_start_date = jh.timestamp_to_date(actual_start_timestamp)
    actual_end_date = jh.timestamp_to_date(actual_end_timestamp)
    success_text = (
        f'Successfully processed {processed_candles} observed candles since '
        f'"{actual_start_date}" through "{actual_end_date}". '
        'Existing rows were retained.'
    )
    if actual_start_timestamp > start_timestamp:
        success_text = (
            f'The requested start was "{requested_start_date}"; the earliest available candle was '
            f'"{actual_start_date}". {success_text}'
        )
    import_result = {
        'exchange': exchange,
        'symbol': symbol,
        'timeframe': '1m',
        'requested_start_timestamp': start_timestamp,
        'requested_start_date': requested_start_date,
        'actual_start_timestamp': actual_start_timestamp,
        'actual_start_date': actual_start_date,
        'actual_end_timestamp': actual_end_timestamp,
        'actual_end_date': actual_end_date,
        'processed_candles': processed_candles,
        'message': success_text,
    }

    _raise_if_cancelled(client_id, running_via_dashboard)

    if running_via_dashboard:
        sync_publish('alert', {
            'message': success_text,
            'type': 'success'
        })
        return import_result

    # # TODO: shen should it close the database?
    # # if it is to skip, then it's being called from another process hence we should leave the database be
    # if not skip_confirmation:
    if not running_via_dashboard:
        # close database connection
        from jesse.services.db import database
        database.close_connection()
        return success_text


def _get_candles_from_backup_exchange(exchange: str, backup_driver: CandleExchange, symbol: str, start_timestamp: int,
                                      end_timestamp: int) -> List[Dict[str, Union[str, Any]]]:
    timeframe = '1m'
    total_candles = []
    # try fetching from database first
    backup_candles = Candle.select(
        Candle.timestamp, Candle.open, Candle.close, Candle.high, Candle.low,
        Candle.volume
    ).where(
        Candle.exchange == backup_driver.name,
        Candle.symbol == symbol,
        Candle.timeframe == timeframe,
        Candle.timestamp.between(start_timestamp, end_timestamp)
    ).order_by(Candle.timestamp.asc()).tuples()
    already_exists = len(backup_candles) == (end_timestamp - start_timestamp) / 60_000 + 1
    if already_exists:
        # loop through them and set new ID and exchange
        for c in backup_candles:
            total_candles.append({
                'id': jh.generate_unique_id(),
                'exchange': exchange,
                'symbol': symbol,
                'timeframe': timeframe,
                'timestamp': c[0],
                'open': c[1],
                'close': c[2],
                'high': c[3],
                'low': c[4],
                'volume': c[5]
            })

        return total_candles

    # try fetching from market now
    days_count = jh.date_diff_in_days(jh.timestamp_to_arrow(start_timestamp), jh.timestamp_to_arrow(end_timestamp))
    # make sure it's rounded up so that we import maybe more candles, but not less
    days_count = max(days_count, 1)
    if type(days_count) is float and not days_count.is_integer():
        days_count = math.ceil(days_count)
    candles_count = days_count * 1440
    start_date = jh.timestamp_to_arrow(start_timestamp).floor('day')
    for _ in range(candles_count):
        temp_start_timestamp = start_date.int_timestamp * 1000
        temp_end_timestamp = temp_start_timestamp + (backup_driver.count - 1) * 60000

        # to make sure it won't try to import candles from the future! LOL
        if temp_start_timestamp > jh.now_to_timestamp():
            break

        # prevent duplicates
        count = Candle.select().where(
            Candle.exchange == backup_driver.name,
            Candle.symbol == symbol,
            Candle.timeframe == timeframe,
            Candle.timestamp.between(temp_start_timestamp, temp_end_timestamp)
        ).count()
        already_exists = count == backup_driver.count

        if not already_exists:
            # it's today's candles if temp_end_timestamp < now
            if temp_end_timestamp > jh.now_to_timestamp():
                temp_end_timestamp = arrow.utcnow().floor('minute').int_timestamp * 1000 - 60000

            # fetch from market
            candles = _fetch_normalized_candles(
                backup_driver, symbol, temp_start_timestamp, temp_end_timestamp, timeframe
            )

            if not len(candles):
                raise CandleNotFoundInExchange(
                    f'No candles exists in the market for this day: {jh.timestamp_to_time(temp_start_timestamp)[:10]} \n'
                    'Try another start_date'
                )

            # fill absent candles (if there's any)
            candles = _fill_absent_candles(candles, temp_start_timestamp, temp_end_timestamp)

            # store in the database
            store_candles_list(candles)

        # add as much as driver's count to the temp_start_time
        start_date = start_date.shift(minutes=backup_driver.count)

        # sleep so that the exchange won't get angry at us
        if not already_exists:
            time.sleep(backup_driver.sleep_time)

    # now try fetching from database again. Why? because we might have fetched more
    # than what's needed, but we only want as much was requested. Don't worry, the next
    # request will probably fetch from database and there won't be any waste!
    backup_candles = Candle.select(
        Candle.timestamp, Candle.open, Candle.close, Candle.high, Candle.low,
        Candle.volume
    ).where(
        Candle.exchange == backup_driver.name,
        Candle.symbol == symbol,
        Candle.timeframe == timeframe,
        Candle.timestamp.between(start_timestamp, end_timestamp)
    ).order_by(Candle.timestamp.asc()).tuples()
    already_exists = len(backup_candles) == (end_timestamp - start_timestamp) / 60_000 + 1
    if already_exists:
        # loop through them and set new ID and exchange
        for c in backup_candles:
            total_candles.append({
                'id': jh.generate_unique_id(),
                'exchange': exchange,
                'symbol': symbol,
                'timeframe': timeframe,
                'timestamp': c[0],
                'open': c[1],
                'close': c[2],
                'high': c[3],
                'low': c[4],
                'volume': c[5]
            })

        return total_candles


def _fill_absent_candles(temp_candles: List[Dict[str, Union[str, Any]]], start_timestamp: int, end_timestamp: int) -> \
        List[Dict[str, Union[str, Any]]]:
    if not temp_candles:
        raise CandleNotFoundInExchange(
            f'No candles exists in the market for this day: {jh.timestamp_to_time(start_timestamp)[:10]} \n'
            'Try another start_date'
        )

    latest_timestamp = max(int(c['timestamp']) for c in temp_candles)
    trailing_gap_minutes = max(0, int((end_timestamp - latest_timestamp) / 60_000))
    if trailing_gap_minutes > MAX_MISSING_EDGE_MINUTES:
        raise CandleNotFoundInExchange(
            f'Provider returned an incomplete trailing range for {temp_candles[0]["symbol"]} on '
            f'{temp_candles[0]["exchange"]}: {trailing_gap_minutes} minutes are missing after the '
            'last real candle. Refusing to generate a large synthetic candle tail.'
        )

    symbol = temp_candles[0]['symbol']
    exchange = temp_candles[0]['exchange']
    candles = []
    first_candle = temp_candles[0]
    started = False
    loop_length = ((end_timestamp - start_timestamp) / 60000) + 1

    for _ in range(int(loop_length)):
        candle_for_timestamp = pydash.find(
            temp_candles, lambda c: c['timestamp'] == start_timestamp)

        if candle_for_timestamp is None:
            if started:
                last_close = candles[-1]['close']
                candles.append({
                    'id': jh.generate_unique_id(),
                    'exchange': exchange,
                    'symbol': symbol,
                    'timeframe': '1m',
                    'timestamp': start_timestamp,
                    'open': last_close,
                    'high': last_close,
                    'low': last_close,
                    'close': last_close,
                    'volume': 0
                })
            else:
                candles.append({
                    'id': jh.generate_unique_id(),
                    'exchange': exchange,
                    'symbol': symbol,
                    'timeframe': '1m',
                    'timestamp': start_timestamp,
                    'open': first_candle['open'],
                    'high': first_candle['open'],
                    'low': first_candle['open'],
                    'close': first_candle['open'],
                    'volume': 0
                })
        # candle is present
        else:
            started = True
            candles.append(candle_for_timestamp)

        start_timestamp += 60000
    return candles


def _fetch_normalized_candles(
    provider: CandleExchange,
    symbol: str,
    start_timestamp: int,
    end_timestamp: int,
    timeframe: str,
) -> List[Dict[str, Union[str, Any]]]:
    """Fetch an inclusive storage range through the provider's half-open normalized contract."""
    interval = jh.timeframe_to_one_minutes(timeframe) * 60_000
    request = HistoricalCandleRequest(
        symbol=symbol,
        timeframe=timeframe,
        requested_range=HistoricalCandleRange(start_timestamp, end_timestamp + interval),
    )
    batch = provider.fetch_candles(request)
    return [
        {
            'id': jh.generate_unique_id(),
            'exchange': provider.name,
            'symbol': symbol,
            'timeframe': timeframe,
            'timestamp': candle.timestamp,
            'open': candle.open,
            'close': candle.close,
            'high': candle.high,
            'low': candle.low,
            'volume': candle.volume,
        }
        for candle in batch.candles
    ]


def store_candles_list(candles: List[Dict]) -> None:
    for c in candles:
        if 'timeframe' not in c:
            raise Exception('Candle has no timeframe')
    Candle.insert_many(candles).on_conflict_ignore().execute()
