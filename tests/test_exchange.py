import pytest

from jesse.exceptions import NegativeBalance
from .utils import single_route_backtest


def test_negative_balance_validation_for_spot_market():
    """
    The initial account balance for USDT is 10_000. So trying to spend 10_001
    should throw NegativeBalance exception
    """
    with pytest.raises(NegativeBalance):
        single_route_backtest('TestSpotNegativeBalance', is_margin_trading=False)


# def test_negative_balance_validation_for_margin_market():
#     """
#     The initial account balance for USDT is 10_000. So trying to spend 10_001
#     should throw NegativeBalance exception
#     """
#     with pytest.raises(NegativeBalance):
#         single_route_backtest('TestMarginNegativeBalance', is_margin_trading=True)
#
#     # TODO: make sure shorting still works!
#
