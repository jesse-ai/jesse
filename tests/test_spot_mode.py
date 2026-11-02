from jesse.testing_utils import single_route_backtest
import pytest
from jesse import exceptions
from jesse.services import metrics
from jesse.store import store


def test_should_be_able_to_short_in_spot_mode():
    with pytest.raises(exceptions.InvalidStrategy):
        single_route_backtest('TestShortInSpot', is_futures_trading=False)


def test_should_raise_exception_if_trying_to_spend_more_than_available_balance_in_spot_mode():
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
    single_route_backtest(
        'TestCanSubmitTakeProfitAndStopLossAtSameTimeInSpot',
        is_futures_trading=False
    )


def test_stop_order_should_consider_executed_take_profit_orders_in_spot():
    """
    test that stop-loss order considers executed take-profit orders (when
    the take-profit order is submitted via multiple orders.
    """
    single_route_backtest(
        'TestStopOrderShouldConsiderExecutedTakeProfitOrdersInSpot',
        is_futures_trading=False
    )


def test_balances_are_handled_correctly_for_cancelling_orders_in_spot():
    single_route_backtest(
        'TestBalancesAreHandledCorrectlyForCancellingOrdersInSpot',
        is_futures_trading=False
    )


@pytest.mark.parametrize('trend', ['up', 'down'])
def test_sell_order_sums_follow_resting_orders_in_spot(trend):
    single_route_backtest(
        'TestSpotSellOrderSumsFollowRestingOrders',
        is_futures_trading=False,
        trend=trend
    )


@pytest.mark.parametrize('strategy_name', [
    'TestCannotOversellByReplacingTakeProfitInSpot',
    'TestCannotOversellByReplacingStopLossInSpot',
])
def test_replacing_exit_orders_cannot_oversell_in_spot(strategy_name):
    with pytest.raises(exceptions.InsufficientBalance):
        single_route_backtest(strategy_name, is_futures_trading=False)


def test_split_exits_within_a_rounding_error_of_the_balance_are_not_an_oversell():
    single_route_backtest(
        'TestSplitExitsWithinRoundingErrorOfBalanceInSpot',
        is_futures_trading=False,
        fee=0.001
    )


@pytest.mark.parametrize('is_futures_trading', [False, True], ids=['spot', 'futures'])
def test_liquidate_at_a_loss_cancels_resting_take_profit(is_futures_trading):
    single_route_backtest(
        'TestLiquidateAtALossCancelsRestingTakeProfit',
        is_futures_trading=is_futures_trading,
        trend='down'
    )


@pytest.mark.parametrize('is_futures_trading', [False, True], ids=['spot', 'futures'])
def test_liquidate_at_a_profit_cancels_resting_stop_loss(is_futures_trading):
    single_route_backtest(
        'TestLiquidateAtAProfitCancelsRestingStopLoss',
        is_futures_trading=is_futures_trading
    )


def test_position_open_increase_reduce_close_events_in_spot():
    single_route_backtest(
        'TestPositionOpenIncreaseReduceCloseEventsInSpot',
        is_futures_trading=False,
        fee=0.001
    ) 


def test_balance_and_fee_reduction_works_correctly_in_spot_mode_in_both_buy_and_sell_orders():
    single_route_backtest(
        'TestBalanceAndFeeReductionWorksCorrectlyInSpotModeInBothBuyAndSellOrders',
        is_futures_trading=False,
        fee=0.001
    )


@pytest.mark.parametrize('is_futures_trading', [False, True], ids=['spot', 'futures'])
@pytest.mark.parametrize('trend', ['up', 'down'])
def test_net_profit_agrees_with_finishing_balance(trend, is_futures_trading):
    single_route_backtest(
        'TestTradePnlMatchesWalletChange',
        is_futures_trading=is_futures_trading,
        trend=trend,
        fee=0.001
    )

    stats = metrics.trades(store.closed_trades.trades, store.app.daily_balance)

    assert stats['total'] == 3
    assert stats['total_open_trades'] == 1
    assert stats['fee'] > 0
    assert (stats['net_profit'] > 0) == (trend == 'up')
    assert round(stats['finishing_balance'] - stats['starting_balance'], 8) == round(stats['net_profit'], 8)


def test_cannot_set_stop_loss_order_in_go_long():
    with pytest.raises(exceptions.InvalidStrategy):
        single_route_backtest(
            'TestCannotSetStopLossOrderInGoLong',
            is_futures_trading=False
        )


def test_cannot_set_take_profit_order_in_go_long():
    with pytest.raises(exceptions.InvalidStrategy):
        single_route_backtest(
            'TestCannotSetTakeProfitOrderInGoLong',
            is_futures_trading=False
        )
