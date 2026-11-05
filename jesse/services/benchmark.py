import numpy as np

import jesse.helpers as jh
from jesse.routes import router
from jesse.services import metrics as stats
from jesse.services.candle_service import generate_completed_candles_from_observed_minutes, get_candles_from_db
from jesse.store import store
from jesse.utils import prices_to_returns

# Name of the combined series of a multi-route run; every other benchmark is named after its symbol.
BUY_AND_HOLD_NAME = 'Buy & Hold'
DAY_MS = 86_400_000


def get_series(initial_balance: float) -> list:
    """
    Calculate the buy-and-hold balance of each route's symbol from its daily closes. With more
    than one symbol, the list ends with the portfolio holding all of them. Must be called
    before store.reset().

    A symbol whose candles can't be read is left out, so that a benchmark problem doesn't
    cost the user the results of the backtest itself.
    """
    series = []
    # The end of the last simulated candle's day, that candle being two minutes before
    # ending_time. Candles are read up to there, and days are complete by then, so a market
    # that closes before midnight keeps its last day.
    last_candle_time = int(store.app.ending_time) - 120_000
    finish_time = last_candle_time - last_candle_time % DAY_MS + DAY_MS
    for r in router.routes:
        try:
            _, minute_candles = get_candles_from_db(
                r.exchange, r.symbol, '1m', store.app.starting_time, finish_time,
                is_for_jesse=False, warmup_candles_num=0, caching=True
            )
            daily_candles = generate_completed_candles_from_observed_minutes('1D', minute_candles, finish_time)
            daily_returns = prices_to_returns(daily_candles[:, 2])
            daily_returns[0] = 0
        except Exception as e:
            jh.error(f'Could not generate the benchmark for {r.symbol}: {e}')
            continue

        # A backtest shorter than a day has nothing to compare: the holding has only just been bought.
        if len(daily_candles) < 2:
            continue

        multiplier = (1 + daily_returns / 100).cumprod()
        series.append({
            'name': r.symbol,
            'timestamps': daily_candles[:, 0],
            'multiplier': multiplier,
            'balance': initial_balance * multiplier,
        })

    if len(series) > 1:
        series.append(_get_portfolio_series(series, initial_balance))

    return series


def _get_portfolio_series(series: list, initial_balance: float) -> dict:
    """
    Split the balance equally between the symbols and never rebalance. A symbol with no candle
    on a given day (a market holiday, for example) keeps its last value, and one that hasn't
    started trading yet stays in cash.
    """
    timestamps = np.unique(np.concatenate([s['timestamps'] for s in series]))
    multiplier = np.zeros(len(timestamps))
    for s in series:
        positions = np.searchsorted(s['timestamps'], timestamps, side='right') - 1
        multiplier += np.where(positions >= 0, s['multiplier'][np.maximum(positions, 0)], 1.0)
    multiplier /= len(series)

    return {
        'name': BUY_AND_HOLD_NAME,
        'timestamps': timestamps,
        'multiplier': multiplier,
        'balance': initial_balance * multiplier,
    }


def sample_timestamps(curve: dict) -> list:
    """
    Timestamps of a benchmark curve's balances. Its points are stamped with the open of their
    daily candle, but each balance is that day's close, known only once the day is over. That
    is when the strategy's own balance samples are taken, so both fall in the same months.
    """
    return [round(point['time'] * 1000) + DAY_MS for point in curve['data']]


def _curve_metrics(curve: dict, annualization: int) -> dict:
    balances = [point['value'] for point in curve['data']]
    starting_balance, finishing_balance = balances[0], balances[-1]
    net_profit = finishing_balance - starting_balance

    return {
        'starting_balance': starting_balance,
        'finishing_balance': finishing_balance,
        'net_profit': net_profit,
        'net_profit_percentage': net_profit / starting_balance * 100,
        **stats.balance_metrics(balances, sample_timestamps(curve), annualization),
    }


def calculate_metrics(equity_curve: list | None) -> dict | None:
    """
    Measure the benchmarks of an equity curve the way the strategy is measured. 'portfolio' is
    the headline: the only symbol of a single-route run, or the combined holding of a
    multi-route one. 'routes' has every symbol on its own. Returns None without a benchmark.
    """
    curves = (equity_curve or [])[1:]
    if not curves:
        return None

    annualization = jh.get_config('env.metrics.annualization', 365)
    portfolio = next((c for c in curves if c['name'] == BUY_AND_HOLD_NAME), curves[0])

    return {
        'portfolio': _curve_metrics(portfolio, annualization),
        'routes': [
            {'symbol': c['name'], **_curve_metrics(c, annualization)}
            for c in curves if c['name'] != BUY_AND_HOLD_NAME
        ],
    }
