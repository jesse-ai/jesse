from jesse.models import CompletedTrade
from jesse.store import store
from .utils import single_route_backtest
import numpy as np


def test_completed_trade_in_a_simple_strategy():
    assert store.completed_trades.trades == []

    single_route_backtest('CanAddCompletedTradeToStore')

    assert len(store.completed_trades.trades) == 1
    assert store.completed_trades.count == 1

    t: CompletedTrade = store.completed_trades.trades[0]

    assert t.entry_price == 10
    assert t.exit_price == 15
    assert t.exchange == 'Sandbox'
    assert t.symbol == 'BTC-USDT'
    assert t.type == 'long'
    assert t.strategy_name == 'CanAddCompletedTradeToStore'
    assert t.qty == 1
    assert t.size == 1*10
    assert t.fee == 0
    assert t.pnl == 5
    assert t.pnl_percentage == 50
    assert t.holding_period == 60*5


def test_completed_trade_in_a_strategy_with_two_trades():
    pass


def test_completed_trade_after_exiting_the_trade():
    single_route_backtest('TestCompletedTradeAfterExitingTrade', leverage=2)


def test_trade_qty_entry_price_exit_price_size_properties():
    # long trade
    t1 = CompletedTrade({
        'type': 'long',
    })
    # add buy orders
    t1.buy_orders.append(np.array([10, 100]))
    t1.buy_orders.append(np.array([10, 200]))
    # add sell orders
    t1.sell_orders.append(np.array([10, 300]))
    t1.sell_orders.append(np.array([10, 400]))
    # assert qty, entry price and exit price
    assert t1.qty == 20
    assert t1.entry_price == 150
    assert t1.exit_price == 350
    assert t1.size == 20*150

    # short trade
    t2 = CompletedTrade({
        'type': 'short',
    })
    # add sell orders
    t2.sell_orders.append(np.array([10, 300]))
    t2.sell_orders.append(np.array([10, 400]))
    # add buy orders
    t2.buy_orders.append(np.array([10, 100]))
    t2.buy_orders.append(np.array([10, 200]))
    # assert qty, entry price and exit price
    assert t2.qty == 20
    assert t2.exit_price == 150
    assert t2.entry_price == 350
    assert t2.size == 20 * 350

