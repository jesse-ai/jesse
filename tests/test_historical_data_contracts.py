import json
from dataclasses import FrozenInstanceError, asdict

import pytest

from jesse.exceptions import InvalidConfig
from jesse.services.historical_data import (
    AdjustmentMode,
    AssetClass,
    HistoricalCandle,
    HistoricalCandleBatch,
    HistoricalCandleDataset,
    HistoricalCandleProvider,
    HistoricalCandleProviderRegistry,
    HistoricalCandleRange,
    HistoricalCandleRequest,
    HistoricalDatasetStatus,
    HistoricalDataQualitySummary,
    HistoricalDataSourceType,
    InstrumentType,
    ProviderCapabilities,
    SymbolCatalogEntry,
)
from jesse.services.historical_data.errors import (
    HistoricalCandleValidationError,
    HistoricalDataRequestError,
    ProviderAuthenticationError,
    ProviderNotRegisteredError,
    ProviderQuotaError,
    ProviderRegistrationError,
    ProviderUnavailableError,
)
from jesse.services.simulation_assumptions import (
    Annualization,
    SimulationModel,
    legacy_type_from_simulation_model,
    resolve_annualization,
    resolve_simulation_model,
)


class BarsOnlyProvider(HistoricalCandleProvider):
    provider_id = 'bars-only'
    capabilities = ProviderCapabilities()

    def _fetch_candles(self, request: HistoricalCandleRequest) -> HistoricalCandleBatch:
        return HistoricalCandleBatch(
            request=request,
            candles=(
                HistoricalCandle(0, 10, 12, 9, 11, 100),
                # The missing middle minute remains absent by contract.
                HistoricalCandle(120_000, 13, 14, 12, 13.5, 50),
            ),
        )


def test_bars_only_provider_supports_sparse_candles_without_optional_capabilities():
    provider = BarsOnlyProvider()
    request = HistoricalCandleRequest(
        symbol='SPY',
        timeframe='1m',
        requested_range=HistoricalCandleRange(0, 180_000),
    )

    batch = provider.fetch_candles(request)

    assert [candle.timestamp for candle in batch.candles] == [0, 120_000]
    assert provider.capabilities.credential_validation is False
    assert provider.capabilities.ticker_search is False


def test_historical_candle_contract_is_immutable_and_validated():
    candle = HistoricalCandle(0, 10, 12, 9, 11, 100, vwap=10.5, transaction_count=4)

    with pytest.raises(FrozenInstanceError):
        candle.close = 12
    with pytest.raises(HistoricalCandleValidationError):
        HistoricalCandle(0, 10, 9, 8, 11, 100)
    with pytest.raises(HistoricalCandleValidationError):
        HistoricalCandle(0, 10, 12, 9, 11, -1)


def test_batch_rejects_duplicate_misaligned_and_out_of_range_timestamps():
    request = HistoricalCandleRequest('SPY', '1m', HistoricalCandleRange(0, 180_000))
    candle = HistoricalCandle(0, 10, 12, 9, 11, 100)

    with pytest.raises(HistoricalCandleValidationError, match='ascending and unique'):
        HistoricalCandleBatch(request, (candle, candle))
    with pytest.raises(HistoricalCandleValidationError, match='not aligned'):
        HistoricalCandleBatch(request, (HistoricalCandle(30_000, 10, 12, 9, 11, 100),))
    with pytest.raises(HistoricalCandleValidationError, match='outside'):
        HistoricalCandleBatch(request, (HistoricalCandle(180_000, 10, 12, 9, 11, 100),))


def test_batch_copies_mutable_provider_sequences_before_validation():
    request = HistoricalCandleRequest('SPY', '1m', HistoricalCandleRange(0, 180_000))
    provider_values = [HistoricalCandle(0, 10, 12, 9, 11, 100)]

    batch = HistoricalCandleBatch(request, provider_values)
    provider_values.append(HistoricalCandle(60_000, 11, 13, 10, 12, 100))

    assert len(batch.candles) == 1


def test_provider_capabilities_reject_unsupported_requests():
    provider = BarsOnlyProvider()

    with pytest.raises(HistoricalDataRequestError, match='timeframe'):
        provider.fetch_candles(HistoricalCandleRequest('SPY', '5m', HistoricalCandleRange(0, 300_000)))
    with pytest.raises(HistoricalDataRequestError, match='adjustment mode'):
        provider.fetch_candles(HistoricalCandleRequest(
            'SPY',
            '1m',
            HistoricalCandleRange(0, 180_000),
            AdjustmentMode.SPLIT_ADJUSTED,
        ))


def test_ready_dataset_requires_provider_provenance_and_is_deeply_immutable():
    dataset = HistoricalCandleDataset(
        id='dataset-1',
        source_type=HistoricalDataSourceType.PROVIDER,
        provider_id='massive-stocks',
        symbol='SPY',
        source_timeframe='1m',
        asset_class=AssetClass.EQUITY,
        instrument_type=InstrumentType.ETF,
        requested_range=HistoricalCandleRange(0, 180_000),
        imported_range=HistoricalCandleRange(0, 180_000),
        adjustment_mode=AdjustmentMode.SPLIT_ADJUSTED,
        status=HistoricalDatasetStatus.READY,
        row_count=2,
        checksum='fabricated-checksum',
        quality=HistoricalDataQualitySummary(unclassified_gap_count=1),
        created_at=1,
        updated_at=2,
        source_metadata={'provider_request_id': 'fabricated'},
    )

    assert dataset.source_metadata['provider_request_id'] == 'fabricated'
    with pytest.raises(TypeError):
        dataset.source_metadata['provider_request_id'] = 'changed'
    assert asdict(dataset)['source_metadata']['provider_request_id'] == 'fabricated'


def test_dataset_coerces_serialized_enums_before_enforcing_ready_invariants():
    with pytest.raises(HistoricalCandleValidationError, match='provider_id'):
        HistoricalCandleDataset(
            id='dataset-1',
            source_type='provider',
            symbol='SPY',
            source_timeframe='1m',
            asset_class='equity',
            instrument_type='etf',
            requested_range=HistoricalCandleRange(0, 180_000),
            adjustment_mode='split_adjusted',
            status='ready',
            row_count=2,
            quality=HistoricalDataQualitySummary(),
            created_at=1,
            updated_at=2,
        )


def test_provider_registry_rejects_duplicates_and_returns_typed_unknown_error():
    registry = HistoricalCandleProviderRegistry()
    provider = BarsOnlyProvider()

    registry.register(provider)

    assert registry.ids() == ('bars-only',)
    assert registry.get('bars-only') is provider
    with pytest.raises(ProviderRegistrationError, match='already registered'):
        registry.register(provider)
    with pytest.raises(ProviderNotRegisteredError) as exc_info:
        registry.get('missing')
    assert exc_info.value.code == 'provider_not_registered'


def test_provider_errors_have_stable_retry_semantics():
    assert ProviderAuthenticationError.code == 'provider_authentication_failed'
    assert ProviderAuthenticationError.retryable is False
    assert ProviderUnavailableError.code == 'provider_unavailable'
    assert ProviderUnavailableError.retryable is True
    assert ProviderQuotaError.code == 'provider_quota_exhausted'
    assert ProviderQuotaError.retryable is False


def test_simulation_model_normalizes_legacy_sessions_and_rejects_conflicts():
    assert resolve_simulation_model({'type': 'spot'}, 'futures') is SimulationModel.SPOT
    assert resolve_simulation_model({'type': ''}, 'spot') is SimulationModel.SPOT
    assert resolve_simulation_model(
        {'simulation_model': 'perpetual_futures', 'type': 'futures'},
        'spot',
    ) is SimulationModel.PERPETUAL_FUTURES
    assert legacy_type_from_simulation_model(SimulationModel.SPOT) == 'spot'

    with pytest.raises(InvalidConfig, match='Conflicting'):
        resolve_simulation_model({'simulation_model': 'spot', 'type': 'futures'}, 'spot')


def test_annualization_supports_only_the_two_product_assumptions():
    assert resolve_annualization({}) is Annualization.CALENDAR_365
    assert resolve_annualization({'annualization': '252'}) is Annualization.TRADING_252

    with pytest.raises(InvalidConfig, match='252 or 365'):
        resolve_annualization({'annualization': 360})
    with pytest.raises(InvalidConfig, match='252 or 365'):
        resolve_annualization({'annualization': 252.9})


class _FakeMassiveResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.headers = {}

    def json(self):
        return self._payload

    def close(self):
        pass


class _FakeMassiveSession:
    """Serve fabricated Massive reference payloads keyed by URL path prefix; no real data or keys."""

    def __init__(self, responses):
        self._responses = responses
        self.requests = []

    def get(self, url, headers=None, params=None, timeout=None, allow_redirects=None):
        self.requests.append((url, params))
        for prefix, payload in self._responses:
            if url.startswith(prefix):
                return _FakeMassiveResponse(payload)
        raise AssertionError(f'Unexpected Massive request {url!r}')


def test_symbol_catalog_entries_default_to_bare_symbols_and_validate_details():
    class SymbolsOnlyProvider(BarsOnlyProvider):
        def list_symbols(self):
            return ('BTC-USDT', 'ETH-USDT')

    entries = SymbolsOnlyProvider().list_symbol_entries()

    assert entries == (SymbolCatalogEntry('BTC-USDT'), SymbolCatalogEntry('ETH-USDT'))
    assert entries[0].details() == {}
    assert SymbolCatalogEntry('SPY-USD', name='SPDR S&P 500', kind='ETF').details() == {
        'name': 'SPDR S&P 500',
        'kind': 'ETF',
    }
    with pytest.raises(HistoricalCandleValidationError):
        SymbolCatalogEntry('')
    with pytest.raises(HistoricalCandleValidationError):
        SymbolCatalogEntry('SPY-USD', name='   ')


def test_massive_stock_catalog_carries_company_name_type_and_listing_venue():
    from jesse.services.historical_data.massive_stocks import MASSIVE_TICKERS_URL, MassiveStocksProvider

    session = _FakeMassiveSession([(MASSIVE_TICKERS_URL, {
        'status': 'OK',
        'results': [
            {'ticker': 'GOOG', 'name': 'Alphabet Inc. Class C', 'market': 'stocks', 'type': 'CS', 'primary_exchange': 'XNAS'},
            {'ticker': 'GGLL', 'name': 'Direxion Daily GOOGL Bull 2X ETF', 'market': 'stocks', 'type': 'ETF', 'primary_exchange': 'XNAS'},
            {'ticker': 'ZZZ', 'market': 'stocks', 'type': 'XYZ', 'primary_exchange': 'QQQQ'},
            {'ticker': 'ODD-W', 'name': 'Excluded warrant', 'market': 'stocks'},
            {'ticker': 'C:EURUSD', 'name': 'Wrong market', 'market': 'fx'},
        ],
    })])
    provider = MassiveStocksProvider(credential_loader=lambda: 'fabricated-key', session=session)

    entries = provider.list_symbol_entries()

    assert entries == (
        SymbolCatalogEntry('GGLL-USD', name='Direxion Daily GOOGL Bull 2X ETF', kind='ETF', venue='NASDAQ'),
        SymbolCatalogEntry('GOOG-USD', name='Alphabet Inc. Class C', kind='Common Stock', venue='NASDAQ'),
        # Unknown codes fall through unchanged rather than hiding the instrument.
        SymbolCatalogEntry('ZZZ-USD', kind='XYZ', venue='QQQQ'),
    )
    assert provider.list_symbols() == ('GGLL-USD', 'GOOG-USD', 'ZZZ-USD')
    assert all(request[1] is None or request[1].get('market') == 'stocks' for request in session.requests)


def test_massive_futures_catalog_describes_contracts_through_their_product():
    from jesse.services.historical_data.massive_stocks import (
        MASSIVE_FUTURES_CONTRACTS_URL,
        MASSIVE_FUTURES_PRODUCTS_URL,
        MassiveFuturesProvider,
    )

    session = _FakeMassiveSession([
        (MASSIVE_FUTURES_PRODUCTS_URL, {'status': 'OK', 'results': [
            {'product_code': 'CL', 'trade_currency_code': 'USD', 'name': 'Light Sweet Crude Oil Futures', 'trading_venue': 'XNYM'},
        ]}),
        (MASSIVE_FUTURES_CONTRACTS_URL, {'status': 'OK', 'results': [
            {'ticker': 'CLF30', 'product_code': 'CL', 'type': 'single', 'name': 'CLF30 Future', 'last_trade_date': '2029-12-19', 'trading_venue': 'XNYM'},
            {'ticker': 'CLF30-CLG30', 'product_code': 'CL', 'type': 'single'},
        ]}),
    ])
    provider = MassiveFuturesProvider(credential_loader=lambda: 'fabricated-key', session=session)

    entries = provider.list_symbol_entries()

    assert entries == (
        SymbolCatalogEntry('CLF30-USD', name='Light Sweet Crude Oil Futures', kind='Future', venue='NYMEX', expiry='2029-12-19'),
    )
    assert provider.search_symbols('crude') == ('CLF30-USD',)
    assert provider.search_symbols('clf') == ('CLF30-USD',)


def _fake_symbol_catalog_backend(monkeypatch, entries):
    from jesse.modes.import_candles_mode import drivers
    from jesse.services import symbol_catalog

    class CatalogProvider(BarsOnlyProvider):
        provider_id = 'Massive Stocks'

        def list_symbol_entries(self):
            return entries

    class FakeLock:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    class FakeRedis:
        def __init__(self):
            self.store = {}

        def get(self, key):
            return self.store.get(key)

        def setex(self, key, ttl, value):
            self.store[key] = value.encode()

        def lock(self, *args, **kwargs):
            return FakeLock()

    fake_redis = FakeRedis()
    provider_calls = []

    class FakeRegistry:
        def get(self, exchange):
            provider_calls.append(exchange)
            return CatalogProvider()

    monkeypatch.setattr(symbol_catalog, 'sync_redis', fake_redis)
    monkeypatch.setattr(drivers, 'build_historical_provider_registry', lambda exchanges: FakeRegistry())
    return fake_redis, provider_calls


def test_supported_symbols_endpoint_returns_and_caches_symbol_details(monkeypatch):
    from jesse.controllers import exchange_controller

    fake_redis, provider_calls = _fake_symbol_catalog_backend(monkeypatch, (
        SymbolCatalogEntry('SPY-USD', name='SPDR S&P 500 ETF Trust', kind='ETF', venue='NYSE Arca'),
        SymbolCatalogEntry('BARE-USD'),
    ))

    expected = {
        'data': ['SPY-USD', 'BARE-USD'],
        'details': {'SPY-USD': {'name': 'SPDR S&P 500 ETF Trust', 'kind': 'ETF', 'venue': 'NYSE Arca'}},
    }
    first = exchange_controller.get_exchange_supported_symbols('Massive Stocks')
    second = exchange_controller.get_exchange_supported_symbols('Massive Stocks')

    assert first.status_code == 200
    assert json.loads(first.body) == expected
    assert json.loads(second.body) == expected
    assert provider_calls == ['Massive Stocks']
    assert list(fake_redis.store) == ['historical-symbols:v2:Massive Stocks']

    fake_redis.store['historical-symbols:v2:Massive Stocks'] = b'["SPY-USD"]'
    corrupted = exchange_controller.get_exchange_supported_symbols('Massive Stocks')
    assert corrupted.status_code == 500


def test_symbol_search_ranks_ticker_prefixes_before_provider_names(monkeypatch):
    from jesse.controllers import exchange_controller
    from jesse.services.symbol_catalog import search_symbol_catalog

    _fake_symbol_catalog_backend(monkeypatch, (
        SymbolCatalogEntry('GGLL-USD', name='Direxion Daily GOOGL Bull 2X ETF', kind='ETF', venue='NASDAQ'),
        SymbolCatalogEntry('GOOG-USD', name='Alphabet Inc. Class C', kind='Common Stock', venue='NASDAQ'),
        SymbolCatalogEntry('GOOGL-USD', name='Alphabet Inc. Class A', kind='Common Stock', venue='NASDAQ'),
        SymbolCatalogEntry('MSFT-USD', name='Microsoft Corp', kind='Common Stock', venue='NASDAQ'),
        SymbolCatalogEntry('BARE-USD'),
    ))

    response = exchange_controller.search_exchange_symbols('Massive Stocks', 'goog', 50)
    payload = json.loads(response.body)

    assert response.status_code == 200
    assert payload['catalog_size'] == 5
    assert [match['symbol'] for match in payload['data']] == ['GOOG-USD', 'GOOGL-USD', 'GGLL-USD']
    assert payload['data'][0] == {
        'symbol': 'GOOG-USD', 'name': 'Alphabet Inc. Class C', 'kind': 'Common Stock', 'venue': 'NASDAQ',
    }

    by_name = json.loads(exchange_controller.search_exchange_symbols('Massive Stocks', 'Alphabet', 1).body)
    assert [match['symbol'] for match in by_name['data']] == ['GOOG-USD']
    assert json.loads(exchange_controller.search_exchange_symbols('Massive Stocks', '   ', 50).body)['data'] == []
    assert exchange_controller.search_exchange_symbols('Massive Stocks', 'goog', 0).status_code == 422

    # Crypto-style catalogs without details still match by ticker prefix and return bare entries.
    plain = {'data': ['BTC-USDT', 'ETH-USDT'], 'details': {}}
    assert search_symbol_catalog(plain, 'bt') == [{'symbol': 'BTC-USDT'}]
    assert search_symbol_catalog(plain, 'bitcoin') == []
