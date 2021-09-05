import numpy as np
import pandas as pd
import pytest

from jesse import utils
from tests.data.test_candles_indicators import test_candles_19


def test_anchor_timeframe():
    assert utils.anchor_timeframe('1m') == '5m'
    assert utils.anchor_timeframe('3m') == '15m'
    assert utils.anchor_timeframe('5m') == '30m'
    assert utils.anchor_timeframe('15m') == '2h'
    assert utils.anchor_timeframe('30m') == '3h'
    assert utils.anchor_timeframe('1h') == '4h'
    assert utils.anchor_timeframe('2h') == '6h'
    assert utils.anchor_timeframe('3h') == '1D'
    assert utils.anchor_timeframe('4h') == '1D'
    assert utils.anchor_timeframe('6h') == '1D'


def test_crossed():
    candles = np.array(test_candles_19)
    cross_100 = utils.crossed(candles[:, 2], 100)
    assert cross_100 == False
    cross_120 = utils.crossed(candles[:, 2], 120)
    assert cross_120 == True
    cross_120 = utils.crossed(candles[:, 2], 120, direction="below")
    assert cross_120 == True
    cross_120 = utils.crossed(candles[:, 2], 120, direction="above")
    assert cross_120 == False
    seq_cross_200 = utils.crossed(candles[:, 2], 200, direction="below", sequential=True)
    assert seq_cross_200[-5] == True
    seq_cross_200 = utils.crossed(candles[:, 2], 200, direction="above", sequential=True)
    assert seq_cross_200[-5] == False
    seq_cross_120 = utils.crossed(candles[:, 2], 120, sequential=True)
    assert seq_cross_120[-1] == True
    array_array_cross_above = utils.crossed(np.array([1., 2, 3, 4, 5, 6]), np.array([3., 3, 3, 3, 3, 3]),
                                            direction="above",
                                            sequential=True)
    assert array_array_cross_above[-3] == True
    array_array_cross_below = utils.crossed(np.array([1., 2, 3, 2, 1, 6]), np.array([3., 3, 3, 3, 3, 3]),
                                            direction="below",
                                            sequential=True)
    assert array_array_cross_below[-3] == True
    array_array_cross = utils.crossed(np.array([1., 2, 3, 4, 1, 2]), np.array([3., 3, 3, 3, 3, 3]),
                                      sequential=True)
    assert array_array_cross[-3] == True
    assert array_array_cross[-2] == True


def test_estimate_risk():
    assert utils.estimate_risk(100, 80) == 20


def test_limit_stop_loss():
    assert utils.limit_stop_loss(100, 105, 'short', 10) == 105
    assert utils.limit_stop_loss(100, 115, 'short', 10) == 110
    assert utils.limit_stop_loss(100, 95, 'long', 10) == 95
    assert utils.limit_stop_loss(100, 85, 'long', 10) == 90

    with pytest.raises(TypeError):
        utils.limit_stop_loss(100, 85, 'long', 'invalid_input')
        utils.limit_stop_loss('invalid_input', 105, 'short', 10)
        utils.limit_stop_loss(100, 'invalid_input', 'short', 10)
        utils.limit_stop_loss(100, 105, 123, 10)


def test_numpy_to_pandas():
    candles = np.array(test_candles_19)
    columns = ["Date", "Open", "Close", "High", "Low", "Volume"]
    df = pd.DataFrame(data=candles, index=pd.to_datetime(candles[:, 0], unit="ms"), columns=columns)
    df["Date"] = pd.to_datetime(df["Date"], unit="ms")

    ohlcv = utils.numpy_candles_to_dataframe(candles, name_date="Date", name_open="Open", name_high="High",
                                             name_low="Low", name_close="Close", name_volume="Volume")

    pd.testing.assert_frame_equal(df, ohlcv)


def test_qty_to_size():
    assert utils.qty_to_size(2, 50) == 100
    assert utils.qty_to_size(2, 49) == 98

    with pytest.raises(TypeError):
        utils.qty_to_size(-10, 'invalid_input')
        utils.qty_to_size('invalid_input', -10)
    with pytest.raises(TypeError):
        utils.qty_to_size(-10, None)
        utils.qty_to_size(None, -10)


def test_risk_to_qty():
    # long
    assert utils.risk_to_qty(10000, 1, 100, 80) == 5
    # short
    assert utils.risk_to_qty(10000, 1, 80, 100) == 5

    # should not return more than maximum capital. Expect 100 instead of 125
    assert utils.risk_to_qty(10000, 5, 100, 96) == 100

    # when fee is included
    assert utils.risk_to_qty(10000, 1, 100, 80, precision=3, fee_rate=0.001) == 4.97


def test_risk_to_size():
    assert round(utils.risk_to_size(10000, 1, 0.7, 8.6)) == 1229

    with pytest.raises(TypeError):
        utils.risk_to_size(10000, 1, 0.7, None)
        utils.risk_to_size(10000, 1, None, 8.6)
        utils.risk_to_size(10000, None, 0.7, 8.6)
        utils.risk_to_size(None, 1, 0.7, 8.6)

    # should not return more than maximum capital
    assert utils.risk_to_size(10000, 5, 4, 100) == 10000


def test_size_to_qty():
    assert utils.size_to_qty(100, 50) == 2
    assert utils.size_to_qty(100, 49, precision=3) == 2.04

    with pytest.raises(TypeError):
        utils.size_to_qty(100, 'invalid_input')
        utils.size_to_qty('invalid_input', 100)
    with pytest.raises(TypeError):
        utils.size_to_qty(100, None)
        utils.size_to_qty(None, 100)

    # when fee is included
    assert utils.size_to_qty(100, 50, fee_rate=0.001) == 1.994


def test_sum_floats():
    assert utils.sum_floats(9.71, 9.813) == 19.523
    assert utils.sum_floats(-1.123, -1.2) == -2.323
    assert utils.sum_floats(1.19, -1.2) == -0.01
    assert utils.sum_floats(-1.19, 1.2) == 0.01


def test_subtract_floats():
    assert utils.subtract_floats(9.813, 9.71) == 0.103
    assert utils.subtract_floats(-1.123, 1.2) == -2.323
    assert utils.subtract_floats(1.123, -1.2) == 2.323
    assert utils.subtract_floats(-1.123, -1.2) == 0.077


def test_prices_to_returns():
    series = np.array([50, 10, 100, 25])
    pct = utils.prices_to_returns(series)
    np.testing.assert_array_equal(pct, np.array([np.nan, -80., 900., -75.]))


def test_combinations_without_repeat():
    a = np.array([4, 2, 9, 1, 3])
    b = utils.combinations_without_repeat(a)
    np.testing.assert_array_equal(b, np.array([[4, 2],
                                               [4, 9],
                                               [4, 1],
                                               [4, 3],
                                               [2, 4],
                                               [2, 9],
                                               [2, 1],
                                               [2, 3],
                                               [9, 4],
                                               [9, 2],
                                               [9, 1],
                                               [9, 3],
                                               [1, 4],
                                               [1, 2],
                                               [1, 9],
                                               [1, 3],
                                               [3, 4],
                                               [3, 2],
                                               [3, 9],
                                               [3, 1]]))


def test_wavelet_denoising():
    candles = np.array(test_candles_19)
    denoised = utils.wavelet_denoising(candles[:, 2], wavelet="sym4", level=1, mode='symmetric', smoothing_factor=2)
    assert len(candles) == len(denoised)
