import jesse.helpers as jh
from jesse.config import config
from jesse.models import CompletedTrade
from jesse.store import store
from .utils import set_up, single_route_backtest


def test_can_add_trade_to_store():
    set_up()

    assert store.completed_trades.trades == []

    trade = CompletedTrade({
        'type': 'long',
        'exchange': 'Sandbox',
        'entry_price': 10,
        'exit_price': 20,
        'take_profit_at': 20,
        'stop_loss_at': 5,
        'qty': 1,
        'orders': [],
        'symbol': 'BTC-USD',
        'opened_at': 1552309186171,
        'closed_at': 1552309186171 + 60000
    })

    store.completed_trades.add_trade(trade)
    assert store.completed_trades.trades == [trade]
    store.reset()
    assert store.completed_trades.trades == []


def test_holding_period():
    trade = CompletedTrade({
        'type': 'long',
        'exchange': 'Sandbox',
        'entry_price': 10,
        'exit_price': 20,
        'take_profit_at': 20,
        'stop_loss_at': 5,
        'qty': 1,
        'orders': [],
        'symbol': 'BTC-USD',
        'opened_at': 1552309186171,
        'closed_at': 1552309186171 + 60000
    })

    # 1 minute == 60 seconds
    assert trade.holding_period == 60


def test_pnl_percentage():
    set_up(zero_fee=True)

    # 1x leverage
    trade = CompletedTrade({
        'type': 'long',
        'exchange': 'Sandbox',
        'entry_price': 10,
        'exit_price': 12,
        'take_profit_at': 20,
        'stop_loss_at': 5,
        'qty': 1,
        'orders': [],
        'symbol': 'BTC-USD',
        'opened_at': jh.now_to_timestamp(),
        'closed_at': jh.now_to_timestamp(),
        'leverage': 1,
    })
    assert trade.pnl_percentage == 20

    # 2x leverage
    trade = CompletedTrade({
        'type': 'long',
        'exchange': 'Sandbox',
        'entry_price': 10,
        'exit_price': 12,
        'take_profit_at': 20,
        'stop_loss_at': 5,
        'qty': 1,
        'orders': [],
        'symbol': 'BTC-USD',
        'opened_at': jh.now_to_timestamp(),
        'closed_at': jh.now_to_timestamp(),
        'leverage': 2,
    })
    assert trade.pnl_percentage == 40


def test_pnl_with_fee():
    # set fee (0.20%)
    config['env']['exchanges']['Sandbox']['fee'] = 0.002

    trade = CompletedTrade({
        'type': 'long',
        'exchange': 'Sandbox',
        'entry_price': 10,
        'exit_price': 20,
        'take_profit_at': 20,
        'stop_loss_at': 5,
        'qty': 1,
        'orders': [],
        'symbol': 'BTC-USD',
        'opened_at': jh.now_to_timestamp(),
        'closed_at': jh.now_to_timestamp()
    })

    assert trade.fee == 0.06
    assert trade.pnl == 9.94


def test_pnl_without_fee():
    set_up(zero_fee=True)

    trade = CompletedTrade({
        'type': 'long',
        'exchange': 'Sandbox',
        'entry_price': 10,
        'exit_price': 20,
        'take_profit_at': 20,
        'stop_loss_at': 5,
        'qty': 1,
        'orders': [],
        'symbol': 'BTC-USD',
        'opened_at': jh.now_to_timestamp(),
        'closed_at': jh.now_to_timestamp()
    })
    assert trade.pnl == 10


def test_r():
    set_up(zero_fee=True)

    trade = CompletedTrade({
        'type': 'long',
        'exchange': 'Sandbox',
        'entry_price': 10,
        'exit_price': 12,
        'take_profit_at': 20,
        'stop_loss_at': 5,
        'qty': 1,
        'orders': [],
        'symbol': 'BTC-USD',
        'opened_at': jh.now_to_timestamp(),
        'closed_at': jh.now_to_timestamp()
    })


def test_risk_percentage():
    set_up(zero_fee=True)

    trade = CompletedTrade({
        'type': 'long',
        'exchange': 'Sandbox',
        'entry_price': 10,
        'exit_price': 12,
        'take_profit_at': 20,
        'stop_loss_at': 5,
        'qty': 1,
        'orders': [],
        'symbol': 'BTC-USD',
        'opened_at': jh.now_to_timestamp(),
        'closed_at': jh.now_to_timestamp()
    })


def test_trade_size():
    trade = CompletedTrade({
        'type': 'long',
        'exchange': 'Sandbox',
        'entry_price': 10,
        'exit_price': 20,
        'take_profit_at': 20,
        'stop_loss_at': 5,
        'qty': 1,
        'orders': [],
        'symbol': 'BTC-USD',
        'opened_at': jh.now_to_timestamp(),
        'closed_at': jh.now_to_timestamp()
    })

    assert trade.size == 10


def test_completed_trade_after_exiting_the_trade():
    single_route_backtest('TestCompletedTradeAfterExitingTrade', leverage=2)
