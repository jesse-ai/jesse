import jesse.helpers as jh
import jesse.services.selectors as selectors
from jesse.config import reset_config
from jesse.enums import timeframes, exchanges
from jesse.factories import fake_range_candle
from jesse.modes import backtest_mode
from jesse.routes import router
from jesse.store import store
from jesse.config import config


def test_backtesting_one_route():
    reset_config()
    router.set_routes([
        (exchanges.SANDBOX, 'BTC-USDT', timeframes.MINUTE_5, 'Test19')
    ])
    config['env']['exchanges'][exchanges.SANDBOX]['type'] = 'futures'
    store.reset(True)

    candles = {}
    key = jh.key(exchanges.SANDBOX, 'BTC-USDT')
    candles[key] = {
        'exchange': exchanges.SANDBOX,
        'symbol': 'BTC-USDT',
        'candles': fake_range_candle(5 * 20)
    }
    routes = router.routes

    # assert that strategy hasn't been initiated before running backtest_mode()
    assert routes[0].strategy is None

    # run backtest (dates are fake just to pass)
    backtest_mode.run('2019-04-01', '2019-04-02', candles)

    one_min = store.candles.get_candles(exchanges.SANDBOX, 'BTC-USDT', '1m')
    five_min = store.candles.get_candles(exchanges.SANDBOX, 'BTC-USDT', '5m')

    # assert the count of present candles
    assert len(five_min) == 20
    assert len(one_min) == 20 * 5

    first_1 = one_min[0]
    last_1 = one_min[-1]
    first_5 = five_min[0]
    last_5 = five_min[-1]

    # assert time in store
    assert store.app.time == last_1[0] + 60000

    # assert timestamps
    assert first_1[0] == first_5[0]
    assert last_1[0] == (last_5[0] + 60000 * 4)

    # there must be only one positions present
    assert len(store.positions.storage) == 1
    p = selectors.get_position(exchanges.SANDBOX, 'BTC-USDT')
    assert p.is_close
    assert p.current_price == last_1[2]
    assert p.current_price == last_5[2]

    # assert routes
    assert len(routes) == 1
    assert routes[0].exchange == exchanges.SANDBOX
    assert routes[0].symbol == 'BTC-USDT'
    assert routes[0].timeframe == '5m'
    assert routes[0].strategy_name == 'Test19'
    # assert that the strategy has been initiated
    assert routes[0].strategy is not None


def test_backtesting_three_routes():
    reset_config()
    router.set_routes([
        (exchanges.SANDBOX, 'BTC-USDT', timeframes.MINUTE_5, 'Test19'),
        (exchanges.SANDBOX, 'ETH-USDT', timeframes.MINUTE_5, 'Test19'),
        (exchanges.SANDBOX, 'XRP-USDT', timeframes.MINUTE_15, 'Test19'),
    ])
    config['env']['exchanges'][exchanges.SANDBOX]['type'] = 'futures'
    store.reset(True)
    candles = {}
    routes = router.routes
    for r in routes:
        key = jh.key(r.exchange, r.symbol)
        candles[key] = {
            'exchange': r.exchange,
            'symbol': r.symbol,
            'candles': fake_range_candle(5 * 3 * 20)
        }

        # assert that strategy hasn't been initiated before running backtest_mode()
        assert r.strategy is None

    # run backtest (dates are fake just to pass)
    backtest_mode.run('2019-04-01', '2019-04-02', candles)

    # there must be three positions present with the updated current_price
    assert len(store.positions.storage) == 3

    for r in routes:
        # r3's '15m' timeframe makes r1 and r2 to support
        # '15' timeframe as well. r1 and r2 also make r3
        # to support '5m' timeframe also.
        r_one_min = store.candles.get_candles(r.exchange, r.symbol, '1m')
        r_five_min = store.candles.get_candles(r.exchange, r.symbol, '5m')
        r_fifteen_min = store.candles.get_candles(r.exchange, r.symbol, '15m')

        # assert the count of present candles
        assert len(r_one_min) == (5 * 3) * 20
        assert len(r_five_min) == 20 * 3
        assert len(r_fifteen_min) == 20

        r_first_1 = r_one_min[0]
        r_last_1 = r_one_min[-1]
        r_first_5 = r_five_min[0]
        r_last_5 = r_five_min[-1]
        r_last_15 = r_fifteen_min[-1]

        # assert timestamps
        assert r_first_1[0] == r_first_5[0]
        assert r_last_1[0] == (r_last_5[0] + 60000 * 4)
        assert r_last_5[0] == (r_last_15[0] + 60000 * 10)

        # assert positions
        p = selectors.get_position(r.exchange, r.symbol)
        assert p.is_close is True
        last_candle = store.candles.get_candles(r.exchange, r.symbol, '1m')[-1]
        assert p.current_price == last_candle[2]

        # assert that the strategy has been initiated
        assert r.strategy is not None
