"""
Shared constants and small utilities for the rule-significance-testing package.
"""
from multiprocessing import cpu_count

from jesse.constants import TIMEFRAME_TO_ONE_MINUTES

# ---------------------------------------------------------------------------
# Multiprocessing
# ---------------------------------------------------------------------------
DEFAULT_CPU_USAGE_RATIO = 0.8   # fraction of available CPU cores used by default
MIN_CPU_CORES = 1                # never spawn fewer than 1 worker

# ---------------------------------------------------------------------------
# Statistical / financial
# ---------------------------------------------------------------------------
TRADING_DAYS_PER_YEAR = 365     # crypto markets trade 24/7, 365 days a year
MIN_OBSERVATIONS = 30           # warn user when fewer bars are available


def _annualization_factor(timeframe: str) -> float:
    """Return the number of bars in a 365-day crypto year."""
    minutes_per_year = TRADING_DAYS_PER_YEAR * 24 * 60
    return minutes_per_year / TIMEFRAME_TO_ONE_MINUTES[timeframe]

# ---------------------------------------------------------------------------
# Progress bar
# ---------------------------------------------------------------------------

def _setup_progress_bar(enabled: bool, total: int, description: str):
    """Return a tqdm progress bar (notebook-aware) or None."""
    if not enabled:
        return None
    try:
        import jesse.helpers as jh
        if jh.is_notebook():
            from tqdm.notebook import tqdm
        else:
            from tqdm import tqdm
    except Exception:
        from tqdm import tqdm
    return tqdm(total=total, desc=description)


def _resolve_cpu_cores(cpu_cores):
    """Return a validated cpu_cores value, defaulting to 80 % of available."""
    available = cpu_count()
    if cpu_cores is None:
        return max(MIN_CPU_CORES, int(available * DEFAULT_CPU_USAGE_RATIO))
    return max(MIN_CPU_CORES, min(cpu_cores, available))
