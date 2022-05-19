from jesse.testing_utils import single_route_backtest
import pytest
from jesse import exceptions
import jesse.helpers as jh


def test_should_be_able_to_short_in_spot_mode():
    # assert exception is raised
    with pytest.raises(exceptions.InvalidStrategy):
        single_route_backtest('TestShortInSpot', is_futures_trading=False)


def test_should_raise_exception_if_trying_to_spend_more_than_available_balance_in_spot_mode():
    # assert exception is raised
    with pytest.raises(exceptions.InsufficientBalance):
        single_route_backtest('TestCannotSpendMoreThanAvailableBalance', is_futures_trading=False)


def test_should_raise_exception_if_trying_to_submit_take_profit_order_with_size_more_than_current_position_qty():
    """
    cannot submit take-profit order with the size more than the current position's qty
    """
    with pytest.raises(exceptions.InsufficientBalance):
        single_route_backtest(
            'TestCannotSubmitTakeProfitOrderWithSizeMoreThanCurrentPositionQty',
            is_futures_trading=False
        )


def test_should_raise_exception_if_trying_to_submit_stop_loss_order_with_size_more_than_current_position_qty():
    """
    cannot submit stop-loss order with the size more than the current position's qty
    """
    with pytest.raises(exceptions.InsufficientBalance):
        single_route_backtest(
            'TestCannotSubmitStopLossOrderWithSizeMoreThanCurrentPositionQty',
            is_futures_trading=False
        )


def test_should_be_able_to_submit_take_profit_order_with_size_less_or_equal_to_current_position_qty():
    """
    test that can indeed submit a take profit order with size less or equal to the current position's qty
    """
    single_route_backtest(
        'TestCanSubmitTakeProfitOrderWithSizeEqualToCurrentPositionQty',
        is_futures_trading=False
    )

    single_route_backtest(
        'TestCanSubmitTakeProfitOrderWithSizeLessThanCurrentPositionQty',
        is_futures_trading=False
    )


def test_should_be_able_to_submit_stop_loss_order_with_size_less_or_equal_to_current_position_qty():
    """
    test that can indeed submit a stop-loss order with size less or equal to the current position's qty
    """
    single_route_backtest(
        'TestCanSubmitStopLossOrderWithSizeEqualToCurrentPositionQty',
        is_futures_trading=False,
        trend='down'
    )

    single_route_backtest(
        'TestCanSubmitStopLossOrderWithSizeLessThanCurrentPositionQty',
        is_futures_trading=False,
        trend='down'
    )


def test_should_be_able_submit_take_profit_and_stop_loss_at_same_time_in_spot():
    """
    test that can indeed submit a take profit and stop-loss order at the same time
    """
    single_route_backtest(
        'TestCanSubmitTakeProfitAndStopLossAtSameTimeInSpot',
        is_futures_trading=False
    )

# tests to write:
# test if fee reduction works correctly in spot mode in both buy and sell orders
# test that both market and limit orders' balance behavior on the exchange work in spot mode
