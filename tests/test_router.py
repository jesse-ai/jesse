from unittest.mock import Mock

import pytest

import jesse.helpers as jh
from jesse import exceptions
from jesse.config import config, reset_config
from jesse.enums import exchanges, timeframes
from jesse.routes import router
from jesse.services.validators import validate_routes


@pytest.fixture(autouse=True)
def _reset_router_and_config() -> None:
    """Give each router contract a clean singleton and configuration object."""
    reset_config()
    router._reset()
    yield
    router._reset()
    reset_config()


def _route(
        symbol: str,
        timeframe: str = timeframes.MINUTE_5,
        exchange: str = exchanges.SANDBOX,
        strategy: str = 'Test19',
) -> dict:
    return {
        'exchange': exchange,
        'symbol': symbol,
        'timeframe': timeframe,
        'strategy': strategy,
    }


def _data_route(
        symbol: str,
        timeframe: str,
        exchange: str = exchanges.SANDBOX,
) -> dict:
    return {
        'exchange': exchange,
        'symbol': symbol,
        'timeframe': timeframe,
    }


def test_routes_populate_trading_and_considering_config() -> None:
    trading_routes = [
        _route('ETH-USD', timeframes.HOUR_3),
        _route('BTC-USD', timeframes.MINUTE_15),
    ]
    data_routes = [
        _data_route('EOS-USD', timeframes.HOUR_3),
        _data_route('EOS-USD', timeframes.HOUR_1),
    ]

    router.initiate(trading_routes, data_routes)

    assert set(config['app']['trading_exchanges']) == {exchanges.SANDBOX}
    assert set(config['app']['trading_symbols']) == {'BTC-USD', 'ETH-USD'}
    assert set(config['app']['trading_timeframes']) == {timeframes.HOUR_3, timeframes.MINUTE_15}
    assert set(config['app']['considering_exchanges']) == {exchanges.SANDBOX}
    assert set(config['app']['considering_symbols']) == {'BTC-USD', 'ETH-USD', 'EOS-USD'}
    assert set(config['app']['considering_timeframes']) == {
        timeframes.MINUTE_1,
        timeframes.MINUTE_15,
        timeframes.HOUR_1,
        timeframes.HOUR_3,
    }


def test_duplicate_trading_pair_is_rejected_across_timeframes() -> None:
    trading_routes = [
        _route('BTC-USDT', timeframes.MINUTE_5),
        _route('BTC-USDT', timeframes.HOUR_1),
    ]

    with pytest.raises(exceptions.InvalidRoutes, match='each exchange-symbol pair can be traded only once'):
        router.initiate(trading_routes)


def test_trading_routes_with_different_quote_assets_are_rejected() -> None:
    trading_routes = [
        _route('BTC-USDT'),
        _route('ETH-USDC'),
    ]

    with pytest.raises(exceptions.InvalidRoutes, match='All trading routes must have the same quote asset'):
        router.initiate(trading_routes)


def test_missing_strategy_is_rejected_with_its_name() -> None:
    strategy_name = 'StrategyThatDoesNotExist'

    with pytest.raises(exceptions.InvalidRoutes, match=strategy_name):
        router.initiate([_route('BTC-USDT', strategy=strategy_name)])


def test_empty_routes_reach_the_public_route_validator() -> None:
    router.initiate([], [])

    with pytest.raises(exceptions.InvalidRoutes, match='No routes found'):
        validate_routes(router)


def test_trading_data_overlap_and_multiple_exchanges_are_preserved() -> None:
    trading_routes = [
        _route('BTC-USDT', timeframes.MINUTE_5),
        _route('ETH-USDT', timeframes.MINUTE_15, exchange=exchanges.BINANCE_SPOT),
    ]
    data_routes = [
        _data_route('BTC-USDT', timeframes.HOUR_1),
        _data_route('SOL-USDT', timeframes.HOUR_3, exchange=exchanges.BINANCE_SPOT),
    ]

    router.initiate(trading_routes, data_routes)

    assert set(config['app']['considering_candles']) == {
        (exchanges.SANDBOX, 'BTC-USDT'),
        (exchanges.BINANCE_SPOT, 'ETH-USDT'),
        (exchanges.BINANCE_SPOT, 'SOL-USDT'),
    }
    assert set(config['app']['considering_exchanges']) == {
        exchanges.SANDBOX,
        exchanges.BINANCE_SPOT,
    }
    assert set(config['app']['considering_timeframes']) == {
        timeframes.MINUTE_1,
        timeframes.MINUTE_5,
        timeframes.MINUTE_15,
        timeframes.HOUR_1,
        timeframes.HOUR_3,
    }


def test_formatted_routes_preserve_input_order_and_shape() -> None:
    trading_routes = [
        _route('ETH-USDT', timeframes.MINUTE_15, exchange=exchanges.BINANCE_SPOT),
        _route('BTC-USDT', timeframes.MINUTE_5),
    ]
    data_routes = [
        _data_route('SOL-USDT', timeframes.HOUR_1, exchange=exchanges.BINANCE_SPOT),
    ]

    router.initiate(trading_routes, data_routes)

    assert router.formatted_routes == trading_routes
    assert router.formatted_data_routes == data_routes
    assert router.all_formatted_routes == trading_routes + data_routes
    assert router.trading_routes_count == 2
    assert router.data_routes_count == 1
    assert router.all_routes_count == 3


def test_reinitializing_routes_replaces_previous_session_state() -> None:
    router.initiate(
        [
            _route('BTC-USDT', timeframes.MINUTE_5),
            _route('ETH-USDT', timeframes.MINUTE_15, exchange=exchanges.BINANCE_SPOT),
        ],
        [_data_route('SOL-USDT', timeframes.HOUR_1, exchange=exchanges.BINANCE_SPOT)],
    )

    next_routes = [_route('XRP-USDT', timeframes.HOUR_3)]
    router.initiate(next_routes)

    assert router.formatted_routes == next_routes
    assert router.formatted_data_routes == []
    assert config['app']['trading_exchanges'] == (exchanges.SANDBOX,)
    assert config['app']['trading_symbols'] == ('XRP-USDT',)
    assert config['app']['trading_timeframes'] == (timeframes.HOUR_3,)
    assert config['app']['considering_candles'] == ((exchanges.SANDBOX, 'XRP-USDT'),)
    assert config['app']['considering_exchanges'] == (exchanges.SANDBOX,)
    assert config['app']['considering_symbols'] == ('XRP-USDT',)
    assert set(config['app']['considering_timeframes']) == {
        timeframes.MINUTE_1,
        timeframes.HOUR_3,
    }


def test_reinitialized_non_live_route_gets_its_own_sandbox_driver() -> None:
    first_exchange = 'First Research Exchange'
    second_exchange = 'Second Research Exchange'
    router.initiate([_route('BTC-USDT', exchange=first_exchange)])

    from jesse.services.api import api
    from jesse.services.broker import Broker

    try:
        api.initiate_driver(first_exchange)
        router.initiate([_route('ETH-USDT', exchange=second_exchange)])

        # Broker construction is the point at which a strategy route becomes
        # capable of submitting orders through the process-wide API service.
        broker = Broker(Mock(), second_exchange, 'ETH-USDT', timeframes.MINUTE_5)

        assert broker.api.drivers[first_exchange].name == first_exchange
        assert broker.api.drivers[second_exchange].name == second_exchange
    finally:
        api.drivers.pop(first_exchange, None)
        api.drivers.pop(second_exchange, None)


def test_reset_config_restores_nested_defaults_without_replacing_the_object() -> None:
    config_reference = config
    config['env']['data']['warmup_candles_num'] = 999
    config['env']['exchanges'][exchanges.SANDBOX]['balance'] = 123
    config['app']['considering_symbols'] = ('BTC-USDT',)

    reset_config()

    assert config is config_reference
    assert config['env']['data']['warmup_candles_num'] == 240
    assert config['env']['exchanges'][exchanges.SANDBOX]['balance'] == 10_000
    assert config['app']['considering_symbols'] == []


def test_reset_config_clears_values_cached_from_the_previous_mode() -> None:
    config['app']['trading_mode'] = 'papertrade'
    # Pytest reads config fresh, so seed the cache state used by normal runtime
    # processes directly.
    jh.CACHED_CONFIG['env.data.warmup_candles_num'] = 999

    assert jh.app_mode() == 'papertrade'
    assert jh.is_live() is True
    assert jh.is_paper_trading() is True

    reset_config()

    assert jh.CACHED_CONFIG == {}
    assert jh.app_mode() == ''
    assert jh.is_live() is False
    assert jh.is_paper_trading() is False
