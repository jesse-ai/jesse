from collections import namedtuple

import numpy as np

from jesse.helpers import get_candle_source

RSMK = namedtuple('RSMK', ['indicator', 'signal'])


def rsmk(candles: np.ndarray, candles_compare: np.ndarray, lookback: int = 90, period: int = 3, signal_period: int = 20,
        source_type: str = "close", sequential: bool = False) -> RSMK:
    """
    RSMK - Relative Strength

    :param candles: np.ndarray
    :param candles_compare: np.ndarray
    :param lookback: int - default: 90
    :param period: int - default: 3
    :param signal_period: int - default: 20
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    if not sequential and candles.shape[0] > 240:
        candles = candles[-240:]
        candles_compare = candles_compare[-240:]

    source = get_candle_source(candles, source_type=source_type)
    source_compare = get_candle_source(candles_compare, source_type=source_type)

    # Calculate log ratio of asset to index
    log_ratio = np.log(source / source_compare)

    # Calculate momentum: difference between current log ratio and the one from 'lookback' periods ago using vectorized operation
    mom = np.full_like(log_ratio, np.nan)
    if len(log_ratio) > lookback:
        mom[lookback:] = log_ratio[lookback:] - log_ratio[:-lookback]

    def ema(series: np.ndarray, period_val: float) -> np.ndarray:
        alpha = 2.0 / (max(1.0, period_val) + 1.0)
        n = series.shape[0]
        out = np.full_like(series, np.nan)

        # Identify the first valid (non-NaN) index
        valid_indices = np.flatnonzero(~np.isnan(series))
        if valid_indices.size == 0:
            return out

        start_idx = valid_indices[0]
        segment = series[start_idx:]
        m = segment.shape[0]

        # Create matrices for vectorized computation
        t = np.arange(m).reshape(-1, 1)  # shape (m, 1)
        i = np.arange(m).reshape(1, -1)  # shape (1, m)
        lag = t - i

        # Compute weights:
        # For t >= i, if i == 0 then weight = (1 - alpha)^(t - i), else weight = alpha * (1 - alpha)^(t - i)
        weights = np.where(lag < 0, 0, np.where(i == 0, (1 - alpha)**lag, alpha * (1 - alpha)**lag))

        ema_segment = np.sum(weights * segment.reshape(1, -1), axis=1)
        out[start_idx:] = ema_segment
        return out

    # Calculate RSMK indicator: EMA of the momentum scaled by 100
    rsmk_indicator = ema(mom, period) * 100.0

    # Calculate signal line as EMA of the RSMK indicator
    rsmk_signal = ema(rsmk_indicator, signal_period)

    if not sequential:
        rsmk_indicator = rsmk_indicator[-1]
        rsmk_signal = rsmk_signal[-1]

    return RSMK(rsmk_indicator, rsmk_signal)
