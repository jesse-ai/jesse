from jesse.config import config
from jesse.enums import Exchanges, Timeframe
from jesse.routes import router
from jesse.store import store


def test_routes():
    # re-define routes
    router.set_routes([
        {'exchange': Exchanges.BITFINEX_SPOT, 'symbol': 'ETH-USD', 'timeframe': Timeframe.HOUR_3.value, 'strategy': 'Test19'},
        {'exchange': Exchanges.SANDBOX, 'symbol': 'BTC-USD', 'timeframe': Timeframe.MINUTE_15.value, 'strategy': 'Test19'},
    ])

    router.set_data_candles([
        {'exchange': Exchanges.BITFINEX_SPOT, 'symbol': 'EOS-USD', 'timeframe': Timeframe.HOUR_3.value},
        {'exchange': Exchanges.BITFINEX_SPOT, 'symbol': 'EOS-USD', 'timeframe': Timeframe.HOUR_1.value},
    ])

    # reset store for new routes to take affect
    store.reset(True)

    # now assert it's working as expected
    assert set(config['app']['trading_exchanges']) == set([Exchanges.SANDBOX, Exchanges.BITFINEX_SPOT])
    assert set(config['app']['trading_symbols']) == set(['BTC-USD', 'ETH-USD'])
    assert set(config['app']['trading_timeframes']) == set([Timeframe.HOUR_3.value, Timeframe.MINUTE_15.value])
    assert set(config['app']['considering_exchanges']) == set([Exchanges.SANDBOX, Exchanges.BITFINEX_SPOT])
    assert set(config['app']['considering_symbols']) == set(['BTC-USD', 'ETH-USD', 'EOS-USD'])
    assert set(config['app']['considering_timeframes']) == set(
        [Timeframe.MINUTE_1.value, Timeframe.HOUR_3.value, Timeframe.MINUTE_15.value, Timeframe.HOUR_1.value])
