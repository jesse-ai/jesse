import math
import pandas as pd
import numpy as np
from typing import Union


def risk_to_size(capital_size, risk_percentage, risk_per_qty, entry_price) -> float:
    """
    calculates the size of the position based on the amount of risk percentage you're willing to take
    example: round(risk_to_size(10000, 1, 0.7, 8.6)) == 1229

    :param capital_size:
    :param risk_percentage:
    :param risk_per_qty:
    :param entry_price:
    :return: float
    """
    if risk_per_qty == 0:
        raise ValueError('risk cannot be zero')

    risk_percentage /= 100
    temp_size = ((risk_percentage * capital_size) / risk_per_qty) * entry_price
    return min(temp_size, capital_size)


def risk_to_qty(capital, risk_per_capital, entry_price, stop_loss_price) -> float:
    """
    a risk management tool to quickly get the qty based on risk percentage

    :param capital:
    :param risk_per_capital:
    :param entry_price:
    :param stop_loss_price:
    :return: float
    """
    risk_per_qty = abs(entry_price - stop_loss_price)
    size = risk_to_size(capital, risk_per_capital, risk_per_qty, entry_price)
    return size_to_qty(size, entry_price)


def size_to_qty(position_size, price, precision=3) -> float:
    """
    converts position-size to quantity
    example: requesting $100 at the price of %50 would return 2

    :param position_size: float
    :param price: float
    :param precision: int
    :return: float
    """
    if math.isnan(position_size) or math.isnan(price):
        raise TypeError()

    return round(position_size / price, precision)


def qty_to_size(qty, price) -> float:
    """
    converts quantity to position-size
    example: requesting 2 shares at the price of %50 would return $100

    :param qty: float
    :param price: float
    :return: float
    """
    if math.isnan(qty) or math.isnan(price):
        raise TypeError()

    return qty * price


def anchor_timeframe(timeframe) -> str:
    """
    Returns the anchor timeframe. Useful for writing
    dynamic strategies using multiple timeframes.

    :param timeframe: str
    :return: str
    """
    from jesse.enums import timeframes

    dic = {
        timeframes.MINUTE_1: timeframes.MINUTE_5,
        timeframes.MINUTE_3: timeframes.MINUTE_15,
        timeframes.MINUTE_5: timeframes.MINUTE_30,
        timeframes.MINUTE_15: timeframes.HOUR_2,
        timeframes.MINUTE_30: timeframes.HOUR_3,
        timeframes.HOUR_1: timeframes.HOUR_4,
        timeframes.HOUR_2: timeframes.HOUR_6,
        timeframes.HOUR_3: timeframes.DAY_1,
        timeframes.HOUR_4: timeframes.DAY_1,
        timeframes.HOUR_6: timeframes.DAY_1,
    }

    return dic[timeframe]


def limit_stop_loss(entry_price, stop_price, trade_type, max_allowed_risk_percentage) -> float:
    """
    Limits the stop-loss price according to the max allowed risk percentage.
    (How many percent you're OK with the price going against your position)

    :param entry_price:
    :param stop_price:
    :param trade_type:
    :param max_allowed_risk_percentage:
    :return: float
    """
    risk = abs(entry_price - stop_price)
    max_allowed_risk = entry_price * (max_allowed_risk_percentage / 100)
    risk = min(risk, max_allowed_risk)
    return (entry_price - risk) if trade_type == 'long' else (entry_price + risk)


def estimate_risk(entry_price, stop_price) -> float:
    """
    estimates the risk per share

    :param entry_price: float
    :param stop_price: float
    :return: float
    """
    if math.isnan(entry_price) or math.isnan(stop_price):
        raise TypeError()

    return abs(entry_price - stop_price)


def crossed(series1: np.ndarray, series2: Union[float, int, np.ndarray], direction=None, sequential=False) -> bool:
    """
    Helper for detecion of crosses

    :param series1: np.ndarray
    :param series2: float, int, np.ndarray
    :param direction: str - default: None - above or below

    :return: bool
    """
    series1 = pd.Series(series1)

    series2 = pd.Series(index=series1.index, data=series2)

    if sequential:

        if direction is None or direction == "above":
            cross_above = pd.Series((series1 > series2) & (series1.shift(1) <= series2.shift(1)))

        if direction is None or direction == "below":
            cross_below = pd.Series((series1 < series2) & (series1.shift(1) >= series2.shift(1)))

        if direction is None:
            cross_any = cross_above | cross_below
            return cross_any.to_numpy()

        if direction == "above":
            return cross_above.to_numpy()
        else:
            return cross_below.to_numpy()
    else:
        if direction is None or direction == "above":
            cross_above = series1.iloc[-2] <= series2.iloc[-2] and series1.iloc[-1] > series2.iloc[-1]
        if direction is None or direction == "below":
            cross_below = series1.iloc[-2] >= series2.iloc[-2] and series1.iloc[-1] < series2.iloc[-1]

        if direction is None:
            return cross_above or cross_below

        if direction == "above":
            return cross_above
        else:
            return cross_below


def numpy_candles_to_dataframe(candles: np.ndarray, name_date="date", name_open="open", name_high="high",
                               name_low="low", name_close="close", name_volume="volume"):
    columns = [name_date, name_open, name_close, name_high, name_low, name_volume]
    df = pd.DataFrame(data=candles, index=candles[:, 0], columns=columns)
    return df
