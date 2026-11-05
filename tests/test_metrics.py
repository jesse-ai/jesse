import numpy as np
import pandas as pd
import pytest

import jesse.helpers as jh
from jesse import research
from jesse.factories import candles_from_close_prices
from jesse.services import metrics
from jesse.store import store
from jesse.strategies import Strategy
from jesse.testing_utils import single_route_backtest


EXCHANGE = 'Sandbox'
SYMBOL = 'BTC-USDT'
DAILY_SAMPLE_MINUTES = 1_440
FIRST_ENTRY_INDEX = 10
SECOND_ENTRY_INDEX = DAILY_SAMPLE_MINUTES + 10
THIRD_ENTRY_INDEX = (2 * DAILY_SAMPLE_MINUTES) + 10


class _SingleTradeMetricsStrategy(Strategy):
    """Close one long at the configured profit or loss price."""

    exit_price = 110

    def should_long(self) -> bool:
        return self.index == FIRST_ENTRY_INDEX

    def go_long(self) -> None:
        self.buy = 1, self.price

    def on_open_position(self, order) -> None:
        if self.exit_price > self.price:
            self.take_profit = 1, self.exit_price
        else:
            self.stop_loss = 1, self.exit_price

    def before_terminate(self) -> None:
        assert len(store.closed_trades.trades) == 1
        assert self.position.is_close

    def should_cancel_entry(self) -> bool:
        return False


class _WinningMetricsStrategy(_SingleTradeMetricsStrategy):
    exit_price = 110


class _LosingMetricsStrategy(_SingleTradeMetricsStrategy):
    exit_price = 90


class _MixedMetricsStrategy(Strategy):
    """Produce two winning longs and one losing short across three crypto days."""

    def before(self) -> None:
        if self.index == 0:
            self.vars['closed_trades'] = 0

    def should_long(self) -> bool:
        return self.index in (FIRST_ENTRY_INDEX, THIRD_ENTRY_INDEX)

    def should_short(self) -> bool:
        return self.index == SECOND_ENTRY_INDEX

    def go_long(self) -> None:
        self.buy = 1, self.price

    def go_short(self) -> None:
        self.sell = 1, self.price

    def on_open_position(self, order) -> None:
        if self.vars['closed_trades'] == 0:
            self.take_profit = 1, 110
        elif self.vars['closed_trades'] == 1:
            self.stop_loss = 1, 110
        else:
            self.take_profit = 1, 105

    def on_close_position(self, order, closed_trade) -> None:
        self.vars['closed_trades'] += 1

    def before_terminate(self) -> None:
        assert self.vars['closed_trades'] == 3
        assert len(store.closed_trades.trades) == 3
        assert self.position.is_close

    def should_cancel_entry(self) -> bool:
        return False


class _NoTradeMetricsStrategy(Strategy):
    """Keep a session trade-free so the public result's zeroed contract is exercised."""

    def should_long(self) -> bool:
        return False

    def go_long(self) -> None:
        pass

    def before_terminate(self) -> None:
        assert store.closed_trades.trades == []

    def should_cancel_entry(self) -> bool:
        return False


def _run_metrics_backtest(
        strategy: type[Strategy],
        prices: np.ndarray,
        fee: float = 0.001,
        annualization: int = 365,
) -> dict:
    """Run a deterministic futures session and return its public research result."""
    candles = candles_from_close_prices(prices.tolist())
    config = {
        'starting_balance': 10_000,
        'fee': fee,
        'type': 'futures',
        'annualization': annualization,
        'futures_leverage': 1,
        'futures_leverage_mode': 'cross',
        'exchange': EXCHANGE,
        'warm_up_candles': 0,
    }
    routes = [{
        'exchange': EXCHANGE,
        'strategy': strategy,
        'symbol': SYMBOL,
        'timeframe': '1m',
    }]
    candle_data = {
        jh.key(EXCHANGE, SYMBOL): {
            'exchange': EXCHANGE,
            'symbol': SYMBOL,
            'candles': candles,
        },
    }
    return research.backtest(config, routes, [], candle_data, fast_mode=False)


def _single_trade_prices(exit_price: float) -> np.ndarray:
    """Keep one entry at 100, then hold the requested exit through a daily sample."""
    prices = np.full(DAILY_SAMPLE_MINUTES + 2, 100.0)
    prices[FIRST_ENTRY_INDEX + 1:] = exit_price
    return prices


def _mixed_trade_prices() -> np.ndarray:
    """Place each completed trade before a separate 1,440-minute balance sample."""
    prices = np.full((3 * DAILY_SAMPLE_MINUTES) + 2, 100.0)
    prices[FIRST_ENTRY_INDEX + 1:SECOND_ENTRY_INDEX] = 110
    prices[SECOND_ENTRY_INDEX] = 100
    prices[SECOND_ENTRY_INDEX + 1:THIRD_ENTRY_INDEX] = 110
    prices[THIRD_ENTRY_INDEX] = 100
    prices[THIRD_ENTRY_INDEX + 1:] = 105
    return prices


def _daily_returns(values: list[float]) -> pd.Series:
    """Build consecutive UTC-like daily observations for annualized metric tests."""
    return pd.Series(values, index=pd.date_range('2025-01-01', periods=len(values), freq='D'))


def test_open_pl_and_total_open_trades():
    single_route_backtest('Test40')

    assert len(store.closed_trades.trades) == 1
    assert store.app.total_open_trades == 1
    assert store.app.total_open_pl == 97  # 99 - 2

    stats = metrics.trades(store.closed_trades.trades, store.app.daily_balance)
    assert stats['total_open_trades'] == 1
    assert stats['open_pl'] == 97


def test_metrics_for_trades_without_fee():
    single_route_backtest('TestMetrics1')

    trades = store.closed_trades.trades
    assert len(trades) == 1
    stats = metrics.trades(store.closed_trades.trades, store.app.daily_balance)

    assert stats['total'] == 1
    assert stats['starting_balance'] == 10000
    assert stats['finishing_balance'] == 10050
    assert stats['win_rate'] == 1
    assert stats['ratio_avg_win_loss'] is np.nan
    assert stats['longs_count'] == 1
    assert stats['shorts_count'] == 0
    assert stats['longs_percentage'] == 100
    assert stats['shorts_percentage'] == 0
    assert stats['fee'] == 0
    assert stats['net_profit'] == 50
    assert stats['net_profit_percentage'] == 0.5
    assert stats['average_win'] == 50
    assert stats['average_loss'] is np.nan
    assert stats['expectancy'] == 50
    assert stats['expectancy_percentage'] == 0.5
    assert stats['expected_net_profit_every_100_trades'] == 50
    assert stats['average_holding_period'] == 300
    assert stats['average_losing_holding_period'] is np.nan
    assert stats['average_winning_holding_period'] == 300
    assert stats['gross_loss'] == 0
    assert stats['gross_profit'] == 50
    assert stats['open_pl'] == 0
    assert stats['largest_losing_trade'] == 0
    assert stats['largest_winning_trade'] == 50

    # A zero-duration session must not divide trade counts by zero.
    original_ending_time = store.app.ending_time
    try:
        store.app.ending_time = store.app.starting_time
        zero_duration_stats = metrics.trades(store.closed_trades.trades, store.app.daily_balance)
        assert zero_duration_stats['avg_trades_per_day'] == 0
        assert zero_duration_stats['avg_trades_per_week'] == 0
        assert zero_duration_stats['avg_trades_per_month'] == 0
    finally:
        store.app.ending_time = original_ending_time

    # Daily-return metrics are exercised below with complete multi-day samples.


def test_crypto_daily_return_metrics_use_365_day_annualization() -> None:
    # This mixed series has both downside and recovery, giving every risk metric
    # a finite value while keeping the expected values independently inspectable.
    returns = _daily_returns([0.02, -0.01, 0.03, -0.02, 0.01])

    assert metrics.cagr(returns, periods=365).iloc[0] == pytest.approx(13.17681588701674)
    assert metrics.sharpe_ratio(returns, periods=365).iloc[0] == pytest.approx(5.527941708708922)
    assert metrics.sortino_ratio(returns, periods=365).iloc[0] == pytest.approx(11.462983904725679)
    assert metrics.calmar_ratio(returns).iloc[0] == pytest.approx(658.8407943508364)
    assert metrics.omega_ratio(returns, periods=365).iloc[0] == pytest.approx(2.0)
    assert metrics.serenity_index(returns).iloc[0] == pytest.approx(2.5311776849554346)
    assert metrics.max_drawdown(returns).iloc[0] == pytest.approx(-0.02)


def _balance_returns(balances: list) -> pd.DataFrame:
    """Daily returns the way a backtest gets them, with pct_change's NaN in the first row."""
    days = pd.date_range('2024-01-01', periods=len(balances), freq='D', tz='UTC')
    return pd.DataFrame(balances, index=days).pct_change(1)


def _balance_serenity(balances: list) -> float:
    timestamps = [1_704_067_200_000 + i * 86_400_000 for i in range(len(balances))]
    return metrics.balance_metrics(balances, timestamps, 365)['serenity_index']


def test_drawdowns_start_from_the_first_balance() -> None:
    # regression: the NaN in the first row spread through the running peak and made every drawdown NaN
    drawdowns = metrics.to_drawdown_series(_balance_returns([100.0, 90.0, 95.0, 100.0, 80.0]))

    assert drawdowns[0].tolist() == pytest.approx([0, -0.1, -0.05, 0, -0.2])


def test_ulcer_index_measures_the_drawdowns_of_a_balance() -> None:
    # Drawdowns 0, 0, -10% and -1%: sqrt((0.1^2 + 0.01^2) / 3)
    assert metrics.ulcer_index(_balance_returns([100.0, 110.0, 99.0, 108.9])).iloc[0] == pytest.approx(0.0580229840, rel=1e-6)


def test_max_drawdown_counts_a_fall_from_the_first_balance() -> None:
    # regression: the first balance wasn't a peak, so this reported -5.3% instead of -10%
    returns = _balance_returns([100.0, 95.0, 90.0, 100.0])

    assert metrics.max_drawdown(returns).iloc[0].iloc[0] == pytest.approx(-0.1)


def test_calmar_ratio_counts_a_fall_from_the_first_balance() -> None:
    days = 366
    balances = [100.0, 50.0] + [50.0 + 50.0 * i / (days - 2) * 1.2 for i in range(1, days - 1)]
    returns = _balance_returns(balances)

    # A year's return of +10%, from 100 to 110, over a drawdown of -50%
    assert metrics.calmar_ratio(returns).iloc[0] == pytest.approx(0.1 / 0.5, rel=1e-6)


def test_serenity_index_of_a_balance_worked_out_by_hand() -> None:
    # regression: this was infinite for every backtest, or NaN for the shortest ones.
    # Returns +10%, -10%, +10% sum to 0.1 with a standard deviation of 0.11547005.
    # Drawdowns 0, 0, -10% and -1% give an ulcer index of 0.05802298, and with so few values
    # the expected shortfall is the worst one, -10%, for a pitfall of 0.1 / 0.11547005.
    # Serenity = 0.1 / (0.05802298 * 0.8660254)
    assert _balance_serenity([100.0, 110.0, 99.0, 108.9]) == pytest.approx(1.9900744, rel=1e-6)


def test_serenity_index_stays_finite_over_a_long_backtest() -> None:
    random = np.random.default_rng(7)
    balances = (10_000 * np.cumprod(1 + random.normal(0.001, 0.02, 500))).tolist()

    assert np.isfinite(_balance_serenity(balances))


def test_serenity_index_rewards_the_same_profit_with_less_risk() -> None:
    calm = [100.0, 104.0, 102.0, 106.0, 104.0, 108.0, 106.0, 110.0]
    rough = [100.0, 130.0, 70.0, 125.0, 75.0, 120.0, 80.0, 110.0]

    assert _balance_serenity(calm) > _balance_serenity(rough) > 0


def test_serenity_index_is_negative_for_a_losing_balance() -> None:
    assert _balance_serenity([100.0, 95.0, 97.0, 90.0, 92.0, 85.0]) < 0


def test_serenity_index_of_a_balance_that_never_fell_is_infinite_like_sortino() -> None:
    assert _balance_serenity([100.0, 110.0, 125.0]) == float('inf')


def test_serenity_index_of_a_balance_that_never_moved_is_undefined() -> None:
    assert np.isnan(_balance_serenity([100.0, 100.0, 100.0]))


def test_serenity_index_of_a_perfectly_steady_rise_is_undefined() -> None:
    # returns with no spread leave the pitfall, and so the index, at 0 / 0
    assert np.isnan(_balance_serenity([100.0, 110.0, 121.0]))


def test_autocorr_penalty_ignores_the_leading_nan_from_pct_change() -> None:
    # metrics.trades() builds daily returns with pct_change(), whose first value is NaN.
    returns = pd.Series([10_000, 10_200, 10_098, 10_401, 10_193, 10_295, 10_090]).pct_change(1)

    penalty = metrics.autocorr_penalty(returns)

    assert np.isfinite(penalty)
    assert penalty >= 1
    assert penalty == pytest.approx(metrics.autocorr_penalty(returns.dropna()))
    assert metrics.sharpe_ratio(returns, periods=365, smart=True).iloc[0] == pytest.approx(
        metrics.sharpe_ratio(returns, periods=365).iloc[0] / penalty
    )
    assert metrics.sortino_ratio(returns, periods=365, smart=True).iloc[0] == pytest.approx(
        metrics.sortino_ratio(returns, periods=365).iloc[0] / penalty
    )


def test_winning_only_daily_returns_have_stable_undefined_ratios() -> None:
    returns = _daily_returns([0.01, 0.02, 0.03])

    with np.errstate(all='ignore'):
        assert np.isposinf(metrics.sortino_ratio(returns, periods=365).iloc[0])
        assert np.isnan(metrics.omega_ratio(returns, periods=365).iloc[0])
    assert metrics.calmar_ratio(returns).iloc[0] == 0
    assert metrics.max_drawdown(returns).iloc[0] == 0


def test_losing_only_daily_returns_have_stable_downside_metrics() -> None:
    returns = _daily_returns([-0.01, -0.02, -0.03])

    assert metrics.sharpe_ratio(returns, periods=365).iloc[0] == pytest.approx(-38.2099463490856)
    assert metrics.sortino_ratio(returns, periods=365).iloc[0] == pytest.approx(-17.687768170607136)
    assert metrics.omega_ratio(returns, periods=365).iloc[0] == 0
    assert metrics.max_drawdown(returns).iloc[0] == pytest.approx(-0.0494)


def test_flat_daily_returns_have_stable_empty_risk_metrics() -> None:
    returns = _daily_returns([0.0, 0.0, 0.0])

    with np.errstate(all='ignore'):
        assert np.isnan(metrics.sharpe_ratio(returns, periods=365).iloc[0])
        assert np.isneginf(metrics.sortino_ratio(returns, periods=365).iloc[0])
        assert np.isnan(metrics.omega_ratio(returns, periods=365).iloc[0])
    assert metrics.cagr(returns, periods=365).iloc[0] == 0
    assert metrics.calmar_ratio(returns).iloc[0] == 0
    assert metrics.max_drawdown(returns).iloc[0] == 0


def test_same_day_returns_do_not_claim_an_annualized_result() -> None:
    returns = pd.Series(
        [0.01, -0.01],
        index=pd.to_datetime(['2025-01-01T00:00:00', '2025-01-01T12:00:00']),
    )

    assert metrics.cagr(returns, periods=365).iloc[0] == 0
    assert metrics.calmar_ratio(returns).iloc[0] == 0


def test_max_underwater_period_counts_days_until_recovery() -> None:
    balances = [10_000, 11_000, 10_500, 10_400, 11_200, 10_800]

    assert metrics.calculate_max_underwater_period(balances) == 2


def _sample_time(date: str) -> int:
    """Daily balances are sampled one minute into the day after the one they measure."""
    return jh.date_to_timestamp(date) + 60_000


def test_monthly_returns_keep_the_last_day_of_each_month() -> None:
    # regression: the heatmap compared each month's first and last samples, so the
    # return of the last day of every month was lost.
    balances = [100, 100, 100, 110, 110]
    timestamps = [
        jh.date_to_timestamp('2021-01-30'),
        _sample_time('2021-01-31'),
        _sample_time('2021-02-01'),
        _sample_time('2021-02-02'),
        _sample_time('2021-03-01'),
    ]

    assert metrics.monthly_returns(balances, timestamps) == {
        (2021, 1): pytest.approx(0),
        (2021, 2): pytest.approx(10),
    }


def test_monthly_returns_compound_to_the_total_return() -> None:
    balances = [100, 120, 90, 99]
    timestamps = [
        jh.date_to_timestamp('2021-01-01'),
        _sample_time('2021-02-01'),
        _sample_time('2021-03-01'),
        _sample_time('2021-04-01'),
    ]

    returns = metrics.monthly_returns(balances, timestamps)

    assert returns == {
        (2021, 1): pytest.approx(20),
        (2021, 2): pytest.approx(-25),
        (2021, 3): pytest.approx(10),
    }
    assert np.prod([1 + r / 100 for r in returns.values()]) == pytest.approx(0.99)


def test_a_final_sample_at_midnight_does_not_open_a_new_month() -> None:
    balances = [100, 105]
    timestamps = [jh.date_to_timestamp('2021-01-01'), jh.date_to_timestamp('2021-02-01')]

    assert metrics.monthly_returns(balances, timestamps) == {(2021, 1): pytest.approx(5)}


def test_monthly_returns_need_matching_timestamps() -> None:
    assert metrics.monthly_returns([100, 110], [jh.date_to_timestamp('2021-01-01')]) == {}
    assert metrics.monthly_returns([100], [jh.date_to_timestamp('2021-01-01')]) == {}


def test_winning_only_backtest_metrics_include_fees() -> None:
    result = _run_metrics_backtest(
        _WinningMetricsStrategy,
        _single_trade_prices(110),
    )
    stats = result['metrics']

    assert stats['total'] == stats['total_winning_trades'] == 1
    assert stats['total_losing_trades'] == 0
    assert stats['fee'] == pytest.approx(0.21)
    assert stats['net_profit'] == pytest.approx(9.79)
    assert stats['finishing_balance'] == pytest.approx(10_009.79)
    assert stats['gross_profit'] == pytest.approx(9.79)
    assert stats['gross_loss'] == 0
    assert np.isnan(stats['average_loss'])
    assert np.isnan(stats['ratio_avg_win_loss'])


def test_losing_only_backtest_metrics_include_fees() -> None:
    result = _run_metrics_backtest(
        _LosingMetricsStrategy,
        _single_trade_prices(90),
    )
    stats = result['metrics']

    assert stats['total'] == stats['total_losing_trades'] == 1
    assert stats['total_winning_trades'] == 0
    assert stats['fee'] == pytest.approx(0.19)
    assert stats['net_profit'] == pytest.approx(-10.19)
    assert stats['finishing_balance'] == pytest.approx(9_989.81)
    assert stats['gross_profit'] == 0
    assert stats['gross_loss'] == pytest.approx(-10.19)
    assert np.isnan(stats['average_win'])
    assert np.isnan(stats['ratio_avg_win_loss'])


def test_mixed_multi_day_backtest_metrics_contract() -> None:
    result = _run_metrics_backtest(
        _MixedMetricsStrategy,
        _mixed_trade_prices(),
    )
    stats = result['metrics']

    assert stats['total'] == 3
    assert stats['total_winning_trades'] == 2
    assert stats['total_losing_trades'] == 1
    assert stats['fee'] == pytest.approx(0.625)
    assert stats['net_profit'] == pytest.approx(4.375)
    assert stats['finishing_balance'] == pytest.approx(10_004.375)
    assert stats['total_open_trades'] == 0
    assert stats['open_pl'] == 0
    assert stats['max_drawdown'] == pytest.approx(-0.10200014186112494)
    assert stats['max_underwater_period'] == 2
    assert stats['positive_months'] == 1
    assert stats['negative_months'] == 0
    assert stats['annual_return'] == pytest.approx(5.465903612204692)
    assert stats['sharpe_ratio'] == pytest.approx(2.45661087496446)
    assert stats['sortino_ratio'] == pytest.approx(4.591544590351203)
    assert stats['calmar_ratio'] == pytest.approx(53.58721578688214)
    assert stats['omega_ratio'] == pytest.approx(1.4299197170055138)
    assert np.isfinite(stats['serenity_index'])
    assert len(store.app.daily_balance_timestamps) == len(store.app.daily_balance)
    assert store.app.daily_balance_timestamps == sorted(store.app.daily_balance_timestamps)


def test_backtest_metrics_include_the_smart_ratios() -> None:
    stats = _run_metrics_backtest(_MixedMetricsStrategy, _mixed_trade_prices())['metrics']

    # The optimize mode's "smart sharpe" / "smart sortino" objectives read these keys.
    assert np.isfinite(stats['smart_sharpe'])
    assert np.isfinite(stats['smart_sortino'])
    assert 0 < stats['smart_sharpe'] <= stats['sharpe_ratio']
    assert 0 < stats['smart_sortino'] <= stats['sortino_ratio']


def test_stock_annualization_changes_ratios_without_changing_timestamp_based_growth() -> None:
    crypto = _run_metrics_backtest(_MixedMetricsStrategy, _mixed_trade_prices(), annualization=365)['metrics']
    stock = _run_metrics_backtest(_MixedMetricsStrategy, _mixed_trade_prices(), annualization=252)['metrics']

    assert crypto['annualization'] == 365
    assert stock['annualization'] == 252
    assert stock['sharpe_ratio'] == pytest.approx(crypto['sharpe_ratio'] * np.sqrt(252 / 365))
    assert stock['sortino_ratio'] == pytest.approx(crypto['sortino_ratio'] * np.sqrt(252 / 365))
    assert stock['annual_return'] == pytest.approx(crypto['annual_return'])
    assert stock['calmar_ratio'] == pytest.approx(crypto['calmar_ratio'])


def test_no_trade_backtest_returns_zeroed_portfolio_metrics() -> None:
    result = _run_metrics_backtest(
        _NoTradeMetricsStrategy,
        np.full(DAILY_SAMPLE_MINUTES + 2, 100.0),
        fee=0,
    )

    assert result['metrics'] == {
        'total': 0,
        'win_rate': 0,
        'net_profit_percentage': 0,
        'annualization': 365,
    }
    assert result['trades'] == []

# def test_stats_for_a_strategy_without_losing_trades():
#     set_up([
#         (exchanges.SANDBOX, 'ETH-USDT', timeframes.MINUTE_5, 'Test08'),
#     ])
#
#     candles = {}
#     key = jh.key(exchanges.SANDBOX, 'ETH-USDT')
#     candles[key] = {
#         'exchange': exchanges.SANDBOX,
#         'symbol': 'ETH-USDT',
#         'candles': test_candles_1
#     }
#
#     # run backtest (dates are fake just to pass)
#     backtest_mode.run('2019-04-01', '2019-04-02', candles)
#     assert len(store.closed_trades.trades) == 1
#     stats_trades = stats.trades(store.closed_trades.trades)
#
#     assert stats_trades == {
#         'total': 1,
#         'starting_balance': 10000,
#         'finishing_balance': 10014.7,
#         'win_rate': 1,
#         'max_R': 1,
#         'min_R': 1,
#         'mean_R': 1,
#         'longs_count': 0,
#         'longs_percentage': 0,
#         'shorts_percentage': 100,
#         'shorts_count': 1,
#         'fee': 0,
#         'pnl': 14.7,
#         'pnl_percentage': 0.15,
#         'average_win': 14.7,
#         'average_loss': np.nan,
#         'expectancy': 14.7,
#         'expectancy_percentage': 0.15,
#         'expected_pnl_every_100_trades': 15.0,
#         'average_holding_period': 180.0,
#         'average_losing_holding_period': np.nan,
#         'average_winning_holding_period': 180.0
#     }


def test_daily_balance_stores_portfolio_value():
    # futures
    single_route_backtest(
        'TestDailyBalanceStoresPortfolioValue',
        is_futures_trading=True,
        candles_count=10*1024
    )

    # spot
    single_route_backtest(
        'TestDailyBalanceStoresPortfolioValue',
        is_futures_trading=False,
        candles_count=10 * 1024
    )
