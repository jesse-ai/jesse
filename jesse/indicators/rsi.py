import numpy as np
from typing import Union

from jesse.helpers import get_candle_source, slice_candles


def rsi(candles: np.ndarray, period: int = 14, source_type: str = "close", sequential: bool = False) -> Union[float, np.ndarray]:
    """
    RSI - Relative Strength Index

    :param candles: np.ndarray
    :param period: int - default: 14
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, sequential)
        source = get_candle_source(candles, source_type=source_type)
    
    # Convert source to a numpy array of floats
    p = np.asarray(source, dtype=float)
    n = len(p)
    
    # Not enough data to compute RSI if we don't have at least period+1 price points
    if n < period + 1:
        return np.nan if not sequential else np.full(n, np.nan)
    
    # Compute price differences
    delta = np.diff(p)
    gains = np.where(delta > 0, delta, 0)
    losses = np.where(delta < 0, -delta, 0)
    
    # Initialize average gains and losses arrays (length equal to len(gains))
    avg_gain = np.zeros_like(gains)
    avg_loss = np.zeros_like(losses)
    
    # Vectorized computation of average gains and losses using matrix operations to mimic Wilder's smoothing method
    alpha = 1/period
    # Compute the initial simple averages
    A0_gain = np.mean(gains[:period])
    A0_loss = np.mean(losses[:period])
    # The number of smoothed values to compute (for gains and losses) equals the length of gains from index (period-1) to end
    # Since gains has length (n-1), we want L = (n-1) - (period-1) = n - period
    L = len(gains) - (period - 1)  
    
    # Vectorized smoothing for avg_gain:
    # x_gain: gains from index 'period' onward, length = (n-1) - period = L - 1
    x_gain = gains[period:]
    if L > 1:
        t_values = np.arange(1, L)  # t=1,...,L-1
        # Build lower triangular matrix of shape (L-1, L-1) with elements (1-alpha)^(t-1-k)
        M_gain = np.tril((1 - alpha) ** (np.subtract.outer(np.arange(L-1), np.arange(L-1))))
        # weighted sum: for each t from 1 to L-1, sum_{k=0}^{t-1} (1-alpha)^(t-1-k)*x_gain[k]
        weighted_sum_gain = M_gain.dot(x_gain)
        A_gain = np.empty(L)
        A_gain[0] = A0_gain
        A_gain[1:] = A0_gain * ((1 - alpha) ** t_values) + alpha * weighted_sum_gain
    else:
        A_gain = np.array([A0_gain])
    avg_gain[period - 1:] = A_gain
    
    # Vectorized smoothing for avg_loss:
    x_loss = losses[period:]
    if L > 1:
        t_values = np.arange(1, L)
        M_loss = np.tril((1 - alpha) ** (np.subtract.outer(np.arange(L-1), np.arange(L-1))))
        weighted_sum_loss = M_loss.dot(x_loss)
        A_loss = np.empty(L)
        A_loss[0] = A0_loss
        A_loss[1:] = A0_loss * ((1 - alpha) ** t_values) + alpha * weighted_sum_loss
    else:
        A_loss = np.array([A0_loss])
    avg_loss[period - 1:] = A_loss
    
    # Prepare RSI result array of same length as price array, fill initial values with NaN
    rsi_values = np.full(n, np.nan)
    
    # Vectorized computation of RSI for indices period to end
    with np.errstate(divide='ignore', invalid='ignore'):
        rs = avg_gain[period - 1:] / avg_loss[period - 1:]
        rsi_comp = 100 - 100 / (1 + rs)
        rsi_comp = np.where(avg_loss[period - 1:] == 0, 100.0, rsi_comp)
    rsi_values[period:] = rsi_comp
    
    return rsi_values if sequential else rsi_values[-1]
