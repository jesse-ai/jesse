import numpy as np

import jesse.indicators as ta
from jesse.factories import fake_range_candle_from_range_prices
from .data.test_candles_indicators import *


def test_acosc():
    candles = np.array(mama_candles)
    single = ta.acosc(candles)
    seq = ta.acosc(candles, sequential=True)

    assert type(single).__name__ == 'AC'
    assert round(single.osc, 2) == -21.97
    assert round(single.change, 2) == -9.22

    assert seq.osc[-1] == single.osc
    assert len(seq.osc) == len(candles)


def test_ad():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.ad(candles)
    seq = ta.ad(candles, sequential=True)
    assert round(single, 0) == 6346031
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_adosc():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.adosc(candles, fast_period=3, slow_period=10)
    seq = ta.adosc(candles, fast_period=3, slow_period=10, sequential=True)

    assert round(single / 1000000, 3) == -1.122
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_adx():
    candles = np.array(adx_candles)

    single = ta.adx(candles)
    seq = ta.adx(candles, sequential=True)

    assert round(single) == 26
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


def test_alligator():
    candles = np.array(mama_candles)
    single = ta.alligator(candles)
    seq = ta.alligator(candles, sequential=True)

    assert type(single).__name__ == 'AG'
    assert round(single.teeth, 0) == 236
    assert round(single.jaw, 0) == 233
    assert round(single.lips, 0) == 222

    assert seq.teeth[-1] == single.teeth
    assert len(seq.teeth) == len(candles)


def test_ao():
    candles = np.array(mama_candles)
    single = ta.ao(candles)
    seq = ta.ao(candles, sequential=True)

    assert round(single.osc, 0) == -46
    assert len(seq[-1]) == len(candles)
    assert seq.osc[-1] == single.osc


def test_apo():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.apo(candles, fast_period=12, slow_period=26, matype=1)
    seq = ta.apo(candles, fast_period=12, slow_period=26, matype=1, sequential=True)

    assert round(single, 2) == -15.32
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_aroon():
    candles = np.array(mama_candles)

    aroon = ta.aroon(candles, period=14)
    assert type(aroon).__name__ == 'AROON'
    assert round(aroon.down, 2) == 100
    assert round(aroon.up, 2) == 64.29

    seq_aroon = ta.aroon(candles, period=14, sequential=True)
    assert seq_aroon.down[-1] == aroon.down
    assert len(seq_aroon.down) == len(candles)
    assert len(seq_aroon.up) == len(candles)


def test_aroon_osc():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.aroonosc(candles, period=14)
    seq = ta.aroonosc(candles, period=14, sequential=True)

    assert round(single, 2) == -35.71
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_atr():
    candles = np.array(atr_candles)

    single = ta.atr(candles)
    seq = ta.atr(candles, sequential=True)

    assert round(single, 1) == 2.8
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_avgprice():
    candles = np.array(mama_candles)

    single = ta.avgprice(candles)
    seq = ta.avgprice(candles, sequential=True)

    assert round(single, 1) == 149.8
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_beta():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.beta(candles)
    seq = ta.beta(candles, sequential=True)

    assert round(single, 2) == -0.31
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


def test_bop():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.bop(candles)
    seq = ta.bop(candles, sequential=True)

    assert round(single, 2) == -0.92
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_cc():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.cc(candles)
    seq = ta.cc(candles, sequential=True)

    assert round(single, 0) == -41
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


def test_cfo():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.cfo(candles)
    seq = ta.cfo(candles, sequential=True)

    assert round(single, 2) == -66.53
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_cg():
    candles = np.array(mama_candles)
    single = ta.cg(candles)
    seq = ta.cg(candles, sequential=True)
    assert round(single, 2) == -5.37
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_chande():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single_long = ta.chande(candles)
    seq_long = ta.chande(candles, sequential=True)

    single_short = ta.chande(candles, direction="short")
    seq_short = ta.chande(candles, direction="short", sequential=True)

    assert round(single_long, 0) == 213
    assert round(single_short, 0) == 165

    assert len(seq_short) == len(candles)
    assert len(seq_long) == len(candles)
    assert seq_long[-1] == single_long
    assert seq_short[-1] == single_short


def test_cmo():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.cmo(candles, period=9)
    seq = ta.cmo(candles, period=9, sequential=True)

    assert round(single, 0) == -70
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_correl():
    candles = np.array(mama_candles)

    single = ta.correl(candles)
    seq = ta.correl(candles, sequential=True)

    assert round(single, 2) == 0.58
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_correlation_cycle():
    candles = np.array(mama_candles)

    single = ta.correlation_cycle(candles)
    assert type(single).__name__ == 'CC'
    assert round(single.real, 2) == 0.23
    assert round(single.imag, 2) == 0.38
    assert round(single.angle, 2) == -55.87
    assert round(single.state, 2) == -1

    seq = ta.correlation_cycle(candles, sequential=True)
    assert seq.real[-1] == single.real
    assert seq.imag[-1] == single.imag
    assert seq.angle[-1] == single.angle
    assert seq.state[-1] == single.state
    assert len(seq.real) == len(candles)
    assert len(seq.imag) == len(candles)
    assert len(seq.angle) == len(candles)
    assert len(seq.state) == len(candles)


def test_cvi():
    candles = np.array(mama_candles)

    single = ta.cvi(candles)
    seq = ta.cvi(candles, sequential=True)

    assert round(single, 2) == 196.8
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_damiani_volatmeter():
    candles = np.array(mama_candles)

    single = ta.damiani_volatmeter(candles)
    assert type(single).__name__ == 'DamianiVolatmeter'
    assert round(single.vol, 2) == 1.39
    assert round(single.anti, 2) == 0.93

    seq = ta.damiani_volatmeter(candles, sequential=True)
    assert seq.vol[-1] == single.vol
    assert seq.anti[-1] == single.anti
    assert len(seq.vol) == len(candles)
    assert len(seq.anti) == len(candles)


def test_dec_osc():
    candles = np.array(mama_candles)
    single = ta.dec_osc(candles)
    seq = ta.dec_osc(candles, sequential=True)
    assert round(single, 0) == -20
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_decycler():
    candles = np.array(mama_candles)
    single = ta.decycler(candles)
    seq = ta.decycler(candles, sequential=True)
    assert round(single, 0) == 233
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_dema():
    candles = np.array(dema_candles)

    single = ta.dema(candles, 9)
    seq = ta.dema(candles, 9, sequential=True)

    assert round(single, 0) == 165
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_devstop():
    candles = np.array(mama_candles)

    single = ta.devstop(candles)
    seq = ta.devstop(candles, sequential=True)

    assert round(single, 0) == 248.0
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_di():
    candles = np.array(mama_candles)

    single = ta.di(candles, period=14)
    assert type(single).__name__ == 'DI'
    assert round(single.plus, 2) == 10.80
    assert round(single.minus, 1) == 45.3

    seq = ta.di(candles, period=14, sequential=True)
    assert seq.plus[-1] == single.plus
    assert seq.minus[-1] == single.minus
    assert len(seq.plus) == len(candles)
    assert len(seq.minus) == len(candles)


def test_dm():
    candles = np.array(mama_candles)

    single = ta.dm(candles, period=14)
    assert type(single).__name__ == 'DM'
    assert round(single.plus, 2) == 36.78
    assert round(single.minus, 1) == 154.1

    seq = ta.dm(candles, period=14, sequential=True)
    assert seq.plus[-1] == single.plus
    assert seq.minus[-1] == single.minus
    assert len(seq.plus) == len(candles)
    assert len(seq.minus) == len(candles)


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


def test_dpo():
    candles = np.array(dema_candles)

    single = ta.dpo(candles)
    seq = ta.dpo(candles, sequential=True)

    assert round(single, 0) == 22
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_dti():
    candles = np.array(mama_candles)

    single = ta.dti(candles)
    seq = ta.dti(candles, sequential=True)

    assert round(single, 2) == -32.6
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_dx():
    candles = np.array(dema_candles)

    single = ta.dx(candles)
    seq = ta.dx(candles, sequential=True)

    assert round(single, 0) == 67
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_efi():
    candles = np.array(mama_candles)
    single = ta.efi(candles)
    seq = ta.efi(candles, sequential=True)
    assert round(single, 0) == -51628073
    assert len(seq) == len(candles)
    assert seq[-1] == single


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


def test_emd():
    candles = np.array(mama_candles)

    single = ta.emd(candles)
    seq = ta.emd(candles, sequential=True)

    assert type(single).__name__ == 'EMD'
    assert round(single.middleband, 2) == 3.12
    assert round(single.upperband, 2) == 1.21
    assert round(single.lowerband, 2) == -0.28

    assert seq.middleband[-1] == single.middleband
    assert seq.upperband[-1] == single.upperband
    assert seq.lowerband[-1] == single.lowerband
    assert len(seq.middleband) == len(candles)
    assert len(seq.upperband) == len(candles)
    assert len(seq.lowerband) == len(candles)


def test_emv():
    candles = np.array(mama_candles)
    single = ta.emv(candles)
    seq = ta.emv(candles, sequential=True)
    assert round(single, 0) == -11
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_er():
    candles = np.array(mama_candles)
    single = ta.er(candles)
    seq = ta.er(candles, sequential=True)
    assert round(single, 2) == 0.02
    assert len(seq) == len(candles)
    assert round(seq[-1], 2) == round(single, 2)

def test_eri():
    candles = np.array(mama_candles)
    single = ta.eri(candles)
    seq = ta.eri(candles, sequential=True)

    assert type(single).__name__ == 'ERI'
    assert round(single.bull, 2) == -7.14
    assert round(single.bear, 2) == -101.49

    assert seq.bull[-1] == single.bull
    assert len(seq.bull) == len(candles)
    assert len(seq.bear) == len(candles)

def test_fisher():
    candles = np.array(mama_candles)
    single = ta.fisher(candles, period=9)
    seq = ta.fisher(candles, period=9, sequential=True)

    assert type(single).__name__ == 'FisherTransform'
    assert round(single.fisher, 2) == -1.77
    assert round(single.signal, 2) == -1.31

    assert seq.fisher[-1] == single.fisher
    assert len(seq.fisher) == len(candles)
    assert len(seq.signal) == len(candles)


def test_fosc():
    candles = np.array(mama_candles)
    single = ta.fosc(candles)
    seq = ta.fosc(candles, sequential=True)
    assert round(single, 0) == -69
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_frama():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.frama(candles, window=10, SC=200, FC=10, )
    seq = ta.frama(candles, window=10, SC=200, FC=10, sequential=True)

    assert round(single, 0) == 219
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_fwma():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.fwma(candles)
    seq = ta.fwma(candles, sequential=True)

    assert round(single, 0) == 161
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_gator():
    candles = np.array(mama_candles)
    single = ta.gatorosc(candles)
    seq = ta.gatorosc(candles, sequential=True)

    assert type(single).__name__ == 'GATOR'
    assert round(single.upper, 2) == 2.39
    assert round(single.upper_change, 2) == 0.98
    assert round(single.lower, 2) == -13.44
    assert round(single.lower_change, 2) == 5.06

    assert seq.upper[-1] == single.upper
    assert len(seq.upper) == len(candles)


def test_gauss():
    candles = np.array(mama_candles)
    single = ta.gauss(candles)
    seq = ta.gauss(candles, sequential=True)
    assert round(single, 0) == 190
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_high_pass():
    candles = np.array(mama_candles)
    single = ta.high_pass(candles)
    seq = ta.high_pass(candles, sequential=True)
    assert round(single, 0) == -106
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_high_pass_2_pole():
    candles = np.array(mama_candles)
    single = ta.high_pass_2_pole(candles)
    seq = ta.high_pass_2_pole(candles, sequential=True)
    assert round(single, 0) == -101
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_hma():
    candles = np.array(mama_candles)
    single = ta.hma(candles)
    seq = ta.hma(candles, sequential=True)

    assert round(single, 0) == 134
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_ht_dcperiod():
    candles = np.array(mama_candles)
    single = ta.ht_dcperiod(candles)
    seq = ta.ht_dcperiod(candles, sequential=True)

    assert round(single, 0) == 24
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_ht_dcphase():
    candles = np.array(mama_candles)
    single = ta.ht_dcphase(candles)
    seq = ta.ht_dcphase(candles, sequential=True)

    assert round(single, 0) == 10
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_ht_phasor():
    candles = np.array(mama_candles)
    single = ta.ht_phasor(candles)
    seq = ta.ht_phasor(candles, sequential=True)

    assert type(single).__name__ == 'IQ'
    assert round(single.inphase, 0) == 11
    assert round(single.quadrature, 0) == -52

    assert seq.inphase[-1] == single.inphase
    assert seq.quadrature[-1] == single.quadrature
    assert len(seq.inphase) == len(candles)
    assert len(seq.quadrature) == len(candles)


def test_ht_sine():
    candles = np.array(mama_candles)
    single = ta.ht_sine(candles)
    seq = ta.ht_sine(candles, sequential=True)

    assert type(single).__name__ == 'SINEWAVE'
    assert round(single.sine, 2) == 0.18
    assert round(single.lead, 2) == 0.82

    assert seq.sine[-1] == single.sine
    assert seq.lead[-1] == single.lead
    assert len(seq.sine) == len(candles)
    assert len(seq.lead) == len(candles)


def test_ht_trendline():
    candles = np.array(mama_candles)
    single = ta.ht_trendline(candles)
    seq = ta.ht_trendline(candles, sequential=True)

    assert round(single, 0) == 236
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_ht_trendmode():
    candles = np.array(mama_candles)
    single = ta.ht_trendmode(candles)
    seq = ta.ht_trendmode(candles, sequential=True)

    assert single == 1
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_ichimoku_cloud():
    candles = np.array(ichimoku_candles)

    ic = ta.ichimoku_cloud(candles)

    current_conversion_line, current_base_line, span_a, span_b = ic

    assert type(ic).__name__ == 'IchimokuCloud'

    assert (current_conversion_line, current_base_line, span_a, span_b) == (8861.59, 8861.59, 8466.385, 8217.45)


def test_ichimoku_cloud_seq():
    candles = np.array(ichimoku_candles)

    conversion_line, base_line, span_a, span_b, lagging_line, future_span_a, future_span_b = ta.ichimoku_cloud_seq(
        candles)
    seq = ta.ichimoku_cloud_seq(candles, sequential=True)

    assert type(seq).__name__ == 'IchimokuCloud'
    assert (conversion_line, base_line, span_a, span_b, lagging_line, future_span_a, future_span_b) == (
        seq.conversion_line[-1], seq.base_line[-1], seq.span_a[-1], seq.span_b[-1], seq.lagging_line[-1],
        seq.future_span_a[-1], seq.future_span_b[-1])
    assert (conversion_line, base_line, span_a, span_b, lagging_line, future_span_a, future_span_b) == (
        8861.59, 8861.59, 8465.25, 8204.715, 8730.0, 8861.59, 8579.49)
    assert len(seq.conversion_line) == len(candles)


def test_itrend():
    candles = np.array(mama_candles)
    single = ta.itrend(candles)
    seq = ta.itrend(candles, sequential=True)

    assert type(single).__name__ == 'ITREND'
    assert round(single.it, 0) == 223
    assert round(single.trigger, 0) == 182
    assert single.signal == -1

    assert seq.it[-1] == single.it
    assert seq.signal[-1] == single.signal
    assert seq.trigger[-1] == single.trigger
    assert len(seq.it) == len(candles)


def test_kama():
    # use the same candles as dema_candles
    candles = np.array(dema_candles)

    single = ta.kama(candles, 10)
    seq = ta.kama(candles, 10, sequential=True)

    assert round(single, 0) == 202
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_kaufmanstop():
    # use the same candles as dema_candles
    candles = np.array(dema_candles)

    single = ta.kaufmanstop(candles)
    seq = ta.kaufmanstop(candles, sequential=True)

    assert round(single, 0) == -57
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_kelner_channels():
    candles = np.array(keltner_channel_candles)

    kc = ta.keltner(candles)
    u, m, l = kc
    assert type(kc).__name__ == 'KeltnerChannel'
    assert round(u, 1) == 145.0
    assert round(m, 1) == 139.7
    assert round(l, 1) == 134.4

    seq_kc = ta.keltner(candles, sequential=True)
    assert seq_kc.upperband[-1] == u
    assert len(seq_kc.upperband) == len(candles)
    assert len(seq_kc.middleband) == len(candles)
    assert len(seq_kc.lowerband) == len(candles)


def test_kst():
    candles = np.array(mama_candles)

    single = ta.kst(candles)
    seq = ta.kst(candles, sequential=True)

    assert type(single).__name__ == 'KST'
    assert round(single.line, 2) == -93.38
    assert round(single.signal, 2) == 31.1

    assert seq.line[-1] == single.line
    assert seq.signal[-1] == single.signal
    assert len(seq.line) == len(candles)
    assert len(seq.signal) == len(candles)


def test_kurtosis():
    candles = np.array(mama_candles)

    single = ta.kurtosis(candles)
    seq = ta.kurtosis(candles, sequential=True)

    assert round(single, 2) == -0.22
    assert len(seq) == len(candles)
    assert seq[-1] == single

def test_kvo():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.kvo(candles)
    seq = ta.kvo(candles, sequential=True)

    assert round(single / 10000000, 2) == -5.52
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_linearreg():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.linearreg(candles)
    seq = ta.linearreg(candles, sequential=True)

    assert round(single, 2) == 179.56
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_linearreg_angle():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.linearreg_angle(candles)
    seq = ta.linearreg_angle(candles, sequential=True)

    assert round(single, 2) == -78.42
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_linearreg_intercept():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.linearreg_intercept(candles)
    seq = ta.linearreg_intercept(candles, sequential=True)

    assert round(single, 2) == 242.98
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_linearreg_slope():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.linearreg_slope(candles)
    seq = ta.linearreg_slope(candles, sequential=True)

    assert round(single, 2) == -4.88
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_lrsi():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.lrsi(candles)
    seq = ta.lrsi(candles, sequential=True)

    assert round(single, 2) == 0.1
    assert round(seq[-2], 2) == 0.04
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_macd():
    candles = np.array(mama_candles)

    single = ta.macd(candles, fast_period=12, slow_period=26, signal_period=9)
    seq = ta.macd(candles, fast_period=12, slow_period=26, signal_period=9, sequential=True)

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

    single = ta.macdext(candles, fast_period=12, fast_matype=0, slow_period=26, slow_matype=0, signal_period=9,
                        signal_matype=0)
    seq = ta.macdext(candles, fast_period=12, fast_matype=0, slow_period=26, slow_matype=0, signal_period=9,
                     signal_matype=0,
                     sequential=True)

    assert type(single).__name__ == 'MACDEXT'
    assert round(single.macd, 2) == -23.12
    assert round(single.signal, 2) == -18.51
    assert round(single.hist, 2) == -4.61

    assert seq.macd[-1] == single.macd
    assert len(seq.macd) == len(candles)
    assert len(seq.signal) == len(candles)
    assert len(seq.hist) == len(candles)


def test_median_ad():
    candles = np.array(mama_candles)

    single = ta.median_ad(candles)
    seq = ta.median_ad(candles, sequential=True)

    assert round(single, 2) == 6.86
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_mean_ad():
    candles = np.array(mama_candles)

    single = ta.mean_ad(candles)
    seq = ta.mean_ad(candles, sequential=True)

    assert round(single, 2) == 23.82
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


def test_marketfi():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.marketfi(candles)
    seq = ta.marketfi(candles, sequential=True)

    assert round(single * 100000, 2) == 2.47
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_mass():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.mass(candles)
    seq = ta.mass(candles, sequential=True)

    assert round(single, 2) == 5.76
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_mcginley_dynamic():
    candles = np.array(mama_candles)

    single = ta.mcginley_dynamic(candles)
    seq = ta.mcginley_dynamic(candles, sequential=True)
    assert round(single, 2) == 107.82
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_medprice():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.medprice(candles)
    seq = ta.medprice(candles, sequential=True)

    assert round(single, 1) == 148.4
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


def test_midpoint():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.midpoint(candles)
    seq = ta.midpoint(candles, sequential=True)

    assert round(single, 1) == 176.4
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_midprice():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.midprice(candles)
    seq = ta.midprice(candles, sequential=True)

    assert round(single, 1) == 176.6
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_minmax():
    candles = np.array(mama_candles)
    single = ta.minmax(candles)
    seq = ta.minmax(candles, sequential=True)

    assert type(single).__name__ == 'EXTREMA'
    assert round(seq.max[-6], 2) == 251.93
    assert round(seq.min[-15], 2) == 210
    assert round(single.last_max, 2) == 251.93
    assert round(single.last_min, 2) == 210

    assert seq.last_max[-1] == single.last_max
    assert seq.last_min[-1] == single.last_min
    assert len(seq.min) == len(candles)


def test_mom():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.mom(candles, period=9)
    seq = ta.mom(candles, period=9, sequential=True)

    assert round(single, 2) == -116.09
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_msw():
    candles = np.array(mama_candles)
    single = ta.msw(candles)
    seq = ta.msw(candles, sequential=True)

    assert type(single).__name__ == 'MSW'
    assert round(single.lead, 2) == -0.66
    assert round(single.sine, 2) == -1.0

    assert seq.lead[-1] == single.lead
    assert seq.sine[-1] == single.sine
    assert len(seq.sine) == len(candles)


def test_natr():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.natr(candles, period=14)
    seq = ta.natr(candles, period=14, sequential=True)

    assert round(single, 2) == 22.55
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_nvi():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.nvi(candles)
    seq = ta.nvi(candles, sequential=True)

    assert round(single, 2) == 722.58
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


def test_pattern_recognizion():
    candles = np.array(inverted_hammer_candles)
    res = ta.pattern_recognition(candles, pattern_type="CDLINVERTEDHAMMER")
    seq = ta.pattern_recognition(candles, pattern_type="CDLINVERTEDHAMMER", sequential=True)
    assert len(seq) == len(candles)
    assert res == 0

    candles = np.array(bullish_engulfing_candles)
    res = ta.pattern_recognition(candles, pattern_type="CDLENGULFING")
    assert res == 0

    candles = np.array(bearish_engulfing_candles)
    res = ta.pattern_recognition(candles, pattern_type="CDLENGULFING")
    assert res == 0

    candles = np.array(hammer_candles)
    res = ta.pattern_recognition(candles, pattern_type="CDLHAMMER")
    assert res == 0

    candles = np.array(doji_candles)
    res = ta.pattern_recognition(candles, pattern_type="CDLDOJI")
    assert res == 1


def test_pivot():
    candles = np.array(mama_candles)
    single = ta.pivot(candles, mode=0)
    seq = ta.pivot(candles, mode=0, sequential=True)

    assert type(single).__name__ == 'PIVOT'

    assert seq.r1[-1] == single.r1
    assert len(seq.r1) == len(candles)
    assert len(seq.r2) == len(candles)
    assert len(seq.r3) == len(candles)
    assert len(seq.r4) == len(candles)
    assert len(seq.pp) == len(candles)
    assert len(seq.s1) == len(candles)
    assert len(seq.s2) == len(candles)
    assert len(seq.s3) == len(candles)
    assert len(seq.s4) == len(candles)


def test_pivot1():
    candles = np.array(mama_candles)
    single = ta.pivot(candles, mode=1)
    seq = ta.pivot(candles, mode=1, sequential=True)

    assert type(single).__name__ == 'PIVOT'

    assert seq.r1[-1] == single.r1
    assert len(seq.r1) == len(candles)
    assert len(seq.r2) == len(candles)
    assert len(seq.r3) == len(candles)
    assert len(seq.r4) == len(candles)
    assert len(seq.pp) == len(candles)
    assert len(seq.s1) == len(candles)
    assert len(seq.s2) == len(candles)
    assert len(seq.s3) == len(candles)
    assert len(seq.s4) == len(candles)


def test_pivot2():
    candles = np.array(mama_candles)
    single = ta.pivot(candles, mode=2)
    seq = ta.pivot(candles, mode=2, sequential=True)

    assert type(single).__name__ == 'PIVOT'

    assert seq.r1[-1] == single.r1
    assert len(seq.r1) == len(candles)
    assert len(seq.r2) == len(candles)
    assert len(seq.r3) == len(candles)
    assert len(seq.r4) == len(candles)
    assert len(seq.pp) == len(candles)
    assert len(seq.s1) == len(candles)
    assert len(seq.s2) == len(candles)
    assert len(seq.s3) == len(candles)
    assert len(seq.s4) == len(candles)


def test_pivot3():
    candles = np.array(mama_candles)
    single = ta.pivot(candles, mode=3)
    seq = ta.pivot(candles, mode=3, sequential=True)

    assert type(single).__name__ == 'PIVOT'

    assert seq.r1[-1] == single.r1
    assert len(seq.r1) == len(candles)
    assert len(seq.r2) == len(candles)
    assert len(seq.r3) == len(candles)
    assert len(seq.r4) == len(candles)
    assert len(seq.pp) == len(candles)
    assert len(seq.s1) == len(candles)
    assert len(seq.s2) == len(candles)
    assert len(seq.s3) == len(candles)
    assert len(seq.s4) == len(candles)


def test_pivot4():
    candles = np.array(mama_candles)
    single = ta.pivot(candles, mode=4)
    seq = ta.pivot(candles, mode=4, sequential=True)

    assert type(single).__name__ == 'PIVOT'

    assert seq.r1[-1] == single.r1
    assert len(seq.r1) == len(candles)
    assert len(seq.r2) == len(candles)
    assert len(seq.r3) == len(candles)
    assert len(seq.r4) == len(candles)
    assert len(seq.pp) == len(candles)
    assert len(seq.s1) == len(candles)
    assert len(seq.s2) == len(candles)
    assert len(seq.s3) == len(candles)
    assert len(seq.s4) == len(candles)


def test_ppo():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.ppo(candles, fast_period=12, slow_period=26, matype=1)
    seq = ta.ppo(candles, fast_period=12, slow_period=26, matype=1, sequential=True)

    assert round(single, 0) == -7
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_pvi():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.pvi(candles)
    seq = ta.pvi(candles, sequential=True)

    assert round(single, 0) == 661
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_qstick():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.qstick(candles)
    seq = ta.qstick(candles, sequential=True)

    assert round(single, 0) == -26.0
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_reflex():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.reflex(candles)
    seq = ta.reflex(candles, sequential=True)

    assert round(single, 2) == -0.55
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


def test_rocp():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.rocp(candles, period=14)
    seq = ta.rocp(candles, period=14, sequential=True)

    assert round(single, 2) == -0.53
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_rocr():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.rocr(candles, period=14)
    seq = ta.rocr(candles, period=14, sequential=True)

    assert round(single, 2) == 0.47
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_rocr100():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.rocr100(candles, period=14)
    seq = ta.rocr100(candles, period=14, sequential=True)

    assert round(single, 2) == 47.33
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_roofing():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.roofing(candles)
    seq = ta.roofing(candles, sequential=True)

    assert round(single, 0) == -36
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_rsi():
    candles = np.array(rsi_candles)

    single = ta.rsi(candles)
    seq = ta.rsi(candles, sequential=True)

    assert round(single, 2) == 57.84
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_rsmk():
    candles = np.array(srsi_candles)
    candles2 = np.array(mama_candles)

    rsmk = ta.rsmk(candles, candles2)
    assert type(rsmk).__name__ == 'RSMK'
    assert round(rsmk.indicator, 2) == 2.1
    assert round(rsmk.signal, 2) == -31.56

    rsmk_seq = ta.rsmk(candles, candles2, sequential=True)
    assert rsmk_seq.indicator[-1] == rsmk.indicator
    assert rsmk_seq.signal[-1] == rsmk.signal
    assert len(rsmk_seq.indicator) == len(candles)
    assert len(rsmk_seq.signal) == len(candles)


def test_rsx():
    candles = np.array(mama_candles)

    single = ta.rsx(candles)
    seq = ta.rsx(candles, sequential=True)

    assert round(single, 2) == 27.81
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_rvi():
    candles = np.array(mama_candles)

    single = ta.rvi(candles)
    seq = ta.rvi(candles, sequential=True)

    assert round(single, 2) == 27.99
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_safezonestop():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.safezonestop(candles)
    seq = ta.safezonestop(candles, sequential=True)

    assert round(single, 2) == -39.15
    assert len(seq) == len(candles)
    assert seq[-1] == single


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

    single = ta.sarext(candles, start_value=0.02, offset_on_reverse=0, acceleration_init_long=0.02,
                       acceleration_long=0.02,
                       acceleration_max_long=0.2, acceleration_init_short=0.02, acceleration_short=0.02,
                       acceleration_max_short=0.2)
    seq = ta.sarext(candles, start_value=0.02, offset_on_reverse=0, acceleration_init_long=0.02, acceleration_long=0.02,
                    acceleration_max_long=0.2, acceleration_init_short=0.02, acceleration_short=0.02,
                    acceleration_max_short=0.2,
                    sequential=True)

    assert round(single, 2) == -243.15
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_sinwma():
    candles = np.array(mama_candles)

    single = ta.sinwma(candles)
    seq = ta.sinwma(candles, sequential=True)

    assert round(single, 2) == 218.86
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_skew():
    candles = np.array(mama_candles)

    single = ta.skew(candles)
    seq = ta.skew(candles, sequential=True)

    assert round(single, 2) == -1.05
    assert len(seq) == len(candles)
    assert seq[-1] == single

def test_sma():
    close_prices = [22.27, 22.19, 22.08, 22.17, 22.18, 22.13, 22.23, 22.43, 22.24, 22.29]
    candles = fake_range_candle_from_range_prices(close_prices)

    single = ta.sma(candles, 10)
    seq = ta.sma(candles, 10, sequential=True)

    assert round(single, 2) == 22.22
    assert len(seq) == len(candles)
    assert seq[-1] == single
    assert np.isnan(ta.sma(candles, 30))


def test_smma():
    candles = np.array(mama_candles)
    single = ta.smma(candles)
    seq = ta.smma(candles, sequential=True)

    assert round(single, 0) == 192
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_srsi():
    candles = np.array(srsi_candles)
    period = 14

    srsi = ta.srsi(candles)
    k, d = srsi
    assert type(srsi).__name__ == 'StochasticRSI'
    assert round(k, 2) == 21.36
    assert round(d, 2) == 12.4

    srsi = ta.srsi(candles, period=period, sequential=True)
    assert srsi.d[-1] == d
    assert srsi.k[-1] == k
    assert len(srsi.d) == len(candles)
    assert len(srsi.k) == len(candles)


def test_stc():
    candles = np.array(mama_candles)
    single = ta.stc(candles)
    seq = ta.stc(candles, sequential=True)

    assert round(single, 2) == 0.0
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_stddev():
    candles = np.array(mama_candles)
    single = ta.stddev(candles)
    seq = ta.stddev(candles, sequential=True)

    assert round(single, 0) == 37
    assert len(seq) == len(candles)
    assert seq[-1] == single


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


def test_supersmoother():
    candles = np.array(mama_candles)
    single = ta.supersmoother(candles)
    seq = ta.supersmoother(candles, sequential=True)
    assert round(single, 0) == 201
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_supersmoother_3_pole():
    candles = np.array(mama_candles)
    single = ta.supersmoother_3_pole(candles)
    seq = ta.supersmoother_3_pole(candles, sequential=True)
    assert round(single, 0) == 207
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


def test_t3():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.t3(candles, period=5, vfactor=0.7)
    seq = ta.t3(candles, period=5, vfactor=0.7, sequential=True)

    assert round(single, 0) == 194
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


def test_trange():
    candles = np.array(mama_candles)

    single = ta.trange(candles)
    seq = ta.trange(candles, sequential=True)

    assert round(single, 2) == 94.35
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_trendflex():
    candles = np.array(mama_candles)

    single = ta.trendflex(candles)
    seq = ta.trendflex(candles, sequential=True)

    assert round(single, 2) == -1.48
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


def test_trix():
    candles = np.array(trix_candles)

    single = ta.trix(candles)
    seq = ta.trix(candles, sequential=True)

    assert round(single, 2) == 30.87
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_tsf():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.tsf(candles)
    seq = ta.tsf(candles, sequential=True)

    assert round(single, 1) == 174.7
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_tsi():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.tsi(candles)
    seq = ta.tsi(candles, sequential=True)

    assert round(single, 1) == -20.5
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_ttm_trend():
  # use the same candles as mama_candles
  candles = np.array(mama_candles)

  single = ta.ttm_trend(candles)
  seq = ta.ttm_trend(candles, sequential=True)

  assert single == False
  assert len(seq) == len(candles)
  assert seq[-1] == single

def test_typprice():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.typprice(candles)
    seq = ta.typprice(candles, sequential=True)

    assert round(single, 1) == 134.9
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


def test_var():
    candles = np.array(vwma_candles)
    single = ta.var(candles)
    seq = ta.var(candles, sequential=True)

    assert round(single, 2) == 69.96
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_vi():
    candles = np.array(mama_candles)

    single = ta.vi(candles)
    seq = ta.vi(candles, sequential=True)

    assert type(single).__name__ == 'VI'
    assert round(single.plus, 2) == 0.66
    assert round(single.minus, 2) == 1.13

    assert seq.plus[-1] == single.plus
    assert len(seq.plus) == len(candles)
    assert len(seq.minus) == len(candles)


def test_vidya():
    candles = np.array(vwma_candles)
    single = ta.vidya(candles)
    seq = ta.vidya(candles, sequential=True)

    assert round(single, 2) == 194.75
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_vosc():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.vosc(candles)
    seq = ta.vosc(candles, sequential=True)

    assert round(single, 2) == 38.18
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_voss():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.voss(candles)
    seq = ta.voss(candles, sequential=True)

    assert type(single).__name__ == 'VossFilter'
    assert round(single.voss, 2) == -30.71
    assert round(single.filt, 2) == -5.98

    assert seq.voss[-1] == single.voss
    assert seq.filt[-1] == single.filt
    assert len(seq.voss) == len(candles)
    assert len(seq.filt) == len(candles)


def test_vpci():
    candles = np.array(mama_candles)
    single = ta.vpci(candles)
    seq = ta.vpci(candles, sequential=True)

    assert round(single.vpci, 2) == -29.46
    assert round(single.vpcis, 2) == -14.4
    assert len(seq.vpci) == len(candles)
    assert seq.vpci[-1] == single.vpci


def test_vpt():
    candles = np.array(mama_candles)
    single = ta.vpt(candles)
    seq = ta.vpt(candles, sequential=True)

    assert round(single, 2) == -1733928.99
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_vwap():
    candles = np.array(mama_candles)
    single = ta.vwap(candles)
    seq = ta.vwap(candles, sequential=True)

    assert round(single, 2) == 134.86
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_vwma():
    candles = np.array(vwma_candles)
    single = ta.vwma(candles)
    seq = ta.vwma(candles, sequential=True)

    assert round(single, 2) == 195.86
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_vwmacd():
    candles = np.array(mama_candles)

    single = ta.vwmacd(candles, fast_period=12, slow_period=26, signalperiod=9)
    seq = ta.vwmacd(candles, fast_period=12, slow_period=26, signalperiod=9, sequential=True)

    assert type(single).__name__ == 'VWMACD'
    assert round(single.macd, 2) == -31.37
    assert round(single.signal, 2) == -19.64
    assert round(single.hist, 2) == -11.73

    assert seq.macd[-1] == single.macd
    assert len(seq.macd) == len(candles)
    assert len(seq.signal) == len(candles)
    assert len(seq.hist) == len(candles)


def test_wad():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.wad(candles)
    seq = ta.wad(candles, sequential=True)

    assert round(single, 2) == -122.14
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_wclprice():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.wclprice(candles)
    seq = ta.wclprice(candles, sequential=True)

    assert round(single, 2) == 128.1
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_wilders():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.wilders(candles)
    seq = ta.wilders(candles, sequential=True)

    assert round(single, 2) == 192.11
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


def test_wma():
    # use the same candles as mama_candles
    candles = np.array(mama_candles)

    single = ta.wma(candles, period=9)
    seq = ta.wma(candles, period=9, sequential=True)

    assert round(single, 2) == 189.13
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_zlema():
    candles = np.array(mama_candles)
    single = ta.zlema(candles)
    seq = ta.zlema(candles, sequential=True)

    assert round(single, 0) == 189
    assert len(seq) == len(candles)
    assert seq[-1] == single


def test_zscore():
    candles = np.array(mama_candles)
    single = ta.zscore(candles)
    seq = ta.zscore(candles, sequential=True)

    assert round(single, 1) == -3.2
    assert len(seq) == len(candles)
    assert seq[-1] == single
