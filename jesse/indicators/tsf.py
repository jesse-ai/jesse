from typing import Union

import numpy as np

from jesse.helpers import get_candle_source, slice_candles


def tsf(candles: np.ndarray, period: int = 14, source_type: str = "close", sequential: bool = False) -> Union[
    float, np.ndarray]:
    """
    TSF - Time Series Forecast
    
    A linear regression projection into the future. It calculates a linear regression line 
    using the specified period and projects it forward.

    :param candles: np.ndarray
    :param period: int - default: 14
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: float | np.ndarray
    """
    candles = slice_candles(candles, sequential)
    source = get_candle_source(candles, source_type=source_type)
    
    if sequential:
        result = np.full_like(source, np.nan)
        if len(source) >= period:
            # Create time indices array
            x = np.arange(period)
            # Calculate means for x
            x_mean = np.mean(x)
            # Calculate denominator term (sum of squared deviations)
            x_diff = x - x_mean
            denominator = np.sum(x_diff ** 2)
            
            # Create sliding windows view of the data
            windows = np.lib.stride_tricks.sliding_window_view(source, period)
            # Calculate means for each window
            y_means = np.mean(windows, axis=1)
            
        # Calculate slopes using vectorized operations
            slopes = np.sum((windows - y_means[:, None]) * x_diff, axis=1) / denominator
            # Calculate intercepts
            intercepts = y_means - slopes * x_mean
            
            # Calculate forecast values
            forecasts = intercepts + slopes * period
            
            # Place forecasts in result array
            result[period-1:] = forecasts
        
        return result
    else:
        # For non-sequential, just calculate the last window
        x = np.arange(period)
        X = np.vstack((np.ones(period), x)).T
        y = source[-period:]
        beta = np.linalg.inv(X.T @ X) @ X.T @ y
        return beta[0] + beta[1] * period
