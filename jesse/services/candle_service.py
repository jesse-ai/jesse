from typing import Tuple
import numpy as np
import arrow
from jesse.exceptions import CandleNotFoundInDatabase, InvalidDateRange, RouteNotFound
import jesse.helpers as jh
from jesse.services import logger
from jesse.routes import router
from timeloop import Timeloop
from datetime import timedelta
from jesse.store import store
from jesse.config import config
from jesse.repositories import candle_repository
from jesse.libs.dynamic_numpy_array import DynamicNumpyArray
from jesse_rust import candle_from_one_minutes as _candle_from_one_minutes_rust


def generate_candle_from_one_minutes(
        timeframe: str,
        candles: np.ndarray,
        accept_forming_candles: bool = False
) -> np.ndarray:
    if len(candles) == 0:
        raise ValueError('No candles were passed')

    if not accept_forming_candles and len(candles) != jh.timeframe_to_one_minutes(timeframe):
        raise ValueError(
            f'Sent only {len(candles)} candles but {jh.timeframe_to_one_minutes(timeframe)} is required to create a "{timeframe}" candle.'
        )

    # the Rust kernel is bit-exact vs numpy for blocks up to 4320 rows (every
    # timeframe through "3D"); beyond that numpy's buffered reduce changes the
    # summation order, so fall back to the original numpy expression there.
    if len(candles) <= 4320 and candles.dtype == np.float64:
        return _candle_from_one_minutes_rust(candles)

    return np.array([
        candles[0][0],
        candles[0][1],
        candles[-1][2],
        candles[:, 3].max(),
        candles[:, 4].min(),
        candles[:, 5].sum(),
    ])


def generate_candle_from_observed_minutes(timeframe: str, candles: np.ndarray) -> np.ndarray:
    """Aggregate observed 1m rows that belong to one clock-aligned timeframe bucket."""
    if len(candles) == 0:
        raise ValueError('No candles were passed')

    timeframe_ms = jh.timeframe_to_one_minutes(timeframe) * 60_000
    bucket_start = int(candles[0, 0]) - (int(candles[0, 0]) % timeframe_ms)
    if ((candles[:, 0].astype(np.int64) // timeframe_ms) * timeframe_ms != bucket_start).any():
        raise ValueError(f'Observed candles span more than one "{timeframe}" clock bucket.')

    generated = generate_candle_from_one_minutes(timeframe, candles, accept_forming_candles=True)
    generated[0] = bucket_start
    return generated


def generate_completed_candles_from_observed_minutes(
        timeframe: str,
        candles: np.ndarray,
        available_at: int,
) -> np.ndarray:
    """Aggregate nonempty clock buckets whose closing boundary is observable by ``available_at``."""
    if len(candles) == 0:
        return np.zeros((0, 6))

    timeframe_ms = jh.timeframe_to_one_minutes(timeframe) * 60_000
    bucket_starts = (candles[:, 0].astype(np.int64) // timeframe_ms) * timeframe_ms
    boundaries = np.flatnonzero(np.diff(bucket_starts)) + 1
    starts = np.concatenate(([0], boundaries))
    stops = np.concatenate((boundaries, [len(candles)]))
    generated = [
        generate_candle_from_observed_minutes(timeframe, candles[start:stop])
        for start, stop in zip(starts, stops)
        if bucket_starts[start] + timeframe_ms <= available_at
    ]
    return np.array(generated) if generated else np.zeros((0, 6))


def candle_dict_to_np_array(candle: dict) -> np.ndarray:
    return np.array([
        candle['timestamp'],
        candle['open'],
        candle['close'],
        candle['high'],
        candle['low'],
        candle['volume']
    ])


def print_candle(candle: np.ndarray, is_partial: bool, symbol: str) -> None:
    """
    Ever since the new GUI dashboard, this function should log instead of actually printing

    :param candle: np.ndarray
    :param is_partial: bool
    :param symbol: str
    """
    if jh.should_execute_silently():
        return

    candle_form = '  ==' if is_partial else '===='
    candle_info = f' {symbol} | {str(arrow.get(candle[0] / 1000))[:-9]} | {candle[1]} | {candle[2]} | {candle[3]} | {candle[4]} | {round(candle[5], 2)}'
    msg = candle_form + candle_info

    # store it in the log file
    logger.info(msg)


def is_bullish(candle: np.ndarray) -> bool:
    return candle[2] >= candle[1]


def is_bearish(candle: np.ndarray) -> bool:
    return candle[2] < candle[1]


def candle_includes_price(candle: np.ndarray, price: float) -> bool:
    return (price >= candle[4]) and (price <= candle[3])


def split_candle(candle: np.ndarray, price: float) -> tuple:
    """
    splits a single candle into two candles: earlier + later

    :param candle: np.ndarray
    :param price: float

    :return: tuple
    """
    timestamp = candle[0]
    o = candle[1]
    c = candle[2]
    h = candle[3]
    l = candle[4]
    v = candle[5]

    if is_bullish(candle) and l < price < o:
        return np.array([
            timestamp, o, price, o, price, v
        ]), np.array([
            timestamp, price, c, h, l, v
        ])
    elif price == o:
        return candle, candle
    elif is_bearish(candle) and o < price < h:
        return np.array([
            timestamp, o, price, price, o, v
        ]), np.array([
            timestamp, price, c, h, l, v
        ])
    elif is_bearish(candle) and l < price < c:
        return np.array([
            timestamp, o, price, h, price, v
        ]), np.array([
            timestamp, price, c, c, l, v
        ])
    elif is_bullish(candle) and c < price < h:
        return np.array([
            timestamp, o, price, price, l, v
        ]), np.array([
            timestamp, price, c, h, c, v
        ]),
    elif is_bearish(candle) and price == c:
        return np.array([
            timestamp, o, c, h, c, v
        ]), np.array([
            timestamp, price, price, price, l, v
        ])
    elif is_bullish(candle) and price == c:
        return np.array([
            timestamp, o, c, c, l, v
        ]), np.array([
            timestamp, price, price, h, price, v
        ])
    elif is_bearish(candle) and price == h:
        return np.array([
            timestamp, o, h, h, o, v
        ]), np.array([
            timestamp, h, c, h, l, v
        ])
    elif is_bullish(candle) and price == l:
        return np.array([
            timestamp, o, l, o, l, v
        ]), np.array([
            timestamp, l, c, h, l, v
        ])
    elif is_bearish(candle) and price == l:
        return np.array([
            timestamp, o, l, h, l, v
        ]), np.array([
            timestamp, l, c, c, l, v
        ])
    elif is_bullish(candle) and price == h:
        return np.array([
            timestamp, o, h, h, l, v
        ]), np.array([
            timestamp, h, c, h, c, v
        ])
    elif is_bearish(candle) and c < price < o:
        return np.array([
            timestamp, o, price, h, price, v
        ]), np.array([
            timestamp, price, c, price, l, v
        ])
    elif is_bullish(candle) and o < price < c:
        return np.array([
            timestamp, o, price, price, l, v
        ]), np.array([
            timestamp, price, c, h, price, v
        ])


def inject_warmup_candles_to_store(
        candles: np.ndarray,
        exchange: str,
        symbol: str,
        available_at: int | None = None,
) -> None:
    if candles is None or candles.size == 0:
        raise ValueError(f'Could not inject warmup candles because the passed candles are empty. Have you imported enough warmup candles for {exchange}/{symbol}?')

    from jesse.config import config

    if available_at is None:
        available_at = int(candles[-1, 0]) + 60_000
    observable_candles = candles[candles[:, 0] + 60_000 <= available_at]
    if len(observable_candles) == 0:
        raise ValueError(
            f'Warmup candles for {exchange}/{symbol} do not close before the common trading start.'
        )

    # Warmup must never preload a source row whose closing boundary is in the
    # trading period; doing so would expose its final OHLCV before simulation.
    batch_add_candle(observable_candles, exchange, symbol, '1m', with_generation=False)

    for timeframe in config['app']['considering_timeframes']:
        if timeframe == '1m':
            continue
        generated_candles = generate_completed_candles_from_observed_minutes(
            timeframe,
            observable_candles,
            available_at,
        )
        batch_add_candle(
            generated_candles,
            exchange,
            symbol,
            timeframe,
            with_generation=False,
        )


def get_candles_from_db(
        exchange: str,
        symbol: str,
        timeframe: str,
        start_date_timestamp: int,
        finish_date_timestamp: int,
        warmup_candles_num: int = 0,
        caching: bool = False,
        is_for_jesse: bool = False
) -> Tuple[np.ndarray, np.ndarray]:
    symbol = symbol.upper()

    # convert start_date and finish_date to timestamps
    trading_start_date_timestamp = jh.timestamp_to_arrow(start_date_timestamp).floor(
        'day').int_timestamp * 1000
    trading_finish_date_timestamp = (jh.timestamp_to_arrow(finish_date_timestamp).floor(
        'day').int_timestamp * 1000) - 60_000

    # if warmup_candles is set, calculate the warmup start and finish timestamps
    if warmup_candles_num > 0:
        warmup_finish_timestamp = trading_start_date_timestamp
        if timeframe == '1m' or is_for_jesse:
            warmup_candles = _get_observed_warmup_candles_from_db(
                exchange,
                symbol,
                warmup_finish_timestamp,
                warmup_candles_num,
                timeframe=timeframe,
                caching=caching,
            )
        else:
            warmup_start_timestamp = warmup_finish_timestamp - (
                    warmup_candles_num * jh.timeframe_to_one_minutes(timeframe) * 60_000)
            warmup_finish_timestamp -= 60_000
            warmup_candles = _get_candles_from_db(
                exchange,
                symbol,
                warmup_start_timestamp,
                warmup_finish_timestamp,
                caching=caching,
            )
    else:
        warmup_candles = None

    # fetch trading candles from database
    trading_candles = _get_candles_from_db(exchange, symbol, trading_start_date_timestamp,
                                           trading_finish_date_timestamp, caching=caching)

    # if timeframe is 1m or is_for_jesse is True, return the candles as is because they
    # are already 1m candles which is the accepted format for practicing with Jesse.
    if timeframe == '1m' or is_for_jesse:
        return warmup_candles, trading_candles

    # if the timeframe is not 1m, generate the candles for the requested timeframe
    if warmup_candles_num > 0:
        warmup_candles = _get_generated_candles(timeframe, warmup_candles)
    else:
        warmup_candles = None
    trading_candles = _get_generated_candles(timeframe, trading_candles)

    return warmup_candles, trading_candles


def _get_candles_from_db(
        exchange, symbol, start_date_timestamp, finish_date_timestamp, caching: bool = False
) -> np.ndarray:
    from jesse.models.Candle import Candle
    from jesse.services.cache import cache

    if caching:
        key = jh.key(exchange, symbol)
        cache_key = f"{start_date_timestamp}-{finish_date_timestamp}-{key}"
        cached_value = cache.get_value(cache_key)
        if cached_value:
            return np.array(cached_value)

    # validate the dates
    if start_date_timestamp == finish_date_timestamp:
        raise InvalidDateRange('start_date and finish_date cannot be the same.')
    if start_date_timestamp > finish_date_timestamp:
        raise InvalidDateRange(f'start_date ({jh.timestamp_to_date(start_date_timestamp)}) is greater than finish_date ({jh.timestamp_to_date(finish_date_timestamp)}).')
    
    # validate finish_date is not in the future
    current_timestamp = arrow.utcnow().int_timestamp * 1000
    if finish_date_timestamp > current_timestamp:
        yesterday_date = jh.timestamp_to_date(current_timestamp - 86400000)
        raise InvalidDateRange(f'The finish date "{jh.timestamp_to_time(finish_date_timestamp)[:19]}" cannot be in the future. Please select a date up to "{yesterday_date}".')

    # validate start_date is not in the future
    if start_date_timestamp > current_timestamp:
        raise InvalidDateRange(f'Can\'t backtest the future! start_date ({jh.timestamp_to_date(start_date_timestamp)}) is greater than the current time ({jh.timestamp_to_date(current_timestamp)}).')

    # Always materialize the database results immediately
    candles_tuple = list(Candle.select(
        Candle.timestamp, Candle.open, Candle.close, Candle.high, Candle.low,
        Candle.volume
    ).where(
        Candle.exchange == exchange,
        Candle.symbol == symbol,
        (Candle.timeframe == '1m') | (Candle.timeframe.is_null()),
        Candle.timestamp.between(start_date_timestamp, finish_date_timestamp)
    ).order_by(Candle.timestamp.asc()).tuples())

    # Check if we got any candles
    if not candles_tuple:
        raise CandleNotFoundInDatabase(f"No candles found for {symbol} on {exchange} between {jh.timestamp_to_date(start_date_timestamp)} and {jh.timestamp_to_date(finish_date_timestamp)}.")
    
    # Convert to numpy array for easier timestamp extraction
    candles_array = np.array(candles_tuple)
    
    if caching:
        # cache for 1 week it for near future calls
        cache.set_value(cache_key, candles_tuple, expire_seconds=60 * 60 * 24 * 7)

    return candles_array


def _get_observed_warmup_candles_from_db(
        exchange: str,
        symbol: str,
        trading_start_timestamp: int,
        candle_count: int,
        timeframe: str = '1m',
        caching: bool = False,
) -> np.ndarray:
    """Load source rows covering the requested number of completed observed clock buckets."""
    from jesse.models.Candle import Candle
    from jesse.services.cache import cache

    cache_key = (
        f'observed-warmup-{trading_start_timestamp}-{candle_count}-{timeframe}-'
        f'{jh.key(exchange, symbol)}'
    )
    if caching:
        cached_value = cache.get_value(cache_key)
        if cached_value:
            return np.array(cached_value)

    timeframe_minutes = jh.timeframe_to_one_minutes(timeframe)
    timeframe_ms = timeframe_minutes * 60_000
    required_bucket_starts: set[int] = set()
    cursor = trading_start_timestamp
    # Cap each requested bucket at one source-hour per page; the 1,000-row floor
    # avoids tiny repeated queries when closed sessions separate sparse buckets.
    page_size = max(candle_count * min(timeframe_minutes, 60), 1_000)
    while len(required_bucket_starts) < candle_count:
        timestamps = list(
            Candle.select(Candle.timestamp)
            .where(
                Candle.exchange == exchange,
                Candle.symbol == symbol,
                (Candle.timeframe == '1m') | Candle.timeframe.is_null(),
                Candle.timestamp < cursor,
            )
            .order_by(Candle.timestamp.desc())
            .limit(page_size)
            .tuples()
        )
        if not timestamps:
            break
        for (timestamp,) in timestamps:
            bucket_start = int(timestamp) - (int(timestamp) % timeframe_ms)
            if bucket_start + timeframe_ms <= trading_start_timestamp:
                required_bucket_starts.add(bucket_start)
        cursor = int(timestamps[-1][0])

    if len(required_bucket_starts) < candle_count:
        raise CandleNotFoundInDatabase(
            f'Only {len(required_bucket_starts)} of {candle_count} required completed {timeframe} '
            f'warmup candles were found '
            f'for {symbol} on {exchange} before {jh.timestamp_to_date(trading_start_timestamp)}.'
        )

    earliest_bucket_start = sorted(required_bucket_starts, reverse=True)[candle_count - 1]
    candles_tuple = list(
        Candle.select(
            Candle.timestamp,
            Candle.open,
            Candle.close,
            Candle.high,
            Candle.low,
            Candle.volume,
        )
        .where(
            Candle.exchange == exchange,
            Candle.symbol == symbol,
            (Candle.timeframe == '1m') | Candle.timeframe.is_null(),
            Candle.timestamp >= earliest_bucket_start,
            Candle.timestamp < trading_start_timestamp,
        )
        .order_by(Candle.timestamp.asc())
        .tuples()
    )
    if caching:
        cache.set_value(cache_key, candles_tuple, expire_seconds=60 * 60 * 24 * 7)
    return np.array(candles_tuple)


def validate_observed_one_minute_candles(candles: np.ndarray, exchange: str, symbol: str) -> None:
    """Validate observed 1m rows without requiring candles at absent timestamps or range edges."""
    if not isinstance(candles, np.ndarray) or candles.ndim != 2 or candles.shape[1] != 6 or len(candles) == 0:
        raise ValueError(f'Candles for {symbol} on {exchange} must be a nonempty six-column array.')
    timestamps = candles[:, 0]
    if not np.isfinite(timestamps).all() or (timestamps % 60_000 != 0).any():
        raise ValueError(f'Candles for {symbol} on {exchange} must have minute-aligned timestamps.')
    if len(timestamps) > 1 and (np.diff(timestamps) <= 0).any():
        raise ValueError(f'Candles for {symbol} on {exchange} must have strictly increasing unique timestamps.')


def _get_generated_candles(timeframe, trading_candles) -> np.ndarray:
    if len(trading_candles) == 0:
        return np.zeros((0, 6))
    return generate_completed_candles_from_observed_minutes(
        timeframe,
        trading_candles,
        int(trading_candles[-1, 0]) + 60_000,
    )


def generate_new_candles_loop() -> None:
    """
    to prevent the issue of missing candles when no volume is traded on the live exchange
    """
    t = Timeloop()

    @t.job(interval=timedelta(seconds=1))
    def time_loop_per_second():
        # make sure all candles are already initiated
        if not store.candles.are_all_initiated:
            return

        # only at first second on each minute
        if jh.now() % 60_000 != 1000:
            return

        # Sparse venues (stock markets) have no candles while the market is closed. An absent
        # minute is not an event there, so nothing is fabricated; such live sessions use the same
        # clock-bucket model as observed-only backtests (see uses_timestamp_buckets).
        if store.candles.uses_timestamp_buckets:
            return

        for c in router.all_formatted_routes:
            exchange, symbol, timeframe = c['exchange'], c['symbol'], c['timeframe']
            current_candle = get_current_candle(exchange, symbol, timeframe)

            # fix for a bug
            if current_candle[0] <= 60_000:
                continue

            # if a missing candle is found, generate an empty candle from the
            # last one this is useful when the exchange doesn't stream an empty
            # candle when no volume is traded at the period of the candle
            if jh.next_candle_timestamp(current_candle, timeframe) < jh.now():
                new_candle = _generate_empty_candle_from_previous_candle(current_candle, timeframe=timeframe)
                add_candle(new_candle, exchange, symbol, timeframe)

    t.start()


def _generate_empty_candle_from_previous_candle(
            previous_candle: np.ndarray,
            timeframe: str = '1m'
    ) -> np.ndarray:
    """
    generate an empty candle from the previous candle
    """
    new_candle = previous_candle.copy()
    candles_count = jh.timeframe_to_one_minutes(timeframe) * 60_000
    new_candle[0] = previous_candle[0] + candles_count
    # new candle's open, close, high, and low all equal to previous candle's close
    new_candle[1] = previous_candle[2]
    new_candle[2] = previous_candle[2]
    new_candle[3] = previous_candle[2]
    new_candle[4] = previous_candle[2]
    # set volume to 0
    new_candle[5] = 0
    return new_candle


def add_candle(
        candle: np.ndarray,
        exchange: str,
        symbol: str,
        timeframe: str,
        with_execution: bool = True,
        with_generation: bool = True,
        with_skip: bool = True
) -> None:
    is_live = jh.is_live()

    # overwrite with_generation based on the config value for live sessions
    if is_live and not jh.get_config('env.data.generate_candles_from_1m'):
        with_generation = False

    candle_timestamp = candle[0]

    if candle_timestamp == 0:
        if jh.is_debugging():
            logger.error(
                f"DEBUGGING-VALUE: please report to Saleh: candle[0] is zero. \nFull candle: {candle}\n"
            )
        return

    arr: DynamicNumpyArray = store.candles.get_storage(exchange, symbol, timeframe)

    if is_live:
        # ignore if candle is still being initially imported
        if with_skip and f'{exchange}-{symbol}' not in store.candles.initiated_pairs:
            return

        # if it's not an old candle, update the related position's current_price
        latest_array, latest_index = arr.snapshot()
        # Stock streams deliver completed bars after their minute ends. Their newest observed
        # close is still the current price; an older REST backfill must never move it backwards.
        newest_sparse_minute = (
            store.candles.uses_timestamp_buckets and timeframe == '1m'
            and candle_timestamp < jh.now()
            and (latest_index == -1 or candle_timestamp >= latest_array[latest_index, 0])
        )
        if newest_sparse_minute or (
                not store.candles.uses_timestamp_buckets
                and jh.next_candle_timestamp(candle, timeframe) > jh.now()
        ):
            _update_position_current_price(exchange, symbol, candle[2])

        # ignore new candle at the time of execution because it messes
        # the count of candles without actually having an impact
        if candle_timestamp >= jh.now():
            return

        _store_or_update_candle_into_db(exchange, symbol, timeframe, candle)

    array, last_index = arr.snapshot()

    # initial
    if last_index == -1:
        arr.append(candle)
        # A session with no warm-up still needs its first observed forming bucket.
        if with_generation and timeframe == '1m':
            _generate_bigger_timeframes(candle, exchange, symbol, with_execution)
        return

    # read the last candle's timestamp once as a plain scalar instead of
    # building an intermediate row view (arr[-1][0]) for every comparison —
    # this function runs twice per simulated minute.
    last_candle_timestamp = array[last_index, 0]

    # if it's new, add
    if candle_timestamp > last_candle_timestamp:
        arr.append(candle)

        # generate other timeframes
        if with_generation and timeframe == '1m':
            _generate_bigger_timeframes(candle, exchange, symbol, with_execution)

    # if it's the last candle again, update
    elif candle_timestamp == last_candle_timestamp:
        arr[last_index] = candle

        # regenerate other timeframes
        if with_generation and timeframe == '1m':
            _generate_bigger_timeframes(candle, exchange, symbol, with_execution)

    # allow updating of the previous candle.
    elif candle_timestamp < last_candle_timestamp:
        # loop through the last 20 items in arr to find it. If so, update it.
        for i in range(max(20, len(arr) - 1)):
            if arr[-i][0] == candle_timestamp:
                arr[-i] = candle
                break
    else:
        logger.info(
            f"Could not find the candle with timestamp {jh.timestamp_to_time(candle[0])} in the storage. Last candle's timestamp: {jh.timestamp_to_time(arr[-1])}. timeframe: {timeframe}, exchange: {exchange}, symbol: {symbol}"
        )


def _store_or_update_candle_into_db(exchange: str, symbol: str, timeframe: str, candle: np.ndarray) -> None:
    # if it's not an initial candle, add it to the storage, if already exists, update it
    if f'{exchange}-{symbol}' in store.candles.initiated_pairs:
        candle_repository.store_candle_into_db(exchange, symbol, timeframe, candle, on_conflict='replace')


def _update_position_current_price(exchange: str, symbol: str, price: float) -> None:
    # get position object
    p = store.positions.get_position(exchange, symbol)

    # for data_route candles, p == None, hence no further action is required
    if p is None:
        return

    if jh.is_live():
        price_precision = store.exchanges.get_exchange(exchange).vars['precisions'][symbol]['price_precision']

        # update position.current_price
        p.current_price = jh.round_price_for_live_mode(price, price_precision)
    else:
        p.current_price = price


def add_candle_from_trade(trade, exchange: str, symbol: str) -> np.ndarray | None:
    """
    In few exchanges, there's no candle stream over the WS, for
    those we have to use cases the trades stream
    """
    if not jh.is_live():
        raise Exception('add_candle_from_trade() is for live modes only')

    # ignore if candle is still being initially imported
    if f'{exchange}-{symbol}' not in store.candles.initiated_pairs:
        return None

    # update position's current price
    _update_position_current_price(exchange, symbol, trade['price'])

    def do(t) -> np.ndarray:
        # in some cases we might be missing the current forming candle like it is on FTX, hence
        # if that is the case, generate the current forming candle (it won't be super accurate)
        current_candle = get_current_candle(exchange, symbol, t)
        if jh.next_candle_timestamp(current_candle, t) < jh.now():
            new_candle = _generate_empty_candle_from_previous_candle(current_candle, t)
            add_candle(new_candle, exchange, symbol, t)

        current_candle = get_current_candle(exchange, symbol, t)

        new_candle = current_candle.copy()
        # close
        new_candle[2] = trade['price']
        # high
        new_candle[3] = max(new_candle[3], trade['price'])
        # low
        new_candle[4] = min(new_candle[4], trade['price'])
        # volume
        new_candle[5] += trade['volume']

        add_candle(new_candle, exchange, symbol, t)
        return new_candle

    # to support both candle generation and ...
    if jh.get_config('env.data.generate_candles_from_1m'):
        return do('1m')
    else:
        for r in router.all_formatted_routes:
            if r['exchange'] != exchange or r['symbol'] != symbol:
                return None
            return do(r['timeframe'])


def _generate_bigger_timeframes(candle: np.ndarray, exchange: str, symbol: str, with_execution: bool) -> None:
    if not jh.is_live():
        return

    for timeframe in config['app']['considering_timeframes']:
        # skip '1m'
        if timeframe == '1m':
            continue

        # Elapsed minutes are not row counts when an exchange omits no-trade bars.
        # Select only observations in this candle's UTC bucket, including forming rows.
        timeframe_ms = jh.timeframe_to_one_minutes(timeframe) * 60_000
        bucket_start = int(candle[0]) - int(candle[0]) % timeframe_ms
        short_candles = get_candles(exchange, symbol, '1m')
        start_index = int(np.searchsorted(short_candles[:, 0], bucket_start, side='left'))
        end_index = int(np.searchsorted(short_candles[:, 0], bucket_start + timeframe_ms, side='left'))
        source_rows = short_candles[start_index:end_index]
        if not len(source_rows):
            continue
        generated_candle = generate_candle_from_observed_minutes(timeframe, source_rows)

        add_candle(
            generated_candle, exchange, symbol, timeframe, with_execution, with_generation=False
        )


def batch_add_candle(
        candles: np.ndarray,
        exchange: str,
        symbol: str,
        timeframe: str,
        with_generation: bool = True
) -> None:
    for c in candles:
        add_candle(c, exchange, symbol, timeframe, with_execution=False, with_generation=with_generation, with_skip=False)


def get_candles(exchange: str, symbol: str, timeframe: str) -> np.ndarray:
    # this runs on every single indicator call, so storage access is done with
    # plain dict lookups instead of going through forming_estimation +
    # get_storage (which rebuild the same key strings several times per call).
    storage = store.candles.storage

    # no need to worry for forming candles when timeframe == 1m
    if timeframe == '1m':
        arr: DynamicNumpyArray = storage.get(f'{exchange}-{symbol}-1m')
        if arr is None:
            raise RouteNotFound(symbol, '1m')
        array, index = arr.snapshot()
        if index == -1:
            return np.zeros((0, 6))
        return array[:index + 1]

    if store.candles.uses_timestamp_buckets:
        return _get_timestamp_bucket_candles(exchange, symbol, timeframe)

    # other timeframes
    required_1m_to_complete_count = jh.timeframe_to_one_minutes(timeframe)
    short_arr: DynamicNumpyArray = storage.get(f'{exchange}-{symbol}-1m')
    if short_arr is None:
        raise RouteNotFound(symbol, '1m')
    short_array, short_index = short_arr.snapshot()
    short_count = short_index + 1
    dif = short_count % required_1m_to_complete_count

    long_arr: DynamicNumpyArray = storage.get(f'{exchange}-{symbol}-{timeframe}')
    if long_arr is None:
        raise RouteNotFound(symbol, timeframe)
    long_array, long_index = long_arr.snapshot()
    long_count = long_index + 1

    if dif == 0 and long_count == 0:
        return np.zeros((0, 6))

    # complete candle
    if dif == 0:
        return long_array[:long_count]
    # generate forming candle only if NOT in live mode
    elif not jh.is_live():
        forming_candle = generate_candle_from_one_minutes(
            timeframe,
            short_array[short_count - dif:short_count],
            True
        )
        add_candle(forming_candle, exchange, symbol, timeframe, with_execution=False, with_generation=False, with_skip=False)
        long_array, long_index = long_arr.snapshot()
        return long_array[:long_index + 1]
    # in live mode, just return the complete candles
    else:
        return long_array[:long_count]


def _get_timestamp_bucket_candles(exchange: str, symbol: str, timeframe: str) -> np.ndarray:
    """Return completed candles plus the current observed-only forming clock bucket."""
    storage = store.candles.storage
    short_arr: DynamicNumpyArray = storage.get(f'{exchange}-{symbol}-1m')
    if short_arr is None:
        raise RouteNotFound(symbol, '1m')
    short_array, short_index = short_arr.snapshot()
    if short_index == -1:
        return np.zeros((0, 6))

    long_arr: DynamicNumpyArray = storage.get(f'{exchange}-{symbol}-{timeframe}')
    if long_arr is None:
        raise RouteNotFound(symbol, timeframe)

    timeframe_ms = jh.timeframe_to_one_minutes(timeframe) * 60_000
    current_bucket_start = int(short_array[short_index, 0])
    current_bucket_start -= current_bucket_start % timeframe_ms

    visible_short = short_array[:short_index + 1]
    bucket_start_index = int(np.searchsorted(visible_short[:, 0], current_bucket_start, side='left'))
    # A previous strategy read may have stored an earlier snapshot of this
    # forming bucket; add_candle updates that row with every newly visible minute.
    forming_candle = generate_candle_from_observed_minutes(
        timeframe,
        visible_short[bucket_start_index:],
    )
    add_candle(
        forming_candle,
        exchange,
        symbol,
        timeframe,
        with_execution=False,
        with_generation=False,
        with_skip=False,
    )
    long_array, long_index = long_arr.snapshot()
    return long_array[:long_index + 1]


def get_current_candle(exchange: str, symbol: str, timeframe: str) -> np.ndarray:
    # no need to worry for forming candles when timeframe == 1m
    if timeframe == '1m':
        arr: DynamicNumpyArray = store.candles.get_storage(exchange, symbol, '1m')
        if len(arr) == 0:
            return np.zeros((0, 6))
        else:
            return arr[-1]

    if jh.is_live():
        # Live stores already hold native exchange bars or clock-aligned locally
        # generated bars. Reconstructing by 1m row count would corrupt sparse history
        # and could override native bars when local generation is disabled.
        arr = store.candles.get_storage(exchange, symbol, timeframe)
        return arr[-1] if len(arr) else np.zeros((0, 6))

    if store.candles.uses_timestamp_buckets:
        candles = _get_timestamp_bucket_candles(exchange, symbol, timeframe)
        return candles[-1] if len(candles) else np.zeros((0, 6))

    # other timeframes
    dif, long_key, short_key = store.candles.forming_estimation(exchange, symbol, timeframe)
    long_count = len(store.candles.get_storage(exchange, symbol, timeframe))
    short_count = len(store.candles.get_storage(exchange, symbol, '1m'))

    # forming candle
    if dif != 0:
        return generate_candle_from_one_minutes(
            timeframe, store.candles.storage[short_key][short_count - dif:short_count],
            True
        )
    if long_count == 0:
        return np.zeros((0, 6))
    else:
        return store.candles.storage[long_key][-1]


def add_multiple_1m_candles(
    candles: np.ndarray,
    exchange: str,
    symbol: str,
) -> None:
    if not (jh.is_backtesting() or jh.is_optimizing()):
        raise Exception('add_multiple_1m_candles() is for backtesting or optimizing only')

    arr: DynamicNumpyArray = store.candles.get_storage(exchange, symbol, '1m')

    # initial
    if len(arr) == 0:
        arr.append_multiple(candles)

    # if it's new, add
    elif candles[0, 0] > arr[-1][0]:
        arr.append_multiple(candles)

    # if it's the last candle again, update
    elif candles[0, 0] >= arr[-len(candles)][0] and candles[-1, 0] >= arr[-1][0]:
        override_candles = int(
            len(candles) - ((candles[-1, 0] - arr[-1][0]) / 60000)
        )
        arr[-override_candles:] = candles

    # Otherwise,it's true and error.
    else:
        raise IndexError(f"Could not find the candle with timestamp {jh.timestamp_to_time(candles[0, 0])} in the storage. Last candle's timestamp: {jh.timestamp_to_time(arr[-1][0])}. exchange: {exchange}, symbol: {symbol}")
