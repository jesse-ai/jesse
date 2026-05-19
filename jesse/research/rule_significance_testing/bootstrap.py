"""
Bootstrap significance test.

Core idea: randomise the *return values* themselves (not their timing) to
simulate what chance alone could produce.

Steps
-----
1. Zero-centre the rule's daily returns by subtracting the observed mean.
   This enforces H0: the rule has no edge (expected return = 0).
2. Resample the zero-centred returns with replacement N times and compute
   the mean of each resample → the bootstrap sampling distribution.
3. p-value = fraction of simulated means ≥ the observed mean.
"""

import numpy as np


def run_bootstrap_test(
    rule_returns: np.ndarray,
    observed_mean: float,
    n_simulations: int,
    cpu_cores: int,
    random_seed: int,
    pbar=None,
    progress_callback=None,
) -> np.ndarray:
    """
    Run bootstrap simulations synchronously and return the full
    array of simulated means.

    Parameters
    ----------
    progress_callback : callable(batch_index, total_batches) or None
        Called each time a batch completes. batch_index is 1-based.
    """
    centered = rule_returns - observed_mean
    
    # We split into batches equal to the `cpu_cores` parameter to maintain 
    # compatibility with the progress bar initialized in rule_significance.py
    # which expects exactly `cpu_cores` updates.
    batch_sizes = _split_into_batches(n_simulations, max(1, cpu_cores))
    total_batches = len(batch_sizes)

    parts = []
    completed = 0
    
    for i, batch_size in enumerate(batch_sizes):
        if batch_size == 0:
            completed += 1
            if pbar is not None:
                pbar.update(1)
            if progress_callback is not None:
                try:
                    progress_callback(completed, total_batches)
                except Exception:
                    pass
            continue
            
        rng = np.random.default_rng(random_seed + i)
        n = len(centered)
        
        # Resample and compute means for this batch
        idx = rng.integers(0, n, size=(batch_size, n))
        batch_means = centered[idx].mean(axis=1)
        parts.append(batch_means)
        
        completed += 1
        if pbar is not None:
            pbar.update(1)
        if progress_callback is not None:
            try:
                progress_callback(completed, total_batches)
            except Exception:
                pass

    return np.concatenate(parts) if parts else np.array([])


def _split_into_batches(n: int, k: int) -> list:
    """Divide n simulations into k roughly equal integer batches."""
    base, extra = divmod(n, k)
    return [base + (1 if i < extra else 0) for i in range(k)]