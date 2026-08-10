import requests
from importlib import import_module

import pytest

from jesse import exceptions
from jesse.modes.import_candles_mode.drivers import drivers
from jesse.modes.import_candles_mode.drivers.Apex.ApexOmniPerpetualMain import (
    ApexOmniPerpetualMain,
)
from jesse.modes.import_candles_mode.drivers.Binance.BinanceMain import BinanceMain
from jesse.modes.import_candles_mode.drivers.Bitfinex.BitfinexSpot import BitfinexSpot
from jesse.modes.import_candles_mode.drivers.Bybit.BybitMain import BybitMain
from jesse.modes.import_candles_mode.drivers.Coinbase.CoinbaseSpot import CoinbaseSpot
from jesse.modes.import_candles_mode.drivers.Gate.GateSpotMain import GateSpotMain
from jesse.modes.import_candles_mode.drivers.Gate.GateUSDTMain import GateUSDTMain
from jesse.modes.import_candles_mode.drivers.Hyperliquid.HyperliquidPerpetualMain import (
    HyperliquidPerpetualMain,
)
from jesse.modes.import_candles_mode.drivers.Kraken.KrakenPerpetualMain import (
    KrakenPerpetualMain,
)
from jesse.modes.import_candles_mode.drivers.Kraken.KrakenSpotMain import KrakenSpotMain
from jesse.modes.import_candles_mode.drivers.KuCoin.KuCoinFuturesMain import (
    KuCoinFuturesMain,
)
from jesse.modes.import_candles_mode.drivers.KuCoin.KuCoinSpotMain import KuCoinSpotMain
from jesse.modes.import_candles_mode.drivers.Lighter.LighterMain import LighterMain
from jesse.modes.import_candles_mode.drivers.interface import CandleExchange


START_TIMESTAMP = 1_700_000_040_000


class FakeResponse:
    """Provide the requests.Response surface shared by the import drivers."""

    def __init__(self, payload, status_code=200, reason='OK'):
        self._payload = payload
        self.status_code = status_code
        self.reason = reason
        self.content = str(payload).encode()

    def json(self):
        return self._payload


def _mock_fetch_response(monkeypatch, driver, captured):
    """Mirror one provider schema and retain the outgoing request for assertions."""
    if isinstance(driver, BinanceMain):
        payload = [[START_TIMESTAMP, '1', '3', '0.5', '2', '4']]

        def request(url, params=None):
            captured.update(params or {})
            return FakeResponse(payload)

        monkeypatch.setattr(driver, '_make_request', request)
        return 'BTC-USDT', 'startTime', START_TIMESTAMP

    if isinstance(driver, BybitMain):
        payload = {'retMsg': 'OK', 'result': {'list': [[START_TIMESTAMP, '1', '3', '0.5', '2', '4']]}}

        def request(url, params=None, timeout=None):
            captured.update(params or {})
            return FakeResponse(payload)

        monkeypatch.setattr(driver.session, 'get', request)
        return 'BTC-USDT', 'start', START_TIMESTAMP

    if isinstance(driver, ApexOmniPerpetualMain):
        payload = {'data': {'BTCUSDT': [{
            't': START_TIMESTAMP, 'o': '1', 'c': '2', 'h': '3', 'l': '0.5', 'v': '4',
        }]}}

        def request(url, params=None):
            captured.update(params or {})
            return FakeResponse(payload)

        monkeypatch.setattr(requests, 'get', request)
        return 'BTC-USDT', 'start', START_TIMESTAMP // 1000

    if isinstance(driver, GateUSDTMain):
        payload = [{'t': START_TIMESTAMP // 1000, 'o': '1', 'c': '2', 'h': '3', 'l': '0.5', 'v': '4'}]

        def request(url, params=None, timeout=None):
            captured.update(params or {})
            return FakeResponse(payload)

        monkeypatch.setattr(driver.session, 'get', request)
        return 'BTC-USDT', 'from', START_TIMESTAMP // 1000

    if isinstance(driver, GateSpotMain):
        payload = [[str(START_TIMESTAMP // 1000), '4', '2', '3', '0.5', '1']]

        def request(url, params=None):
            captured.update(params or {})
            return FakeResponse(payload)

        monkeypatch.setattr(requests, 'get', request)
        return 'BTC-USDT', 'from', START_TIMESTAMP // 1000

    if isinstance(driver, HyperliquidPerpetualMain):
        driver.all_org_symbols = {'BTC-USD': 'BTC'}
        payload = [{'t': START_TIMESTAMP, 'o': '1', 'c': '2', 'h': '3', 'l': '0.5', 'v': '4'}]

        def request(url, json=None, headers=None):
            captured.update((json or {}).get('req', {}))
            return FakeResponse(payload)

        monkeypatch.setattr(requests, 'post', request)
        return 'BTC-USD', 'startTime', START_TIMESTAMP

    if isinstance(driver, LighterMain):
        driver._market_ids = {'BTC-USD': 1}
        payload = {'c': [{
            't': START_TIMESTAMP, 'o': '1', 'c': '2', 'h': '3', 'l': '0.5', 'v': '4',
        }]}

        def request(url, params=None):
            captured.update(params or {})
            return FakeResponse(payload)

        monkeypatch.setattr(requests, 'get', request)
        return 'BTC-USD', 'start_timestamp', START_TIMESTAMP

    if isinstance(driver, KuCoinFuturesMain):
        payload = [[START_TIMESTAMP, '1', '3', '0.5', '2', '4']]

        def request(params):
            captured.update(params)
            return payload

        monkeypatch.setattr(driver, '_request', request)
        return 'BTC-USDT', 'from', START_TIMESTAMP

    if isinstance(driver, KuCoinSpotMain):
        payload = [[str(START_TIMESTAMP // 1000), '1', '2', '3', '0.5', '4', '8']]

        def request(params):
            captured.update(params)
            return payload

        monkeypatch.setattr(driver, '_request', request)
        return 'BTC-USDT', 'startAt', START_TIMESTAMP // 1000

    if isinstance(driver, KrakenPerpetualMain):
        payload = {'candles': [{
            'time': START_TIMESTAMP, 'open': '1', 'close': '2', 'high': '3',
            'low': '0.5', 'volume': '4',
        }]}

        def request(url, params=None, timeout=None):
            captured.update(params or {})
            return FakeResponse(payload)

        monkeypatch.setattr(driver.session, 'get', request)
        return 'BTC-USD', 'from', START_TIMESTAMP // 1000

    if isinstance(driver, KrakenSpotMain):
        driver._altname_cache = {'BTC-USD': 'XBTUSD'}
        payload = {
            'error': [],
            'result': {
                'XXBTZUSD': [[START_TIMESTAMP // 1000, '1', '3', '0.5', '2', '1.5', '4', 1]],
                'last': START_TIMESTAMP // 1000,
            },
        }

        def request(url, params=None, timeout=None):
            captured.update(params or {})
            return FakeResponse(payload)

        monkeypatch.setattr(driver.session, 'get', request)
        return 'BTC-USD', 'since', START_TIMESTAMP // 1000

    if isinstance(driver, BitfinexSpot):
        driver.all_unique_symbols = {'BTC-USD': 'BTCUSD'}
        payload = [[START_TIMESTAMP, 1, 2, 3, 0.5, 4]]

        def request(url, params=None):
            captured.update(params or {})
            return FakeResponse(payload)

        monkeypatch.setattr(driver, '_make_request', request)
        return 'BTC-USD', 'start', START_TIMESTAMP

    if isinstance(driver, CoinbaseSpot):
        payload = {'candles': [{
            'start': START_TIMESTAMP // 1000, 'open': '1', 'close': '2',
            'high': '3', 'low': '0.5', 'volume': '4',
        }]}

        def request(url, params=None):
            captured.update(params or {})
            return FakeResponse(payload)

        monkeypatch.setattr(requests, 'get', request)
        return 'BTC-USD', 'start', START_TIMESTAMP // 1000

    raise AssertionError(f'No mocked provider contract for {type(driver).__name__}')


@pytest.mark.parametrize('driver_class', drivers.values(), ids=drivers.keys())
def test_registered_driver_fetch_contract(monkeypatch, driver_class):
    driver = driver_class()
    captured = {}
    symbol, start_key, expected_start = _mock_fetch_response(monkeypatch, driver, captured)

    candles = driver.fetch(symbol, START_TIMESTAMP, timeframe='1m')

    assert len(candles) == 1
    assert candles[0].keys() == {
        'id', 'exchange', 'symbol', 'timeframe', 'timestamp',
        'open', 'close', 'high', 'low', 'volume',
    }
    assert candles[0] | {'id': '<generated>'} == {
        'id': '<generated>',
        'exchange': driver.name,
        'symbol': symbol,
        'timeframe': '1m',
        'timestamp': START_TIMESTAMP,
        'open': 1.0,
        'close': 2.0,
        'high': 3.0,
        'low': 0.5,
        'volume': 4.0,
    }
    assert captured[start_key] == expected_start


@pytest.mark.parametrize(
    ('status_code', 'exception_type'),
    [
        (400, ValueError),
        (404, ValueError),
        (429, ConnectionError),
        (502, exceptions.ExchangeInMaintenance),
        (503, ConnectionError),
    ],
)
def test_driver_http_error_contract(status_code, exception_type):
    response = FakeResponse({}, status_code=status_code, reason='provider error')

    with pytest.raises(exception_type):
        CandleExchange.validate_response(response)


def test_kucoin_exchange_rate_limit_is_bounded(monkeypatch):
    driver = drivers['KuCoin Spot']()
    attempts = []

    def request(url, params=None, timeout=None):
        attempts.append(params)
        return FakeResponse({'code': '429000', 'msg': 'too many requests'})

    monkeypatch.setattr(driver.session, 'get', request)
    kucoin_spot_module = import_module(
        'jesse.modes.import_candles_mode.drivers.KuCoin.KuCoinSpotMain'
    )
    monkeypatch.setattr(kucoin_spot_module.time, 'sleep', lambda _: None)

    with pytest.raises(ConnectionError, match='rate limited'):
        driver.fetch('BTC-USDT', START_TIMESTAMP)

    assert len(attempts) == 4


def test_bybit_rejects_provider_symbol_error(monkeypatch):
    driver = drivers['Bybit Spot']()
    monkeypatch.setattr(
        driver.session,
        'get',
        lambda *args, **kwargs: FakeResponse({'retMsg': 'symbol invalid', 'result': {'list': []}}),
    )

    with pytest.raises(exceptions.SymbolNotFound, match='symbol invalid'):
        driver.fetch('NOT-REAL', START_TIMESTAMP)


@pytest.mark.parametrize(
    ('payload', 'exception_type'),
    [
        ({'msg': 'temporarily unavailable'}, exceptions.ExchangeInMaintenance),
        ({'data': {}}, exceptions.InvalidSymbol),
    ],
)
def test_apex_rejects_malformed_or_unsupported_responses(monkeypatch, payload, exception_type):
    driver = drivers['Apex Omni Perpetual']()
    monkeypatch.setattr(requests, 'get', lambda *args, **kwargs: FakeResponse(payload))

    with pytest.raises(exception_type):
        driver.fetch('BTC-USDT', START_TIMESTAMP)


def test_futures_driver_page_sizes_match_live_provider_limits():
    assert drivers['Kraken Pro Futures']().count == 2_000
    assert drivers['KuCoin USDT Perpetual']().count == 200
