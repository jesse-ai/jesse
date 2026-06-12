"""
Rule significance testing package for Jesse research module.

Tests whether a trading rule has genuine predictive power.

Public API
----------
rule_significance_test  – run bootstrap significance test
plot_significance_test  – visualise the sampling distribution
"""

from .rule_significance import rule_significance_test
from .plots import plot_significance_test

__all__ = [
    'rule_significance_test',
    'plot_significance_test',
]
