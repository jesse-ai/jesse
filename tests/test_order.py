from jesse.testing_utils import single_route_backtest


def test_order_is_stop_loss_property():
    single_route_backtest('TestOrderIsStopLossProperty')


def test_order_is_take_profit_property():
    single_route_backtest('TestOrderIsTakeProfitProperty')


def test_order_value_property():
    single_route_backtest('TestOrderValueProperty')
