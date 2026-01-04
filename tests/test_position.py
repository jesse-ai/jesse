from jesse.enums import exchanges
from jesse.models import Position
from jesse.testing_utils import set_up, single_route_backtest
from jesse.services import position_service


def test_increase_a_long_position():
    set_up()

    p = position_service.create_position(exchanges.SANDBOX, 'BTC-USDT', {
        'entry_price': 50,
        'current_price': 50,
        'qty': 2,
    })

    position_service._mutating_increase(p, 2, 100)

    assert p.qty == 4
    assert p.entry_price == 75


def test_increase_a_short_position():
    set_up()

    p = position_service.create_position(exchanges.SANDBOX, 'BTC-USDT', {
        'entry_price': 50,
        'current_price': 50,
        'qty': -2,
    })

    position_service._mutating_increase(p, 2, 40)

    assert p.qty == -4
    assert p.entry_price == 45


def test_initiating_position():
    position = position_service.create_position(exchanges.SANDBOX, 'BTC-USDT', {
        'current_price': 100,
        'qty': 0
    })

    assert position.exchange_name == 'Sandbox'
    assert position.symbol == 'BTC-USDT'
    assert position.current_price == 100
    assert position.qty == 0
    assert position.closed_at is None
    assert position.opened_at is None
    assert position.entry_price is None
    assert position.exit_price is None


def test_is_able_to_close_via_reduce_position_too():
    set_up()

    p = position_service.create_position(exchanges.SANDBOX, 'BTC-USDT', {
        'entry_price': 50,
        'current_price': 50,
        'qty': 2,
    })

    position_service._mutating_reduce(p, 2, 50)

    assert p.qty == 0


def test_open_position():
    set_up()

    p = position_service.create_position(exchanges.SANDBOX, 'BTC-USDT')

    assert p.qty == 0
    assert p.entry_price is None
    assert p.exit_price is None
    assert p.current_price is None

    position_service._mutating_open(p, 1, 50)

    assert p.qty == 1
    assert p.entry_price == 50
    assert p.exit_price is None


def test_position_is_close():
    p = position_service.create_position(exchanges.SANDBOX, 'BTC-USDT', {
        'entry_price': 50,
        'current_price': 60,
        'qty': 0,
    })
    assert p.is_close is True

    p.qty = 2
    assert p.is_close is False


def test_position_is_open():
    p = position_service.create_position(exchanges.SANDBOX, 'BTC-USDT', {
        'entry_price': 50,
        'current_price': 60,
        'qty': 2,
    })
    assert p.is_open is True

    p.qty = 0
    assert p.is_open is False


def test_position_pnl():
    # long winning position
    p1: Position = position_service.create_position(exchanges.SANDBOX, 'BTC-USDT', {
        'entry_price': 100,
        'current_price': 110,
        'qty': 2,
    })
    assert p1.pnl == 20

    # long losing position
    p2: Position = position_service.create_position(exchanges.SANDBOX, 'BTC-USDT', {
        'entry_price': 100,
        'current_price': 90,
        'qty': 2,
    })
    assert p2.pnl == -20

    # short winning position
    p3: Position = position_service.create_position(exchanges.SANDBOX, 'BTC-USDT', {
        'entry_price': 100,
        'current_price': 90,
        'qty': -2,
    })
    assert p3.pnl == 20

    # short losing position
    p3: Position = position_service.create_position(exchanges.SANDBOX, 'BTC-USDT', {
        'entry_price': 100,
        'current_price': 110,
        'qty': -2,
    })
    assert p3.pnl == -20


def test_position_pnl_percentage():
    p = position_service.create_position(exchanges.SANDBOX, 'BTC-USDT', {
        'entry_price': 50,
        'current_price': 60,
        'qty': 2,
    })

    # long position
    assert p.pnl_percentage == 20

    p.current_price -= 20
    assert p.pnl_percentage == -20

    # short position
    p.entry_price = 50
    p.qty = -2
    p.current_price = 40
    assert p.pnl_percentage == 20


def test_position_roi():
    set_up()
    p = position_service.create_position(exchanges.SANDBOX, 'BTC-USDT')
    position_service._mutating_open(p, 3, 100)
    p.current_price = 110

    assert p.value == 330
    assert p.total_cost == 300

    assert p.roi == 10


def test_position_type():
    p = position_service.create_position(exchanges.SANDBOX, 'BTC-USDT', {'current_price': 100, 'qty': 0})
    assert p.type == 'close'

    p = position_service.create_position(exchanges.SANDBOX, 'BTC-USDT', {'current_price': 100, 'qty': 1})
    assert p.type == 'long'

    p = position_service.create_position(exchanges.SANDBOX, 'BTC-USDT', {
        'current_price': 100,
        'qty': -1
    })
    assert p.type == 'short'


def test_position_value():
    long_position = position_service.create_position(exchanges.SANDBOX, 'BTC-USDT', {'current_price': 100, 'qty': 1})
    short_position = position_service.create_position(exchanges.SANDBOX, 'BTC-USDT', {'current_price': 100, 'qty': -1})

    assert long_position.value == 100
    assert short_position.value == 100

    closed_position_value = position_service.create_position(exchanges.SANDBOX, 'BTC-USDT', {'qty': 0})
    assert closed_position_value.value == 0


def test_position_with_leverage():
    # with 1x leverage
    single_route_backtest('TestPositionWithLeverage1', leverage=1)

    # with 2x leverage
    single_route_backtest('TestPositionWithLeverage2', leverage=2)


def test_reduce_a_long_position():
    set_up()

    p = position_service.create_position(exchanges.SANDBOX, 'BTC-USDT', {
        'entry_price': 50,
        'current_price': 50,
        'qty': 2,
    })

    position_service._mutating_reduce(p, 1, 50)

    assert p.qty == 1


def test_reduce_a_short_position():
    set_up()

    p = position_service.create_position(exchanges.SANDBOX, 'BTC-USDT', {
        'entry_price': 50,
        'current_price': 50,
        'qty': -2,
    })

    position_service._mutating_reduce(p, 1, 50)

    assert p.qty == -1


def test_position_exchange_type_property():
    single_route_backtest(
        'TestPositionExchangeTypeProperty1',
        is_futures_trading=True
    )

    single_route_backtest(
        'TestPositionExchangeTypeProperty2',
        is_futures_trading=False
    )


def test_position_total_cost_property():
    # futures
    single_route_backtest(
        'TestPositionTotalCostProperty',
        is_futures_trading=True,
        leverage=2
    )

    # spot
    single_route_backtest(
        'TestPositionTotalCostProperty',
        is_futures_trading=False
    )

