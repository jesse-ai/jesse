import numpy as np

from jesse.services.metrics import deflated_sharpe_ratio, expected_max_sharpe

# Reference values computed with the numguard reference implementation of
# Bailey & Lopez de Prado (2014): per-period Sharpe = annualized / sqrt(365),
# null SR std = 1/sqrt(n_observations - 1), exact E[max] formula.
TOL = 1e-9


def test_expected_max_sharpe_matches_reference():
    assert abs(expected_max_sharpe(200, 1 / np.sqrt(364)) - 0.14495283882665905) < TOL
    assert expected_max_sharpe(1, 0.1) == 0.0


def test_deflated_sharpe_matches_reference():
    assert abs(deflated_sharpe_ratio(2.0, 365, 200) - 0.221787790810632) < 1e-7
    assert abs(
        deflated_sharpe_ratio(1.2, 180, 500, skew=-0.5, kurt=5.0)
        - 0.014849505815470308
    ) < 1e-7


def test_single_trial_reduces_to_probabilistic_sharpe():
    # with one trial there is no deflation: the bar is zero
    assert abs(deflated_sharpe_ratio(2.0, 365, 1) - 0.9768039819822307) < 1e-7


def test_deflation_is_monotonic_in_trial_count():
    values = [deflated_sharpe_ratio(2.0, 365, n) for n in (1, 10, 100, 1000)]
    assert all(values[i] > values[i + 1] for i in range(len(values) - 1))


def test_insufficient_observations_returns_nan():
    assert np.isnan(deflated_sharpe_ratio(2.0, 2, 10))
    assert np.isnan(deflated_sharpe_ratio(np.nan, 365, 10))
