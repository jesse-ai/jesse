import jesse.helpers as jh
from jesse.config import reset_config
from jesse.enums import exchanges, timeframes, order_roles
from jesse.factories import fake_range_candle_from_range_prices
from jesse.models import CompletedTrade
from jesse.modes import backtest_mode
from jesse.routes import router
from jesse.store import store
from jesse.config import config


def get_btc_candles():
    candles = {}
    candles[jh.key(exchanges.SANDBOX, 'BTC-USDT')] = {
        'exchange': exchanges.SANDBOX,
        'symbol': 'BTC-USDT',
        'candles': fake_range_candle_from_range_prices(range(1, 100))
    }
    return candles


def set_up(routes, is_futures_trading=True):
    reset_config()
    if is_futures_trading:
        # used only in futures trading
        config['env']['exchanges'][exchanges.SANDBOX]['type'] = 'futures'
    else:
        config['env']['exchanges'][exchanges.SANDBOX]['type'] = 'spot'
    router.set_routes(routes)
    store.reset(True)


def test_can_handle_multiple_entry_orders_too_close_to_each_other():
    set_up([
        (exchanges.SANDBOX, 'BTC-USDT', timeframes.MINUTE_1, 'Test34'),
    ])

    backtest_mode.run('2019-04-01', '2019-04-02', get_btc_candles())

    assert len(store.completed_trades.trades) == 1

    t: CompletedTrade = store.completed_trades.trades[0]

    assert t.type == 'long'
    assert t.stop_loss_at == 0.4
    assert t.entry_price == (1.1 + 1.2 + 1.3 + 1.4) / 4
    assert t.exit_price == 3
    assert t.take_profit_at == 3
    # 4 entry + 1 exit
    assert len(t.orders) == 5
    # last order is closing order
    assert t.orders[-1].role == order_roles.CLOSE_POSITION
    # first order must be opening order
    assert t.orders[0].role == order_roles.OPEN_POSITION
    # second order must be increasing order
    assert t.orders[1].role == order_roles.INCREASE_POSITION
    assert t.orders[2].role == order_roles.INCREASE_POSITION
def test_conflicting_orders():
    set_up([
        (exchanges.SANDBOX, 'BTC-USDT', timeframes.MINUTE_1, 'Test04'),
    ])

    backtest_mode.run('2019-04-01', '2019-04-02', get_btc_candles())

    assert len(store.completed_trades.trades) == 1

    t: CompletedTrade = store.completed_trades.trades[0]

    assert t.type == 'long'
    assert t.stop_loss_at == 1.0
    assert t.entry_price == (1.1 + 1.11) / 2
    assert t.exit_price == (1.2 + 1.3) / 2
    assert t.take_profit_at == (1.2 + 1.3) / 2


def test_conflicting_orders_2():
    set_up([
        (exchanges.SANDBOX, 'BTC-USDT', timeframes.MINUTE_1, 'Test20'),
    ])

    backtest_mode.run('2019-04-01', '2019-04-02', get_btc_candles())

    assert len(store.completed_trades.trades) == 1

    t: CompletedTrade = store.completed_trades.trades[0]

    assert t.entry_price == 2.5
    assert t.take_profit_at == 2.6
    assert t.stop_loss_at == 2.4
    assert t.exit_price == 2.6



#
# def test_can_handle_not_correctly_sorted_multiple_orders():
#     set_up([
#         (exchanges.SANDBOX, 'BTC-USDT', timeframes.MINUTE_1, 'Test35'),
#     ])
#
#     backtest_mode.run('2019-04-01', '2019-04-02', get_btc_candles())
#
#     assert len(store.completed_trades.trades) == 1
#
#     t: CompletedTrade = store.completed_trades.trades[0]
#
#     assert t.type == 'long'
#     assert t.stop_loss_at == 0.4
#     assert t.entry_price == (1.1 + 1.2 + 1.3 + 1.4) / 4
#     assert t.exit_price == 3
#     assert t.take_profit_at == 3
