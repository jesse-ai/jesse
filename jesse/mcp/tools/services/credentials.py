"""
Jesse Credential Service Functions

MCP counterpart of the Dashboard's "Exchange API Keys" and "Data Providers" credential pages:
store, list, and delete exchange API keys used by Jesse Live and data provider keys (such as
Massive) used by historical imports, through the same authenticated Jesse routes the Dashboard
calls.

Secret boundary: secrets only travel from the caller to Jesse. Every result is rebuilt from an
allow-list of non-secret metadata (ids, names, exchange or provider, timestamps, field
requirements); Jesse's response bodies are never passed through, so the masked key fragments
the Dashboard shows and any unexpected fields are dropped. Error messages are written here
rather than copied from a response body or an exception, because either can contain submitted
values. Nothing here reads a stored secret back, and the Dashboard's password-confirmed CSV
export has no MCP counterpart.
"""

import functools
import uuid
from datetime import datetime
from typing import Any, Callable, NamedTuple, Optional

import requests

import jesse.mcp.mcp_config as mcp_config
from jesse.enums import data_providers
from jesse.info import live_trading_exchanges

from .auth import hash_password


REQUEST_TIMEOUT_SECONDS = 30
# Credential validation performs a live provider round-trip, which can be slow on free plans.
VALIDATION_TIMEOUT_SECONDS = 90
DEFAULT_DATA_PROVIDER = data_providers.MASSIVE
# ExchangeApiKeys keeps name, api_key and api_secret in peewee CharFields, whose default
# VARCHAR(255) makes PostgreSQL reject longer values with an opaque 500, so they are checked first.
MAX_EXCHANGE_FIELD_LENGTH = 255
# Body of the 401 Jesse sends when the dashboard password hash is wrong. The provider
# validation route also answers 401, for a key the provider rejected, so the body tells them apart.
_JESSE_AUTH_REJECTION_MESSAGE = 'Invalid password'
# Prefix of the 400 message Jesse sends for a duplicate exchange API key name.
_DUPLICATE_NAME_PREFIX = 'API key with the name'


class _JesseResponse(NamedTuple):
    status_code: int
    payload: Any


class _JesseUnavailable(Exception):
    """Jesse could not be called; carries the MCP error type and a message safe to return."""

    def __init__(self, error_type: str, message: str):
        super().__init__(message)
        self.error_type = error_type
        self.message = message


def _error(action: str, error_type: str, message: str, **extra: Any) -> dict:
    return {'status': 'error', 'action': action, 'error_type': error_type, 'message': message, **extra}


def _contained(action: str) -> Callable[[Callable[..., dict]], Callable[..., dict]]:
    """
    Turn any unexpected exception into a generic MCP error.

    FastMCP would otherwise return the exception text to the client, and exceptions raised
    while handling a request can quote the submitted secrets.
    """

    def decorator(func: Callable[..., dict]) -> Callable[..., dict]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> dict:
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                return _error(
                    action, 'internal_error',
                    f'The credential tool failed unexpectedly ({type(exc).__name__}). Details are '
                    'withheld because they could contain credential values.',
                )

        return wrapper

    return decorator


def _call(method: str, path: str, json_body: Optional[dict] = None,
          timeout: int = REQUEST_TIMEOUT_SECONDS) -> _JesseResponse:
    """Call one authenticated Jesse route and return its status code and parsed JSON body (None if not JSON)."""
    api_url = mcp_config.JESSE_API_URL
    password = mcp_config.JESSE_PASSWORD
    if not api_url or not password:
        raise _JesseUnavailable('config_error', 'The MCP worker has no Jesse API URL or dashboard password configured.')
    try:
        response = requests.request(
            method,
            f'{api_url}{path}',
            headers={'Authorization': hash_password(password)},  # Jesse expects the bare hash, not Bearer
            json=json_body,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        # The exception text is not relayed: it may quote the request.
        raise _JesseUnavailable('connection_error', f'Could not reach the Jesse API ({type(exc).__name__}).') from None
    try:
        payload = response.json()
    except ValueError:
        payload = None
    return _JesseResponse(response.status_code, payload)


def _message_of(payload: Any) -> str:
    """Jesse's own message field, for matching known responses only; it is never returned."""
    if isinstance(payload, dict) and isinstance(payload.get('message'), str):
        return payload['message']
    return ''


def _is_auth_rejection(response: _JesseResponse) -> bool:
    return response.status_code == 401 and _message_of(response.payload) == _JESSE_AUTH_REJECTION_MESSAGE


def _auth_error(action: str) -> dict:
    return _error(action, 'authentication_failed', 'Jesse rejected the MCP worker credentials (dashboard password).')


def _unexpected(action: str, what: str) -> dict:
    return _error(action, 'unexpected_response', f'Jesse returned an unexpected response while {what}.')


def _jesse_error(action: str, what: str, status_code: int) -> dict:
    return _error(action, 'jesse_error', f'Jesse could not {what} (HTTP {status_code}).', http_status=status_code)


def _clean_uuid(value: Any) -> Optional[str]:
    """Canonical form of an exchange API key id (a UUID), or None when the value is not one."""
    if not isinstance(value, str):
        return None
    try:
        return str(uuid.UUID(value.strip()))
    except ValueError:
        return None


def _clean_iso_datetime(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return None
    return value


def _clean_timestamp(value: Any) -> Optional[int]:
    # bool is an int subclass, so it is excluded explicitly.
    return value if isinstance(value, int) and not isinstance(value, bool) else None


# ---------------------------------------------------------------------------
# Exchange API keys
# ---------------------------------------------------------------------------

def _field(key: str, label: str, location: str, required: bool = True, value_format: str = 'text') -> dict:
    return {'key': key, 'label': label, 'location': location, 'required': required, 'format': value_format}


def _exchange_fields(exchange: str) -> list[dict]:
    """
    Credential fields the Dashboard's Exchange API Keys form asks for on `exchange`.

    The exchange-name rules mirror dashboard-v1/app/pages/exchange-api-keys.vue, and the
    additional field keys are the ones jesse-live reads through get_additional_fields():
    Apex in LiveExchange, KuCoin in the KuCoin drivers, Lighter in LighterPerpetualMain (which
    also honors an optional account_index the Dashboard form does not show). Both indexes go
    through int() in that driver, hence the integer format.
    """
    is_apex = exchange.startswith('Apex')
    is_kucoin = 'kucoin' in exchange.lower()
    is_lighter = exchange.startswith('Lighter')
    is_hyperliquid = 'Hyperliquid' in exchange

    if is_lighter:
        api_key_label, api_secret_label = 'L1 Wallet Address', 'API Private Key'
    elif is_hyperliquid:
        api_key_label, api_secret_label = 'Wallet Address', 'Private Key'
    else:
        api_key_label, api_secret_label = 'API Key', 'API Secret'

    fields = [_field('api_key', api_key_label, 'argument'), _field('api_secret', api_secret_label, 'argument')]
    if is_lighter:
        fields.append(_field('api_key_index', 'API Key Index', 'additional_fields', value_format='integer'))
        fields.append(_field('account_index', 'Account Index', 'additional_fields', required=False, value_format='integer'))
    if is_apex or is_kucoin:
        fields.append(_field('api_passphrase', 'API Passphrase', 'additional_fields'))
    if is_apex:
        fields.append(_field('wallet_address', 'Wallet Address', 'additional_fields'))
        fields.append(_field('stark_private_key', 'Omni/Stark Key', 'additional_fields'))
    return fields


def _exchange_requirements(exchange: str) -> dict:
    return {'exchange': exchange, 'fields': _exchange_fields(exchange)}


def _unsupported_exchange(action: str) -> dict:
    # The rejected value is not echoed: a misplaced secret would otherwise come straight back.
    return _error(
        action, 'unsupported_exchange',
        'exchange must be a live-trading exchange name exactly as get_exchange_api_key_requirements() lists it.',
    )


def _exchange_key_metadata(entry: Any) -> Optional[dict]:
    """Keep only the non-secret metadata of one stored key; None when the entry has no valid id."""
    if not isinstance(entry, dict):
        return None
    key_id = _clean_uuid(entry.get('id'))
    if key_id is None:
        return None
    return {
        'id': key_id,
        'name': entry.get('name') if isinstance(entry.get('name'), str) else None,
        'exchange': entry.get('exchange') if isinstance(entry.get('exchange'), str) else None,
        'created_at': _clean_iso_datetime(entry.get('created_at')),
    }


def _fetch_exchange_keys(action: str) -> list[dict] | dict:
    """Return the metadata of every stored exchange API key, or the MCP error to return."""
    response = _call('GET', '/exchange/api-keys')
    if _is_auth_rejection(response):
        return _auth_error(action)
    if response.status_code != 200:
        return _jesse_error(action, 'list the stored exchange API keys', response.status_code)
    if not isinstance(response.payload, dict) or not isinstance(response.payload.get('data'), list):
        return _unexpected(action, 'listing exchange API keys')
    return [meta for meta in (_exchange_key_metadata(entry) for entry in response.payload['data']) if meta]


@_contained('exchange_api_key_requirements_failed')
def get_exchange_api_key_requirements_service(exchange: Optional[str] = None) -> dict:
    """Describe the credential fields each live-trading exchange accepts; no request to Jesse is needed."""
    action = 'exchange_api_key_requirements_failed'
    if exchange is None or (isinstance(exchange, str) and not exchange.strip()):
        exchanges = list(live_trading_exchanges)
    elif isinstance(exchange, str) and exchange.strip() in live_trading_exchanges:
        exchanges = [exchange.strip()]
    else:
        return _unsupported_exchange(action) | {'supported_exchanges': list(live_trading_exchanges)}
    return {
        'status': 'success',
        'action': 'exchange_api_key_requirements_retrieved',
        'message': f'Credential fields for {len(exchanges)} live-trading exchange(s).',
        'exchanges': [_exchange_requirements(name) for name in exchanges],
    }


@_contained('exchange_api_keys_list_failed')
def get_exchange_api_keys_service() -> dict:
    """List stored exchange API keys as id, name, exchange, and created_at only."""
    action = 'exchange_api_keys_list_failed'
    try:
        keys = _fetch_exchange_keys(action)
    except _JesseUnavailable as exc:
        return _error(action, exc.error_type, exc.message)
    if isinstance(keys, dict):
        return keys
    return {
        'status': 'success',
        'action': 'exchange_api_keys_listed',
        'message': f'Found {len(keys)} stored exchange API key(s).',
        'exchange_api_keys': keys,
    }


def _clean_additional_fields(exchange: str, additional_fields: Any) -> dict[str, str] | str:
    """Validate additional fields against the exchange's requirements; returns the cleaned dict or an error message."""
    allowed = {field['key']: field for field in _exchange_fields(exchange) if field['location'] == 'additional_fields'}
    if additional_fields is None:
        additional_fields = {}
    if not isinstance(additional_fields, dict):
        return 'additional_fields must be an object mapping field names to string values.'
    # Unknown keys are not echoed either, in case a value was passed as a key by mistake.
    if any(key not in allowed for key in additional_fields):
        accepted = ', '.join(allowed) or 'none'
        return f'additional_fields contains a field {exchange} does not use. Accepted fields: {accepted}.'

    cleaned: dict[str, str] = {}
    for key, field in allowed.items():
        value = additional_fields.get(key)
        # Integer fields also take a JSON number, but every value is stored as a string: the
        # Dashboard's list route masks each additional field by slicing it, which fails on an int.
        # bool is an int subclass, so it is excluded explicitly.
        if field['format'] == 'integer' and isinstance(value, int) and not isinstance(value, bool):
            value = str(value)
        if value is not None and not isinstance(value, str):
            return f'additional_fields.{key} must be a string.'
        value = (value or '').strip()
        if not value:
            if field['required']:
                return f'{exchange} requires additional_fields.{key} ({field["label"]}).'
            continue
        if field['format'] == 'integer':
            try:
                int(value)
            except ValueError:
                return f'additional_fields.{key} must be an integer.'
        cleaned[key] = value
    return cleaned


@_contained('exchange_api_key_store_failed')
def store_exchange_api_key_service(
    exchange: str,
    name: str,
    api_key: str,
    api_secret: str,
    additional_fields: Optional[dict[str, str]] = None,
) -> dict:
    """Store one exchange API key for Jesse Live and return only its id, name, exchange, and created_at."""
    action = 'exchange_api_key_store_failed'
    values = {'exchange': exchange, 'name': name, 'api_key': api_key, 'api_secret': api_secret}
    for key, value in values.items():
        if not isinstance(value, str):
            return _error(action, 'invalid_request', f'{key} is required and must be a string.')
    exchange, name, api_key, api_secret = exchange.strip(), name.strip(), api_key.strip(), api_secret.strip()

    if exchange not in live_trading_exchanges:
        return _unsupported_exchange(action)
    for key, value in (('name', name), ('api_key', api_key), ('api_secret', api_secret)):
        if not value:
            return _error(action, 'invalid_request', f'{key} must not be empty.')
        if len(value) > MAX_EXCHANGE_FIELD_LENGTH:
            return _error(action, 'invalid_request', f'{key} must be at most {MAX_EXCHANGE_FIELD_LENGTH} characters.')
    extras = _clean_additional_fields(exchange, additional_fields)
    if isinstance(extras, str):
        return _error(action, 'invalid_request', extras)

    body = {'exchange': exchange, 'name': name, 'api_key': api_key, 'api_secret': api_secret, 'additional_fields': extras}
    try:
        response = _call('POST', '/exchange/api-keys/store', body)
    except _JesseUnavailable as exc:
        return _error(action, exc.error_type, exc.message)

    if _is_auth_rejection(response):
        return _auth_error(action)
    if response.status_code == 400 and _message_of(response.payload).startswith(_DUPLICATE_NAME_PREFIX):
        return _error(action, 'name_taken', 'An exchange API key with this name already exists. Choose another name.')
    if response.status_code == 400:
        return _error(action, 'rejected', 'Jesse rejected the exchange API key.', http_status=400)
    if response.status_code != 200:
        return _jesse_error(action, 'store the exchange API key', response.status_code)

    stored = response.payload.get('data') if isinstance(response.payload, dict) else None
    metadata = _exchange_key_metadata(stored)
    if metadata is None:
        return _unexpected(action, 'storing the exchange API key; call get_exchange_api_keys() to check whether it was saved')
    return {
        'status': 'success',
        'action': 'exchange_api_key_stored',
        'message': f'Stored the exchange API key "{name}" for {exchange}.',
        # name and exchange are the validated inputs, so nothing Jesse echoes back reaches the result.
        'exchange_api_key': {**metadata, 'name': name, 'exchange': exchange},
    }


@_contained('exchange_api_key_delete_failed')
def delete_exchange_api_key_service(exchange_api_key_id: str) -> dict:
    """Delete one stored exchange API key by id and return the metadata of the deleted key."""
    action = 'exchange_api_key_delete_failed'
    key_id = _clean_uuid(exchange_api_key_id)
    if key_id is None:
        return _error(action, 'invalid_request', 'id must be an exchange API key id from get_exchange_api_keys().')

    try:
        # Jesse's delete route reports success for unknown ids, so the key is looked up first.
        keys = _fetch_exchange_keys(action)
        if isinstance(keys, dict):
            return keys
        target = next((key for key in keys if key['id'] == key_id), None)
        if target is None:
            return _error(action, 'not_found', 'No stored exchange API key has this id. Call get_exchange_api_keys().')
        response = _call('POST', '/exchange/api-keys/delete', {'id': key_id})
    except _JesseUnavailable as exc:
        return _error(action, exc.error_type, exc.message)

    if _is_auth_rejection(response):
        return _auth_error(action)
    if response.status_code != 200:
        return _jesse_error(action, 'delete the exchange API key', response.status_code)
    return {
        'status': 'success',
        'action': 'exchange_api_key_deleted',
        'message': f'Deleted the exchange API key "{target["name"]}".',
        'exchange_api_key': target,
    }


# ---------------------------------------------------------------------------
# Data provider credentials
# ---------------------------------------------------------------------------

def _provider_status(entry: Any) -> Optional[dict]:
    """Keep only the non-secret configuration status of one data provider."""
    if not isinstance(entry, dict) or not isinstance(entry.get('provider_id'), str):
        return None
    fields = entry.get('credential_fields') if isinstance(entry.get('credential_fields'), list) else []
    return {
        'provider_id': entry['provider_id'],
        'name': entry.get('name') if isinstance(entry.get('name'), str) else entry['provider_id'],
        'configured': entry.get('configured') is True,
        'created_at': _clean_timestamp(entry.get('created_at')),
        'updated_at': _clean_timestamp(entry.get('updated_at')),
        'credential_fields': [
            {'key': field['key'], 'label': field.get('label'), 'secret': field.get('secret') is True}
            for field in fields
            if isinstance(field, dict) and isinstance(field.get('key'), str)
        ],
    }


def _fetch_provider_statuses(action: str) -> list[dict] | dict:
    """Return the status of every supported data provider, or the MCP error to return."""
    response = _call('GET', '/data-providers/credentials')
    if _is_auth_rejection(response):
        return _auth_error(action)
    if response.status_code != 200:
        return _jesse_error(action, 'list the data provider credentials', response.status_code)
    if not isinstance(response.payload, dict) or not isinstance(response.payload.get('data'), list):
        return _unexpected(action, 'listing data provider credentials')
    return [status for status in (_provider_status(entry) for entry in response.payload['data']) if status]


def _clean_provider_id(provider_id: Any) -> Optional[str]:
    return provider_id.strip() if isinstance(provider_id, str) and provider_id.strip() else None


@_contained('data_provider_credentials_list_failed')
def get_data_provider_credentials_service() -> dict:
    """List every supported data provider with its credential fields and configuration status."""
    action = 'data_provider_credentials_list_failed'
    try:
        providers = _fetch_provider_statuses(action)
    except _JesseUnavailable as exc:
        return _error(action, exc.error_type, exc.message)
    if isinstance(providers, dict):
        return providers
    configured = [provider['provider_id'] for provider in providers if provider['configured']]
    return {
        'status': 'success',
        'action': 'data_provider_credentials_listed',
        'message': f'Configured data providers: {", ".join(configured)}' if configured else 'No data provider credentials are configured.',
        'configured_providers': configured,
        'data_providers': providers,
    }


@_contained('data_provider_credentials_store_failed')
def store_data_provider_credentials_service(api_key: str, provider_id: str = DEFAULT_DATA_PROVIDER) -> dict:
    """Store a data provider API key. Jesse rejects a second key until the existing one is deleted."""
    action = 'data_provider_credentials_store_failed'
    provider = _clean_provider_id(provider_id)
    if provider is None:
        return _error(action, 'invalid_request', 'provider_id must be a non-empty string.')
    if not isinstance(api_key, str) or not api_key.strip():
        return _error(action, 'invalid_request', 'api_key is required and must be a non-empty string.')

    try:
        response = _call('POST', '/data-providers/credentials/store', {'provider_id': provider, 'api_key': api_key.strip()})
    except _JesseUnavailable as exc:
        return _error(action, exc.error_type, exc.message)

    if _is_auth_rejection(response):
        return _auth_error(action)
    if response.status_code == 409:
        return _error(
            action, 'already_configured',
            f'{provider} already has a stored API key. Delete it with delete_data_provider_credentials() before storing a new one.',
        )
    if response.status_code == 400:
        return _error(action, 'unsupported_provider', 'provider_id must be one of the providers get_data_provider_credentials() lists.')
    if response.status_code != 200:
        return _jesse_error(action, 'store the data provider credentials', response.status_code)

    status = _provider_status(response.payload.get('data') if isinstance(response.payload, dict) else None)
    if status is None:
        return _unexpected(action, 'storing the data provider credentials; call get_data_provider_credentials() to check')
    return {
        'status': 'success',
        'action': 'data_provider_credentials_stored',
        'message': f'Stored the {provider} API key. Call validate_data_provider_credentials() to test it.',
        'data_provider': status,
    }


@_contained('data_provider_credentials_delete_failed')
def delete_data_provider_credentials_service(provider_id: str = DEFAULT_DATA_PROVIDER) -> dict:
    """Delete a data provider's stored credentials. Imported candles are kept."""
    action = 'data_provider_credentials_delete_failed'
    provider = _clean_provider_id(provider_id)
    if provider is None:
        return _error(action, 'invalid_request', 'provider_id must be a non-empty string.')

    try:
        # Jesse's delete route succeeds even when nothing is stored, so the status is checked first.
        providers = _fetch_provider_statuses(action)
        if isinstance(providers, dict):
            return providers
        current = next((status for status in providers if status['provider_id'] == provider), None)
        if current is None:
            return _error(action, 'unsupported_provider', 'provider_id must be one of the providers get_data_provider_credentials() lists.')
        if not current['configured']:
            return _error(action, 'not_found', f'{provider} has no stored API key.')
        response = _call('POST', '/data-providers/credentials/delete', {'provider_id': provider})
    except _JesseUnavailable as exc:
        return _error(action, exc.error_type, exc.message)

    if _is_auth_rejection(response):
        return _auth_error(action)
    if response.status_code != 200:
        return _jesse_error(action, 'delete the data provider credentials', response.status_code)
    status = _provider_status(response.payload.get('data') if isinstance(response.payload, dict) else None)
    return {
        'status': 'success',
        'action': 'data_provider_credentials_deleted',
        'message': f'Deleted the {provider} API key. Already imported candles are kept.',
        'data_provider': status or {**current, 'configured': False, 'created_at': None, 'updated_at': None},
    }


# Jesse's validation route answers with these statuses (see data_provider_credentials_controller);
# the messages are written here so a provider response can never be relayed.
_VALIDATION_ERRORS = {
    400: ('unsupported_provider', 'provider_id must be one of the providers get_data_provider_credentials() lists.'),
    401: ('credentials_rejected', '{provider} rejected the stored API key.'),
    403: ('missing_entitlement', 'The stored {provider} API key cannot access the reference data used for validation.'),
    404: ('not_configured', '{provider} has no stored API key.'),
    429: ('rate_limited', '{provider} rate limit reached. Try again shortly.'),
    502: ('validation_failed', '{provider} could not validate the API key.'),
    503: ('provider_unavailable', '{provider} is currently unavailable.'),
}


@_contained('data_provider_credentials_validate_failed')
def validate_data_provider_credentials_service(provider_id: str = DEFAULT_DATA_PROVIDER) -> dict:
    """Check the stored data provider key against the provider without returning the key."""
    action = 'data_provider_credentials_validate_failed'
    provider = _clean_provider_id(provider_id)
    if provider is None:
        return _error(action, 'invalid_request', 'provider_id must be a non-empty string.')

    try:
        response = _call('POST', '/data-providers/credentials/validate', {'provider_id': provider},
                         timeout=VALIDATION_TIMEOUT_SECONDS)
    except _JesseUnavailable as exc:
        return _error(action, exc.error_type, exc.message)

    if _is_auth_rejection(response):
        return _auth_error(action)
    if response.status_code == 200:
        return {
            'status': 'success',
            'action': 'data_provider_credentials_validated',
            'message': f'{provider} accepted the stored API key.',
            'provider_id': provider,
        }
    if response.status_code in _VALIDATION_ERRORS:
        error_type, message = _VALIDATION_ERRORS[response.status_code]
        # Jesse answers 400 for an unknown provider, which must not be echoed: a misplaced
        # secret would come straight back. Every other status means the provider is supported.
        extra = {} if response.status_code == 400 else {'provider_id': provider}
        return _error(action, error_type, message.format(provider=provider), **extra)
    return _jesse_error(action, 'validate the data provider credentials', response.status_code)
