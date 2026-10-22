import math

import numpy as np
import pytest

import jesse.helpers as jh
from jesse.factories import candles_from_close_prices
from jesse.modes.optimize_mode import fitness

EXCHANGE = 'Optimization Objectives Exchange'
SYMBOL = 'TEST-USDT'
SENTINEL_SCORE = 0.0001

# Every objective offered for optimization: config.py ('optimization.objective_function')
# and the MCP create_optimization_draft tool both list exactly these.
OBJECTIVES = ('sharpe', 'calmar', 'sortino', 'omega', 'serenity', 'smart sharpe', 'smart sortino')


def _wave(minutes: int, start: int) -> list:
    # Several days of 1m closes with ups and downs, so the daily returns give
    # finite risk ratios. Deterministic: a slow sine plus a faster wobble.
    return [
        round(100 + 8 * math.sin((start + i) / 900) + 1.5 * math.sin((start + i) / 37), 4)
        for i in range(minutes)
    ]


def _candles(prices: list) -> dict:
    return {
        jh.key(EXCHANGE, SYMBOL): {
            'exchange': EXCHANGE,
            'symbol': SYMBOL,
            'candles': candles_from_close_prices(prices),
        },
    }


def _fitness(objective: str, monkeypatch) -> tuple:
    log = []
    monkeypatch.setattr(fitness.logger, 'log_optimize_mode', lambda message, session_id=None: log.append(message))
    user_config = {
        'exchange': {
            'name': EXCHANGE,
            'balance': 10_000,
            'fee': 0,
            'type': 'futures',
            'futures_leverage': 1,
            'futures_leverage_mode': 'cross',
        },
        'warm_up_candles': 0,
    }
    routes = [{'exchange': EXCHANGE, 'strategy': 'TestOptimizationIsolation', 'symbol': SYMBOL, 'timeframe': '1m'}]
    score, training_metrics, _ = fitness.get_fitness(
        user_config, routes, [], [], {'entry_interval': 60},
        {}, _candles(_wave(5 * 1440, 0)),
        {}, _candles(_wave(2 * 1440, 5 * 1440)),
        10, True, 'objectives-test', objective,
    )
    return score, training_metrics, log


@pytest.mark.parametrize('objective', OBJECTIVES)
def test_every_offered_objective_reads_a_metric_the_backtest_emits(objective, monkeypatch) -> None:
    score, training_metrics, log = _fitness(objective, monkeypatch)

    # A missing metric key surfaces as a caught KeyError: the trial is logged as failed
    # and silently scored at the sentinel.
    assert not [m for m in log if m.startswith('Trial evaluation failed')], log
    assert training_metrics['total'] > 5
    assert score is not None


@pytest.mark.parametrize('smart, plain, metric_key, plain_key', [
    ('smart sharpe', 'sharpe', 'smart_sharpe', 'sharpe_ratio'),
    ('smart sortino', 'sortino', 'smart_sortino', 'sortino_ratio'),
])
def test_smart_objectives_score_like_their_plain_counterparts(smart, plain, metric_key, plain_key, monkeypatch) -> None:
    smart_score, smart_metrics, _ = _fitness(smart, monkeypatch)
    plain_score, plain_metrics, _ = _fitness(plain, monkeypatch)

    # Same backtest, so the same plain ratio; the smart one divides it by an
    # autocorrelation penalty >= 1, so it is finite, positive here, and no larger.
    assert plain_metrics[plain_key] == pytest.approx(smart_metrics[plain_key])
    assert np.isfinite(smart_metrics[metric_key])
    assert 0 < smart_metrics[metric_key] <= smart_metrics[plain_key]
    assert SENTINEL_SCORE < smart_score <= plain_score
