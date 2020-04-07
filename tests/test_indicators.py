import numpy as np

from jesse.config import config, reset_config
from jesse.enums import exchanges, timeframes
from jesse.factories import fake_range_candle_from_range_prices
import jesse.indicators as ta
from jesse.store import store
from .data.test_candles_indicators import *


def set_up(count=2):
    reset_config()
    config['app']['considering_timeframes'] = ['1m', '5m']
    config['app']['considering_symbols'] = ['BTCUSD']
    config['app']['considering_exchanges'] = ['Sandbox']
    store.reset()
    store.candles.init_storage(count)


def test_sma():
    close_prices = [22.27, 22.19, 22.08, 22.17, 22.18, 22.13, 22.23, 22.43, 22.24, 22.29]
    candles = fake_range_candle_from_range_prices(close_prices)

    single = ta.sma(candles, 10)
    seq = ta.sma(candles, 10, sequential=True)

    assert round(single, 2) == 22.22
    assert len(seq) == len(candles)
    assert seq[-1] == single
    assert np.isnan(ta.sma(candles, 30))


def test_ema():
    close_prices = [
        204.23, 205.01, 196.9, 197.33, 198.7, 199.86, 202.23, 200.3, 212.3, 210.82603059, 220.84, 218.99,
        212.71, 211.01, 213.19, 212.99724894,
        212.67760477, 209.85, 187.2, 184.15, 176.99, 175.9, 178.99, 150.96, 133.85, 138.18, 126.32, 125.23,
        114.79,
        118.73, 110.74409879, 111.72, 124.04, 118.52, 113.64, 119.65, 117.11129288, 109.23, 110.77, 102.65,
        91.99
    ]
    candles = fake_range_candle_from_range_prices(close_prices)

    single = ta.ema(candles, 8)
    seq = ta.ema(candles, 8, sequential=True)

    assert round(single, 3) == 108.546
    assert len(seq) == len(candles)
    assert seq[-1] == single
    assert np.isnan(ta.ema(candles, 400))


def test_stoch():
    candles = np.array(stoch_candles)

    stoch = ta.stoch(candles, fastk_period=14, slowk_period=3, slowk_matype=0, slowd_period=3, slowd_matype=0)
    k, d = stoch
    assert type(stoch).__name__ == 'Stochastic'
    assert round(k, 2) == 53.68
    assert round(d, 2) == 49.08

    stoch = ta.stoch(candles, fastk_period=14, slowk_period=3, slowk_matype=0, slowd_period=3, slowd_matype=0,
                     sequential=True)
    assert stoch.d[-1] == d
    assert stoch.k[-1] == k
    assert len(stoch.d) == len(candles)
    assert len(stoch.k) == len(candles)


def test_doji():
    set_up(240)
    candles = np.array(doji_candles)

    store.candles.batch_add_candle(candles, exchanges.SANDBOX, 'BTCUSD', timeframes.MINUTE_1)
    res = ta.doji(exchanges.SANDBOX, 'BTCUSD', timeframes.MINUTE_1)
    assert res == 1

    new_candle = np.array([1565416800000, 211.96, 211.64, 212.8, 211.64, 925.33769619])
    store.candles.add_candle(new_candle, exchanges.SANDBOX, 'BTCUSD', timeframes.MINUTE_1)
    res = ta.doji(exchanges.SANDBOX, 'BTCUSD', timeframes.MINUTE_1)
    assert res == 0


def test_inverted_hammer():
    set_up(500)

    candles = np.array(inverted_hammer_candles)

    store.candles.batch_add_candle(candles, exchanges.SANDBOX, 'BTCUSD', timeframes.MINUTE_1)
    res = ta.inverted_hammer(exchanges.SANDBOX, 'BTCUSD', timeframes.MINUTE_1)
    assert res == 0

    new_candle = np.array([1563606000000, 226.88, 226.09, 228.25, 226, 1407.91947504])
    store.candles.add_candle(new_candle, exchanges.SANDBOX, 'BTCUSD', timeframes.MINUTE_1)
    res = ta.inverted_hammer(exchanges.SANDBOX, 'BTCUSD', timeframes.MINUTE_1)
    assert res == 1


def test_hammer():
    set_up(500)

    candles = np.array(hammer_candles)

    store.candles.batch_add_candle(candles, exchanges.SANDBOX, 'BTCUSD', timeframes.MINUTE_1)
    res = ta.hammer(exchanges.SANDBOX, 'BTCUSD', timeframes.MINUTE_1)
    assert res == 0

    new_candle = np.array([1563487200000, 224.01, 223.61, 224.28, 222.53, 1531.27654409])
    store.candles.add_candle(new_candle, exchanges.SANDBOX, 'BTCUSD', timeframes.MINUTE_1)
    res = ta.hammer(exchanges.SANDBOX, 'BTCUSD', timeframes.MINUTE_1)
    assert res == 1


def test_bearish_engulfing():
    set_up(500)

    candles = np.array(bearish_engulfing_candles)

    store.candles.batch_add_candle(candles, exchanges.SANDBOX, 'BTCUSD', timeframes.MINUTE_1)
    res = ta.engulfing(exchanges.SANDBOX, 'BTCUSD', timeframes.MINUTE_1)
    assert res == 0

    new_candle = np.array([1563472800000, 223.99, 222.84, 225.26, 222.5, 5777.43564279])
    store.candles.add_candle(new_candle, exchanges.SANDBOX, 'BTCUSD', timeframes.MINUTE_1)
    res = ta.engulfing(exchanges.SANDBOX, 'BTCUSD', timeframes.MINUTE_1)
    assert res == -1


def test_bullish_engulfing():
    set_up(500)

    candles = np.array(bullish_engulfing_candles)

    store.candles.batch_add_candle(candles, exchanges.SANDBOX, 'BTCUSD', timeframes.MINUTE_1)
    res = ta.engulfing(exchanges.SANDBOX, 'BTCUSD', timeframes.MINUTE_1)
    assert res == 0

    new_candle = np.array([1563411600000, 208.53, 212.77, 214.31, 208.53, 5739.5236321])
    store.candles.add_candle(new_candle, exchanges.SANDBOX, 'BTCUSD', timeframes.MINUTE_1)
    res = ta.engulfing(exchanges.SANDBOX, 'BTCUSD', timeframes.MINUTE_1)
    assert res == 1


def test_adx():
    candles = np.array(adx_candles)

    single = ta.adx(candles)
    seq = ta.adx(candles, sequential=True)

    assert round(single) == 26
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_atr():
    candles = np.array(atr_candles)

    single = ta.atr(candles)
    seq = ta.atr(candles, sequential=True)

    assert round(single, 1) == 2.8
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_bollinger_bands():
    candles = np.array(bollinger_bands_candles)

    bb = ta.bollinger_bands(candles)
    u, m, l = bb
    assert type(bb).__name__ == 'BollingerBands'
    assert round(u, 1) == 145.8
    assert round(m, 1) == 141.2
    assert round(l, 1) == 136.7

    seq_bb = ta.bollinger_bands(candles, sequential=True)
    assert seq_bb.upperband[-1] == u
    assert len(seq_bb.upperband) == len(candles)
    assert len(seq_bb.middleband) == len(candles)
    assert len(seq_bb.lowerband) == len(candles)


def test_bollinger_bands_width():
    candles = np.array(bollinger_bands_width_candles)

    single = ta.bollinger_bands_width(candles)
    seq = ta.bollinger_bands_width(candles, sequential=True)

    assert round(single, 4) == 0.0771
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_rsi():
    candles = np.array(rsi_candles)

    single = ta.rsi(candles)
    seq = ta.rsi(candles, sequential=True)

    assert round(single, 2) == 57.84
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_ichimoku_cloud():
    candles = np.array(ichimoku_candles)

    ic = ta.ichimoku_cloud(candles)

    current_conversion_line, current_base_line, span_a, span_b = ic

    assert type(ic).__name__ == 'IchimokuCloud'

    assert (current_conversion_line, current_base_line, span_a, span_b) == (8861.59, 8861.59, 8466.385, 8217.45)


def test_trix():
    candles = np.array(trix_candles)

    single = ta.trix(candles)
    seq = ta.trix(candles, sequential=True)

    assert round(single, 2) == 30.87
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_tema():
    # use the same candles as trix_candles
    candles = np.array(trix_candles)

    single = ta.tema(candles)
    seq = ta.tema(candles, sequential=True)

    assert round(single, 2) == 213.2
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_dema():
    candles = np.array(dema_candles)

    single = ta.dema(candles, 9)
    seq = ta.dema(candles, 9, sequential=True)

    assert round(single, 0) == 165
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_kama():
    # use the same candles as dema_candles
    candles = np.array(dema_candles)

    single = ta.kama(candles, 10)
    seq = ta.kama(candles, 10, sequential=True)

    assert round(single, 0) == 202
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_mama():
    candles = np.array(mama_candles)

    mama = ta.mama(candles, 0.5, 0.05)
    assert type(mama).__name__ == 'MAMA'
    assert round(mama.mama, 2) == 206.78
    assert round(mama.fama, 2) == 230.26

    seq_mama = ta.mama(candles, 0.5, 0.05, sequential=True)
    assert seq_mama.mama[-1] == mama.mama
    assert len(seq_mama.mama) == len(candles)
    assert len(seq_mama.fama) == len(candles)


def test_sar():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.sar(candles, acceleration=0.02, maximum=0.2)
    seq = ta.sar(candles, acceleration=0.02, maximum=0.2, sequential=True)

    assert round(single, 2) == 243.15
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_sar_ext():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.sarext(candles, startvalue=0.02, offsetonreverse=0, accelerationinitlong=0.02, accelerationlong=0.02,
                       accelerationmaxlong=0.2, accelerationinitshort=0.02, accelerationshort=0.02,
                       accelerationmaxshort=0.2)
    seq = ta.sarext(candles, startvalue=0.02, offsetonreverse=0, accelerationinitlong=0.02, accelerationlong=0.02,
                    accelerationmaxlong=0.2, accelerationinitshort=0.02, accelerationshort=0.02,
                    accelerationmaxshort=0.2,
                    sequential=True)

    assert round(single, 2) == -243.15
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_t3():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.t3(candles, period=5, vfactor=0.7)
    seq = ta.t3(candles, period=5, vfactor=0.7, sequential=True)

    assert round(single, 0) == 194
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_trima():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.trima(candles, period=9)
    seq = ta.trima(candles, period=9, sequential=True)

    assert round(single, 0) == 211
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_wma():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.wma(candles, period=9)
    seq = ta.wma(candles, period=9, sequential=True)

    assert round(single, 2) == 189.13
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_adxr():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.adxr(candles, period=14)
    seq = ta.adxr(candles, period=14, sequential=True)

    assert round(single, 0) == 36
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_apo():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.apo(candles, fastperiod=12, slowperiod=26, matype=1)
    seq = ta.apo(candles, fastperiod=12, slowperiod=26, matype=1, sequential=True)

    assert round(single, 2) == -15.32
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_aroon():
    candles = np.array(mama_candles)

    aroon = ta.aroon(candles, period=14)
    assert type(aroon).__name__ == 'AROON'
    assert round(aroon.aroondown, 2) == 100
    assert round(aroon.aroonup, 2) == 64.29

    seq_aroon = ta.aroon(candles, period=14, sequential=True)
    assert seq_aroon.aroondown[-1] == aroon.aroondown
    assert len(seq_aroon.aroondown) == len(candles)
    assert len(seq_aroon.aroonup) == len(candles)


def test_aroon_osc():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.aroonosc(candles, period=14)
    seq = ta.aroonosc(candles, period=14, sequential=True)

    assert round(single, 2) == -35.71
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_bop():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.bop(candles)
    seq = ta.bop(candles, sequential=True)

    assert round(single, 2) == -0.92
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_cci():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.cci(candles, period=14)
    seq = ta.cci(candles, period=14, sequential=True)

    assert round(single, 2) == -285.29
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_cmo():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.cmo(candles, period=9)
    seq = ta.cmo(candles, period=9, sequential=True)

    assert round(single, 0) == -70
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_mfi():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.mfi(candles, period=9)
    seq = ta.mfi(candles, period=9, sequential=True)

    assert round(single, 1) == 31.2
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_mom():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.mom(candles, period=9)
    seq = ta.mom(candles, period=9, sequential=True)

    assert round(single, 2) == -116.09
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_ppo():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.ppo(candles, fastperiod=12, slowperiod=26, matype=1)
    seq = ta.ppo(candles, fastperiod=12, slowperiod=26, matype=1, sequential=True)

    assert round(single, 0) == -7
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_willr():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.willr(candles, period=9)
    seq = ta.willr(candles, period=9, sequential=True)

    assert round(single, 2) == -95.61
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_ultosc():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.ultosc(candles, timeperiod1=7, timeperiod2=14, timeperiod3=28)
    seq = ta.ultosc(candles, timeperiod1=7, timeperiod2=14, timeperiod3=28, sequential=True)

    assert round(single, 2) == 31.37
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_dmi():
    candles = np.array(mama_candles)

    dmi = ta.dmi(candles, period=14)
    assert type(dmi).__name__ == 'DMI'
    assert round(dmi.plus, 2) == 10.80
    assert round(dmi.minus, 1) == 45.3

    seq_dmi = ta.dmi(candles, period=14, sequential=True)
    assert seq_dmi.plus[-1] == dmi.plus
    assert seq_dmi.minus[-1] == dmi.minus
    assert len(seq_dmi.plus) == len(candles)
    assert len(seq_dmi.minus) == len(candles)


def test_adosc():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.adosc(candles, fastperiod=3, slowperiod=10)
    seq = ta.adosc(candles, fastperiod=3, slowperiod=10, sequential=True)

    assert round(single / 1000000, 3) == -1.122
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_obv():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.obv(candles)
    seq = ta.obv(candles, sequential=True)

    assert round(single / 1000000, 0) == -6
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_natr():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.natr(candles, period=14)
    seq = ta.natr(candles, period=14, sequential=True)

    assert round(single, 2) == 22.55
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_roc():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.roc(candles, period=14)
    seq = ta.roc(candles, period=14, sequential=True)

    assert round(single, 2) == -52.67
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_stochf():
    candles = np.array(mama_candles)

    single = ta.stochf(candles, fastk_period=5, fastd_period=3, fastd_matype=0)
    seq = ta.stochf(candles, fastk_period=5, fastd_period=3, fastd_matype=0, sequential=True)

    assert type(single).__name__ == 'StochasticFast'
    assert round(single.k, 2) == 4.87
    assert round(single.d, 2) == 13.5

    assert seq.k[-1] == single.k
    assert len(seq.k) == len(candles)
    assert len(seq.d) == len(candles)


def test_macd():
    candles = np.array(mama_candles)

    single = ta.macd(candles, fastperiod=12, slowperiod=26, signalperiod=9)
    seq = ta.macd(candles, fastperiod=12, slowperiod=26, signalperiod=9, sequential=True)

    assert type(single).__name__ == 'MACD'
    assert round(single.macd, 2) == -15.32
    assert round(single.signal, 2) == -4.10
    assert round(single.hist, 2) == -11.22

    assert seq.macd[-1] == single.macd
    assert len(seq.macd) == len(candles)
    assert len(seq.signal) == len(candles)
    assert len(seq.hist) == len(candles)


def test_macdext():
    candles = np.array(mama_candles)

    single = ta.macdext(candles, fastperiod=12, fastmatype=0, slowperiod=26, slowmatype=0, signalperiod=9,
                        signalmatype=0)
    seq = ta.macdext(candles, fastperiod=12, fastmatype=0, slowperiod=26, slowmatype=0, signalperiod=9, signalmatype=0,
                     sequential=True)

    assert type(single).__name__ == 'MACDEXT'
    assert round(single.macd, 2) == -23.12
    assert round(single.signal, 2) == -18.51
    assert round(single.hist, 2) == -4.61

    assert seq.macd[-1] == single.macd
    assert len(seq.macd) == len(candles)
    assert len(seq.signal) == len(candles)
    assert len(seq.hist) == len(candles)


def test_donchian():
    candles = np.array(mama_candles)

    single = ta.donchian(candles, period=20)
    seq = ta.donchian(candles, period=20, sequential=True)

    assert type(single).__name__ == 'DonchianChannel'
    assert round(single.upperband, 2) == 277.20
    assert round(single.middleband, 2) == 189.20
    assert round(single.lowerband, 2) == 101.20

    assert seq.middleband[-1] == single.middleband
    assert len(seq.upperband) == len(candles)
    assert len(seq.middleband) == len(candles)
    assert len(seq.lowerband) == len(candles)


def test_frama():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.frama(candles, window=10, SC=200, FC=10, )
    seq = ta.frama(candles, window=10, SC=200, FC=10, sequential=True)

    assert round(single, 0) == 219
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_supertrend():
    candles = np.array(mama_candles)

    single = ta.supertrend(candles, period=10, factor=3)
    seq = ta.supertrend(candles, period=10, factor=3, sequential=True)

    assert type(single).__name__ == 'SuperTrend'
    assert round(single.trend, 2) == 228.45
    assert seq.changed[-16] == True
    assert seq.changed[-1] == False

    assert seq.trend[-1] == single.trend
    assert len(seq.trend) == len(candles)
    assert len(seq.changed) == len(candles)
