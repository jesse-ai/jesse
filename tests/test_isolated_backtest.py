import math

import numpy as np
import pytest

import jesse.helpers as jh
import jesse.services.selectors as selectors
from jesse import exceptions
from jesse.config import reset_config
from jesse.enums import exchanges, timeframes, order_roles, order_types
from jesse.factories import range_candles, candles_from_close_prices
from jesse.models import CompletedTrade
from jesse.models import Order
from jesse.modes import backtest_mode
from jesse.routes import router
from jesse.store import store
from jesse.strategies import Strategy
from tests.data import test_candles_0
from tests.data import test_candles_1
from .utils import set_up, single_route_backtest, two_routes_backtest


# def test_():
#     single_route_backtest('TestTakeProfitPriceIsReplacedWithMarketOrderWhenMoreConvenientLongPosition')


def test_can_pass_strategy_as_string():
    pass


def test_can_pass_strategy_as_class():
    pass


def test_warm_up_candles_more_than_passed():
    pass


def test_warm_up_candles_equals_to_passed():
    pass
