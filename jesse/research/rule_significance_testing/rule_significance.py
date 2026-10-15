"""
Public entry point: rule_significance_test()

Tests whether a trading rule has next-bar predictive power or whether its
observed next-bar returns could plausibly arise from chance.

Null hypothesis H0: the rule's expected next-bar detrended return is not
                    positive.

The function runs in two phases:

  Phase 1 – Signal collection (sequential)
      A signal-only backtest is run using Jesse's candle engine.  The
      strategy is fully initialised (same as a normal backtest) but no
      orders are ever submitted.  At each completed bar the strategy's
      should_long() / should_short() methods are called to record the raw
      entry signal (+1 / -1 / 0).

  Phase 2 – Bootstrap simulation
      Resample random-length contiguous blocks of the rule's zero-centred
      returns and build a null sampling distribution while preserving local
      time-series dependence.
      p-value = fraction of simulated means ≥ the observed mean.
"""

import warnings
from typing import Dict, List, Optional

import numpy as np
from jesse.services.simulation_assumptions import resolve_annualization

from .common import (
    MIN_OBSERVATIONS,
    _elapsed_annualization_factor,
    _setup_progress_bar,
    _resolve_cpu_cores,
)
from .simulator import run_signal_only_backtest
from .bootstrap import run_bootstrap_test


def rule_significance_test(
    config: dict,
    routes: List[Dict[str, str]],
    data_routes: List[Dict[str, str]],
    candles: dict,
    warmup_candles: Optional[dict] = None,
    hyperparameters: Optional[dict] = None,
    n_simulations: int = 2000,
    random_seed: Optional[int] = None,
    progress_bar: bool = False,
    cpu_cores: Optional[int] = None,
    progress_callback=None,
    bootstrap_mean_block_length: int = 10,
) -> dict:
    """
    Test whether a trading rule has next-bar predictive power using
    bootstrap resampling.

    Parameters
    ----------
    config : dict
        Same format as research.backtest():
            {
                'starting_balance': 10_000,
                'fee': 0.001,
                'type': 'futures',           # or 'spot'
                'futures_leverage': 3,
                'futures_leverage_mode': 'cross',
                'exchange': 'Binance',
                'warm_up_candles': 210,
            }
    routes : list[dict]
        Exactly one trading route.  Example:
            [{'exchange': 'Binance', 'symbol': 'BTC-USDT',
              'timeframe': '4h', 'strategy': 'MyStrategy'}]
    data_routes : list[dict]
        Any number of data-only routes (no strategy key required).
    candles : dict
        1-minute candles keyed by "{exchange}-{symbol}", same format as
        research.backtest().
    warmup_candles : dict, optional
        Warm-up candles (same key format as ``candles``).
    hyperparameters : dict, optional
        Hyperparameters forwarded to the strategy.
    n_simulations : int
        Number of bootstrap resamples (default 2000; 2000+ recommended).
    random_seed : int, optional
        Random seed for reproducibility.
    bootstrap_mean_block_length : int
        Mean length of the stationary-bootstrap blocks (default 10 bars).
    progress_bar : bool
        Show a tqdm progress bar over the simulation batches.
    cpu_cores : int, optional
        Number of logical batches to split the simulations into for progress reporting. Defaults to 80 % of available cores.

    Returns
    -------
    dict with keys:
        observed_mean     float       mean next-bar log return of the rule
        annualized_return float       observed_mean annualized over actual elapsed calendar time
        simulated_means   np.ndarray  shape (n_simulations,)
        p_value           float       fraction of sims ≥ observed_mean
        n_simulations     int         simulations actually completed
        n_observations    int         number of bars used (after NaN removal)
        bootstrap_mean_block_length int  mean stationary-bootstrap block length
    """
    # ------------------------------------------------------------------
    # Input validation
    # ------------------------------------------------------------------
    if len(routes) != 1:
        raise ValueError(
            f'rule_significance_test() requires exactly one trading route; '
            f'{len(routes)} were provided.'
        )
    if bootstrap_mean_block_length < 1:
        raise ValueError('bootstrap_mean_block_length must be at least 1')

    resolved_seed = random_seed if random_seed is not None else 42
    resolved_cores = _resolve_cpu_cores(cpu_cores)

    # ------------------------------------------------------------------
    # Phase 1: Signal collection (sequential, single run)
    # ------------------------------------------------------------------
    def phase1_callback(current, total):
        if progress_callback:
            # Phase 1 (signal extraction) takes the bulk of the time. Map to 0-90% of progress.
            mapped_current = int((current / total) * 90)
            progress_callback(mapped_current, 100)

    bar_timestamps, close_prices, signals = run_signal_only_backtest(
        config=config,
        routes=routes,
        data_routes=data_routes,
        candles=candles,
        warmup_candles=warmup_candles,
        hyperparameters=hyperparameters,
        progress_callback=phase1_callback,
    )

    # ------------------------------------------------------------------
    # NaN / data-quality checks
    # ------------------------------------------------------------------
    nan_mask = ~(np.isfinite(close_prices) & np.isfinite(signals.astype(float)))
    if nan_mask.any():
        warnings.warn(
            f'rule_significance_test: {nan_mask.sum()} bar(s) contain NaN or '
            f'infinite values and will be dropped.',
            stacklevel=2,
        )
        close_prices = close_prices[~nan_mask]
        signals = signals[~nan_mask]
        bar_timestamps = bar_timestamps[~nan_mask]

    # ------------------------------------------------------------------
    # Log returns & detrending
    # ------------------------------------------------------------------
    # The signal emitted at bar t is evaluated against the following bar's
    # return, which is the first return that was not already known at signal time.
    log_returns = np.log(close_prices[1:] / close_prices[:-1])
    signals = signals[:-1]

    # Remove any NaN introduced by the log computation (e.g. price = 0)
    valid = np.isfinite(log_returns)
    if not valid.all():
        warnings.warn(
            f'rule_significance_test: {(~valid).sum()} NaN log-return(s) dropped.',
            stacklevel=2,
        )
        log_returns = log_returns[valid]
        signals = signals[valid]

    n_obs = len(log_returns)
    if n_obs < MIN_OBSERVATIONS:
        warnings.warn(
            f'rule_significance_test: only {n_obs} observations available. '
            f'Results may be unreliable (recommended minimum: {MIN_OBSERVATIONS}).',
            stacklevel=2,
        )

    # Detrend: subtract the mean log-return so that a rule with no edge has
    # E[return] = 0, regardless of whether the market trended during the period.
    mean_log_return = log_returns.mean()
    detrended = log_returns - mean_log_return

    # Rule returns: each signal contributes (signal × next detrended return).
    # Neutral bars (signal = 0) contribute 0 and remain in the observation count.
    rule_returns = signals * detrended
    observed_mean = float(rule_returns.mean())

    # ------------------------------------------------------------------
    # Phase 2: Bootstrap simulations
    # ------------------------------------------------------------------
    def phase2_callback(current, total):
        if progress_callback:
            # Phase 2 (bootstrap simulations) maps to the final 10%
            mapped_current = 90 + int((current / total) * 10)
            progress_callback(mapped_current, 100)

    print(
        f'Starting rule significance test (bootstrap) with '
        f'{n_simulations} simulations...'
    )

    pbar = _setup_progress_bar(progress_bar, resolved_cores, 'Simulations (bootstrap)')

    try:
        sim_means = run_bootstrap_test(
            rule_returns=rule_returns,
            observed_mean=observed_mean,
            n_simulations=n_simulations,
            cpu_cores=resolved_cores,
            random_seed=resolved_seed,
            mean_block_length=bootstrap_mean_block_length,
            pbar=pbar,
            progress_callback=phase2_callback,
        )
    finally:
        if pbar is not None:
            pbar.close()

    # p-value: fraction of simulated means that equalled or exceeded the
    # observed mean under the null hypothesis.
    p_value = float(np.mean(sim_means >= observed_mean))
    annualization = int(resolve_annualization(config))
    annualization_factor = _elapsed_annualization_factor(
        n_obs,
        int(bar_timestamps[0]),
        int(bar_timestamps[-1]),
    )

    return {
        'observed_mean': observed_mean,
        'annualized_return': observed_mean * annualization_factor,
        'annualization': annualization,
        'simulated_means': sim_means,
        'p_value': p_value,
        'n_simulations': len(sim_means),
        'n_observations': n_obs,
        'bootstrap_mean_block_length': bootstrap_mean_block_length,
    }
