from jesse.testing_utils import single_route_backtest
import pytest
from jesse import exceptions


def test_should_be_able_to_short_in_spot_mode():
    # assert exception is raised
    with pytest.raises(exceptions.InvalidStrategy):
        single_route_backtest('TestShortInSpot', is_futures_trading=False)


# def test_can_run_a_simple_backtest_in_spot_mode():
#     single_route_backtest('TestSpotMode101', is_futures_trading=False)
