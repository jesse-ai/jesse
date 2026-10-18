import pytest

import jesse.helpers as jh
from jesse.config import config, reset_config, set_config


def paper_session_config(**backup_checks):
    return {
        'warm_up_candles': 210,
        'logging': {},
        'exchanges': {'Binance Perpetual Futures': {
            'fee': 0.0004, 'balance': 10_000, 'type': 'futures', 'futures_leverage': 1,
            'futures_leverage_mode': 'cross',
        }},
        'notifications': {'enabled': False},
        'persistency': True,
        'generate_candles_from_1m': False,
        **backup_checks,
    }


@pytest.fixture
def paper_mode():
    reset_config()
    config['app']['trading_mode'] = 'papertrade'
    jh.clear_config_caches()
    yield
    reset_config()


def test_a_session_sets_its_own_backup_check_intervals(paper_mode):
    set_config(paper_session_config(order_backup_check_seconds=60, candle_backup_refresh_seconds=90))

    assert config['env']['data']['order_backup_check_seconds'] == 60
    assert config['env']['data']['candle_backup_refresh_seconds'] == 90


def test_zero_turns_a_check_off(paper_mode):
    set_config(paper_session_config(order_backup_check_seconds=0, candle_backup_refresh_seconds=0))

    assert config['env']['data']['order_backup_check_seconds'] == 0
    # 0 (off) must stay distinct from None (automatic).
    assert config['env']['data']['candle_backup_refresh_seconds'] == 0


@pytest.mark.parametrize('backup_checks', [
    {},  # a session saved before these settings existed
    {'order_backup_check_seconds': None, 'candle_backup_refresh_seconds': None},
    {'order_backup_check_seconds': '', 'candle_backup_refresh_seconds': ''},
])
def test_missing_or_empty_intervals_keep_the_previous_behavior(paper_mode, backup_checks):
    set_config(paper_session_config(**backup_checks))

    assert config['env']['data']['order_backup_check_seconds'] == 10
    # None means the automatic candle interval: 5 seconds plus 1 per symbol.
    assert config['env']['data']['candle_backup_refresh_seconds'] is None
