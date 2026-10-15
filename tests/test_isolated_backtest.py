import pytest
import numpy as np
import jesse.helpers as jh
from jesse.factories import candles_from_close_prices
from jesse.strategies import Strategy
from jesse import research


class _IsolationTradeStrategy(Strategy):
    def should_long(self) -> bool:
        return self.index == 0

    def go_long(self) -> None:
        self.buy = 1, self.price

    def should_cancel_entry(self) -> bool:
        return False

    def on_open_position(self, order) -> None:
        self.take_profit = self.position.qty, self.price + 2


class _IsolationFailureStrategy(Strategy):
    def before(self) -> None:
        raise RuntimeError('intentional strategy failure')

    def should_long(self) -> bool:
        return False

    def go_long(self) -> None:
        pass

    def should_cancel_entry(self) -> bool:
        return False


def _isolation_inputs(exchange: str, exchange_type: str, strategy: type[Strategy]) -> tuple[dict, list, dict]:
    symbol = 'TEST-USDT'
    config = {
        'starting_balance': 10_000,
        'fee': 0.001,
        'type': exchange_type,
        'exchange': exchange,
        'warm_up_candles': 0,
    }
    if exchange_type == 'futures':
        config.update({
            'futures_leverage': 2,
            'futures_leverage_mode': 'cross',
        })

    routes = [{
        'exchange': exchange,
        'strategy': strategy,
        'symbol': symbol,
        'timeframe': '1m',
    }]
    candles = {
        jh.key(exchange, symbol): {
            'exchange': exchange,
            'symbol': symbol,
            'candles': candles_from_close_prices(range(10, 31)),
        },
    }
    return config, routes, candles


def _isolation_fingerprint(exchange: str, exchange_type: str) -> dict:
    config, routes, candles = _isolation_inputs(exchange, exchange_type, _IsolationTradeStrategy)
    result = research.backtest(config, routes, [], candles)
    trade = result['trades'][0]
    metrics = result['metrics']

    def normalized(value):
        return round(value, 8) if isinstance(value, float) else value

    return {
        'metrics': {
            key: normalized(metrics[key])
            for key in ('total', 'finishing_balance', 'net_profit', 'fee')
        },
        'trade': {
            key: normalized(trade[key])
            for key in ('type', 'entry_price', 'exit_price', 'qty', 'fee', 'PNL', 'opened_at', 'closed_at')
        },
    }


def _assert_isolated_runtime_is_clean() -> None:
    from jesse.config import config
    from jesse.routes import router
    from jesse.services.api import api
    from jesse.store import store

    assert config['app']['trading_mode'] == ''
    assert router.routes == []
    assert router.data_routes == []
    assert api.drivers == {}
    assert store.vars == {}
    assert store.exchanges.storage == {}
    assert store.orders.storage == {}
    assert jh.is_live() is False
    assert jh.is_optimizing() is False


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
    assert result['metrics'] == {'net_profit_percentage': 0, 'total': 0, 'win_rate': 0, 'annualization': 365}


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
    assert result['metrics'] == {'net_profit_percentage': 0, 'total': 0, 'win_rate': 0, 'annualization': 365}


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
    assert result['metrics'] == {'net_profit_percentage': 0, 'total': 0, 'win_rate': 0, 'annualization': 365}


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
def test_backtest_replays_observed_internal_gaps(fast_mode: bool):
    observed_times = []

    class TestStrategy(Strategy):
        def before(self):
            observed_times.append(self.time)

        def should_long(self):
            return False

        def should_cancel_entry(self):
            return False

        def go_long(self):
            pass

    candles = candles_from_close_prices([101, 102, 103, 104, 105, 106, 107, 108, 109, 110])
    # Remove an internal row to prove research uses provider-observed events
    # without manufacturing a callback for the absent minute.
    candles = np.delete(candles, 5, axis=0)
    expected_times = (candles[:, 0] + 60_000).tolist()

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

    research.backtest(config, routes, data_routes, candles, fast_mode=fast_mode)

    assert observed_times == expected_times


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


def test_representative_backtests_are_independent_of_run_order():
    # Process-wide drivers and configuration must not make a research result
    # depend on which exchange ran immediately before it.
    futures_first = _isolation_fingerprint('Isolation Futures', 'futures')
    spot_second = _isolation_fingerprint('Isolation Spot', 'spot')

    spot_first = _isolation_fingerprint('Isolation Spot', 'spot')
    futures_second = _isolation_fingerprint('Isolation Futures', 'futures')

    assert futures_first['metrics']['total'] == 1
    assert spot_first['metrics']['total'] == 1
    assert futures_first == futures_second
    assert spot_first == spot_second


def test_research_backtest_cleans_runtime_state_after_success():
    from jesse.config import config
    from jesse.store import store

    # Prime mode caches and shared strategy variables with values that cannot
    # belong to the research session.
    config['app']['trading_mode'] = 'papertrade'
    store.vars['outside-session'] = True
    assert jh.is_live() is True

    _isolation_fingerprint('Cleanup Exchange', 'futures')

    _assert_isolated_runtime_is_clean()


def test_research_backtest_cleans_runtime_state_after_strategy_failure():
    config, routes, candles = _isolation_inputs(
        'Failing Exchange',
        'futures',
        _IsolationFailureStrategy,
    )

    with pytest.raises(RuntimeError, match='intentional strategy failure'):
        research.backtest(config, routes, [], candles)

    _assert_isolated_runtime_is_clean()
