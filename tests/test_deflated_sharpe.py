import numpy as np

from jesse.services.metrics import (
    deflated_sharpe_ratio,
    expected_max_sharpe,
    return_moments,
)

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


def test_missing_moments_return_nan():
    # The moments are unavailable exactly when the return series had no dispersion.
    # Its standard deviation is floating-point residue rather than a true zero, so the
    # Sharpe divides out to ~1e16 -- finite, and past the isfinite guard. Deflating
    # that answered 1.0: certainty of an edge, from the one input that cannot show one.
    assert np.isnan(deflated_sharpe_ratio(8.8e16, 250, 4, skew=np.nan, kurt=np.nan))
    assert np.isnan(deflated_sharpe_ratio(2.0, 250, 4, skew=np.nan, kurt=3.0))
    assert np.isnan(deflated_sharpe_ratio(2.0, 250, 4, skew=0.0, kurt=np.nan))

    # Real moments are unaffected.
    assert 0 <= deflated_sharpe_ratio(2.0, 250, 4, skew=-0.5, kurt=5.0) <= 1


def test_return_moments_reject_a_series_with_no_dispersion():
    # A constant series does not reach an exact `std == 0`: its standard deviation is
    # floating-point residue rather than a true zero, so the moments came out as huge
    # finite numbers and the Sharpe divided out to ~1e16 -- which deflated to 1.0,
    # certainty of an edge from the one input that cannot show one. Checked across
    # values and lengths, since the residue depends on both.
    for value in (1e-7, 1e-4, 0.001, 0.01, 1.0, 100.0):
        for n in (3, 10, 250, 5000):
            skew, kurt = return_moments(np.full(n, value))
            assert np.isnan(skew) and np.isnan(kurt), f"leaked at value={value}, n={n}"

    assert all(np.isnan(x) for x in return_moments(np.zeros(250)))
    assert all(np.isnan(x) for x in return_moments(np.array([0.01, 0.02])))

    # A real but very quiet series still has moments.
    skew, kurt = return_moments(np.random.default_rng(1).normal(0, 1e-8, 250))
    assert np.isfinite(skew) and np.isfinite(kurt)
