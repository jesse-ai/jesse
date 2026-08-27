from datetime import timedelta

import pytest

from jesse.research.monte_carlo.monte_carlo_trades import _calculate_metrics_from_equity_curve


SECONDS_PER_YEAR = timedelta(days=365).total_seconds()


def _equity_curve(points):
    return [{
        'name': 'Portfolio',
        'data': [
            {'time': timestamp, 'value': value}
            for timestamp, value in points
        ]
    }]


def test_calmar_ratio_uses_annualized_return():
    result = _calculate_metrics_from_equity_curve(
        _equity_curve([
            (0, 100),
            (SECONDS_PER_YEAR, 90),
            (2 * SECONDS_PER_YEAR, 121),
        ]),
        starting_balance=100,
    )

    assert result['total_return'] == pytest.approx(21)
    assert result['max_drawdown'] == pytest.approx(-10)
    assert result['calmar_ratio'] == pytest.approx(1)


def test_calmar_ratio_is_zero_without_positive_time_span():
    result = _calculate_metrics_from_equity_curve(
        _equity_curve([
            (0, 100),
            (0, 90),
            (0, 121),
        ]),
        starting_balance=100,
    )

    assert result['calmar_ratio'] == 0


def test_calmar_ratio_is_zero_without_drawdown():
    result = _calculate_metrics_from_equity_curve(
        _equity_curve([
            (0, 100),
            (SECONDS_PER_YEAR, 121),
        ]),
        starting_balance=100,
    )

    assert result['calmar_ratio'] == 0
