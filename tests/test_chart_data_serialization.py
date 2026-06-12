import json
import math

import numpy as np
import pytest

import jesse.helpers as jh


# This mirrors what Starlette's JSONResponse does internally: it renders with
# `allow_nan=False`, which raises `ValueError: Out of range float values are not
# JSON compliant` if NaN / Infinity / -Infinity reach the encoder. The
# `/backtest/sessions/{id}/chart-data` endpoint hit exactly this when a strategy's
# `after()` produced NaN values for a custom chart line (GitHub issue #563).
def _render_like_jsonresponse(content):
    return json.dumps(content, ensure_ascii=False, allow_nan=False)


def _sample_chart_data():
    """
    Approximates the structure assembled in backtest_mode for the frontend:
    custom lines added from a strategy's `after()` hook may legitimately contain
    NaN (e.g. an indicator that is not warmed up yet) or +/-inf (e.g. division
    by zero).
    """
    return {
        'add_line_to_candle_chart': {
            'my_line': [
                {'time': 1, 'value': 10.0},
                {'time': 2, 'value': float('nan')},
                {'time': 3, 'value': float('inf')},
                {'time': 4, 'value': float('-inf')},
                {'time': 5, 'value': np.float64('nan')},
                {'time': 6, 'value': 20.5},
            ]
        },
        'add_extra_line_chart': [np.float64('nan'), 1.0, np.int64(3)],
        'flag': True,
    }


def test_raw_chart_data_with_nan_is_not_json_compliant():
    """Without sanitizing, the data reproduces the issue #563 failure."""
    raw = _sample_chart_data()
    with pytest.raises(ValueError):
        _render_like_jsonresponse(raw)


def test_cleaned_chart_data_is_json_compliant():
    """
    The chart-data endpoint must strip BOTH NaN and infinite values before
    handing the payload to JSONResponse. `clean_infinite_values` alone leaves
    NaN behind, which was the root cause of issue #563.
    """
    raw = _sample_chart_data()

    # Exactly the composition the controller now applies.
    cleaned = jh.clean_nan_values(jh.clean_infinite_values(raw))

    # Must not raise anymore.
    serialized = _render_like_jsonresponse(cleaned)
    reloaded = json.loads(serialized)

    line = reloaded['add_line_to_candle_chart']['my_line']
    assert line[0]['value'] == 10.0          # untouched valid float
    assert line[1]['value'] is None          # NaN -> None
    assert line[2]['value'] is None          # +inf -> None
    assert line[3]['value'] is None          # -inf -> None
    assert line[4]['value'] is None          # numpy NaN -> None
    assert line[5]['value'] == 20.5          # untouched valid float

    extra = reloaded['add_extra_line_chart']
    assert extra[0] is None                  # numpy NaN -> None
    assert extra[1] == 1.0
    assert extra[2] == 3                      # numpy int preserved
    assert reloaded['flag'] is True          # bool preserved (not coerced to int)


def test_clean_infinite_values_alone_leaves_nan():
    """Regression guard documenting why both cleaners are required."""
    only_inf_cleaned = jh.clean_infinite_values({'v': float('nan')})
    assert math.isnan(only_inf_cleaned['v'])
    with pytest.raises(ValueError):
        _render_like_jsonresponse(only_inf_cleaned)
