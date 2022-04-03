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
    assert result['metrics'] == {'net_profit_percentage': 0, 'total': 0, 'win_rate': 0}
    assert result['charts'] is None
    assert result['logs'] is None


def test_can_pass_strategy_as_class():
    class TestStrategy(Strategy):
        def should_long(self):
            return False

        def should_cancel(self):
            return False

        def go_long(self):
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
    assert result['metrics'] == {'net_profit_percentage': 0, 'total': 0, 'win_rate': 0}
    assert result['charts'] is None
    assert result['logs'] is None


def test_warm_up_candles_more_than_warmup_candles_config_raises_error():
    class TestStrategy(Strategy):
        def should_long(self):
            return False

        def should_cancel(self):
            return False

        def go_long(self):
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


def test_store_state_app_is_reset_properly():
    class TestStateApp(Strategy):
        def before(self) -> None:
            if self.index == 0:
                from jesse.store import store
                assert store.app.daily_balance == [10000]

        def should_long(self) -> bool:
            return False

        def should_cancel(self) -> bool:
            return True

        def go_long(self):
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
        {'exchange': exchange_name, 'strategy': TestStateApp, 'symbol': symbol, 'timeframe': timeframe},
    ]
    extra_routes = []
    candles = {
        jh.key(exchange_name, symbol): {
            'exchange': exchange_name,
            'symbol': symbol,
            'candles': fake_candles,
        },
    }

    # run the backtest for the first time
    research.backtest(config, routes, extra_routes, candles)
    # run the backtest for the second time and assert that the app.daily_balance is reset
    research.backtest(config, routes, extra_routes, candles)


def test_dna_method_works_in_isolated_backtest():
    # first define the strategy without the dna method, hence the hyperparameter defaults
    class TestStrategy1(Strategy):
        def before(self) -> None:
            if self.index == 0:
                assert self.hp['hp1'] == 70
                assert self.hp['hp2'] == 100

        def should_long(self) -> bool:
            return False

        def should_cancel(self) -> bool:
            return True

        def go_long(self):
            pass

        def hyperparameters(self):
            return [
                {'name': 'hp1', 'type': int, 'min': 10, 'max': 95, 'default': 70},
                {'name': 'hp2', 'type': int, 'min': 50, 'max': 1000, 'default': 100},
            ]

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
        {'exchange': exchange_name, 'strategy': TestStrategy1, 'symbol': symbol, 'timeframe': timeframe},
    ]
    extra_routes = []
    candles = {
        jh.key(exchange_name, symbol): {
            'exchange': exchange_name,
            'symbol': symbol,
            'candles': fake_candles,
        },
    }

    research.backtest(config, routes, extra_routes, candles)

    # now define the strategy with the dna method
    class TestStrategy2(Strategy):
        def before(self) -> None:
            if self.index == 0:
                assert self.hp['hp1'] == 10
                assert self.hp['hp2'] == 880

        def should_long(self) -> bool:
            return False

        def should_cancel(self) -> bool:
            return True

        def go_long(self):
            pass

        def hyperparameters(self):
            return [
                {'name': 'hp1', 'type': int, 'min': 10, 'max': 95, 'default': 70},
                {'name': 'hp2', 'type': int, 'min': 50, 'max': 1000, 'default': 100},
            ]

        def dna(self):
            return "(m"

    # redefine routes to use the new strategy
    routes = [
        {'exchange': exchange_name, 'strategy': TestStrategy2, 'symbol': symbol, 'timeframe': timeframe},
    ]

    research.backtest(config, routes, extra_routes, candles)
