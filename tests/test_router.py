from jesse.config import config
from jesse.enums import exchanges, timeframes
from jesse.routes import router
from jesse.store import store
from jesse.services import exchange_service, order_service, position_service


def test_routes():
    # re-define routes
    trading_routes = [
        {'exchange': exchanges.SANDBOX, 'symbol': 'ETH-USD', 'timeframe': timeframes.HOUR_3, 'strategy': 'Test19'},
        {'exchange': exchanges.SANDBOX, 'symbol': 'BTC-USD', 'timeframe': timeframes.MINUTE_15, 'strategy': 'Test19'},
    ]
    data_routes = [
        {'exchange': exchanges.SANDBOX, 'symbol': 'EOS-USD', 'timeframe': timeframes.HOUR_3},
        {'exchange': exchanges.SANDBOX, 'symbol': 'EOS-USD', 'timeframe': timeframes.HOUR_1},
    ]
    
    router.initiate(trading_routes, data_routes)

    # reset store
    store.reset() 
    # initialize exchanges state
    exchange_service.initialize_exchanges_state()
    # initialize orders state
    order_service.initialize_orders_state()
    # initialize positions state
    position_service.initialize_positions_state()

    # now assert it's working as expected
    assert set(config['app']['trading_exchanges']) == set([exchanges.SANDBOX])
    assert set(config['app']['trading_symbols']) == set(['BTC-USD', 'ETH-USD'])
    assert set(config['app']['trading_timeframes']) == set([timeframes.HOUR_3, timeframes.MINUTE_15])
    assert set(config['app']['considering_exchanges']) == set([exchanges.SANDBOX, exchanges.SANDBOX])
    assert set(config['app']['considering_symbols']) == set(['BTC-USD', 'ETH-USD', 'EOS-USD'])
    assert set(config['app']['considering_timeframes']) == set(
        [timeframes.MINUTE_1, timeframes.HOUR_3, timeframes.MINUTE_15, timeframes.HOUR_1])
