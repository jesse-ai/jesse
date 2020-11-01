import jesse.helpers as jh
from jesse.enums import order_types, sides, order_statuses
from jesse.models import Order
from jesse.config import config, reset_config
from jesse.enums import exchanges, timeframes, order_types, order_flags, order_roles
from jesse.routes import router
from jesse.store import store
from jesse.services import selectors
from jesse.models import Position, Exchange

position: Position = None
exchange: Exchange = None


def set_up_without_fee(is_margin_trading=False):
    reset_config()
    config['env']['exchanges'][exchanges.SANDBOX]['type'] = 'margin'
    config['env']['exchanges'][exchanges.SANDBOX]['fee'] = 0
    config['env']['exchanges'][exchanges.SANDBOX]['assets'] = [
        {'asset': 'USDT', 'balance': 1000},
        {'asset': 'BTC', 'balance': 0},
    ]
    if is_margin_trading:
        # used only in margin trading
        config['env']['exchanges'][exchanges.SANDBOX]['type'] = 'margin'
        config['env']['exchanges'][exchanges.SANDBOX]['settlement_currency'] = 'USDT'
    config['app']['trading_mode'] = 'backtest'
    config['app']['considering_exchanges'] = ['Sandbox']
    router.set_routes([(exchanges.SANDBOX, 'BTCUSDT', '5m', 'Test19')])
    store.reset(True)

    global position
    global exchange
    position = selectors.get_position(exchanges.SANDBOX, 'BTCUSDT')
    position.current_price = 50
    exchange = selectors.get_exchange(exchanges.SANDBOX)


def test_cancel_order():
    set_up_without_fee()

    order = Order({
        'id': jh.generate_unique_id(),
        'exchange': exchange.name,
        'symbol': 'BTCUSDT',
        'type': order_types.LIMIT,
        'price': 129.33,
        'qty': 10.2041,
        'side': sides.BUY,
        'status': order_statuses.ACTIVE,
        'created_at': jh.now(),
    })

    assert order.is_canceled is False

    order.cancel()

    assert order.is_canceled is True
    assert order.canceled_at == jh.now()


def test_execute_order():
    set_up_without_fee()

    order = Order({
        'id': jh.generate_unique_id(),
        'symbol': 'BTCUSDT',
        'exchange': exchange.name,
        'type': order_types.LIMIT,
        'price': 129.33,
        'qty': 10.2041,
        'side': sides.BUY,
        'status': order_statuses.ACTIVE,
        'created_at': jh.now(),
    })

    assert order.is_executed is False
    assert order.executed_at is None

    order.execute()

    assert order.is_executed is True
    assert order.executed_at == jh.now()
