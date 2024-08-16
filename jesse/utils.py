import math
from decimal import Decimal
from typing import Union

import numpy as np
import pandas as pd

import jesse.helpers as jh
from jesse.enums import timeframes
import statsmodels.api as sm


def anchor_timeframe(timeframe: str) -> str:
    """
    Returns the anchor timeframe. Useful for writing
    dynamic strategies using multiple timeframes.

    :param timeframe: str
    :return: str
    """

    dic = {
        timeframes.MINUTE_1: timeframes.MINUTE_5,
        timeframes.MINUTE_3: timeframes.MINUTE_15,
        timeframes.MINUTE_5: timeframes.MINUTE_30,
        timeframes.MINUTE_15: timeframes.HOUR_2,
        timeframes.MINUTE_30: timeframes.HOUR_3,
        timeframes.MINUTE_45: timeframes.HOUR_3,
        timeframes.HOUR_1: timeframes.HOUR_4,
        timeframes.HOUR_2: timeframes.HOUR_6,
        timeframes.HOUR_3: timeframes.DAY_1,
        timeframes.HOUR_4: timeframes.DAY_1,
        timeframes.HOUR_6: timeframes.DAY_1,
        timeframes.HOUR_8: timeframes.DAY_1,
        timeframes.HOUR_12: timeframes.DAY_1,
    }

    return dic[timeframe]


def crossed(series1: np.ndarray, series2: Union[float, int, np.ndarray], direction: str = None,
            sequential: bool = False) -> bool:
    """
    Helper for detection of crosses

    :param series1: np.ndarray
    :param series2: float, int, np.array
    :param direction: str - default: None - above or below
    :param sequential: bool - default: False

    :return: bool
    """

    if sequential:
        series1_shifted = jh.np_shift(series1, 1, np.nan)

        if type(series2) is np.ndarray:
            series2_shifted = jh.np_shift(series2, 1, np.nan)
        else:
            series2_shifted = series2

        if direction is None or direction == "above":
            cross_above = np.logical_and(series1 > series2, series1_shifted <= series2_shifted)

        if direction is None or direction == "below":
            cross_below = np.logical_and(series1 < series2, series1_shifted >= series2_shifted)

        if direction is None:
            return np.logical_or(cross_above, cross_below)

    else:
        if type(series2) is not np.ndarray:
            series2 = np.array([series2, series2])

        if direction is None or direction == "above":
            cross_above = series1[-2] <= series2[-2] and series1[-1] > series2[-1]
        if direction is None or direction == "below":
            cross_below = series1[-2] >= series2[-2] and series1[-1] < series2[-1]

        if direction is None:
            return cross_above or cross_below

    if direction == "above":
        return cross_above
    else:
        return cross_below


def estimate_risk(entry_price: float, stop_price: float) -> float:
    """
    estimates the risk per share

    :param entry_price: float
    :param stop_price: float
    :return: float
    """
    if math.isnan(entry_price) or math.isnan(stop_price):
        raise TypeError()

    return abs(entry_price - stop_price)


def limit_stop_loss(entry_price: float, stop_price: float, trade_type: str, max_allowed_risk_percentage: int) -> float:
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


def numpy_candles_to_dataframe(candles: np.ndarray, name_date: str = "date", name_open: str = "open",
                               name_high: str = "high",
                               name_low: str = "low", name_close: str = "close",
                               name_volume: str = "volume") -> pd.DataFrame:
    columns = [name_date, name_open, name_close, name_high, name_low, name_volume]
    df = pd.DataFrame(data=candles, index=pd.to_datetime(candles[:, 0], unit="ms"), columns=columns)
    df[name_date] = pd.to_datetime(df.index, unit="ms")
    return df


def qty_to_size(qty: float, price: float) -> float:
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


def risk_to_qty(capital: float, risk_per_capital: float, entry_price: float, stop_loss_price: float, precision: int = 8,
                fee_rate: float = 0) -> float:
    """
    a risk management tool to quickly get the qty based on risk percentage

    :param capital:
    :param risk_per_capital:
    :param entry_price:
    :param stop_loss_price:
    :param precision:
    :param fee_rate:
    :return: float
    """
    risk_per_qty = abs(entry_price - stop_loss_price)
    size = risk_to_size(capital, risk_per_capital, risk_per_qty, entry_price)

    if fee_rate != 0:
        size = size * (1 - fee_rate * 3)

    return size_to_qty(size, entry_price, precision=precision, fee_rate=fee_rate)


def risk_to_size(capital_size: float, risk_percentage: float, risk_per_qty: float, entry_price: float) -> float:
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


def size_to_qty(position_size: float, entry_price: float, precision: int = 3, fee_rate: float = 0) -> float:
    """
    converts position-size to quantity
    example: requesting $100 at the entry_price of $50 would return 2
    :param position_size: float
    :param entry_price: float
    :param precision: int
    :param fee_rate:
    :return: float
    """
    # make sure entry_price is not None
    if entry_price is None:
        raise TypeError(f"entry_price is None")

    if math.isnan(position_size) or math.isnan(entry_price):
        raise TypeError(f"position_size: {position_size}, entry_price: {entry_price}")

    if fee_rate != 0:
        position_size *= 1 - fee_rate * 3

    return jh.floor_with_precision(position_size / entry_price, precision)


def subtract_floats(float1: float, float2: float) -> float:
    """
    Subtracts two floats without the rounding issue in Python

    :param float1: float
    :param float2: float

    :return: float
    """
    return float(Decimal(str(float1)) - Decimal(str(float2)))


def sum_floats(float1: float, float2: float) -> float:
    """
    Sums two floats without the rounding issue in Python

    :param float1: float
    :param float2: float

    :return: float
    """
    return float(Decimal(str(float1)) + Decimal(str(float2)))


def strictly_increasing(series: np.ndarray, lookback: int) -> bool:
    a = series[-lookback:]
    diff = np.diff(a)
    return np.all(diff > 0)


def strictly_decreasing(series: np.ndarray, lookback: int) -> bool:
    a = series[-lookback:]
    diff = np.diff(a)
    return np.all(diff < 0)


def streaks(series: np.ndarray, use_diff=True) -> np.ndarray:
    if use_diff:
        series = np.diff(series)
    pos = np.clip(series, 0, 1).astype(bool).cumsum()
    neg = np.clip(series, -1, 0).astype(bool).cumsum()
    streak = np.where(series >= 0, pos - np.maximum.accumulate(np.where(series <= 0, pos, 0)),
                      -neg + np.maximum.accumulate(np.where(series >= 0, neg, 0)))

    return np.concatenate(
        (np.full((series.shape[0] - streak.shape[0]), np.nan), streak)
    )


def signal_line(series: np.ndarray, period: int = 10, matype: int = 0) -> np.ndarray:
    from jesse.indicators.ma import ma
    return ma(series, period=period, matype=matype, sequential=True)


def kelly_criterion(win_rate: float, ratio_avg_win_loss: float) -> float:
    return win_rate - ((1 - win_rate) / ratio_avg_win_loss)


def prices_to_returns(price_series: np.ndarray) -> np.ndarray:
    """
    converts a series of asset prices to returns.
    """
    pct = np.diff(price_series) / price_series[:-1] * 100
    return jh.same_length(price_series, pct)


def z_score(series: np.ndarray) -> np.ndarray:
    """
    A Z-score is a numerical measurement that describes a value's relationship to the mean of a group of values. Z-score is measured in terms of standard deviations from the mean
    """
    return (series - np.mean(series)) / np.std(series)


def are_cointegrated(price_returns_1: np.ndarray, price_returns_2: np.ndarray, cutoff=0.05) -> bool:
    """
    Uses unit-root test on residuals to test for cointegrated relationship
    See Hamilton (1994) 19.2 for more details
    H_0 is that there is no cointegration i.e. that the residuals have are unit root series (non-stationary)
    We must observe significant p-value to convince ourselves that the series are cointegrated
    """
    from statsmodels.tsa.stattools import coint

    p_value = coint(price_returns_1, price_returns_2)[1]
    return p_value < cutoff


def dd(msg: str) -> None:
    """
    The dd function dumps the given variables and ends execution of the script. 
    Used for debugging. 

    :param msg: str
    """
    print(msg)
    jh.terminate_app()


def combinations_without_repeat(a: np.ndarray, n: int = 2) -> np.ndarray:
    """
    Creates an array containing all combinations of the passed arrays individual values without repetitions. Useful for the optimization mode.
    """
    from itertools import permutations
    if n <= 1:
        raise ValueError("n must be >= 2")
    return np.array(list(permutations(a, n)))


def wavelet_denoising(raw: np.ndarray, wavelet='haar', level: int = 1, mode: str = 'symmetric',
                      smoothing_factor: float = 0, threshold_mode: str = 'hard') -> np.ndarray:
    """
    deconstructs, thresholds then reconstructs
    higher thresholds = less detailed reconstruction

    Only consider haar, db, sym, coif wavelet basis functions, as these are relatively suitable for financial data
    """
    import pywt
    # Deconstruct
    coeff = pywt.wavedec(raw, wavelet, mode=mode)
    # Mean absolute deviation of a signal
    max_level = pywt.dwt_max_level(len(raw), wavelet)
    level = min(level, max_level)
    madev = np.mean(np.absolute(coeff[-level] - np.mean(coeff[-level])))
    # The hardcored factor is explained here: https://en.wikipedia.org/wiki/Median_absolute_deviation
    sigma = (1 / 0.67449) * madev * smoothing_factor
    threshold = sigma * np.sqrt(2 * np.log(len(raw)))
    coeff[1:] = (pywt.threshold(i, value=threshold, mode=threshold_mode) for i in coeff[1:])
    signal = pywt.waverec(coeff, wavelet, mode=mode)
    if len(signal) > len(raw):
        signal = np.delete(signal, -1)
    return signal


def calculate_alpha_beta(returns1: np.ndarray, returns2: np.ndarray) -> tuple:
    # Add a constant to the independent variable (returns2)
    X = sm.add_constant(returns2)  # Independent variable
    model = sm.OLS(returns1, X).fit()  # Fit the model
    alpha = model.params[0]  # Intercept (alpha)
    beta = model.params[1]  # Slope (beta)
    return alpha, beta
