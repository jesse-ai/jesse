from collections import namedtuple

from .macd import macd
from .sma import sma
from .stddev import stddev

import numpy as np
import jesse.helpers as jh
from jesse.helpers import get_candle_source, slice_candles

WaddahATTRExplosionTuple = namedtuple('WaddahATTRExplosionTuple', [
                                      'explosion_line', 'trend_power', 'trend_direction'])


def waddah_attr_explosion(candles: np.ndarray, sensitivity: int = 150, fast_length: int = 20, slow_length: int = 40, channel_length: int = 20, mult: float = 2.0, source_type: str = "close") -> WaddahATTRExplosionTuple:
    """
    @author LazyBear 
    credits: https://www.tradingview.com/v/iu3kKWDI/

    WADDAH_ATTR_EXPLOSION - Waddah ATTR Explosion

    :param candles: np.ndarray
    :param sensitivity: int - default: 150
    :param fast_length: int - default: 20
    :param slow_length: int - default: 40
    :param channel_length: int - default: 20
    :param mult: float - default: 2.0
    :param source_type: str - default: "close"
    :param sequential: bool - default: False

    :return: WaddahATTRExplosionTuple(explosion_line, trend_power, trend_direction)
    """
    jh.dump(candles)
    if len(candles.shape) == 1:
        source = candles
    else:
        candles = slice_candles(candles, False)
        source = get_candle_source(candles, source_type=source_type)

    t1 = (macd(source, fast_period=fast_length, slow_period=slow_length)[0] -
          macd(source[:-1], fast_period=fast_length, slow_period=slow_length)[0])*sensitivity
    trend = 1 if t1 >= 0 else -1
    e1 = _calc_bb_upper(source, channel_length, mult) - _calc_bb_lower(source, channel_length, mult)

    return WaddahATTRExplosionTuple(e1, t1, trend)


def _calc_bb_upper(source, length, mult):
    basis = sma(source, length)
    dev = mult * stddev(source, length)
    return basis + dev


def _calc_bb_lower(source, length, mult):
    basis = sma(source, length)
    dev = mult * stddev(source, length)
    return basis - dev
