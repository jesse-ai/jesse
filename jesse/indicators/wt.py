from collections import namedtuple
import numpy as np
from jesse.helpers import slice_candles
import jesse_rust

Wavetrend = namedtuple('Wavetrend', ['wt1', 'wt2', 'wtCrossUp', 'wtCrossDown', 'wtOversold', 'wtOverbought', 'wtVwap'])


# Wavetrend indicator ported from:  https://www.tradingview.com/script/Msm4SjwI-VuManChu-Cipher-B-Divergences/
#                                   https://www.tradingview.com/script/2KE8wTuF-Indicator-WaveTrend-Oscillator-WT/
#
# buySignal = wtCross and wtCrossUp and wtOversold
# sellSignal = wtCross and wtCrossDown and wtOverbought
#
# See https://github.com/ysdede/lazarus3/blob/partialexit/strategies/lazarus3/__init__.py for working jesse.ai example.

def wt(candles: np.ndarray, wtchannellen: int = 9, wtaveragelen: int = 12, wtmalen: int = 3, oblevel: int = 53, oslevel: int = -53, source_type: str = "hlc3", sequential: bool = False) -> Wavetrend:
    """
    Wavetrend indicator

    :param candles: np.ndarray
    :param wtchannellen:  int - default: 9
    :param wtaveragelen: int - default: 12
    :param wtmalen: int - default: 3
    :param oblevel: int - default: 53
    :param oslevel: int - default: -53
    :param source_type: str - default: "hlc3"
    :param sequential: bool - default: False

    :return: Wavetrend
    """
    candles = slice_candles(candles, sequential)
    
    # Use the Rust implementation
    wt1, wt2, wtCrossUp, wtCrossDown, wtOversold, wtOverbought, wtVwap = jesse_rust.wt(
        candles, 
        wtchannellen, 
        wtaveragelen, 
        wtmalen, 
        float(oblevel), 
        float(oslevel), 
        source_type
    )

    if sequential:
        return Wavetrend(wt1, wt2, wtCrossUp, wtCrossDown, wtOversold, wtOverbought, wtVwap)
    else:
        return Wavetrend(wt1[-1], wt2[-1], wtCrossUp[-1], wtCrossDown[-1], wtOversold[-1], wtOverbought[-1], wtVwap[-1])
