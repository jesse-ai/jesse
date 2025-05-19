from typing import Tuple
import numpy as np
import arrow
from jesse.exceptions import CandleNotFoundInDatabase, InvalidDateRange
import jesse.helpers as jh
from jesse.services import logger
from jesse.models import Candle
from typing import List, Dict


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
    store.candles.batch_add_candle(candles, exchange, symbol, '1m', with_generation=False)

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

                store.candles.add_candle(
                    generated_candle,
                    exchange,
                    symbol,
                    timeframe,
                    with_execution=False,
                    with_generation=False
                )


def get_candles(
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
    from jesse.models import Candle
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
        today_str = jh.timestamp_to_date(current_timestamp)
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


def get_existing_candles() -> List[Dict]:
    """
    Returns a list of all existing candles grouped by exchange and symbol
    """
    results = []
    
    # Get unique exchange-symbol combinations
    pairs = Candle.select(
        Candle.exchange, 
        Candle.symbol
    ).distinct().tuples()

    for exchange, symbol in pairs:
        # Get first and last candle for this pair
        first = Candle.select(
            Candle.timestamp
        ).where(
            Candle.exchange == exchange,
            Candle.symbol == symbol
        ).order_by(
            Candle.timestamp.asc()
        ).first()

        last = Candle.select(
            Candle.timestamp
        ).where(
            Candle.exchange == exchange,
            Candle.symbol == symbol
        ).order_by(
            Candle.timestamp.desc()
        ).first()

        if first and last:
            results.append({
                'exchange': exchange,
                'symbol': symbol,
                'start_date': arrow.get(first.timestamp / 1000).format('YYYY-MM-DD'),
                'end_date': arrow.get(last.timestamp / 1000).format('YYYY-MM-DD')
            })

    return results

def delete_candles(exchange: str, symbol: str) -> None:
    """
    Deletes all candles for the given exchange and symbol
    """
    Candle.delete().where(
        Candle.exchange == exchange,
        Candle.symbol == symbol
    ).execute()
