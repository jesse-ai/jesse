import random

import pytest

from jesse.research.monte_carlo.monte_carlo_trades import (
    _calculate_metrics_from_equity_curve,
    _fractional_returns,
    _reconstruct_equity_curve_from_returns,
)

STARTING_BALANCE = 10_000.0
# a compounding run: the later trades move far more money than the early balance ever held
PNLS = [500, -300, 2000, -1500, 40000, -25000]
# a daily curve carries far more points than trades, which is where the scheduling loop does work
SHAPES = [len(PNLS), 365, 3287]


def _curve(returns: list, points: int) -> list:
    shell = [{'name': 'Portfolio', 'data': [{'time': i, 'value': 0} for i in range(points)]}]
    return _reconstruct_equity_curve_from_returns(returns, shell, STARTING_BALANCE)


def _values(returns: list, points: int) -> list:
    return [point['value'] for point in _curve(returns, points)[0]['data']]


@pytest.mark.parametrize('points', SHAPES)
def test_original_order_reproduces_the_realised_balance(points):
    returns = _fractional_returns([{'PNL': pnl} for pnl in PNLS], STARTING_BALANCE)
    assert _values(returns, points)[-1] == pytest.approx(STARTING_BALANCE + sum(PNLS))


@pytest.mark.parametrize('points', SHAPES)
def test_reordering_keeps_the_final_value_and_never_goes_negative(points):
    returns = _fractional_returns([{'PNL': pnl} for pnl in PNLS], STARTING_BALANCE)
    random.seed(0)
    for _ in range(50):
        shuffled = returns[:]
        random.shuffle(shuffled)
        values = _values(shuffled, points)
        assert values[-1] == pytest.approx(STARTING_BALANCE + sum(PNLS))
        assert min(values) > 0


@pytest.mark.parametrize('points', SHAPES)
def test_no_ordering_reports_a_drawdown_deeper_than_a_total_loss(points):
    # the regression this guards: replaying absolute PnLs put the balance below zero, and a 9-year
    # run reported a 5th-percentile drawdown of -2204%
    returns = _fractional_returns([{'PNL': pnl} for pnl in PNLS], STARTING_BALANCE)
    random.seed(0)
    for _ in range(50):
        shuffled = returns[:]
        random.shuffle(shuffled)
        metrics = _calculate_metrics_from_equity_curve(_curve(shuffled, points), STARTING_BALANCE)
        assert metrics['max_drawdown'] >= -100


def test_reordering_still_moves_the_drawdown():
    returns = _fractional_returns([{'PNL': pnl} for pnl in PNLS], STARTING_BALANCE)
    random.seed(0)
    seen = set()
    for _ in range(50):
        shuffled = returns[:]
        random.shuffle(shuffled)
        metrics = _calculate_metrics_from_equity_curve(_curve(shuffled, 365), STARTING_BALANCE)
        seen.add(round(metrics['max_drawdown'], 6))
    assert len(seen) > 1


@pytest.mark.parametrize('pnls', [
    (5000, -20000, 3000, 4000),   # wiped out mid-run
    (9000, 3000, 4000, -30000),   # wiped out on the final trade
    (-10000, 5000),               # lost exactly the starting balance
])
def test_a_run_that_lost_the_balance_backing_a_trade_is_rejected(pnls):
    with pytest.raises(ValueError):
        _fractional_returns([{'PNL': pnl} for pnl in pnls], STARTING_BALANCE)
