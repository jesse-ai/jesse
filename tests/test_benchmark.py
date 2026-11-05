import importlib
import json
from types import SimpleNamespace

import numpy as np
import pytest

import jesse.helpers as jh
from jesse import exceptions
from jesse.enums import exchanges
from jesse.modes import backtest_mode
from jesse.routes import router
from jesse.services import backtest_report, benchmark, charts
from jesse.services import metrics as stats
from jesse.store import store
from jesse.testing_utils import get_btc_and_eth_candles, get_btc_candles, get_downtrend_candles, set_up

# jesse.models re-exports the model class under the module's name, so load the
# module itself to reach its DB helper functions.
backtest_session_model = importlib.import_module('jesse.models.BacktestSession')

DAY_MS = 86_400_000
START = 1_546_300_800_000  # 2019-01-01


def _daily_candles(closes: list, start: int = START, timestamps: list = None) -> np.ndarray:
    """Rows shaped like the database's: timestamp, open, close, high, low, volume."""
    times = timestamps or [start + i * DAY_MS for i in range(len(closes))]
    return np.array([[t, c, c, c, c, 1.0] for t, c in zip(times, closes)], dtype=float)


def _use_candles(monkeypatch, candles_by_symbol: dict) -> None:
    """Serve daily candles by symbol. A symbol that isn't listed has no candles in the database."""
    def fake_get_candles_from_db(exchange, symbol, timeframe, *args, **kwargs):
        if symbol not in candles_by_symbol:
            raise exceptions.CandleNotFoundInDatabase(f'No candles for {symbol}')
        return None, candles_by_symbol[symbol]

    monkeypatch.setattr(benchmark, 'get_candles_from_db', fake_get_candles_from_db)


def _use_routes(monkeypatch, *symbols: str) -> None:
    routes = [SimpleNamespace(exchange=exchanges.SANDBOX, symbol=symbol) for symbol in symbols]
    monkeypatch.setattr(router, 'routes', routes)
    monkeypatch.setattr(store.app, 'starting_time', START, raising=False)
    monkeypatch.setattr(store.app, 'ending_time', START + 10 * DAY_MS, raising=False)


def _curve(name: str, balances: list, start: int = START) -> dict:
    return {
        'name': name,
        'color': '#000000',
        'data': [{'time': (start + i * DAY_MS) / 1000, 'value': value, 'color': '#000000'} for i, value in enumerate(balances)],
    }


def test_a_single_route_has_no_combined_series(monkeypatch):
    _use_routes(monkeypatch, 'BTC-USDT')
    _use_candles(monkeypatch, {'BTC-USDT': _daily_candles([100, 110, 99])})

    series = benchmark.get_series(1000)

    assert [s['name'] for s in series] == ['BTC-USDT']
    # bought at the first close, so the first day is flat
    assert series[0]['balance'].tolist() == pytest.approx([1000, 1100, 990])


def test_a_market_that_closes_before_midnight_keeps_its_last_day(monkeypatch):
    # regression: its last day was dropped as incomplete, cutting the final close from the benchmark
    hour_ms = 3_600_000
    closes_at = [START + day * DAY_MS + 21 * hour_ms for day in range(3)]
    _use_routes(monkeypatch, 'CL-USD')
    monkeypatch.setattr(store.app, 'ending_time', float(closes_at[-1] + 120_000))
    _use_candles(monkeypatch, {'CL-USD': _daily_candles([100, 110, 120], timestamps=closes_at)})

    series = benchmark.get_series(1000)

    assert series[0]['timestamps'].tolist() == [START, START + DAY_MS, START + 2 * DAY_MS]
    assert series[0]['balance'].tolist() == pytest.approx([1000, 1100, 1200])


def test_a_24_hour_market_ends_on_its_last_full_day(monkeypatch):
    last_minute = START + 3 * DAY_MS - 60_000
    finishes = []
    candles = _daily_candles([100, 110, 120, 130], timestamps=[START, START + DAY_MS, START + 2 * DAY_MS, last_minute])

    def fake_get_candles_from_db(exchange, symbol, timeframe, start, finish, **kwargs):
        finishes.append((timeframe, finish))
        return None, candles

    _use_routes(monkeypatch, 'BTC-USDT')
    monkeypatch.setattr(store.app, 'ending_time', float(last_minute + 120_000))
    monkeypatch.setattr(benchmark, 'get_candles_from_db', fake_get_candles_from_db)

    series = benchmark.get_series(1000)

    assert finishes == [('1m', START + 3 * DAY_MS)]
    assert len(series[0]['timestamps']) == 3


def test_several_routes_end_with_the_portfolio_holding_them_equally(monkeypatch):
    _use_routes(monkeypatch, 'BTC-USDT', 'ETH-USDT')
    _use_candles(monkeypatch, {
        'BTC-USDT': _daily_candles([100, 200, 100]),
        'ETH-USDT': _daily_candles([10, 10, 20]),
    })

    series = benchmark.get_series(1000)

    assert [s['name'] for s in series] == ['BTC-USDT', 'ETH-USDT', benchmark.BUY_AND_HOLD_NAME]
    # 500 in each and never rebalanced: (1000 + 500), then (500 + 1000)
    assert series[-1]['balance'].tolist() == pytest.approx([1000, 1500, 1500])


def test_a_symbol_with_no_candle_on_a_day_keeps_its_last_value(monkeypatch):
    _use_routes(monkeypatch, 'BTC-USDT', 'AAPL-USD')
    _use_candles(monkeypatch, {
        'BTC-USDT': _daily_candles([100, 100, 100]),
        # no candle on the middle day, like a market holiday
        'AAPL-USD': _daily_candles([10, 20], timestamps=[START, START + 2 * DAY_MS]),
    })

    series = benchmark.get_series(1000)

    assert series[-1]['balance'].tolist() == pytest.approx([1000, 1000, 1500])


def test_a_symbol_that_starts_later_stays_in_cash_until_then(monkeypatch):
    _use_routes(monkeypatch, 'BTC-USDT', 'NEW-USDT')
    _use_candles(monkeypatch, {
        'BTC-USDT': _daily_candles([100, 200, 200]),
        'NEW-USDT': _daily_candles([5, 10], start=START + DAY_MS),
    })

    series = benchmark.get_series(1000)

    assert series[-1]['balance'].tolist() == pytest.approx([1000, 1500, 2000])


def test_a_symbol_without_candles_is_left_out_of_the_benchmark(monkeypatch):
    _use_routes(monkeypatch, 'BTC-USDT', 'ETH-USDT', 'MISSING-USDT')
    _use_candles(monkeypatch, {
        'BTC-USDT': _daily_candles([100, 200]),
        'ETH-USDT': _daily_candles([10, 20]),
    })

    assert [s['name'] for s in benchmark.get_series(1000)] == ['BTC-USDT', 'ETH-USDT', benchmark.BUY_AND_HOLD_NAME]


def test_empty_candles_are_left_out_of_the_benchmark(monkeypatch):
    _use_routes(monkeypatch, 'BTC-USDT')
    _use_candles(monkeypatch, {'BTC-USDT': np.zeros((0, 6))})

    assert benchmark.get_series(1000) == []


def test_the_only_symbol_left_needs_no_portfolio(monkeypatch):
    _use_routes(monkeypatch, 'BTC-USDT', 'MISSING-USDT')
    _use_candles(monkeypatch, {'BTC-USDT': _daily_candles([100, 200])})

    assert [s['name'] for s in benchmark.get_series(1000)] == ['BTC-USDT']


def test_a_backtest_shorter_than_a_day_has_no_benchmark(monkeypatch):
    # regression: a single candle printed Buy & Hold +0.00% next to N/A everywhere else
    _use_routes(monkeypatch, 'BTC-USDT')
    monkeypatch.setattr(store.app, 'ending_time', float(START + DAY_MS + 60_000))
    _use_candles(monkeypatch, {'BTC-USDT': _daily_candles([100])})

    assert benchmark.get_series(1000) == []


def test_no_benchmark_means_no_metrics():
    portfolio = _curve('Portfolio', [1000, 1100])

    assert benchmark.calculate_metrics(None) is None
    assert benchmark.calculate_metrics([]) is None
    assert benchmark.calculate_metrics([portfolio]) is None


def test_a_single_symbol_is_the_headline_and_its_own_route():
    balances = [1000, 1100, 1050, 1200]
    metrics = benchmark.calculate_metrics([_curve('Portfolio', [1000] * 4), _curve('BTC-USDT', balances)])

    assert metrics['routes'][0]['symbol'] == 'BTC-USDT'
    assert metrics['portfolio']['net_profit_percentage'] == pytest.approx(20)
    assert metrics['portfolio']['net_profit'] == pytest.approx(200)
    assert metrics['portfolio']['starting_balance'] == 1000
    assert metrics['portfolio']['finishing_balance'] == 1200
    assert metrics['portfolio']['sharpe_ratio'] == metrics['routes'][0]['sharpe_ratio']


def test_several_symbols_are_headed_by_the_portfolio():
    metrics = benchmark.calculate_metrics([
        _curve('Portfolio', [1000, 1000]),
        _curve('BTC-USDT', [1000, 2000]),
        _curve('ETH-USDT', [1000, 500]),
        _curve(benchmark.BUY_AND_HOLD_NAME, [1000, 1250]),
    ])

    assert [route['symbol'] for route in metrics['routes']] == ['BTC-USDT', 'ETH-USDT']
    assert metrics['portfolio']['net_profit_percentage'] == pytest.approx(25)
    assert [route['net_profit_percentage'] for route in metrics['routes']] == pytest.approx([100, -50])


def test_the_benchmark_is_measured_like_the_strategy():
    balances = [1000, 1040, 980, 1100, 1060, 1200, 1150, 1300]
    timestamps = [START + i * DAY_MS for i in range(len(balances))]

    expected = stats.balance_metrics(balances, timestamps, 365)
    metrics = benchmark.calculate_metrics([_curve('Portfolio', balances), _curve('BTC-USDT', balances, START - DAY_MS)])['portfolio']

    for key, value in expected.items():
        assert metrics[key] == pytest.approx(value, nan_ok=True), key


def test_annualization_comes_from_the_session(monkeypatch):
    monkeypatch.setattr(jh, 'get_config', lambda key, default=None: 252 if key == 'env.metrics.annualization' else default)
    balances = [1000, 1040, 980, 1100, 1060, 1200]
    timestamps = [START + i * DAY_MS for i in range(len(balances))]

    sharpe = benchmark.calculate_metrics([_curve('Portfolio', balances), _curve('BTC-USDT', balances, START - DAY_MS)])['portfolio']['sharpe_ratio']

    assert sharpe == pytest.approx(stats.balance_metrics(balances, timestamps, 252)['sharpe_ratio'])


def test_a_days_close_counts_in_the_month_of_that_day():
    january_31 = 1_548_892_800_000
    # The daily candles of Jan 30, Jan 31 and Feb 1. Reading them at their open would count
    # the Feb 1 close in January, since balance samples are read just before they were taken.
    curve = _curve('BTC-USDT', [100, 110, 121], january_31 - DAY_MS)

    months = stats.monthly_returns([p['value'] for p in curve['data']], benchmark.sample_timestamps(curve))

    assert months == pytest.approx({(2019, 1): 10.0, (2019, 2): 10.0})


def test_one_candle_is_too_little_to_measure_but_doesnt_break():
    metrics = benchmark.calculate_metrics([_curve('Portfolio', [1000, 1000]), _curve('BTC-USDT', [1000])])['portfolio']

    assert metrics['net_profit'] == 0
    assert np.isnan(metrics['sharpe_ratio'])
    assert np.isnan(metrics['max_drawdown'])
    assert jh.clean_nan_values(metrics)['sharpe_ratio'] is None


def test_a_flat_market_has_no_drawdown():
    metrics = benchmark.calculate_metrics([_curve('Portfolio', [1000] * 40), _curve('BTC-USDT', [1000] * 40)])['portfolio']

    assert metrics['net_profit_percentage'] == 0
    assert metrics['max_drawdown'] == 0
    assert metrics['positive_months'] == 0
    assert metrics['negative_months'] == 0


def test_metrics_survive_the_trip_to_the_database():
    metrics = benchmark.calculate_metrics([_curve('Portfolio', [1000, 1100]), _curve('BTC-USDT', [1000, 1100, 1200])])

    assert json.loads(json.dumps(metrics))['portfolio']['net_profit'] == pytest.approx(200)


class _Backtest:
    """What a backtest published to the dashboard and saved to its session."""

    def __init__(self) -> None:
        self.published = {}
        self.saved = {}
        self.statuses = []

    def run(self, routes: list, candles: dict, is_benchmark: bool, pdf: bool = True) -> None:
        backtest_mode.run('000', False, {}, exchanges.SANDBOX, routes, [], '2019-04-01', '2019-04-02', candles, benchmark=is_benchmark, pdf=pdf)

    @property
    def session(self) -> SimpleNamespace:
        """The session as the database would return it, round-tripped through JSON."""
        def stored(key: str):
            return json.loads(json.dumps(self.saved.get(key)))

        return SimpleNamespace(
            id='00000000-0000-0000-0000-000000000000', title=None, description=None,
            equity_curve_json=stored('equity_curve') or [], metrics_json=stored('metrics'), trades_json=stored('trades'),
            hyperparameters_json=stored('hyperparameters'),
            state_json={'form': {'routes': [{'symbol': s, 'timeframe': '1m', 'strategy': 'TestOnClosePosition'} for s in self.symbols]}},
        )

    @property
    def symbols(self) -> list:
        return [curve['name'] for curve in self.saved['equity_curve'][1:] if curve['name'] != benchmark.BUY_AND_HOLD_NAME] or ['BTC-USDT']


@pytest.fixture
def backtest(monkeypatch):
    """Take the dashboard's path through a real simulation, keeping what it publishes and saves."""
    result = _Backtest()
    set_up()
    monkeypatch.setattr(jh, 'should_execute_silently', lambda: False)
    monkeypatch.setattr(backtest_mode, 'publish_status', lambda *args, **kwargs: None)
    monkeypatch.setattr(backtest_mode, 'sync_publish', lambda event, message, compression=False: result.published.__setitem__(event, message))
    monkeypatch.setattr(charts, '_plot_backtest_charts', lambda **kwargs: None)
    monkeypatch.setattr(backtest_session_model, 'store_backtest_session', lambda **kwargs: None)
    monkeypatch.setattr(backtest_session_model, 'update_backtest_session_status', lambda session_id, status: result.statuses.append(status))
    monkeypatch.setattr(backtest_session_model, 'update_backtest_session_results', lambda **kwargs: result.saved.update(kwargs))
    _use_candles(monkeypatch, {
        'BTC-USDT': _daily_candles([100, 110, 121, 115]),
        'ETH-USDT': _daily_candles([10, 9, 12, 13]),
    })
    return result


SINGLE_ROUTE = [{'symbol': 'BTC-USDT', 'timeframe': '1m', 'strategy': 'TestOnClosePosition'}]
TWO_ROUTES = SINGLE_ROUTE + [{'symbol': 'ETH-USDT', 'timeframe': '1m', 'strategy': 'TestOnClosePosition'}]


def test_a_backtest_without_the_report_keeps_no_balances_but_still_measures_its_benchmark(backtest):
    backtest.run(SINGLE_ROUTE, get_btc_candles(100), True, pdf=False)

    assert 'equity_curve' not in backtest.saved or backtest.saved['equity_curve'] is None
    assert backtest.published['metrics']['benchmark']['portfolio']['net_profit_percentage'] == pytest.approx(15)
    assert backtest.saved['metrics']['benchmark'] == backtest.published['metrics']['benchmark']
    assert backtest.statuses == ['finished']


def test_a_backtest_with_neither_the_report_nor_the_benchmark_builds_no_curves(backtest, monkeypatch):
    def fail(benchmark: bool = False) -> list:
        raise AssertionError('nothing asked for the curves')

    monkeypatch.setattr(charts, 'equity_curve', fail)

    backtest.run(SINGLE_ROUTE, get_btc_candles(100), False, pdf=False)

    assert backtest.statuses == ['finished']
    assert 'benchmark' not in backtest.saved['metrics']


def test_a_chart_failure_still_saves_the_finished_backtest(backtest, monkeypatch):
    def fail(**kwargs):
        raise MemoryError('Unable to allocate 165. GiB for an array')

    monkeypatch.setattr(charts, '_plot_backtest_charts', fail)

    backtest.run(SINGLE_ROUTE, get_btc_candles(100), True, pdf=False)

    assert backtest.statuses == ['finished']
    assert backtest.saved['metrics'] == backtest.published['metrics']
    assert 'MemoryError' in backtest.published['notification']['message']


def test_a_single_route_backtest_saves_its_benchmark(backtest):
    backtest.run(SINGLE_ROUTE, get_btc_candles(100), True)

    assert [curve['name'] for curve in backtest.saved['equity_curve']] == ['Portfolio', 'BTC-USDT']
    assert backtest.published['metrics']['benchmark']['portfolio']['net_profit_percentage'] == pytest.approx(15)
    assert backtest.saved['metrics']['benchmark'] == backtest.published['metrics']['benchmark']
    assert backtest.statuses == ['finished']
    assert backtest_report.generate_pdf(backtest.session).startswith(b'%PDF')


def test_a_multi_route_backtest_saves_each_symbol_and_the_portfolio(backtest):
    backtest.run(TWO_ROUTES, get_btc_and_eth_candles(), True)

    assert [curve['name'] for curve in backtest.saved['equity_curve']] == ['Portfolio', 'BTC-USDT', 'ETH-USDT', benchmark.BUY_AND_HOLD_NAME]
    metrics = backtest.saved['metrics']['benchmark']
    assert [route['symbol'] for route in metrics['routes']] == ['BTC-USDT', 'ETH-USDT']
    assert metrics['portfolio']['net_profit_percentage'] == pytest.approx((15 + 30) / 2)
    assert backtest_report.generate_pdf(backtest.session).startswith(b'%PDF')


def test_a_backtest_without_the_benchmark_still_saves_its_balances(backtest):
    backtest.run(SINGLE_ROUTE, get_btc_candles(100), False)

    assert [curve['name'] for curve in backtest.saved['equity_curve']] == ['Portfolio']
    assert 'benchmark' not in backtest.saved['metrics']
    assert backtest_report.generate_pdf(backtest.session).startswith(b'%PDF')


def test_a_backtest_survives_its_benchmark_failing(backtest, monkeypatch):
    _use_candles(monkeypatch, {})

    backtest.run(SINGLE_ROUTE, get_btc_candles(100), True)

    assert [curve['name'] for curve in backtest.saved['equity_curve']] == ['Portfolio']
    assert 'benchmark' not in backtest.saved['metrics']
    assert backtest.statuses == ['finished']


def test_a_backtest_without_trades_has_nothing_to_measure(backtest):
    routes = [{'symbol': 'BTC-USDT', 'timeframe': '1m', 'strategy': 'TestOnClosePosition'}]
    # the strategy waits for a price of 10, which this downtrend never reaches
    backtest.run(routes, get_downtrend_candles(50), True)

    assert backtest.published['metrics'] is None
    assert backtest.saved['equity_curve'] is None
    assert backtest.statuses == ['finished']


def test_equity_curve_only_has_a_benchmark_when_asked_for(monkeypatch):
    set_up()
    monkeypatch.setattr(store.closed_trades, 'trades', [object()], raising=False)
    monkeypatch.setattr(store.app, 'daily_balance', [1000.0, 1100.0], raising=False)
    monkeypatch.setattr(store.app, 'daily_balance_timestamps', [START, START + DAY_MS], raising=False)
    _use_routes(monkeypatch, 'BTC-USDT', 'ETH-USDT')
    _use_candles(monkeypatch, {'BTC-USDT': _daily_candles([100, 110]), 'ETH-USDT': _daily_candles([10, 11])})

    assert [curve['name'] for curve in charts.equity_curve(False)] == ['Portfolio']

    curves = charts.equity_curve(True)
    assert [curve['name'] for curve in curves] == ['Portfolio', 'BTC-USDT', 'ETH-USDT', benchmark.BUY_AND_HOLD_NAME]
    assert len({curve['color'] for curve in curves}) == len(curves)
    json.dumps(curves)


def test_equity_curve_colors_every_route_of_a_large_backtest(monkeypatch):
    set_up()
    monkeypatch.setattr(store.closed_trades, 'trades', [object()], raising=False)
    monkeypatch.setattr(store.app, 'daily_balance', [1000.0, 1100.0], raising=False)
    monkeypatch.setattr(store.app, 'daily_balance_timestamps', [START, START + DAY_MS], raising=False)
    symbols = [f'S{i}-USDT' for i in range(25)]
    _use_routes(monkeypatch, *symbols)
    _use_candles(monkeypatch, {symbol: _daily_candles([100, 110]) for symbol in symbols})

    curves = charts.equity_curve(True)

    assert len(curves) == 27
    assert all(curve['color'].startswith('#') for curve in curves)
