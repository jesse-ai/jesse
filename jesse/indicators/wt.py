import numpy as np
import talib as ta
from jesse.helpers import get_candle_source
from collections import namedtuple

wavetrend = namedtuple('Wavetrend', ['wt1', 'wt2', 'wtCrossUp', 'wtCrossDown', 'wtOversold', 'wtOverbought', 'wtVwap'])

# Wavetrend indicator ported from:  https://www.tradingview.com/script/Msm4SjwI-VuManChu-Cipher-B-Divergences/
#                                   https://www.tradingview.com/script/2KE8wTuF-Indicator-WaveTrend-Oscillator-WT/
#
# buySignal = wtCross and wtCrossUp and wtOversold
# sellSignal = wtCross and wtCrossDown and wtOverbought
#
# See https://github.com/ysdede/lazarus3/blob/partialexit/strategies/lazarus3/__init__.py for working jesse.ai example.


def wt(candles: np.ndarray,
             wtchannellen: int = 9,
             wtaveragelen: int = 12,
             wtmalen: int = 3,
             oblevel: int = 53,
             oslevel: int = -53,
             source_type="hlc3",
             sequential=False) -> wavetrend:
    if not sequential and len(candles) > 240:
        candles = candles[-240:]

    src = get_candle_source(candles, source_type=source_type)

    # wt
    esa = ta.EMA(src, wtchannellen)
    de = ta.EMA(abs(src - esa), wtchannellen)
    ci = (src - esa) / (0.015 * de)
    wt1 = ta.EMA(ci, wtaveragelen)
    wt2 = ta.SMA(wt1, wtmalen)

    wtVwap = wt1 - wt2
    wtOversold = wt2 <= oslevel
    wtOverbought = wt2 >= oblevel
    wtCrossUp = wt2 - wt1 <= 0
    wtCrossDown = wt2 - wt1 >= 0

    if sequential:
        return wavetrend(wt1, wt2, wtCrossUp, wtCrossDown, wtOversold, wtOverbought, wtVwap)
    else:
        return wavetrend(wt1[-1], wt2[-1], wtCrossUp[-1], wtCrossDown[-1], wtOversold[-1], wtOverbought[-1], wtVwap[-1])
