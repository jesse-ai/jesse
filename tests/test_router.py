from jesse.config import config
from jesse.enums import exchanges, timeframes
from jesse.routes import router
from jesse.store import store


def test_routes():
    # re-define routes
    router.set_routes([
        {'exchange': exchanges.BITFINEX_SPOT, 'symbol': 'ETH-USD', 'timeframe': timeframes.HOUR_3, 'strategy': 'Test19'},
        {'exchange': exchanges.SANDBOX, 'symbol': 'BTC-USD', 'timeframe': timeframes.MINUTE_15, 'strategy': 'Test19'},
    ])

    router.set_extra_candles([
        {'exchange': exchanges.BITFINEX_SPOT, 'symbol': 'EOS-USD', 'timeframe': timeframes.HOUR_3},
        {'exchange': exchanges.BITFINEX_SPOT, 'symbol': 'EOS-USD', 'timeframe': timeframes.HOUR_1},
    ])

    # reset store for new routes to take affect
    store.reset(True)

    # now assert it's working as expected
    assert set(config['app']['trading_exchanges']) == set([exchanges.SANDBOX, exchanges.BITFINEX_SPOT])
    assert set(config['app']['trading_symbols']) == set(['BTC-USD', 'ETH-USD'])
    assert set(config['app']['trading_timeframes']) == set([timeframes.HOUR_3, timeframes.MINUTE_15])
    assert set(config['app']['considering_exchanges']) == set([exchanges.SANDBOX, exchanges.BITFINEX_SPOT])
    assert set(config['app']['considering_symbols']) == set(['BTC-USD', 'ETH-USD', 'EOS-USD'])
    assert set(config['app']['considering_timeframes']) == set(
        [timeframes.MINUTE_1, timeframes.HOUR_3, timeframes.MINUTE_15, timeframes.HOUR_1])
