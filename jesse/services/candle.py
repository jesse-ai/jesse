import arrow
import numpy as np

import jesse.helpers as jh
from jesse.services import logger


def generate_candle_from_one_minutes(timeframe: str,
                                     candles: np.ndarray,
                                     accept_forming_candles: bool = False) -> np.ndarray:
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
