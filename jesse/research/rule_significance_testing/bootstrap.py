"""Stationary-bootstrap significance test for a rule-return time series."""

import numpy as np


def run_bootstrap_test(
    rule_returns: np.ndarray,
    observed_mean: float,
    n_simulations: int,
    cpu_cores: int,
    random_seed: int,
    pbar=None,
    progress_callback=None,
    mean_block_length: int = 10,
) -> np.ndarray:
    """
    Resample random-length contiguous blocks and return the simulated means.

    The stationary bootstrap preserves local serial dependence in the
    rule-return series. Its block lengths are geometrically distributed; a
    mean of 10 observations matches the conventional value used for weakly
    dependent financial returns while keeping the public API deterministic.

    Parameters
    ----------
    progress_callback : callable(batch_index, total_batches) or None
        Called each time a batch completes. batch_index is 1-based.
    """
    if mean_block_length < 1:
        raise ValueError('mean_block_length must be at least 1')

    centered = np.asarray(rule_returns, dtype=np.float64) - observed_mean
    n = len(centered)
    if n == 0:
        return np.array([], dtype=np.float64)

    # Keep one random stream across every batch so changing the batch count
    # cannot change a seeded experiment's bootstrap samples.
    rng = np.random.default_rng(random_seed)

    # We split into batches equal to the `cpu_cores` parameter to maintain
    # compatibility with the progress bar initialized in rule_significance.py
    # which expects exactly `cpu_cores` updates.
    batch_sizes = _split_into_batches(n_simulations, max(1, cpu_cores))
    total_batches = len(batch_sizes)

    simulated_means = np.empty(n_simulations, dtype=np.float64)
    completed = 0
    simulation_index = 0
    restart_probability = 1 / mean_block_length
    observation_indices = np.arange(n)

    for batch_size in batch_sizes:
        for _ in range(batch_size):
            # Every restart begins a new block at a uniformly sampled source
            # index. Between restarts the source index advances normally,
            # wrapping at the end so the resample remains stationary.
            restarts = np.empty(n, dtype=np.bool_)
            restarts[0] = True
            restarts[1:] = rng.random(n - 1) < restart_probability
            restart_positions = np.flatnonzero(restarts)
            block_starts = rng.integers(0, n, size=len(restart_positions))
            block_ids = np.cumsum(restarts) - 1
            offsets = observation_indices - restart_positions[block_ids]
            sampled_indices = (block_starts[block_ids] + offsets) % n
            simulated_means[simulation_index] = centered[sampled_indices].mean()
            simulation_index += 1

        completed += 1
        if pbar is not None:
            pbar.update(1)
        if progress_callback is not None:
            try:
                progress_callback(completed, total_batches)
            except Exception:
                pass

    return simulated_means


def _split_into_batches(n: int, k: int) -> list:
    """Divide n simulations into k roughly equal integer batches."""
    base, extra = divmod(n, k)
    return [base + (1 if i < extra else 0) for i in range(k)]
