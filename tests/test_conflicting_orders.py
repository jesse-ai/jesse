import jesse.helpers as jh
from jesse.config import reset_config
from jesse.enums import exchanges
from jesse.factories import candles_from_close_prices
from jesse.models import CompletedTrade
from jesse.routes import router
from jesse.store import store
from jesse.config import config
from tests.utils import single_route_backtest


def get_btc_candles():
    return {
        jh.key(exchanges.SANDBOX, 'BTC-USDT'): {
            'exchange': exchanges.SANDBOX,
            'symbol': 'BTC-USDT',
            'candles': candles_from_close_prices(range(1, 100)),
        }
    }


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
    single_route_backtest('Test34')

    assert len(store.completed_trades.trades) == 1

    t: CompletedTrade = store.completed_trades.trades[0]

    assert t.type == 'long'
    assert t.entry_price == (1.1 + 1.2 + 1.3 + 1.4) / 4
    assert t.exit_price == 3
    # 4 entry + 1 exit
    assert len(t.orders) == 5


def test_conflicting_orders():
    single_route_backtest('Test04')

    assert len(store.completed_trades.trades) == 1

    t: CompletedTrade = store.completed_trades.trades[0]

    assert t.type == 'long'
    assert t.entry_price == (1.1 + 1.11) / 2
    assert t.exit_price == (1.2 + 1.3) / 2


def test_conflicting_orders_2():
    single_route_backtest('Test20')

    assert len(store.completed_trades.trades) == 1

    t: CompletedTrade = store.completed_trades.trades[0]

    assert t.entry_price == 2.5
    assert t.exit_price == 2.6


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
#     assert t.entry_price == (1.1 + 1.2 + 1.3 + 1.4) / 4
#     assert t.exit_price == 3
