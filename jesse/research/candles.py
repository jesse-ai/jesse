import numpy as np
from typing import Union, Tuple
from jesse import factories, utils
import jesse.helpers as jh
from jesse.services.candle import get_candles as _get_candles


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
    if not jh.is_jesse_project():
        raise FileNotFoundError(
            'Invalid directory: ".env" file not found. To use Jesse inside notebooks, create notebooks inside the root of a Jesse project.'
        )

    return _get_candles(exchange, symbol, timeframe, start_date_timestamp, finish_date_timestamp, warmup_candles_num, caching, is_for_jesse)


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
