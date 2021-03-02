from jesse.modes.import_candles_mode.drivers.binance_inverse_futures import encode_symbol, decode_symbol


def test_encode_symbol():
    assert encode_symbol('BTC-PERP') == 'BTCUSD_PERP'
    assert encode_symbol('BTC-200925') == 'BTCUSD_200925'


def test_decode_symbol():
    assert decode_symbol('BTCUSD_PERP') == 'BTC-PERP'
    assert decode_symbol('BTCUSD_200925') == 'BTC-200925'
