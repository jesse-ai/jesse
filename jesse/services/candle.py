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

    required_candles = jh.timeframe_to_one_minutes(timeframe)
    
    if not accept_forming_candles and len(candles) != required_candles:
        # Check if we should fill missing candles
        fill_missing = jh.get_config('env.data.fill_missing_candles', True)
        
        if fill_missing and len(candles) < required_candles:
            # Log warning about missing data
            from jesse.services.logger import info
            info(
                f'Insufficient data for {timeframe} candle: only {len(candles)} candles available, '
                f'but {required_candles} required. Filling with empty candles.'
            )
            
            # Create empty candles to fill the gap
            empty_candles = []
            last_timestamp = candles[-1][0] if len(candles) > 0 else 0
            last_price = candles[-1][2] if len(candles) > 0 else 0
            
            for i in range(required_candles - len(candles)):
                # Create empty candle with open=close=last_price, volume=0
                empty_candle = np.array([
                    last_timestamp + (i + 1) * 60_000,  # timestamp
                    last_price,  # open
                    last_price,  # close
                    last_price,  # high
                    last_price,  # low
                    0  # volume
                ])
                empty_candles.append(empty_candle)
            
            # Combine original candles with empty ones
            candles = np.concatenate([candles, np.array(empty_candles)])
        else:
            raise ValueError(
                f'Sent only {len(candles)} candles but {required_candles} is required to create a "{timeframe}" candle.'
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
    low = candle[4]
    v = candle[5]

    if is_bullish(candle) and low < price < o:
        return np.array([
            timestamp, o, price, o, price, v
        ]), np.array([
            timestamp, price, c, h, low, v
        ])
    elif price == o:
        return candle, candle
    elif is_bearish(candle) and o < price < h:
        return np.array([
            timestamp, o, price, price, o, v
        ]), np.array([
            timestamp, price, c, h, low, v
        ])
    elif is_bearish(candle) and low < price < c:
        return np.array([
            timestamp, o, price, h, price, v
        ]), np.array([
            timestamp, price, c, c, low, v
        ])
    elif is_bullish(candle) and c < price < h:
        return np.array([
            timestamp, o, price, price, low, v
        ]), np.array([
            timestamp, price, c, h, c, v
        ]),
    elif is_bearish(candle) and price == c:
        return np.array([
            timestamp, o, c, h, c, v
        ]), np.array([
            timestamp, price, price, price, low, v
        ])
    elif is_bullish(candle) and price == c:
        return np.array([
            timestamp, o, c, c, low, v
        ]), np.array([
            timestamp, price, price, h, price, v
        ])
    elif is_bearish(candle) and price == h:
        return np.array([
            timestamp, o, h, h, o, v
        ]), np.array([
            timestamp, h, c, h, low, v
        ])
    elif is_bullish(candle) and price == low:
        return np.array([
            timestamp, o, low, o, low, v
        ]), np.array([
            timestamp, low, c, h, low, v
        ])
    elif is_bearish(candle) and price == low:
        return np.array([
            timestamp, o, low, h, low, v
        ]), np.array([
            timestamp, low, c, c, low, v
        ])
    elif is_bullish(candle) and price == h:
        return np.array([
            timestamp, o, h, h, low, v
        ]), np.array([
            timestamp, h, c, h, c, v
        ])
    elif is_bearish(candle) and c < price < o:
        return np.array([
            timestamp, o, price, h, price, v
        ]), np.array([
            timestamp, price, c, price, low, v
        ])
    elif is_bullish(candle) and o < price < c:
        return np.array([
            timestamp, o, price, price, low, v
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

    # Check if this is a CSV data source
    if exchange.lower() == 'custom':
        return _get_csv_candles(
            symbol, timeframe, start_date_timestamp, finish_date_timestamp, 
            warmup_candles_num, is_for_jesse
        )

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
            # Check if we should fill missing candles
            fill_missing = jh.get_config('env.data.fill_missing_candles', True)
            
            if fill_missing:
                # Log warning about missing data
                from jesse.services.logger import info
                info(
                    f'Missing candles for {symbol} on {exchange}. '
                    f'Requested data from {jh.timestamp_to_date(start_date_timestamp)}, '
                    f'but earliest available candle is from {jh.timestamp_to_date(earliest_available)}. '
                    f'Filling with empty candles.'
                )
                
                # Calculate how many minutes we need to fill at the beginning
                missing_minutes = int((earliest_available - start_date_timestamp) // 60_000)
                
                # Create empty candles to fill the gap at the beginning
                empty_candles = []
                first_price = candles_array[0][1] if len(candles_array) > 0 else 0  # Use first open price
                
                for i in range(missing_minutes):
                    empty_candle = np.array([
                        start_date_timestamp + i * 60_000,  # timestamp
                        first_price,  # open
                        first_price,  # close
                        first_price,  # high
                        first_price,  # low
                        0  # volume
                    ])
                    empty_candles.append(empty_candle)
                
                # Combine empty candles at the beginning with original candles
                if empty_candles:
                    candles_array = np.concatenate([np.array(empty_candles), candles_array])
            else:
                raise CandleNotFoundInDatabase(
                    f"Missing candles for {symbol} on {exchange}. "
                    f"Requested data from {jh.timestamp_to_date(start_date_timestamp)}, "
                    f"but earliest available candle is from {jh.timestamp_to_date(earliest_available)}."
                )
            
        # For finish date validation, we need to check if we have candles up to exactly one minute
        # before the start of the requested finish date
        # Check if the latest available candle timestamp is before the required last candle
        if latest_available < finish_date_timestamp:
            # Check if we should fill missing candles
            fill_missing = jh.get_config('env.data.fill_missing_candles', True)
            
            if fill_missing:
                # Log warning about missing data
                from jesse.services.logger import info
                info(
                    f'Missing recent candles for "{symbol}" on "{exchange}". '
                    f'Requested data until "{jh.timestamp_to_time(finish_date_timestamp)[:19]}", '
                    f'but latest available candle is up to "{jh.timestamp_to_time(latest_available)[:19]}". '
                    f'Filling with empty candles.'
                )
                
                # Calculate how many minutes we need to fill
                missing_minutes = int((finish_date_timestamp - latest_available) // 60_000)
                
                # Create empty candles to fill the gap
                empty_candles = []
                last_price = candles_array[-1][2] if len(candles_array) > 0 else 0  # Use last close price
                
                for i in range(missing_minutes):
                    empty_candle = np.array([
                        latest_available + (i + 1) * 60_000,  # timestamp
                        last_price,  # open
                        last_price,  # close
                        last_price,  # high
                        last_price,  # low
                        0  # volume
                    ])
                    empty_candles.append(empty_candle)
                
                # Combine original candles with empty ones
                if empty_candles:
                    candles_array = np.concatenate([candles_array, np.array(empty_candles)])
            else:
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
    required_candles = jh.timeframe_to_one_minutes(timeframe)
    
    for i in range(len(trading_candles)):
        if (i + 1) % required_candles == 0:
            # Get the slice of candles for this timeframe
            start_idx = max(0, i - (required_candles - 1))
            end_idx = min(i + 1, len(trading_candles))
            candle_slice = trading_candles[start_idx:end_idx]
            
            # If we don't have enough candles, fill with empty ones
            if len(candle_slice) < required_candles:
                fill_missing = jh.get_config('env.data.fill_missing_candles', True)
                
                if fill_missing:
                    from jesse.services.logger import info
                    info(
                        f'Insufficient data for {timeframe} candle generation: only {len(candle_slice)} candles available, '
                        f'but {required_candles} required. Filling with empty candles.'
                    )
                    
                    empty_candles = []
                    last_timestamp = candle_slice[-1][0] if len(candle_slice) > 0 else 0
                    last_price = candle_slice[-1][2] if len(candle_slice) > 0 else 0
                    
                    for j in range(required_candles - len(candle_slice)):
                        empty_candle = np.array([
                            last_timestamp + (j + 1) * 60_000,  # timestamp
                            last_price,  # open
                            last_price,  # close
                            last_price,  # high
                            last_price,  # low
                            0  # volume
                        ])
                        empty_candles.append(empty_candle)
                    
                    # Combine original candles with empty ones
                    candle_slice = np.concatenate([candle_slice, np.array(empty_candles)])
                else:
                    raise ValueError(
                        f'Insufficient data for {timeframe} candle: only {len(candle_slice)} candles available, '
                        f'but {required_candles} required.'
                    )
            
            generated_candles.append(
                generate_candle_from_one_minutes(
                    timeframe,
                    candle_slice,
                    True
                )
            )
        # Handle the case where we don't have enough data for a complete candle
        # but we're at the end of the data
        elif i == len(trading_candles) - 1 and len(trading_candles) < required_candles and (i + 1) % required_candles != 0:
            fill_missing = jh.get_config('env.data.fill_missing_candles', True)
            
            if fill_missing:
                from jesse.services.logger import info
                info(
                    f'Insufficient data for {timeframe} candle generation: only {len(trading_candles)} candles available, '
                    f'but {required_candles} required. Filling with empty candles.'
                )
                
                # Fill with empty candles to complete the timeframe
                empty_candles = []
                last_timestamp = trading_candles[-1][0] if len(trading_candles) > 0 else 0
                last_price = trading_candles[-1][2] if len(trading_candles) > 0 else 0
                
                for j in range(required_candles - len(trading_candles)):
                    empty_candle = np.array([
                        last_timestamp + (j + 1) * 60_000,  # timestamp
                        last_price,  # open
                        last_price,  # close
                        last_price,  # high
                        last_price,  # low
                        0  # volume
                    ])
                    empty_candles.append(empty_candle)
                
                # Combine original candles with empty ones
                complete_candle_slice = np.concatenate([trading_candles, np.array(empty_candles)])
                
                generated_candles.append(
                    generate_candle_from_one_minutes(
                        timeframe,
                        complete_candle_slice,
                        True
                    )
                )
            else:
                raise ValueError(
                    f'Insufficient data for {timeframe} candle: only {len(trading_candles)} candles available, '
                    f'but {required_candles} required.'
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


def _get_csv_candles(
        symbol: str,
        timeframe: str,
        start_date_timestamp: int,
        finish_date_timestamp: int,
        warmup_candles_num: int = 0,
        is_for_jesse: bool = False
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Get candles from CSV data source.
    
    Args:
        symbol: Symbol name
        timeframe: Timeframe
        start_date_timestamp: Start timestamp in milliseconds
        finish_date_timestamp: Finish timestamp in milliseconds
        warmup_candles_num: Number of warmup candles
        is_for_jesse: Whether this is for Jesse framework
        
    Returns:
        Tuple of (warmup_candles, trading_candles)
    """
    from jesse.services.csv_data_provider import csv_data_provider
    
    try:
        # Get candles from CSV data provider
        candles = csv_data_provider.get_candles(
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date_timestamp,
            finish_date=finish_date_timestamp
        )
        
        if candles is None or len(candles) == 0:
            return None, None
        
        # Convert to numpy array if needed
        if not isinstance(candles, np.ndarray):
            candles = np.array(candles)
        
        # Calculate warmup candles if needed
        warmup_candles = None
        if warmup_candles_num > 0:
            # Calculate warmup period
            warmup_period_ms = warmup_candles_num * jh.timeframe_to_one_minutes(timeframe) * 60_000
            warmup_start = start_date_timestamp - warmup_period_ms
            
            # Get warmup candles
            warmup_candles = csv_data_provider.get_candles(
                symbol=symbol,
                timeframe=timeframe,
                start_date=warmup_start,
                finish_date=start_date_timestamp - 1
            )
            
            if warmup_candles is not None and len(warmup_candles) > 0:
                if not isinstance(warmup_candles, np.ndarray):
                    warmup_candles = np.array(warmup_candles)
            else:
                warmup_candles = None
        
        return warmup_candles, candles
        
    except Exception as e:
        from jesse.services import logger
        logger.error(f"Error getting CSV candles for {symbol}: {e}")
        return None, None
