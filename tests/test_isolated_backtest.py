import pytest
import jesse.helpers as jh
from jesse.factories import candles_from_close_prices
from jesse.strategies import Strategy
from jesse import research


def test_can_pass_strategy_as_string():
    fake_candles = candles_from_close_prices([101, 102, 103, 104, 105, 106, 107, 108, 109, 110])
    exchange_name = 'Fake Exchange'
    symbol = 'FAKE-USDT'
    timeframe = '1m'
    config = {
        'starting_balance': 10_000,
        'fee': 0,
        'futures_leverage': 2,
        'futures_leverage_mode': 'cross',
        'exchange': exchange_name,
        'settlement_currency': 'USDT',
        'warm_up_candles': 0
    }
    routes = [
        {'exchange': exchange_name, 'strategy': 'TestEmptyStrategy', 'symbol': symbol, 'timeframe': timeframe},
    ]
    extra_routes = []
    candles = {
        jh.key(exchange_name, symbol): {
            'exchange': exchange_name,
            'symbol': symbol,
            'candles': fake_candles,
        },
    }

    result = research.backtest(config, routes, extra_routes, candles)

    # result must have None values because the strategy makes no decisions
    assert result['metrics'] is None
    assert result['charts'] is None
    assert result['logs'] is None


def test_can_pass_strategy_as_class():
    class TestStrategy(Strategy):
        def should_long(self):
            return False

        def should_short(self):
            return False

        def should_cancel(self):
            return False

        def go_long(self):
            pass

        def go_short(self):
            pass

    fake_candles = candles_from_close_prices([101, 102, 103, 104, 105, 106, 107, 108, 109, 110])
    exchange_name = 'Fake Exchange'
    symbol = 'FAKE-USDT'
    timeframe = '1m'
    config = {
        'starting_balance': 10_000,
        'fee': 0,
        'futures_leverage': 2,
        'futures_leverage_mode': 'cross',
        'exchange': exchange_name,
        'settlement_currency': 'USDT',
        'warm_up_candles': 0
    }
    routes = [
        {'exchange': exchange_name, 'strategy': TestStrategy, 'symbol': symbol, 'timeframe': timeframe},
    ]
    extra_routes = []
    candles = {
        jh.key(exchange_name, symbol): {
            'exchange': exchange_name,
            'symbol': symbol,
            'candles': fake_candles,
        },
    }

    result = research.backtest(config, routes, extra_routes, candles)

    # result must have None values because the strategy makes no decisions
    assert result['metrics'] is None
    assert result['charts'] is None
    assert result['logs'] is None


def test_warm_up_candles_more_than_warmup_candles_config_raises_error():
    class TestStrategy(Strategy):
        def should_long(self):
            return False

        def should_short(self):
            return False

        def should_cancel(self):
            return False

        def go_long(self):
            pass

        def go_short(self):
            pass

    fake_candles = candles_from_close_prices([101, 102, 103, 104, 105, 106, 107, 108, 109, 110])
    exchange_name = 'Fake Exchange'
    symbol = 'FAKE-USDT'
    timeframe = '1m'
    config = {
        'starting_balance': 10_000,
        'fee': 0,
        'futures_leverage': 2,
        'futures_leverage_mode': 'cross',
        'exchange': exchange_name,
        'settlement_currency': 'USDT',
        'warm_up_candles': 100
    }
    routes = [
        {'exchange': exchange_name, 'strategy': TestStrategy, 'symbol': symbol, 'timeframe': timeframe},
    ]
    extra_routes = []
    candles = {
        jh.key(exchange_name, symbol): {
            'exchange': exchange_name,
            'symbol': symbol,
            'candles': fake_candles,
        },
    }

    # assert that it raises IndexError when warm_up_candles==100 and candles.length==10
    with pytest.raises(IndexError):
        research.backtest(config, routes, extra_routes, candles)
