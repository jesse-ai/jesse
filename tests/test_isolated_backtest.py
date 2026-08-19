import pytest
import numpy as np
import jesse.helpers as jh
from jesse.factories import candles_from_close_prices
from jesse.strategies import Strategy
from jesse import research


def test_can_pass_strategy_as_string_in_futures_exchange():
    fake_candles = candles_from_close_prices([101, 102, 103, 104, 105, 106, 107, 108, 109, 110])
    exchange_name = 'Fake Exchange'
    symbol = 'FAKE-USDT'
    timeframe = '1m'
    config = {
        'starting_balance': 10_000,
        'fee': 0,
        'type': 'futures',
        'futures_leverage': 2,
        'futures_leverage_mode': 'cross',
        'exchange': exchange_name,
        'warm_up_candles': 0
    }
    routes = [
        {'exchange': exchange_name, 'strategy': 'TestEmptyStrategy', 'symbol': symbol, 'timeframe': timeframe},
    ]
    data_routes = []
    candles = {
        jh.key(exchange_name, symbol): {
            'exchange': exchange_name,
            'symbol': symbol,
            'candles': fake_candles,
        },
    }

    result = research.backtest(config, routes, data_routes, candles)

    # result must have None values because the strategy makes no decisions
    assert result['metrics'] == {'net_profit_percentage': 0, 'total': 0, 'win_rate': 0}


def test_can_pass_strategy_as_class_in_a_futures_exchange():
    class TestStrategy(Strategy):
        def before(self) -> None:
            if self.index == 0:
                assert self.exchange_type == 'futures'

        def should_long(self):
            return False

        def should_cancel_entry(self):
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
        'type': 'futures',
        'futures_leverage': 2,
        'futures_leverage_mode': 'cross',
        'exchange': exchange_name,
        'warm_up_candles': 0
    }
    routes = [
        {'exchange': exchange_name, 'strategy': TestStrategy, 'symbol': symbol, 'timeframe': timeframe},
    ]
    data_routes = []
    candles = {
        jh.key(exchange_name, symbol): {
            'exchange': exchange_name,
            'symbol': symbol,
            'candles': fake_candles,
        },
    }

    result = research.backtest(config, routes, data_routes, candles)

    # result must have None values because the strategy makes no decisions
    assert result['metrics'] == {'net_profit_percentage': 0, 'total': 0, 'win_rate': 0}


def test_can_pass_strategy_as_class_in_a_spot_exchange():
    class TestStrategy(Strategy):
        def before(self) -> None:
            if self.index == 0:
                assert self.exchange_type == 'spot'

        def should_long(self):
            return False

        def should_cancel_entry(self):
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
        'type': 'spot',
        'exchange': exchange_name,
        'warm_up_candles': 0
    }
    routes = [
        {'exchange': exchange_name, 'strategy': TestStrategy, 'symbol': symbol, 'timeframe': timeframe},
    ]
    data_routes = []
    candles = {
        jh.key(exchange_name, symbol): {
            'exchange': exchange_name,
            'symbol': symbol,
            'candles': fake_candles,
        },
    }

    result = research.backtest(config, routes, data_routes, candles)

    # result must have None values because the strategy makes no decisions
    assert result['metrics'] == {'net_profit_percentage': 0, 'total': 0, 'win_rate': 0}


def test_store_state_app_is_reset_properly_in_isolated_backtest():
    class TestStateApp(Strategy):
        def before(self) -> None:
            if self.index == 0:
                from jesse.store import store
                assert store.app.daily_balance == [10000]

        def should_long(self) -> bool:
            return False

        def should_cancel_entry(self) -> bool:
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
        'type': 'futures',
        'futures_leverage': 2,
        'futures_leverage_mode': 'cross',
        'exchange': exchange_name,
        'warm_up_candles': 0
    }
    routes = [
        {'exchange': exchange_name, 'strategy': TestStateApp, 'symbol': symbol, 'timeframe': timeframe},
    ]
    data_routes = []
    candles = {
        jh.key(exchange_name, symbol): {
            'exchange': exchange_name,
            'symbol': symbol,
            'candles': fake_candles,
        },
    }

    # run the backtest for the first time
    research.backtest(config, routes, data_routes, candles)
    # run the backtest for the second time and assert that the app.daily_balance is reset
    research.backtest(config, routes, data_routes, candles)


def test_dna_method_works_in_isolated_backtest():
    # first define the strategy without the dna method, hence the hyperparameter defaults
    class TestStrategy1(Strategy):
        def before(self) -> None:
            if self.index == 0:
                assert self.hp['hp1'] == 70
                assert self.hp['hp2'] == 100

        def should_long(self) -> bool:
            return False

        def should_cancel_entry(self) -> bool:
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
        'type': 'futures',
        'futures_leverage': 2,
        'futures_leverage_mode': 'cross',
        'exchange': exchange_name,
        'warm_up_candles': 0
    }
    routes = [
        {'exchange': exchange_name, 'strategy': TestStrategy1, 'symbol': symbol, 'timeframe': timeframe},
    ]
    data_routes = []
    candles = {
        jh.key(exchange_name, symbol): {
            'exchange': exchange_name,
            'symbol': symbol,
            'candles': fake_candles,
        },
    }

    research.backtest(config, routes, data_routes, candles)

    # now define the strategy with the dna method
    class TestStrategy2(Strategy):
        def before(self) -> None:
            if self.index == 0:
                assert self.hp['hp1'] == 10
                assert self.hp['hp2'] == 880

        def should_long(self) -> bool:
            return False

        def should_cancel_entry(self) -> bool:
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

    research.backtest(config, routes, data_routes, candles)


@pytest.mark.parametrize('fast_mode', [False, True], ids=['step', 'fast'])
def test_backtest_rejects_missing_internal_one_minute_candles(fast_mode: bool):
    class TestStrategy(Strategy):
        def before(self):
            # Reaching a lifecycle hook would mean validation happened too late,
            # after the simulator had already started mutating shared state.
            raise AssertionError('strategy must not execute with missing input candles')

        def should_long(self):
            return False

        def should_cancel_entry(self):
            return False

        def go_long(self):
            pass

    candles = candles_from_close_prices([101, 102, 103, 104, 105, 106, 107, 108, 109, 110])
    # Keep the first intervals valid and remove an internal row to prove that
    # validation covers the complete source timeline rather than one boundary.
    candles = np.delete(candles, 5, axis=0)
    previous_timestamp = int(candles[4][0])
    expected_timestamp = previous_timestamp + 60_000
    actual_timestamp = int(candles[5][0])

    exchange_name = 'Fake Exchange'
    symbol = 'FAKE-USDT'
    timeframe = '1m'
    config = {
        'starting_balance': 10_000,
        'fee': 0,
        'type': 'futures',
        'futures_leverage': 2,
        'futures_leverage_mode': 'cross',
        'exchange': exchange_name,
        'warm_up_candles': 0
    }
    routes = [
        {'exchange': exchange_name, 'strategy': TestStrategy, 'symbol': symbol, 'timeframe': timeframe},
    ]
    data_routes = []
    candles = {
        jh.key(exchange_name, symbol): {
            'exchange': exchange_name,
            'symbol': symbol,
            'candles': candles,
        },
    }

    expected_message = (
        f'Missing 1 one-minute candle for {symbol} on {exchange_name}. '
        f'Expected timestamp {expected_timestamp} after {previous_timestamp}, '
        f'but got {actual_timestamp}.'
    )
    with pytest.raises(ValueError) as exc_info:
        research.backtest(config, routes, data_routes, candles, fast_mode=fast_mode)

    assert str(exc_info.value) == expected_message


def test_passed_candles_are_not_affected_by_running_isolated_backtests():
    class TestStrategy(Strategy):
        def should_long(self):
            return False

        def should_cancel_entry(self):
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
        'type': 'futures',
        'futures_leverage': 2,
        'futures_leverage_mode': 'cross',
        'exchange': exchange_name,
        'warm_up_candles': 4
    }
    routes = [
        {'exchange': exchange_name, 'strategy': TestStrategy, 'symbol': symbol, 'timeframe': timeframe},
    ]
    data_routes = []
    candles = {
        jh.key(exchange_name, symbol): {
            'exchange': exchange_name,
            'symbol': symbol,
            'candles': fake_candles,
        },
    }

    assert len(candles['Fake Exchange-FAKE-USDT']['candles']) == 10

    research.backtest(config, routes, data_routes, candles)

    assert len(candles['Fake Exchange-FAKE-USDT']['candles']) == 10
