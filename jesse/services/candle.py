import arrow
import click
import numpy as np

import jesse.helpers as jh


def generate_candle_from_one_minutes(timeframe,
                                     candles: np.ndarray,
                                     accept_forming_candles=False):
    """

    :param timeframe:
    :param candles:
    :param accept_forming_candles:
    :return:
    """
    if len(candles) == 0:
        raise ValueError('No candles were passed')

    if not accept_forming_candles and len(candles) != jh.timeframe_to_one_minutes(timeframe):
        raise ValueError(
            'Sent only {} candles but {} is required to create a "{}" candle.'.format(
                len(candles), jh.timeframe_to_one_minutes(timeframe),
                timeframe
            )
        )

    return np.array([
        candles[0][0],
        candles[0][1],
        candles[-1][2],
        candles[:, 3].max(),
        candles[:, 4].min(),
        candles[:, 5].sum(),
    ])


def print_candle(candle, is_partial, symbol):
    """

    :param candle:
    :param is_partial:
    :param symbol:
    :return:
    """
    if jh.should_execute_silently():
        return

    if is_bullish(candle) and is_partial is True:
        candle_form = click.style('  ==', fg='green')
    elif is_bullish(candle) and is_partial is False:
        candle_form = click.style('====', bg='green')
    elif is_bearish(candle) and is_partial is True:
        candle_form = click.style('  ==', fg='red')
    else:
        candle_form = click.style('====', bg='red')

    if is_bullish(candle):
        candle_info = click.style(' {} | {} | {} | {} | {} | {} | {}'.format(
            symbol, str(arrow.get(candle[0] / 1000))[:-9], candle[1], candle[2],
            candle[3], candle[4], round(candle[5], 2)),
            fg='green')
    else:
        candle_info = click.style(' {} | {} | {} | {} | {} | {} | {}'.format(
            symbol, str(arrow.get(candle[0] / 1000))[:-9], candle[1], candle[2],
            candle[3], candle[4], round(candle[5], 2)),
            fg='red')

    print(candle_form + candle_info)


def is_bullish(candle: np.ndarray) -> bool:
    """

    :param candle:
    :return:
    """
    return candle[2] >= candle[1]


def is_bearish(candle: np.ndarray) -> bool:
    """

    :param candle:
    :return:
    """
    return candle[2] < candle[1]


def candle_includes_price(candle, price) -> bool:
    """

    :param candle:
    :param price:
    :return:
    """
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
