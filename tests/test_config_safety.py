"""
Regression tests for normalize_settings_sections() — the guard that keeps
/config/get from ever raising KeyError on a malformed or partially stored config.

Background: a get->update round-trip could double-wrap the stored config under a
stray "data" key (stored as {"data": {backtest, live, optimization}}). The old
get_config() then did data['backtest']['exchanges'] unconditionally and returned
an HTTP 500 ("KeyError: 'backtest'"), which blocked every MCP backtest. The
normalize step unwraps that and guarantees the indexed sections exist.

These tests target the pure normalize_settings_sections() function, so they touch
no global state. The companion fix in set_config() (accepting the dict-keyed
`exchanges` map the API/MCP send, falling back to the dict key when an inner
"name" is absent) is exercised end-to-end by every backtest / RST / Monte Carlo /
optimization run, all of which go through set_config().
"""
import copy

from jesse.modes.data_provider import normalize_settings_sections


def _full_config():
    return {
        'backtest': {'exchanges': {'Binance Spot': {'fee': 0.001}}, 'warm_up_candles': 240},
        'live': {'exchanges': {'Binance Spot': {'fee': 0.001}}},
        'optimization': {'cpu_cores': 2},
    }


def test_normalize_leaves_valid_config_untouched():
    cfg = _full_config()
    out = normalize_settings_sections(copy.deepcopy(cfg))
    assert out == cfg


def test_normalize_unwraps_double_wrapped_config():
    inner = _full_config()
    wrapped = {'data': copy.deepcopy(inner)}
    out = normalize_settings_sections(wrapped)
    assert 'data' not in out
    assert out['backtest']['exchanges'] == inner['backtest']['exchanges']
    assert out['optimization'] == inner['optimization']


def test_normalize_does_not_unwrap_when_sections_present_at_top():
    # A valid config that also carries an unrelated 'data' key must NOT be unwrapped.
    cfg = _full_config()
    cfg['data'] = {'backtest': {'exchanges': {'WRONG': {}}}}
    out = normalize_settings_sections(copy.deepcopy(cfg))
    assert out['backtest']['exchanges'] == {'Binance Spot': {'fee': 0.001}}


def test_normalize_backfills_missing_sections():
    out = normalize_settings_sections({})
    for s in ('backtest', 'live', 'optimization'):
        assert isinstance(out[s], dict)
    assert out['backtest']['exchanges'] == {}
    assert out['live']['exchanges'] == {}


def test_normalize_coerces_null_sections():
    out = normalize_settings_sections({'backtest': None, 'live': None, 'optimization': None})
    assert out['backtest']['exchanges'] == {}
    assert out['live']['exchanges'] == {}
    assert isinstance(out['optimization'], dict)


def test_normalize_handles_non_dict_input():
    for bad in (None, [], 'nope', 42):
        out = normalize_settings_sections(bad)
        assert out['backtest']['exchanges'] == {}
        assert out['live']['exchanges'] == {}
        assert isinstance(out['optimization'], dict)


def test_normalize_preserves_partial_section_contents():
    out = normalize_settings_sections({'backtest': {'warm_up_candles': 100}})
    assert out['backtest']['warm_up_candles'] == 100
    assert out['backtest']['exchanges'] == {}


def test_normalize_is_idempotent():
    once = normalize_settings_sections({'data': _full_config()})
    twice = normalize_settings_sections(copy.deepcopy(once))
    assert once == twice


def test_normalize_reproduces_the_original_500_shape():
    # Exact shape that caused the production 500: the real sections nested under "data".
    out = normalize_settings_sections({'data': _full_config()})
    # The line that used to crash — data['backtest']['exchanges'] — now succeeds:
    assert list(out['backtest']['exchanges'].keys()) == ['Binance Spot']
