from typing import Tuple
import numpy as np
import arrow
from jesse.exceptions import CandleNotFoundInDatabase, InvalidDateRange
import jesse.helpers as jh
from jesse.services import logger
from jesse.routes import router
from timeloop import Timeloop
from datetime import timedelta
from jesse.store import store
from jesse.config import config
from jesse.repositories import candle_repository
from jesse.libs.dynamic_numpy_array import DynamicNumpyArray


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

    return np.array([
        candles[0][0],
        candles[0][1],
        candles[-1][2],
        candles[:, 3].max(),
        candles[:, 4].min(),
        candles[:, 5].sum(),
    ])


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


def inject_warmup_candles_to_store(candles: np.ndarray, exchange: str, symbol: str) -> None:
    if candles is None or candles.size == 0:
        raise ValueError(f'Could not inject warmup candles because the passed candles are empty. Have you imported enough warmup candles for {exchange}/{symbol}?')

    from jesse.config import config
    from jesse.store import store

    # batch add 1m candles:
    batch_add_candle(candles, exchange, symbol, '1m', with_generation=False)

    # loop to generate, and add candles (without execution)
    for i in range(len(candles)):
        for timeframe in config['app']['considering_timeframes']:
            # skip 1m. already added
            if timeframe == '1m':
                continue

            num = jh.timeframe_to_one_minutes(timeframe)

            if (i + 1) % num == 0:
                generated_candle = generate_candle_from_one_minutes(
                    timeframe,
                    candles[(i - (num - 1)):(i + 1)],
                    True
                )

                add_candle(
                    generated_candle,
                    exchange,
                    symbol,
                    timeframe,
                    with_execution=False,
                    with_generation=False
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
        warmup_start_timestamp = warmup_finish_timestamp - (
                warmup_candles_num * jh.timeframe_to_one_minutes(timeframe) * 60_000)
        warmup_finish_timestamp -= 60_000
        warmup_candles = _get_candles_from_db(exchange, symbol, warmup_start_timestamp, warmup_finish_timestamp,
                                              caching=caching)
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
        Candle.timeframe == '1m' or Candle.timeframe.is_null(),
        Candle.timestamp.between(start_date_timestamp, finish_date_timestamp)
    ).order_by(Candle.timestamp.asc()).tuples())

    # Check if we got any candles
    if not candles_tuple:
        raise CandleNotFoundInDatabase(f"No candles found for {symbol} on {exchange} between {jh.timestamp_to_date(start_date_timestamp)} and {jh.timestamp_to_date(finish_date_timestamp)}.")
    
    # Convert to numpy array for easier timestamp extraction
    candles_array = np.array(candles_tuple)
    
    # Verify the retrieved data covers the requested range
    if len(candles_array) > 0:
        earliest_available = candles_array[0][0]  # First timestamp
        latest_available = candles_array[-1][0]   # Last timestamp
        
        # Check if earliest available timestamp is after the requested start date
        if earliest_available > start_date_timestamp + 60_000:  # Allow 1 minute tolerance
            raise CandleNotFoundInDatabase(
                f"Missing candles for {symbol} on {exchange}. "
                f"Requested data from {jh.timestamp_to_date(start_date_timestamp)}, "
                f"but earliest available candle is from {jh.timestamp_to_date(earliest_available)}."
            )
            
        # For finish date validation, we need to check if we have candles up to exactly one minute
        # before the start of the requested finish date
        # Check if the latest available candle timestamp is before the required last candle
        if latest_available < finish_date_timestamp:
            # Missing candles at the end of the requested range
            raise CandleNotFoundInDatabase(
                f"Missing recent candles for \"{symbol}\" on \"{exchange}\". "
                f"Requested data until \"{jh.timestamp_to_time(finish_date_timestamp)[:19]}\", "
                f"but latest available candle is up to \"{jh.timestamp_to_time(latest_available)[:19]}\"."
            )

    if caching:
        # cache for 1 week it for near future calls
        cache.set_value(cache_key, candles_tuple, expire_seconds=60 * 60 * 24 * 7)

    return candles_array


def _get_generated_candles(timeframe, trading_candles) -> np.ndarray:
    # generate candles for the requested timeframe
    generated_candles = []
    for i in range(len(trading_candles)):
        num = jh.timeframe_to_one_minutes(timeframe)

        if (i + 1) % num == 0:
            generated_candles.append(
                generate_candle_from_one_minutes(
                    timeframe,
                    trading_candles[(i - (num - 1)):(i + 1)],
                    True
                )
            )

    return np.array(generated_candles)


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
    # overwrite with_generation based on the config value for live sessions
    if jh.is_live() and not jh.get_config('env.data.generate_candles_from_1m'):
        with_generation = False

    if candle[0] == 0:
        if jh.is_debugging():
            logger.error(
                f"DEBUGGING-VALUE: please report to Saleh: candle[0] is zero. \nFull candle: {candle}\n"
            )
        return

    arr: DynamicNumpyArray = store.candles.get_storage(exchange, symbol, timeframe)

    if jh.is_live():
        # ignore if candle is still being initially imported
        if with_skip and f'{exchange}-{symbol}' not in store.candles.initiated_pairs:
            return

        # if it's not an old candle, update the related position's current_price
        if jh.next_candle_timestamp(candle, timeframe) > jh.now():
            _update_position_current_price(exchange, symbol, candle[2])

        # ignore new candle at the time of execution because it messes
        # the count of candles without actually having an impact
        if candle[0] >= jh.now():
            return

        _store_or_update_candle_into_db(exchange, symbol, timeframe, candle)

    # initial
    if len(arr) == 0:
        arr.append(candle)

    # if it's new, add
    elif candle[0] > arr[-1][0]:
        arr.append(candle)

        # generate other timeframes
        if with_generation and timeframe == '1m':
            _generate_bigger_timeframes(candle, exchange, symbol, with_execution)

    # if it's the last candle again, update
    elif candle[0] == arr[-1][0]:
        arr[-1] = candle

        # regenerate other timeframes
        if with_generation and timeframe == '1m':
            _generate_bigger_timeframes(candle, exchange, symbol, with_execution)

    # allow updating of the previous candle.
    elif candle[0] < arr[-1][0]:
        # loop through the last 20 items in arr to find it. If so, update it.
        for i in range(max(20, len(arr) - 1)):
            if arr[-i][0] == candle[0]:
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

        last_candle = get_current_candle(exchange, symbol, timeframe)
        generate_from_count = int((candle[0] - last_candle[0]) / 60_000)
        number_of_candles = len(get_candles(exchange, symbol, '1m'))
        short_candles = get_candles(exchange, symbol, '1m')[-1 - generate_from_count:]

        if generate_from_count == -1:
            # it's receiving an slightly older candle than the last one. Ignore it
            return

        if generate_from_count < 0:
            current_1m = get_current_candle(exchange, symbol, '1m')
            raise ValueError(
                f'generate_from_count cannot be negative! '
                f'generate_from_count:{generate_from_count}, candle[0]:{candle[0]}, '
                f'last_candle[0]:{last_candle[0]}, current_1m:{current_1m[0]}, number_of_candles:{number_of_candles}')

        if len(short_candles) == 0:
            raise ValueError(
                f'No candles were passed. More info:'
                f'\nexchange:{exchange}, symbol:{symbol}, timeframe:{timeframe}, generate_from_count:{generate_from_count}'
                f'\nlast_candle\'s timestamp: {last_candle[0]}'
                f'\ncurrent timestamp: {jh.now()}'
            )

        # update latest candle
        generated_candle = generate_candle_from_one_minutes(
            timeframe,
            short_candles,
            accept_forming_candles=True
        )

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
    # no need to worry for forming candles when timeframe == 1m
    if timeframe == '1m':
        arr: DynamicNumpyArray = store.candles.get_storage(exchange, symbol, '1m')
        if len(arr) == 0:
            return np.zeros((0, 6))
        else:
            return arr[:]

    # other timeframes
    dif, long_key, short_key = store.candles.forming_estimation(exchange, symbol, timeframe)
    long_count = len(store.candles.get_storage(exchange, symbol, timeframe))
    short_count = len(store.candles.get_storage(exchange, symbol, '1m'))

    if dif == 0 and long_count == 0:
        return np.zeros((0, 6))

    # complete candle
    if dif == 0:
        return store.candles.storage[long_key][:long_count]
    # generate forming candle only if NOT in live mode
    elif not jh.is_live():
        forming_candle = generate_candle_from_one_minutes(
            timeframe,
            store.candles.storage[short_key][short_count - dif:short_count],
            True
        )
        existing_candles_arr: DynamicNumpyArray = store.candles.storage[long_key]
        add_candle(forming_candle, exchange, symbol, timeframe, with_execution=False, with_generation=False, with_skip=False)
        return existing_candles_arr[:]
    # in live mode, just return the complete candles
    else:
        return store.candles.storage[long_key][:long_count]


def get_current_candle(exchange: str, symbol: str, timeframe: str) -> np.ndarray:
    # no need to worry for forming candles when timeframe == 1m
    if timeframe == '1m':
        arr: DynamicNumpyArray = store.candles.get_storage(exchange, symbol, '1m')
        if len(arr) == 0:
            return np.zeros((0, 6))
        else:
            return arr[-1]

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
