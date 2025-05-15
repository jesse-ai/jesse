import datetime as dt

import numpy as np
import pytest

from jesse.strategies.Strategy import StrategyCandles

def test_strategy_candles():

    c1 = np.array([1543387200000, 200, 190, 220, 300, 1000])
    c2 = np.array([1543387500000, 190, 250, 220, 301, 1010])
    c3 = np.array([1543387800000, 250, 270, 220, 302, 1020])

    candles_np = np.hstack((c1, c2, c3))
    with pytest.raises(ValueError):
        candles = StrategyCandles(candles_np)

    candles_np = np.vstack((c1, c2, c3))
    candles = StrategyCandles(candles_np)

    assert candles.time[1] == 1543387500000
    assert candles.open[1] == 190
    assert candles.close[1] == 250
    assert candles.high[1] == 220
    assert candles.low[1] == 301
    assert candles.time_dt[1] == dt.datetime(2018, 11, 28, 9, 45)

    assert (candles.time == candles_np[:, 0]).all()
    assert (candles.open == candles_np[:, 1]).all()
    assert (candles.close == candles_np[:, 2]).all()
    assert (candles.high == candles_np[:, 3]).all()
    assert (candles.low == candles_np[:, 4]).all()
    assert (candles.volume == candles_np[:, 5]).all()

    assert (candles[0] == c1).all()
    assert (candles[1] == c2).all()
    assert (candles[2] == c3).all()

    assert candles[-2].time == candles.time[-2]
    assert candles[-2].open == candles.open[-2]
    assert candles[-2].close == candles.close[-2]
    assert candles[-2].high == candles.high[-2]
    assert candles[-2].low == candles.low[-2]
    assert candles[-2].volume == candles.volume[-2]
    assert candles[-2].time_dt == candles.time_dt[-2]

    assert candles.time_dt[-1] == dt.datetime.fromtimestamp(candles.time[-1] / 1000)

    assert type(candles[0]) == type(candles)
    assert type(candles[0:1]) == type(candles)
    assert type(candles[0:1, 0:2]) == np.ndarray




