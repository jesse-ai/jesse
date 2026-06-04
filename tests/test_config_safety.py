"""
Regression tests for the config-handling fixes:

1. normalize_settings_sections() — guards /config/get so a malformed or partially
   stored config can never raise KeyError (previously surfaced as an HTTP 500
   "KeyError: 'backtest'" when the stored config was double-wrapped under a stray
   "data" key by a get->update round-trip).

2. set_config() — must accept the dict-keyed `exchanges` map that the API/MCP send
   (keyed by exchange name, with no redundant inner "name"). A missing "name" used
   to raise KeyError deep inside a spawned backtest/RST worker, which then exited
   silently, leaving the session stuck.
"""
import copy

from jesse.config import config, reset_config, set_config
from jesse.modes.data_provider import normalize_settings_sections


def _full_config():
    return {
        'backtest': {'exchanges': {'Binance Spot': {'fee': 0.001}}, 'warm_up_candles': 240},
        'live': {'exchanges': {'Binance Spot': {'fee': 0.001}}},
        'optimization': {'cpu_cores': 2},
    }


# ---------------------------------------------------------------------------
# normalize_settings_sections
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# set_config
# ---------------------------------------------------------------------------

def test_set_config_accepts_dict_keyed_exchanges_without_name():
    reset_config()
    config['app']['trading_mode'] = 'backtest'
    try:
        conf = {
            'warm_up_candles': 240,
            'logging': {},
            'exchanges': {
                'Binance Perpetual Futures': {
                    'fee': 0.0006, 'type': 'futures', 'balance': 10000,
                    'futures_leverage': 2, 'futures_leverage_mode': 'cross',
                }
            },
        }
        set_config(conf)  # must NOT raise KeyError: 'name'
        ex = config['env']['exchanges']['Binance Perpetual Futures']
        assert ex['fee'] == 0.0006
        assert ex['type'] == 'futures'
        assert ex['balance'] == 10000
        assert ex['futures_leverage'] == 2
        assert ex['futures_leverage_mode'] == 'cross'
    finally:
        reset_config()


def test_set_config_prefers_explicit_name_over_key():
    reset_config()
    config['app']['trading_mode'] = 'backtest'
    try:
        conf = {
            'warm_up_candles': 210,
            'logging': {},
            'exchanges': {
                'ignored_key': {
                    'name': 'Binance Spot', 'fee': 0.001, 'type': 'spot', 'balance': 5000,
                }
            },
        }
        set_config(conf)
        # When an explicit 'name' is provided (dashboard format) it wins; the dict
        # key is not used as the exchange name.
        assert 'Binance Spot' in config['env']['exchanges']
        assert 'ignored_key' not in config['env']['exchanges']
    finally:
        reset_config()
