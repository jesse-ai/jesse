import arrow
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


_MINUTE = 60_000
_HOUR = 3_600_000
_DAY = 86_400_000
_MONDAY = jh.arrow_to_timestamp(arrow.get('2021-01-04T00:00:00+00:00'))
_SESSION_CONFIG = {
    'starting_balance': 10_000,
    'fee': 0,
    'type': 'futures',
    'futures_leverage': 2,
    'futures_leverage_mode': 'cross',
    'exchange': 'Fake Exchange',
    'warm_up_candles': 0,
}


def _weekday_sessions(days: int) -> np.ndarray:
    """Observed 1m rows of `days` consecutive sessions from a Monday, 14:30 to 20:59 UTC."""
    rows = candles_from_close_prices([100 + i / 100 + (i % 7) / 10 for i in range(days * 390)])
    session_minutes = np.arange(870, 1260) * _MINUTE
    rows[:, 0] = np.concatenate([_MONDAY + day * _DAY + session_minutes for day in range(days)])
    return rows


def _aggregate(rows: np.ndarray, bucket_start: int) -> list:
    return [bucket_start, rows[0, 1], rows[-1, 2], rows[:, 3].max(), rows[:, 4].min(), rows[:, 5].sum()]


def _record_decisions(timeframe: str, candles: np.ndarray, fast_mode: bool, warmup: np.ndarray = None) -> list:
    decisions = []

    class TestStrategy(Strategy):
        def before(self):
            decisions.append((int(self.time), np.copy(self.candles)))

        def should_long(self):
            return False

        def go_long(self):
            pass

        def should_cancel_entry(self):
            return False

    def as_candles(rows):
        return {jh.key('Fake Exchange', 'FAKE-USD'): {'exchange': 'Fake Exchange', 'symbol': 'FAKE-USD', 'candles': rows}}

    research.backtest(
        _SESSION_CONFIG,
        [{'exchange': 'Fake Exchange', 'strategy': TestStrategy, 'symbol': 'FAKE-USD', 'timeframe': timeframe}],
        [],
        as_candles(candles),
        warmup_candles=as_candles(warmup) if warmup is not None else None,
        fast_mode=fast_mode,
    )
    return decisions


@pytest.mark.parametrize('fast_mode', [False, True], ids=['step', 'fast'])
@pytest.mark.parametrize('timeframe', ['1D', '4h'])
def test_a_candle_that_closes_while_the_market_is_closed_runs_the_strategy_when_trading_resumes(
        fast_mode: bool, timeframe: str,
):
    rows = _weekday_sessions(3)
    decisions = _record_decisions(timeframe, rows, fast_mode)

    session_opens = [_MONDAY + day * _DAY + 870 * _MINUTE for day in range(3)]
    resumes = [session_opens[1] + _MINUTE, session_opens[2] + _MINUTE]
    if timeframe == '1D':
        # each day's candle closes at midnight, while the market is closed
        assert [time for time, _ in decisions] == resumes
    else:
        # the 20:00 candle closes at midnight too; the 12:00 and 16:00 ones close in the session
        assert [time for time, _ in decisions] == [
            _MONDAY + 16 * _HOUR, _MONDAY + 20 * _HOUR,
            resumes[0], _MONDAY + _DAY + 16 * _HOUR, _MONDAY + _DAY + 20 * _HOUR,
            resumes[1], _MONDAY + 2 * _DAY + 16 * _HOUR, _MONDAY + 2 * _DAY + 20 * _HOUR,
        ]

    timeframe_ms = jh.timeframe_to_one_minutes(timeframe) * _MINUTE
    for time, candles in decisions:
        if time not in resumes:
            continue
        # the candle that closed overnight, complete, then the new one forming from the first row
        resume_row = rows[rows[:, 0] == time - _MINUTE][0]
        closed_start = int(candles[-2][0])
        closed_rows = rows[(rows[:, 0] >= closed_start) & (rows[:, 0] < closed_start + timeframe_ms)]
        assert closed_start + timeframe_ms <= time - _MINUTE
        assert candles[-2].tolist() == _aggregate(closed_rows, closed_start)
        assert candles[-1].tolist() == _aggregate(resume_row[None, :], int(resume_row[0]) - int(resume_row[0]) % timeframe_ms)


@pytest.mark.parametrize('fast_mode', [False, True], ids=['step', 'fast'])
@pytest.mark.parametrize('timeframe', ['1D', '4h'])
def test_a_backtest_starting_after_a_closure_runs_the_candle_that_closed_during_it(
        fast_mode: bool, timeframe: str,
):
    rows = _weekday_sessions(3)
    start = _MONDAY + _DAY
    continuous = _record_decisions(timeframe, rows, fast_mode)
    started_later = _record_decisions(timeframe, rows[rows[:, 0] >= start], fast_mode, warmup=rows[rows[:, 0] < start])

    # Monday's last candle closed overnight: the run from Tuesday makes the decision on it
    # that the continuous run makes, at the same time and on the same candles
    expected = [(time, candles) for time, candles in continuous if time > start]
    assert started_later[0][0] == start + 870 * _MINUTE + _MINUTE
    assert [time for time, _ in started_later] == [time for time, _ in expected]
    for (_, candles), (_, continuous_candles) in zip(started_later, expected):
        np.testing.assert_array_equal(candles, continuous_candles)


@pytest.mark.parametrize('fast_mode', [False, True], ids=['step', 'fast'])
def test_a_candle_whose_last_minute_is_missing_runs_the_strategy_on_the_next_row(fast_mode: bool):
    rows = candles_from_close_prices([100 + i / 100 for i in range(9 * 60)])
    rows[:, 0] = _MONDAY + np.arange(len(rows)) * _MINUTE
    # 03:59 is missing, so nothing observes the 00:00 candle's close until the 04:00 row
    rows = np.delete(rows, 239, axis=0)
    decisions = _record_decisions('4h', rows, fast_mode)

    assert [time for time, _ in decisions] == [_MONDAY + 4 * _HOUR + _MINUTE, _MONDAY + 8 * _HOUR]
    candles = decisions[0][1]
    assert candles[-2].tolist() == _aggregate(rows[:239], _MONDAY)
    assert candles[-1].tolist() == _aggregate(rows[239:240], _MONDAY + 4 * _HOUR)


def test_the_replay_releases_a_candle_whose_close_the_warmup_did_not_observe():
    from jesse.modes.backtest_mode import _timestamp_bucket_generation_schedule

    rows = _weekday_sessions(1)[:3]
    friday = _MONDAY - 3 * _DAY
    one_day = [('1D', 1440)]
    # the warmup ended with Friday's session: Monday's first row releases Friday's candle
    assert _timestamp_bucket_generation_schedule(rows, one_day, friday + 1259 * _MINUTE) == {0: [('1D', friday)]}
    # a warmup whose last row is its day's last minute released that day itself
    assert _timestamp_bucket_generation_schedule(rows, one_day, friday + 1439 * _MINUTE) == {}
    # a candle the rows continue is theirs to release (these end before Monday closes)
    assert _timestamp_bucket_generation_schedule(rows, one_day, _MONDAY + 869 * _MINUTE) == {}
    assert _timestamp_bucket_generation_schedule(rows, one_day) == {}


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
