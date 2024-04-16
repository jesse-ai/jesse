import numpy as np
from jesse import utils
from jesse import factories
from typing import Union


def get_candles(
        exchange: str,
        symbol: str,
        timeframe: str,
        start_date: str,
        finish_date: str,
        warmup_candles: int = 0,
        is_for_jesse: bool = False
) -> np.ndarray:
    """
    Returns candles from the database in numpy format

    :param exchange: str
    :param symbol: str
    :param timeframe: str
    :param start_date: str
    :param finish_date: str
    :param warmup_candles: int
    :param is_for_jesse: bool

    :return: np.ndarray
    """
    import arrow
    import jesse.helpers as jh
    from jesse.models import Candle
    from jesse.exceptions import CandleNotFoundInDatabase
    from jesse.services.candle import generate_candle_from_one_minutes

    # check if .env file exists
    if not jh.is_jesse_project():
        raise FileNotFoundError(
            'Invalid directory: ".env" file not found. To use Jesse inside notebooks, create notebooks inside the root of a Jesse project.'
        )

    symbol = symbol.upper()

    start_date_timestamp = jh.date_to_timestamp(start_date)
    # make sure starting from the beginning of the day instead
    start_date_timestamp = jh.timestamp_to_arrow(start_date_timestamp).floor('day').int_timestamp * 1000
    finish_date_timestamp = jh.date_to_timestamp(finish_date)
    # make sure finishing until the beginning of the day instead then -1 candle to make sure it doesn't include the finishing date
    finish_date_timestamp = (jh.timestamp_to_arrow(finish_date_timestamp).floor('day').int_timestamp * 1000) - 60_000

    # warmup_candles
    if warmup_candles > 0:
        start_date_timestamp -= warmup_candles * jh.timeframe_to_one_minutes(timeframe) * 60_000

    # validate
    if start_date_timestamp == finish_date_timestamp:
        raise ValueError('start_date and finish_date cannot be the same.')
    if start_date_timestamp > finish_date_timestamp:
        raise ValueError('start_date cannot be bigger than finish_date.')
    if finish_date_timestamp > arrow.utcnow().int_timestamp * 1000:
        raise ValueError('Can\'t backtest the future!')

    # fetch from database
    candles_tuple = Candle.select(
        Candle.timestamp, Candle.open, Candle.close, Candle.high, Candle.low,
        Candle.volume
    ).where(
        Candle.exchange == exchange,
        Candle.symbol == symbol,
        Candle.timeframe == '1m' or Candle.timeframe.is_null(),
        Candle.timestamp.between(start_date_timestamp, finish_date_timestamp)
    ).order_by(Candle.timestamp.asc()).tuples()

    candles = np.array(tuple(candles_tuple))
    needed_candles_count = int((finish_date_timestamp - start_date_timestamp) / 60_000) + 1

    # validate that there are enough candles for selected period
    if len(candles) == 0:
        raise CandleNotFoundInDatabase(
            f'No candles found for {symbol} between {start_date_timestamp}({jh.timestamp_to_date(start_date_timestamp)}) and {finish_date_timestamp}({jh.timestamp_to_date(finish_date_timestamp)}). Try importing candles first.'
        )
    elif candles[0][0] != start_date_timestamp:
        raise CandleNotFoundInDatabase(
            f'Not enough candles found for {symbol} between {start_date_timestamp}({jh.timestamp_to_date(start_date_timestamp)}) and {finish_date_timestamp}({jh.timestamp_to_date(finish_date_timestamp)}). The first candle found is at {jh.timestamp_to_date(candles[0][0])}.'
        )
    elif candles[-1][0] != finish_date_timestamp:
        raise CandleNotFoundInDatabase(
            f'Not enough candles found for {symbol} between {start_date_timestamp}({jh.timestamp_to_date(start_date_timestamp)}) and {finish_date_timestamp}({jh.timestamp_to_date(finish_date_timestamp)}). The last candle found is at {jh.timestamp_to_date(candles[-1][0])}.'
        )
    elif len(candles) != needed_candles_count:
        raise CandleNotFoundInDatabase(
            f'Not enough candles found for {symbol} between {start_date_timestamp}({jh.timestamp_to_date(start_date_timestamp)}) and {finish_date_timestamp}({jh.timestamp_to_date(finish_date_timestamp)}). Found {len(candles)} candles but needed {needed_candles_count}.\n'
            f'Are you considering the warmup candles? For more info please read:\n https://jesse.trade/help/faq/i-imported-candles-but-keep-getting-not-enough-candles'
        )

    # if timeframe is 1m or is_for_jesse is True, return the candles as is because they
    # are already 1m candles which is the accepted format for practicing with Jesse.
    if timeframe == '1m' or is_for_jesse:
        return candles

    generated_candles = []
    for i in range(len(candles)):
        num = jh.timeframe_to_one_minutes(timeframe)

        if (i + 1) % num == 0:
            generated_candles.append(
                generate_candle_from_one_minutes(
                    timeframe,
                    candles[(i - (num - 1)):(i + 1)],
                    True
                )
            )

    return np.array(generated_candles)


def store_candles(candles: np.ndarray, exchange: str, symbol: str) -> None:
    """
    Stores candles in the database. The stored data can later be used for being fetched again via get_candles or even for running backtests on them.
    A common use case for this function is for importing candles from a CSV file so you can later use them for backtesting.
    """
    from jesse.modes.import_candles_mode import store_candles_list as store_candles_from_list
    import jesse.helpers as jh

    # check if .env file exists
    if not jh.is_unit_testing() and not jh.is_jesse_project():
        raise FileNotFoundError(
            'Invalid directory: ".env" file not found. To use Jesse inside notebooks, create notebooks inside the root of a Jesse project.'
        )

    # validate that candles type must be np.ndarray
    if not isinstance(candles, np.ndarray):
        raise TypeError('candles must be a numpy array.')

    # add validation for timeframe to make sure it's `1m`
    if candles[1][0] - candles[0][0] != 60_000:
        raise ValueError(
            f'Candles passed to the research.store_candles() must be 1m candles. '
            f'\nThe difference between your candle timestamps is {candles[1][0] - candles[0][0]} milliseconds which is '
            f'more than the accepted 60000 milliseconds.'
        )

    arr = [{
        'id': jh.generate_unique_id(),
        'exchange': exchange,
        'symbol': symbol,
        'timeframe': '1m',
        'timestamp': c[0],
        'open': c[1],
        'close': c[2],
        'high': c[3],
        'low': c[4],
        'volume': c[5]
    } for c in candles]

    if not jh.is_unit_testing():
        store_candles_from_list(arr)


def candlestick_chart(candles: np.ndarray):
    """
    Displays a candlestick chart from the numpy array
    """
    import mplfinance as mpf
    df = utils.numpy_candles_to_dataframe(candles)
    mpf.plot(df, type='candle')


def fake_candle(attributes: dict = None, reset: bool = False) -> np.ndarray:
    """
    Generates a fake candle.
    """
    return factories.fake_candle(attributes, reset)


def fake_range_candles(count: int) -> np.ndarray:
    """
    Generates a range of candles with random values.
    """
    return factories.range_candles(count)


def candles_from_close_prices(prices: Union[list, range]) -> np.ndarray:
    """
    Generates a range of candles from a list of close prices.
    The first candle has the timestamp of "2021-01-01T00:00:00+00:00"
    """
    return factories.candles_from_close_prices(prices)
