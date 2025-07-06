from collections import namedtuple
import numpy as np
from jesse_rust import ichimoku_cloud as ichimoku_cloud_rust

IchimokuCloud = namedtuple('IchimokuCloud', ['conversion_line', 'base_line', 'span_a', 'span_b'])


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
        
    conversion_line, base_line, span_a, span_b = ichimoku_cloud_rust(
        candles, conversion_line_period, base_line_period, 
        lagging_line_period, displacement
    )
    
    return IchimokuCloud(conversion_line, base_line, span_a, span_b)
