from random import randint

import numpy as np

first_timestamp = 1552309186171
open_price = randint(40, 100)
close_price = randint(open_price, 110) if randint(0, 1) else randint(
    30, open_price)
max_price = max(open_price, close_price)
high_price = max_price if randint(0, 1) else randint(max_price, max_price + 10)
min_price = min(open_price, close_price)
low_price = min_price if randint(0, 1) else randint(min_price, min_price + 10)


def fake_range_candle(count) -> np.ndarray:
    """

    :param count:
    :return:
    """
    fake_candle(reset=True)
    arr = np.zeros((count, 6))
    for i in range(count):
        arr[i] = fake_candle()
    return arr


def fake_range_candle_from_range_prices(prices) -> np.ndarray:
    """

    :param prices:
    :return:
    """
    fake_candle(reset=True)
    global first_timestamp
    arr = []
    prev_p = np.nan
    for p in prices:
        # first prev_p
        if np.isnan(prev_p):
            prev_p = p - 0.5

        first_timestamp += 60000
        open_p = prev_p
        close_p = p
        high_p = max(open_p, close_p)
        low_p = min(open_p, close_p)
        vol = randint(0, 200)

        arr.append([first_timestamp, open_p, close_p, high_p, low_p, vol])

        # save prev_p for next candle
        prev_p = p

    return np.array(arr)


def fake_candle(attributes=None, reset=False):
    """

    :param attributes:
    :param reset:
    :return:
    """
    global first_timestamp
    global open_price
    global close_price
    global max_price
    global high_price
    global min_price
    global low_price

    if reset:
        first_timestamp = 1552309186171
        open_price = randint(40, 100)
        close_price = randint(open_price, 110)
        high_price = max(open_price, close_price)
        low_price = min(open_price, close_price)

    if attributes is None:
        attributes = {}

    first_timestamp += 60000
    open_price = close_price
    close_price += randint(1, 8)
    high_price = max(open_price, close_price)
    low_price = min(open_price - 1, close_price)
    volume = randint(1, 100)
    timestamp = first_timestamp

    return np.array([
        attributes.get('timestamp', timestamp),
        attributes.get('open', open_price),
        attributes.get('close', close_price),
        attributes.get('high', high_price),
        attributes.get('low', low_price),
        attributes.get('volume', volume)
    ], dtype=np.float64)
