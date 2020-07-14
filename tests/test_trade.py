import jesse.helpers as jh
from jesse.config import config, reset_config
from jesse.models import CompletedTrade
from jesse.store import store


def no_fee():
    """

    """
    print(config)
    config['env']['exchanges']['Sandbox']['fee'] = 0


def set_up():
    """

    """
    reset_config()
    store.reset(True)


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
        'symbol': 'BTCUSD',
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
        'symbol': 'BTCUSD',
        'opened_at': 1552309186171,
        'closed_at': 1552309186171 + 60000
    })

    # 1 minute == 60 seconds
    assert trade.holding_period == 60


def test_PNL_percentage():
    no_fee()

    trade = CompletedTrade({
        'type': 'long',
        'exchange': 'Sandbox',
        'entry_price': 10,
        'exit_price': 12,
        'take_profit_at': 20,
        'stop_loss_at': 5,
        'qty': 1,
        'orders': [],
        'symbol': 'BTCUSD',
        'opened_at': jh.now(),
        'closed_at': jh.now()
    })
    assert trade.PNL_percentage == 20


def test_PNL_with_fee():
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
        'symbol': 'BTCUSD',
        'opened_at': jh.now(),
        'closed_at': jh.now()
    })

    assert trade.fee == 0.06
    assert trade.PNL == 9.94


def test_PNL_without_fee():
    no_fee()

    trade = CompletedTrade({
        'type': 'long',
        'exchange': 'Sandbox',
        'entry_price': 10,
        'exit_price': 20,
        'take_profit_at': 20,
        'stop_loss_at': 5,
        'qty': 1,
        'orders': [],
        'symbol': 'BTCUSD',
        'opened_at': jh.now(),
        'closed_at': jh.now()
    })
    assert trade.PNL == 10


def test_R():
    no_fee()

    trade = CompletedTrade({
        'type': 'long',
        'exchange': 'Sandbox',
        'entry_price': 10,
        'exit_price': 12,
        'take_profit_at': 20,
        'stop_loss_at': 5,
        'qty': 1,
        'orders': [],
        'symbol': 'BTCUSD',
        'opened_at': jh.now(),
        'closed_at': jh.now()
    })
    assert trade.risk_reward_ratio == 2


def test_risk_percentage():
    no_fee()

    trade = CompletedTrade({
        'type': 'long',
        'exchange': 'Sandbox',
        'entry_price': 10,
        'exit_price': 12,
        'take_profit_at': 20,
        'stop_loss_at': 5,
        'qty': 1,
        'orders': [],
        'symbol': 'BTCUSD',
        'opened_at': jh.now(),
        'closed_at': jh.now()
    })
    assert trade.risk_percentage == round((((10 - 5) / 1) * 10), 2)


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
        'symbol': 'BTCUSD',
        'opened_at': jh.now(),
        'closed_at': jh.now()
    })

    assert trade.size == 10


