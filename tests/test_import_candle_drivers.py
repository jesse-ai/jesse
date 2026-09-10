import requests
from importlib import import_module

import pytest

from jesse import exceptions
from jesse.modes.import_candles_mode.drivers import drivers
from jesse.modes.import_candles_mode.drivers.Apex.ApexOmniPerpetualMain import (
    ApexOmniPerpetualMain,
)
from jesse.modes.import_candles_mode.drivers.Alpaca.AlpacaStocksMain import AlpacaStocksMain
from jesse.modes.import_candles_mode.drivers.Alpaca.alpaca_utils import ms_to_rfc3339
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
from jesse.services.historical_data import HistoricalCandleRange, HistoricalCandleRequest


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

    if isinstance(driver, AlpacaStocksMain):
        # bars are keyed by ticker; `t` is the RFC3339 bar start (UTC)
        driver._feed = 'iex'
        driver._headers = {}
        payload = {'bars': {'BTC': [{
            't': ms_to_rfc3339(START_TIMESTAMP), 'o': '1', 'h': '3', 'l': '0.5', 'c': '2', 'v': '4',
        }]}}

        def request(url, params):
            captured.update(params or {})
            return payload

        monkeypatch.setattr(driver, '_get', request)
        return 'BTC-USD', 'start', ms_to_rfc3339(START_TIMESTAMP)

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


@pytest.mark.parametrize('driver_class', drivers.values(), ids=drivers.keys())
def test_registered_driver_normalized_fetch_contract(monkeypatch, driver_class):
    driver = driver_class()
    captured = {}
    symbol, start_key, expected_start = _mock_fetch_response(monkeypatch, driver, captured)
    request = HistoricalCandleRequest(
        symbol=symbol,
        timeframe='1m',
        requested_range=HistoricalCandleRange(
            START_TIMESTAMP,
            START_TIMESTAMP + driver.count * 60_000,
        ),
    )

    batch = driver.fetch_candles(request)

    assert batch.request == request
    assert len(batch.candles) == 1
    candle = batch.candles[0]
    assert (
        candle.timestamp,
        candle.open,
        candle.close,
        candle.high,
        candle.low,
        candle.volume,
    ) == (START_TIMESTAMP, 1.0, 2.0, 3.0, 0.5, 4.0)
    assert batch.continuation_token is None
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


def test_binance_starting_time_is_the_exact_first_minute_candle(monkeypatch):
    # regression: the weekly lookup skipped the listing week and returned a future date for
    # symbols listed within the last seven days, which made their imports fail outright.
    driver = drivers['Binance Perpetual Futures']()
    captured = {}
    listing = 1_775_483_400_000  # 2026-04-06 13:50 UTC

    def request(url, params=None):
        captured.update(params or {})
        return FakeResponse([[listing, '1', '3', '0.5', '2', '4', listing + 59_999]])

    monkeypatch.setattr(driver, '_make_request', request)

    assert driver.get_starting_time('AAPL-USDT') == listing
    assert captured == {'interval': '1m', 'symbol': 'AAPLUSDT', 'startTime': 0, 'limit': 1}

    monkeypatch.setattr(driver, '_make_request', lambda url, params=None: FakeResponse([]))
    assert driver.get_starting_time('AAPL-USDT') is None
    request_range = HistoricalCandleRange(1_700_000_000_000, 1_800_000_000_000)
    assert driver.find_earliest_available_timestamp(
        HistoricalCandleRequest('AAPL-USDT', '1m', request_range)
    ) == request_range.start_timestamp


def test_bybit_starting_time_is_the_first_minute_candle(monkeypatch):
    driver = drivers['Bybit USDT Perpetual']()
    captured = {}
    listing = 1_585_132_560_000

    def request(url, params=None, timeout=None):
        captured.update(params or {})
        return FakeResponse({'retMsg': 'OK', 'result': {'list': [[str(listing), '1', '3', '0.5', '2', '4', '9']]}})

    monkeypatch.setattr(driver.session, 'get', request)

    assert driver.get_starting_time('BTC-USDT') == listing
    assert captured['interval'] == '1' and captured['limit'] == 1 and captured['symbol'] == 'BTCUSDT'

    monkeypatch.setattr(driver.session, 'get', lambda url, params=None, timeout=None: FakeResponse({'retMsg': 'OK', 'result': {'list': []}}))
    assert driver.get_starting_time('BTC-USDT') is None


def test_apex_starting_time_narrows_month_week_day_hour_minute(monkeypatch):
    driver = drivers['Apex Omni Perpetual']()
    listing = 1_718_420_640_000  # 2024-06-15 03:04 UTC
    firsts = {'M': 1_717_200_000_000, 'W': 1_717_977_600_000, 'D': 1_718_409_600_000, '60': 1_718_420_400_000, '1': listing}
    calls = []

    def request(url, params=None):
        calls.append(dict(params))
        first = firsts[params['interval']]
        return FakeResponse({'data': {'BTCUSDT': [{'t': first, 'o': '1', 'c': '2', 'h': '3', 'l': '0.5', 'v': '4'}]}})

    monkeypatch.setattr(requests, 'get', request)
    monkeypatch.setattr(driver, 'validate_response', lambda response: None)

    assert driver.get_starting_time('BTC-USDT') == listing
    assert [call['interval'] for call in calls] == ['M', 'W', 'D', '60', '1']
    # Every window after the first starts at the previous step's first candle and stays under 200 rows.
    # The weekly window looks one week back so a week bucket starting in the previous month is seen.
    assert calls[1]['start'] == firsts['M'] // 1000 - 7 * 86400 and calls[1]['end'] == calls[1]['start'] + 35 * 86400
    assert calls[4]['start'] == firsts['60'] // 1000 and calls[4]['end'] == calls[4]['start'] + 3600
    assert all(call['limit'] == 200 for call in calls)

    monkeypatch.setattr(requests, 'get', lambda url, params=None: FakeResponse({'data': {}}))
    with pytest.raises(exceptions.InvalidSymbol):
        driver.get_starting_time('NOPE-USDT')


def test_bitfinex_starting_time_is_the_first_minute_candle(monkeypatch):
    driver = drivers['Bitfinex Spot']()
    driver.all_unique_symbols = {'BTC-USD': 'BTCUSD'}
    captured = {}
    listing = 1_364_774_820_000  # 2013-04-01 00:07 UTC

    def request(url, params=None):
        captured['url'] = url
        captured.update(params or {})
        return FakeResponse([[listing, '1', '2', '3', '0.5', '4']])

    monkeypatch.setattr(driver, '_make_request', request)

    assert driver.get_starting_time('BTC-USD') == listing
    assert captured['url'].endswith('/trade:1m:tBTCUSD/hist') and captured['sort'] == 1 and captured['limit'] == 1

    monkeypatch.setattr(driver, '_make_request', lambda url, params=None: FakeResponse([]))
    with pytest.raises(exceptions.SymbolNotFound):
        driver.get_starting_time('BTC-USD')
    # A symbol the exchange does not list is rejected before any candle request is made.
    with pytest.raises(exceptions.SymbolNotFound):
        driver.get_starting_time('NOPE-USD')


def test_hyperliquid_starting_time_refines_day_to_minute_within_retention(monkeypatch):
    driver = drivers['Hyperliquid Perpetual']()
    day, hour, minute = 1_733_356_800_000, 1_733_400_000_000, 1_733_401_260_000
    calls = []

    def post(url, json=None, headers=None):
        req = json['req']
        calls.append((req['interval'], req['startTime'], req['endTime']))
        first = {'1d': day, '1h': hour, '1m': minute}[req['interval']]
        return FakeResponse([{'t': first, 'o': '1', 'c': '2', 'h': '3', 'l': '0.5', 'v': '4'}])

    monkeypatch.setattr(requests, 'post', post)

    assert driver.get_starting_time('HYPE-USD') == minute
    assert [call[0] for call in calls] == ['1d', '1h', '1m']
    assert calls[0][1] == 0 and calls[1][1:] == (day, day + 86_400_000) and calls[2][1:] == (hour, hour + 3_600_000)

    # Outside hourly retention the day start is kept, which is never later than the first candle.
    def post_old(url, json=None, headers=None):
        return FakeResponse([{'t': day, 'o': '1', 'c': '2', 'h': '3', 'l': '0.5', 'v': '4'}] if json['req']['interval'] == '1d' else [])

    monkeypatch.setattr(requests, 'post', post_old)
    assert driver.get_starting_time('BTC-USD') == day
