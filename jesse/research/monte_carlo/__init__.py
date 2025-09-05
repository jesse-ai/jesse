"""
Aggregator for Monte Carlo package.

Re-exports:
- monte_carlo_trades: trade-order shuffle Monte Carlo (from monte_carlo_trades)
- monte_carlo_candles: candles-based Monte Carlo (from monte_carlo_candles)
- All plotting and summary functions for easy access
"""

from .monte_carlo_trades import (
    monte_carlo_trades,
    print_monte_carlo_trades_summary,
    plot_monte_carlo_trades_chart
)
from .monte_carlo_candles import (
    monte_carlo_candles,
    print_monte_carlo_candles_summary,
    plot_monte_carlo_candles_chart
)

__all__ = [
    'monte_carlo_trades',
    'monte_carlo_candles',
    'print_monte_carlo_trades_summary',
    'plot_monte_carlo_trades_chart',
    'print_monte_carlo_candles_summary',
    'plot_monte_carlo_candles_chart',
]

