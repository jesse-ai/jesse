from collections import namedtuple
import numpy as np
from numba import njit

IchimokuCloud = namedtuple('IchimokuCloud', ['conversion_line', 'base_line', 'span_a', 'span_b'])


@njit
def _get_period_hl(candles: np.ndarray, period: int) -> tuple:
    """
    Calculate period high and low using Numba
    """
    period_high = candles[-period:, 3].max()  # high prices
    period_low = candles[-period:, 4].min()   # low prices
    return period_high, period_low


@njit
def _calculate_ichimoku(candles: np.ndarray, conversion_line_period: int, 
                       base_line_period: int, lagging_line_period: int,
                       displacement: int) -> tuple:
    """
    Core Ichimoku Cloud calculation using Numba
    """
    # Calculate for earlier period (displaced)
    earlier_candles = candles[:-(displacement - 1)]
    
    # Earlier periods calculations
    small_ph, small_pl = _get_period_hl(earlier_candles, conversion_line_period)
    mid_ph, mid_pl = _get_period_hl(earlier_candles, base_line_period)
    long_ph, long_pl = _get_period_hl(earlier_candles, lagging_line_period)
    
    early_conversion_line = (small_ph + small_pl) / 2
    early_base_line = (mid_ph + mid_pl) / 2
    span_a = (early_conversion_line + early_base_line) / 2
    span_b = (long_ph + long_pl) / 2
    
    # Current period calculations
    current_small_ph, current_small_pl = _get_period_hl(candles, conversion_line_period)
    current_mid_ph, current_mid_pl = _get_period_hl(candles, base_line_period)
    
    current_conversion_line = (current_small_ph + current_small_pl) / 2
    current_base_line = (current_mid_ph + current_mid_pl) / 2
    
    return current_conversion_line, current_base_line, span_a, span_b


def ichimoku_cloud(candles: np.ndarray, conversion_line_period: int = 9, base_line_period: int = 26,
                   lagging_line_period: int = 52, displacement: int = 26) -> IchimokuCloud:
    """
    Ichimoku Cloud

    :param candles: np.ndarray
    :param conversion_line_period: int - default: 9
    :param base_line_period: int - default: 26
    :param lagging_line_period: int - default: 52
    :param displacement: - default: 26

    :return: IchimokuCloud(conversion_line, base_line, span_a, span_b)
    """
    if candles.shape[0] < 80:
        return IchimokuCloud(np.nan, np.nan, np.nan, np.nan)

    if candles.shape[0] > 80:
        candles = candles[-80:]
        
    conversion_line, base_line, span_a, span_b = _calculate_ichimoku(
        candles, conversion_line_period, base_line_period, 
        lagging_line_period, displacement
    )
    
    return IchimokuCloud(conversion_line, base_line, span_a, span_b)
