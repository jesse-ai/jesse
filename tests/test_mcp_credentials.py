import asyncio
import json
import uuid
from datetime import datetime, timezone
from hashlib import sha256
from types import SimpleNamespace
from urllib.parse import urlsplit

import peewee
import pytest
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mcp.server.fastmcp import FastMCP

import jesse.mcp.tools.services.candles as candles_service
import jesse.mcp.tools.services.credentials as credentials_service
from jesse.controllers import data_provider_credentials_controller, exchange_controller
from jesse.info import live_trading_exchanges
from jesse.mcp.agent_rules import _load_packaged_rules
from jesse.mcp.tools import register_tools
from jesse.mcp.tools.credentials import register_credentials_tools
from jesse.models.DataProviderCredentials import DataProviderCredentials
from jesse.models.ExchangeApiKeys import ExchangeApiKeys
from jesse.services import auth
from jesse.services.historical_data import massive_stocks
from jesse.services.historical_data.errors import (
    ProviderAuthenticationError,
    ProviderEntitlementError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderUnavailableError,
)
from jesse.store.state_app import AppState
from tests.mcp_tool_adapters import callable_tool


PASSWORD = 'credential-tools-password'
JESSE_URL = 'http://jesse.test'

# Fake secrets. Each has a distinctive first and last four characters because Jesse's
# Dashboard transformer masks values as value[:4] + '***...***' + value[-4:]; checking for
# those fragments proves the MCP results carry no masked remnant either.
API_KEY = 'QZXAapi-key-sentinel-0001VWKA'
API_SECRET = 'QZXBapi-secret-sentinel-0002VWKB'
PASSPHRASE = 'QZXCpassphrase-sentinel-VWKC'
WALLET = 'QZXDwallet-sentinel-VWKD'
STARK_KEY = 'QZXEstark-private-sentinel-VWKE'
MASSIVE_KEY = 'QZXFmassive-key-sentinel-VWKF'
SECRETS = (API_KEY, API_SECRET, PASSPHRASE, WALLET, STARK_KEY, MASSIVE_KEY)
SECRET_FIELD_NAMES = {'api_key', 'api_secret', 'api_passphrase', 'wallet_address', 'stark_private_key',
                      'credentials', 'passphrase'}

APEX = 'Apex Omni Perpetual'
APEX_FIELDS = {'api_passphrase': PASSPHRASE, 'wallet_address': WALLET, 'stark_private_key': STARK_KEY}

CREDENTIAL_TOOLS = {
    'get_exchange_api_key_requirements',
    'get_exchange_api_keys',
    'store_exchange_api_key',
    'delete_exchange_api_key',
    'get_data_provider_credentials',
    'store_data_provider_credentials',
    'delete_data_provider_credentials',
    'validate_data_provider_credentials',
}


class FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self):
        def decorator(func):
            self.tools[func.__name__] = callable_tool(func)
            return func

        return decorator

    def resource(self, uri):
        def decorator(func):
            return func

        return decorator


def _registered_tools() -> dict:
    mcp = FakeMCP()
    register_tools(mcp)
    return mcp.tools


def _assert_discloses_nothing(result) -> None:
    """No secret, masked fragment, or secret-named field anywhere in an MCP result."""
    dumped = json.dumps(result)
    for secret in SECRETS:
        assert secret not in dumped
        assert secret[:4] not in dumped and secret[-4:] not in dumped
    assert '***' not in dumped

    def walk(value):
        if isinstance(value, dict):
            assert not SECRET_FIELD_NAMES & set(value), value
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(result)


# ---------------------------------------------------------------------------
# Registration and the tool boundary
# ---------------------------------------------------------------------------

def test_credential_and_symbol_tools_are_registered():
    tools = _registered_tools()

    for name in CREDENTIAL_TOOLS | {'search_symbols'}:
        assert name in tools, name
    assert 'never repeat them back' in tools['store_exchange_api_key'].__doc__
    assert 'Massive Futures lists CME stock futures' in tools['search_symbols'].__doc__


def test_no_tool_can_export_or_reveal_credentials():
    """Credential tools are exactly store/list/delete/validate plus field discovery."""
    tools = _registered_tools()

    credential_like = {
        name for name in tools
        if any(word in name for word in ('api_key', 'credential', 'secret', 'passphrase', 'export'))
    }
    # export_candles writes stored market data into the project; it never reaches a credential route.
    assert credential_like == CREDENTIAL_TOOLS | {'export_candles'}
    import jesse.mcp.tools.services.candles as candles_service
    candle_source = open(candles_service.__file__, encoding='utf-8').read()
    assert '/api-keys' not in candle_source and 'credentials' not in candle_source.split('def export_candles_service')[1]
    source = open(credentials_service.__file__, encoding='utf-8').read()
    # The Dashboard's password-confirmed CSV export and import routes stay Dashboard-only.
    assert 'download-api-keys' not in source and 'import-api-keys' not in source
    assert 'notification' not in source


# ---------------------------------------------------------------------------
# Field requirements
# ---------------------------------------------------------------------------

def _fields(result: dict, exchange: str) -> dict:
    entry = next(item for item in result['exchanges'] if item['exchange'] == exchange)
    return {field['key']: field for field in entry['fields']}


def test_requirements_list_every_live_exchange_with_the_dashboard_form_fields():
    result = credentials_service.get_exchange_api_key_requirements_service()

    assert result['status'] == 'success'
    assert [item['exchange'] for item in result['exchanges']] == list(live_trading_exchanges)

    binance = _fields(result, 'Binance Perpetual Futures')
    assert list(binance) == ['api_key', 'api_secret']
    assert binance['api_key']['label'] == 'API Key' and binance['api_key']['location'] == 'argument'

    apex = _fields(result, APEX)
    assert {key for key, field in apex.items() if field['location'] == 'additional_fields'} == set(APEX_FIELDS)
    assert all(field['required'] for field in apex.values())

    for kucoin in ('KuCoin Spot', 'KuCoin USDT Perpetual'):
        extras = {key for key, field in _fields(result, kucoin).items() if field['location'] == 'additional_fields'}
        assert extras == {'api_passphrase'}

    lighter = _fields(result, 'Lighter Perpetual')
    assert lighter['api_key']['label'] == 'L1 Wallet Address'
    assert lighter['api_key_index']['required'] is True and lighter['api_key_index']['format'] == 'integer'
    assert lighter['account_index']['required'] is False

    hyperliquid = _fields(result, 'Hyperliquid Perpetual')
    assert (hyperliquid['api_key']['label'], hyperliquid['api_secret']['label']) == ('Wallet Address', 'Private Key')
    assert list(hyperliquid) == ['api_key', 'api_secret']


def test_requirements_for_one_exchange_and_unsupported_names():
    one = credentials_service.get_exchange_api_key_requirements_service(' KuCoin Spot ')
    assert [item['exchange'] for item in one['exchanges']] == ['KuCoin Spot']

    unsupported = credentials_service.get_exchange_api_key_requirements_service(API_KEY)
    assert unsupported['error_type'] == 'unsupported_exchange'
    assert unsupported['supported_exchanges'] == list(live_trading_exchanges)
    _assert_discloses_nothing(unsupported)

    massive = credentials_service.get_exchange_api_key_requirements_service('Massive Stocks')
    assert massive['error_type'] == 'unsupported_exchange'


# ---------------------------------------------------------------------------
# Disposable Jesse backend: the real credential routes over a throwaway SQLite database
# ---------------------------------------------------------------------------

@pytest.fixture
def backend(tmp_path, monkeypatch):
    """
    Serve the MCP services' calls with Jesse's real exchange and data-provider routers,
    authenticated by the real require_auth, over a SQLite file in tmp_path.

    A file rather than ':memory:' because TestClient runs sync routes in worker threads and
    peewee opens one connection per thread, each of which would see its own empty in-memory
    database. The Massive validator is replaced so no request leaves the test.
    """
    db = peewee.SqliteDatabase(str(tmp_path / 'credentials.db'))
    models = [ExchangeApiKeys, DataProviderCredentials]
    # Jesse stores timezone-aware UTC datetimes, which PostgreSQL returns as datetimes. SQLite
    # keeps them as text that peewee cannot parse back, so the fake clock is naive UTC.
    monkeypatch.setattr('jesse.helpers.now_to_datetime', lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    monkeypatch.setitem(auth.ENV_VALUES, 'PASSWORD', PASSWORD)
    monkeypatch.setattr(credentials_service.mcp_config, 'JESSE_API_URL', JESSE_URL)
    monkeypatch.setattr(credentials_service.mcp_config, 'JESSE_PASSWORD', PASSWORD)

    validated_keys = []

    def fake_validate(api_key):
        validated_keys.append(api_key)
        failure = state.validation_failure
        if failure is not None:
            raise failure(f'provider said no to {api_key}')

    state = SimpleNamespace(validation_failure=None)
    monkeypatch.setattr(data_provider_credentials_controller, 'validate_massive_api_key', fake_validate)

    app = FastAPI()

    @app.exception_handler(auth.InvalidAuthError)
    async def invalid_auth_handler(_request, _exc):
        return auth.unauthorized_response()

    app.include_router(exchange_controller.router)
    app.include_router(data_provider_credentials_controller.router)
    client = TestClient(app)
    calls = []

    def route(method, url, headers=None, json=None, timeout=None, **_kwargs):
        assert timeout, 'every outgoing request must have a timeout'
        assert url.startswith(JESSE_URL), f'unexpected outgoing request to {url}'
        path = urlsplit(url).path
        calls.append({'method': method, 'path': path, 'json': json})
        return client.request(method, path, json=json, headers=headers)

    monkeypatch.setattr(requests, 'request', route)
    with db.bind_ctx(models):
        db.create_tables(models)
        yield SimpleNamespace(client=client, calls=calls, validated_keys=validated_keys, state=state)
        db.drop_tables(models)
    db.close()


def _store_apex(**overrides):
    kwargs = dict(exchange=APEX, name='Main Apex', api_key=API_KEY, api_secret=API_SECRET,
                  additional_fields=dict(APEX_FIELDS))
    kwargs.update(overrides)
    return credentials_service.store_exchange_api_key_service(**kwargs)


def test_exchange_key_store_list_delete_keeps_secrets_write_only(backend):
    tools = _registered_tools()

    stored = tools['store_exchange_api_key'](
        exchange=APEX, name=' Main Apex ', api_key=f' {API_KEY} ', api_secret=API_SECRET,
        additional_fields={key: f' {value} ' for key, value in APEX_FIELDS.items()},
    )

    assert stored['status'] == 'success', stored
    metadata = stored['exchange_api_key']
    assert set(metadata) == {'id', 'name', 'exchange', 'created_at'}
    assert (metadata['name'], metadata['exchange']) == ('Main Apex', APEX)
    uuid.UUID(metadata['id'])
    _assert_discloses_nothing(stored)

    # The secrets reached Jesse's store, trimmed, exactly where jesse-live reads them.
    row = ExchangeApiKeys.get_by_id(metadata['id'])
    assert (row.api_key, row.api_secret) == (API_KEY, API_SECRET)
    assert row.get_additional_fields() == APEX_FIELDS

    listed = tools['get_exchange_api_keys']()
    assert listed['exchange_api_keys'] == [metadata]
    _assert_discloses_nothing(listed)

    # The Dashboard's own list route keeps its masked view; only the MCP result drops it.
    dashboard = backend.client.get('/exchange/api-keys', headers={'Authorization': sha256(PASSWORD.encode('utf-8')).hexdigest()})
    assert dashboard.json()['data'][0]['api_key'] == f'{API_KEY[:4]}***...***{API_KEY[-4:]}'

    deleted = tools['delete_exchange_api_key'](metadata['id'])
    assert deleted['status'] == 'success'
    assert deleted['exchange_api_key'] == metadata
    _assert_discloses_nothing(deleted)
    assert ExchangeApiKeys.get_or_none(ExchangeApiKeys.id == metadata['id']) is None

    again = tools['delete_exchange_api_key'](metadata['id'])
    assert again['error_type'] == 'not_found'
    assert [call['path'] for call in backend.calls].count('/exchange/api-keys/delete') == 1


def test_saved_id_is_the_one_live_sessions_resolve(backend):
    """A live session only receives exchange_api_key_id; jesse-live resolves it through AppState."""
    stored = _store_apex()
    key_id = stored['exchange_api_key']['id']

    app_state = AppState()
    app_state.set_exchange_api_key(key_id)

    assert app_state.exchange_api_key is not None
    assert app_state.exchange_api_key.exchange_name == APEX
    # LiveExchange reads these three additional fields for Apex exchanges.
    fields = app_state.exchange_api_key.get_additional_fields()
    assert (fields['api_passphrase'], fields['wallet_address'], fields['stark_private_key']) == (PASSPHRASE, WALLET, STARK_KEY)

    credentials_service.delete_exchange_api_key_service(key_id)
    after_delete = AppState()
    after_delete.set_exchange_api_key(key_id)
    assert after_delete.exchange_api_key is None


def test_lighter_and_plain_exchanges_store_only_their_own_fields(backend):
    lighter = credentials_service.store_exchange_api_key_service(
        'Lighter Perpetual', 'Lighter main', API_KEY, API_SECRET, {'api_key_index': ' 3 ', 'account_index': ''},
    )
    assert lighter['status'] == 'success', lighter
    assert ExchangeApiKeys.get_by_id(lighter['exchange_api_key']['id']).get_additional_fields() == {'api_key_index': '3'}

    binance = credentials_service.store_exchange_api_key_service('Binance Spot', 'Spot', API_KEY, API_SECRET)
    assert binance['status'] == 'success'
    assert ExchangeApiKeys.get_by_id(binance['exchange_api_key']['id']).get_additional_fields() == {}


def test_duplicate_names_are_reported_without_secrets(backend):
    assert _store_apex()['status'] == 'success'

    duplicate = _store_apex(api_key=f'{API_KEY}-other')

    assert duplicate['error_type'] == 'name_taken'
    _assert_discloses_nothing(duplicate)
    assert ExchangeApiKeys.select().count() == 1


@pytest.mark.parametrize(('overrides', 'error_type', 'fragment'), [
    ({'exchange': 'Massive Stocks'}, 'unsupported_exchange', 'live-trading exchange'),
    ({'exchange': API_KEY}, 'unsupported_exchange', 'live-trading exchange'),
    ({'name': '   '}, 'invalid_request', 'name must not be empty'),
    ({'api_secret': ''}, 'invalid_request', 'api_secret must not be empty'),
    ({'api_key': 'x' * 256}, 'invalid_request', 'at most 255'),
    ({'additional_fields': {'api_passphrase': PASSPHRASE, 'wallet_address': WALLET}}, 'invalid_request', 'stark_private_key'),
    ({'additional_fields': {**APEX_FIELDS, API_SECRET: 'x'}}, 'invalid_request', 'Accepted fields'),
    ({'additional_fields': [PASSPHRASE]}, 'invalid_request', 'must be an object'),
    ({'additional_fields': {**APEX_FIELDS, 'wallet_address': 7}}, 'invalid_request', 'must be a string'),
    ({'exchange': 'Lighter Perpetual', 'additional_fields': {'api_key_index': 'two'}}, 'invalid_request', 'integer'),
    ({'exchange': 'Lighter Perpetual', 'additional_fields': {'api_key_index': True}}, 'invalid_request', 'must be a string'),
    ({'exchange': 'Lighter Perpetual', 'additional_fields': {}}, 'invalid_request', 'api_key_index'),
    ({'exchange': 'KuCoin Spot', 'additional_fields': {}}, 'invalid_request', 'api_passphrase'),
    ({'exchange': 'Binance Spot', 'additional_fields': {'api_passphrase': PASSPHRASE}}, 'invalid_request', 'Accepted fields: none'),
])
def test_invalid_exchange_keys_are_rejected_before_reaching_jesse(backend, overrides, error_type, fragment):
    result = _store_apex(**overrides)

    assert result['status'] == 'error'
    assert result['error_type'] == error_type
    assert fragment in result['message']
    _assert_discloses_nothing(result)
    assert backend.calls == []


@pytest.mark.parametrize('bad_id', ['', '   ', 'not-a-uuid', API_KEY])
def test_delete_rejects_malformed_ids_without_a_request(backend, bad_id):
    result = credentials_service.delete_exchange_api_key_service(bad_id)

    assert result['error_type'] == 'invalid_request'
    _assert_discloses_nothing(result)
    assert backend.calls == []


def test_unknown_exchange_key_id_is_not_found(backend):
    result = credentials_service.delete_exchange_api_key_service(str(uuid.uuid4()))

    assert result['error_type'] == 'not_found'
    assert [call['path'] for call in backend.calls] == ['/exchange/api-keys']


def test_data_provider_store_list_validate_delete(backend):
    tools = _registered_tools()

    initial = tools['get_data_provider_credentials']()
    assert initial['configured_providers'] == []
    assert initial['data_providers'] == [{
        'provider_id': 'Massive', 'name': 'Massive', 'configured': False, 'created_at': None, 'updated_at': None,
        'credential_fields': [{'key': 'api_key', 'label': 'API Key', 'secret': True}],
    }]

    stored = tools['store_data_provider_credentials'](f' {MASSIVE_KEY} ')
    assert stored['status'] == 'success'
    assert stored['data_provider']['configured'] is True
    assert isinstance(stored['data_provider']['created_at'], int)
    _assert_discloses_nothing(stored)

    # Massive imports read the stored key internally; no credential id is involved.
    assert massive_stocks._load_massive_api_key() == MASSIVE_KEY

    listed = tools['get_data_provider_credentials']()
    assert listed['configured_providers'] == ['Massive']
    _assert_discloses_nothing(listed)

    conflict = tools['store_data_provider_credentials'](f'{MASSIVE_KEY}-new')
    assert conflict['error_type'] == 'already_configured'
    _assert_discloses_nothing(conflict)
    assert massive_stocks._load_massive_api_key() == MASSIVE_KEY

    validated = tools['validate_data_provider_credentials']()
    assert validated['status'] == 'success'
    assert backend.validated_keys == [MASSIVE_KEY]
    _assert_discloses_nothing(validated)

    deleted = tools['delete_data_provider_credentials']()
    assert deleted['status'] == 'success'
    assert deleted['data_provider']['configured'] is False
    assert DataProviderCredentials.get_or_none(DataProviderCredentials.provider_id == 'Massive') is None

    assert tools['delete_data_provider_credentials']()['error_type'] == 'not_found'
    assert tools['validate_data_provider_credentials']()['error_type'] == 'not_configured'


@pytest.mark.parametrize(('failure', 'error_type'), [
    (ProviderAuthenticationError, 'credentials_rejected'),
    (ProviderEntitlementError, 'missing_entitlement'),
    (ProviderRateLimitError, 'rate_limited'),
    (ProviderUnavailableError, 'provider_unavailable'),
    (ProviderRequestError, 'validation_failed'),
])
def test_validation_failures_are_typed_and_never_quote_the_provider(backend, failure, error_type):
    credentials_service.store_data_provider_credentials_service(MASSIVE_KEY)
    backend.state.validation_failure = failure

    result = credentials_service.validate_data_provider_credentials_service()

    # A provider rejection is also an HTTP 401 from Jesse; it must not look like a bad dashboard password.
    assert result['error_type'] == error_type
    _assert_discloses_nothing(result)


@pytest.mark.parametrize('call', [
    lambda: credentials_service.store_data_provider_credentials_service(MASSIVE_KEY, 'Unknown'),
    lambda: credentials_service.delete_data_provider_credentials_service('Unknown'),
    lambda: credentials_service.validate_data_provider_credentials_service('Unknown'),
    # A key misplaced into provider_id must not come back in the error.
    lambda: credentials_service.store_data_provider_credentials_service('placeholder', MASSIVE_KEY),
    lambda: credentials_service.delete_data_provider_credentials_service(MASSIVE_KEY),
    lambda: credentials_service.validate_data_provider_credentials_service(MASSIVE_KEY),
])
def test_unsupported_data_providers_are_rejected(backend, call):
    result = call()

    assert result['error_type'] == 'unsupported_provider'
    _assert_discloses_nothing(result)


def test_empty_data_provider_arguments_make_no_request(backend):
    assert credentials_service.store_data_provider_credentials_service('   ')['error_type'] == 'invalid_request'
    assert credentials_service.delete_data_provider_credentials_service(' ')['error_type'] == 'invalid_request'
    assert backend.calls == []


@pytest.mark.parametrize(('tool', 'kwargs'), [
    ('get_exchange_api_keys', {}),
    ('store_exchange_api_key', dict(exchange=APEX, name='Main', api_key=API_KEY, api_secret=API_SECRET,
                                    additional_fields=APEX_FIELDS)),
    ('delete_exchange_api_key', {'id': str(uuid.uuid4())}),
    ('get_data_provider_credentials', {}),
    ('store_data_provider_credentials', {'api_key': MASSIVE_KEY}),
    ('delete_data_provider_credentials', {}),
    ('validate_data_provider_credentials', {}),
])
def test_wrong_dashboard_password_is_an_authentication_error(backend, monkeypatch, tool, kwargs):
    monkeypatch.setattr(credentials_service.mcp_config, 'JESSE_PASSWORD', 'not-the-password')

    result = _registered_tools()[tool](**kwargs)

    assert result['error_type'] == 'authentication_failed'
    _assert_discloses_nothing(result)
    assert ExchangeApiKeys.select().count() == 0
    assert DataProviderCredentials.select().count() == 0


# ---------------------------------------------------------------------------
# Malformed or hostile Jesse responses
# ---------------------------------------------------------------------------

KEY_ID = str(uuid.uuid4())
_LEAKY_ENTRY = {
    'id': KEY_ID, 'name': 'Main', 'exchange': APEX, 'created_at': '2026-09-28T10:00:00',
    'api_key': API_KEY, 'api_secret': f'{API_SECRET[:4]}***...***{API_SECRET[-4:]}',
    'api_passphrase': PASSPHRASE, 'wallet_address': WALLET, 'stark_private_key': STARK_KEY,
    'provider_id': 'Massive', 'configured': True, 'credentials': {'api_key': MASSIVE_KEY},
    'credential_fields': [{'key': 'api_key', 'label': 'API Key', 'secret': True, 'value': MASSIVE_KEY}],
}
_LEAKY_TEXT = ' '.join(SECRETS)


class _Response:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body
        self.text = body if isinstance(body, str) else json.dumps(body)

    def json(self):
        if isinstance(self._body, str):
            # Real JSON decode errors quote the body too, so the service must not relay them.
            raise ValueError(f'not JSON: {self._body}')
        return self._body


def _leaky_message(prefix=''):
    return {'status': 'error', 'message': f'{prefix}{_LEAKY_TEXT}', 'error': _LEAKY_TEXT, 'detail': _LEAKY_TEXT}


MALFORMED_RESPONSES = {
    'success_list_with_secrets': _Response(200, {'status': 'success', 'message': _LEAKY_TEXT, 'data': [_LEAKY_ENTRY]}),
    'success_entry_with_secrets': _Response(200, {'status': 'success', 'message': _LEAKY_TEXT, 'data': _LEAKY_ENTRY}),
    'success_non_json': _Response(200, _LEAKY_TEXT),
    'success_json_list': _Response(200, list(SECRETS)),
    'success_without_data': _Response(200, {'status': 'success', 'message': _LEAKY_TEXT}),
    'duplicate_name_400': _Response(400, _leaky_message('API key with the name ')),
    **{f'error_{status}': _Response(status, _leaky_message()) for status in (400, 401, 403, 404, 409, 422, 429, 500, 502, 503)},
    'dashboard_auth_401': _Response(401, {'message': 'Invalid password'}),
    'error_non_json': _Response(500, _LEAKY_TEXT),
}
RAISED = {
    'network_error': requests.exceptions.ConnectionError(_LEAKY_TEXT),
    'unexpected_exception': RuntimeError(_LEAKY_TEXT),
}
TOOL_CALLS = {
    'get_exchange_api_key_requirements': {},
    'get_exchange_api_keys': {},
    'store_exchange_api_key': dict(exchange=APEX, name='Main', api_key=API_KEY, api_secret=API_SECRET,
                                   additional_fields=APEX_FIELDS),
    'delete_exchange_api_key': {'id': KEY_ID},
    'get_data_provider_credentials': {},
    'store_data_provider_credentials': {'api_key': MASSIVE_KEY},
    'delete_data_provider_credentials': {},
    'validate_data_provider_credentials': {},
}


@pytest.fixture
def scripted_jesse(monkeypatch):
    """Answer every Jesse call with one scripted response, or raise one scripted exception."""
    monkeypatch.setattr(credentials_service.mcp_config, 'JESSE_API_URL', JESSE_URL)
    monkeypatch.setattr(credentials_service.mcp_config, 'JESSE_PASSWORD', PASSWORD)
    script = SimpleNamespace(outcome=None, calls=[])

    def fake_request(method, url, headers=None, json=None, timeout=None):
        script.calls.append({'method': method, 'url': url, 'headers': headers, 'json': json, 'timeout': timeout})
        if isinstance(script.outcome, Exception):
            raise script.outcome
        return script.outcome

    monkeypatch.setattr(requests, 'request', fake_request)
    return script


@pytest.mark.parametrize('tool', sorted(TOOL_CALLS))
@pytest.mark.parametrize('outcome', sorted(MALFORMED_RESPONSES) + sorted(RAISED))
def test_no_result_ever_discloses_a_secret(scripted_jesse, tool, outcome):
    scripted_jesse.outcome = MALFORMED_RESPONSES.get(outcome) or RAISED[outcome]

    result = _registered_tools()[tool](**TOOL_CALLS[tool])

    assert result['status'] in ('success', 'error')
    if result['status'] == 'error':
        assert isinstance(result['error_type'], str) and isinstance(result['message'], str)
    _assert_discloses_nothing(result)


def test_malformed_success_bodies_are_errors_not_empty_results(scripted_jesse):
    scripted_jesse.outcome = MALFORMED_RESPONSES['success_non_json']

    assert credentials_service.get_exchange_api_keys_service()['error_type'] == 'unexpected_response'
    assert credentials_service.get_data_provider_credentials_service()['error_type'] == 'unexpected_response'
    stored = credentials_service.store_exchange_api_key_service(APEX, 'Main', API_KEY, API_SECRET, APEX_FIELDS)
    assert stored['error_type'] == 'unexpected_response'
    assert 'get_exchange_api_keys()' in stored['message']


def test_unexpected_exceptions_and_network_errors_are_contained(scripted_jesse):
    scripted_jesse.outcome = RAISED['unexpected_exception']
    assert credentials_service.get_exchange_api_keys_service()['error_type'] == 'internal_error'

    scripted_jesse.outcome = RAISED['network_error']
    result = credentials_service.store_data_provider_credentials_service(MASSIVE_KEY)
    assert result['error_type'] == 'connection_error'
    assert 'ConnectionError' in result['message']


def test_requests_use_the_hashed_dashboard_password_and_timeouts(scripted_jesse):
    scripted_jesse.outcome = _Response(200, {'status': 'success', 'message': 'ok'})

    credentials_service.validate_data_provider_credentials_service()
    credentials_service.get_exchange_api_keys_service()

    validate_call, list_call = scripted_jesse.calls
    assert validate_call['headers']['Authorization'] == sha256(PASSWORD.encode('utf-8')).hexdigest()
    assert validate_call['timeout'] == credentials_service.VALIDATION_TIMEOUT_SECONDS
    assert list_call['timeout'] == credentials_service.REQUEST_TIMEOUT_SECONDS


def test_missing_worker_configuration_is_reported(monkeypatch):
    monkeypatch.setattr(credentials_service.mcp_config, 'JESSE_API_URL', None)
    monkeypatch.setattr(credentials_service.mcp_config, 'JESSE_PASSWORD', None)

    assert credentials_service.get_exchange_api_keys_service()['error_type'] == 'config_error'


# ---------------------------------------------------------------------------
# FastMCP's own argument handling, which runs before any credential service
# ---------------------------------------------------------------------------

def _fastmcp_server() -> FastMCP:
    server = FastMCP('credential-tests')
    register_credentials_tools(server)
    return server


def _client_view(tool: str, arguments: dict) -> str:
    """The text an MCP client receives, including FastMCP's own argument-validation errors."""
    try:
        return str(asyncio.run(_fastmcp_server().call_tool(tool, arguments)))
    except Exception as exc:
        return str(exc)


@pytest.mark.parametrize(('tool', 'arguments'), [
    # A missing argument makes pydantic quote every argument, secrets included.
    ('store_exchange_api_key', {'exchange': 'KuCoin Spot', 'api_key': API_KEY, 'api_secret': API_SECRET,
                                'additional_fields': {'api_passphrase': PASSPHRASE}}),
    ('store_data_provider_credentials', {'key': MASSIVE_KEY}),
    ('delete_exchange_api_key', {'exchange_api_key_id': API_KEY}),
    # A wrong type makes pydantic quote the value.
    ('store_exchange_api_key', {'exchange': 'KuCoin Spot', 'name': 'Main', 'api_key': API_KEY,
                                'api_secret': API_SECRET, 'additional_fields': PASSPHRASE}),
    ('store_exchange_api_key', {'exchange': 'KuCoin Spot', 'name': 'Main', 'api_key': {'key': API_KEY},
                                'api_secret': API_SECRET, 'additional_fields': {'api_passphrase': PASSPHRASE}}),
    ('store_exchange_api_key', {'exchange': APEX, 'name': 'Main', 'api_key': API_KEY, 'api_secret': API_SECRET,
                                'additional_fields': {**APEX_FIELDS, 'wallet_address': [WALLET]}}),
    ('store_data_provider_credentials', {'api_key': [MASSIVE_KEY]}),
    ('validate_data_provider_credentials', {'provider_id': {'api_key': MASSIVE_KEY}}),
    ('get_exchange_api_key_requirements', {'exchange': [API_SECRET]}),
])
def test_fastmcp_argument_errors_never_quote_submitted_values(scripted_jesse, tool, arguments):
    text = _client_view(tool, arguments)

    assert 'Error executing tool' not in text
    assert "'status': 'error'" in text or '"status": "error"' in text
    _assert_discloses_nothing(text)
    assert scripted_jesse.calls == []


def test_fastmcp_schema_keeps_the_advertised_argument_types():
    schemas = {tool.name: tool.inputSchema for tool in asyncio.run(_fastmcp_server().list_tools())}

    store = schemas['store_exchange_api_key']['properties']
    for name in ('exchange', 'name', 'api_key', 'api_secret'):
        assert store[name]['type'] == 'string', name
    assert store['additional_fields']['type'] == 'object'
    assert schemas['store_data_provider_credentials']['properties']['provider_id']['default'] == 'Massive'
    assert schemas['delete_exchange_api_key']['properties']['id']['type'] == 'string'


def test_integer_fields_accept_json_numbers_through_fastmcp(backend):
    text = _client_view('store_exchange_api_key', {
        'exchange': 'Lighter Perpetual', 'name': 'Lighter main', 'api_key': API_KEY, 'api_secret': API_SECRET,
        'additional_fields': {'api_key_index': 3, 'account_index': 12},
    })

    assert 'exchange_api_key_stored' in text, text
    _assert_discloses_nothing(text)
    row = ExchangeApiKeys.get(ExchangeApiKeys.name == 'Lighter main')
    assert row.get_additional_fields() == {'api_key_index': '3', 'account_index': '12'}
    # The Dashboard's list route masks additional fields by slicing them, so they must be strings.
    dashboard = backend.client.get('/exchange/api-keys', headers={'Authorization': sha256(PASSWORD.encode('utf-8')).hexdigest()})
    assert dashboard.status_code == 200


# ---------------------------------------------------------------------------
# Symbol search (shares this file's fake-backend style) and documentation
# ---------------------------------------------------------------------------

def _fake_response(status_code, payload):
    return SimpleNamespace(status_code=status_code, json=lambda: payload, text=json.dumps(payload))


@pytest.fixture
def mcp_backend(monkeypatch):
    calls = []
    queued = []

    def fake_request(method, url, headers=None, json=None, timeout=None):
        calls.append({'method': method, 'url': url, 'headers': headers, 'json': json, 'timeout': timeout})
        return queued.pop(0)

    def fake_post(url, headers=None, json=None, timeout=None):
        return fake_request('POST', url, headers=headers, json=json, timeout=timeout)

    monkeypatch.setattr(credentials_service.mcp_config, 'JESSE_API_URL', 'http://jesse.test')
    monkeypatch.setattr(credentials_service.mcp_config, 'JESSE_PASSWORD', 'test-password')
    monkeypatch.setattr('requests.request', fake_request)
    monkeypatch.setattr('requests.post', fake_post)
    return calls, queued


def test_search_symbols_service_uses_the_shared_search_endpoint(mcp_backend):
    calls, queued = mcp_backend
    queued.append(_fake_response(200, {
        'data': [{'symbol': 'MSFT-USD', 'name': 'Microsoft Corp', 'kind': 'Common Stock', 'venue': 'NASDAQ'}],
        'catalog_size': 13152,
    }))

    result = candles_service.search_symbols_service('Massive Stocks', 'microsoft', limit=5)

    assert calls[0]['url'] == 'http://jesse.test/exchange/search-symbols'
    assert calls[0]['json'] == {'exchange': 'Massive Stocks', 'query': 'microsoft', 'limit': 5}
    assert calls[0]['headers']['Authorization'] != 'test-password'
    assert result['status'] == 'success'
    assert result['match_count'] == 1
    assert result['catalog_size'] == 13152
    assert result['matches'][0]['symbol'] == 'MSFT-USD'

    queued.append(_fake_response(200, {'data': [], 'catalog_size': 47961}))
    miss = candles_service.search_symbols_service('Massive Futures', 'AAPL')
    assert miss['match_count'] == 0
    assert 'No symbol on Massive Futures matches' in miss['message']

    queued.append(_fake_response(401, {'error': 'Massive API credentials are not configured'}))
    failure = candles_service.search_symbols_service('Massive Stocks', 'msft')
    assert failure['status'] == 'error'
    assert failure['http_status'] == 401
    assert 'not configured' in failure['message']


def test_rules_and_resource_describe_write_only_management():
    rules = _load_packaged_rules()
    resource = open(credentials_service.__file__.replace('tools/services/credentials.py', 'resources/credentials.md'),
                    encoding='utf-8').read()

    assert 'no tool returns a stored secret' in ' '.join(rules.split())
    assert 'get_exchange_api_key_requirements()' in rules
    for tool in CREDENTIAL_TOOLS:
        assert tool in resource, tool
    assert 'exchange_api_key_id' in resource
