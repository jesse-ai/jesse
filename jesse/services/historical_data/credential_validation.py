import requests

from .errors import (
    ProviderAuthenticationError,
    ProviderEntitlementError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderUnavailableError,
)


MASSIVE_CREDENTIAL_TEST_URL = 'https://api.massive.com/v3/reference/tickers'
# Ten seconds bounds a user-triggered settings action without making transient network failures look immediate.
MASSIVE_CREDENTIAL_TEST_TIMEOUT_SECONDS = 10
# The one-minute chart is what imports need, so testing it also catches plans without intraday data.
FMP_CREDENTIAL_TEST_URL = 'https://financialmodelingprep.com/stable/historical-chart/1min'
FMP_CREDENTIAL_TEST_TIMEOUT_SECONDS = 10


def validate_massive_api_key(api_key: str) -> None:
    """Verify a Massive key against an endpoint included in every Stocks plan."""
    try:
        # The fixed host and disabled redirects prevent credentials from being forwarded elsewhere.
        with requests.get(
            MASSIVE_CREDENTIAL_TEST_URL,
            headers={'Authorization': f'Bearer {api_key}'},
            params={'market': 'stocks', 'active': 'true', 'limit': 1},
            timeout=MASSIVE_CREDENTIAL_TEST_TIMEOUT_SECONDS,
            allow_redirects=False,
            stream=True,
        ) as response:
            status_code = response.status_code
    except requests.RequestException as exc:
        raise ProviderUnavailableError('Massive is currently unavailable') from exc

    if status_code == 200:
        return
    if status_code == 401:
        raise ProviderAuthenticationError('Massive rejected the API key')
    if status_code == 403:
        raise ProviderEntitlementError('The API key cannot access Massive reference data')
    if status_code == 429:
        raise ProviderRateLimitError('Massive rate limit reached')
    if status_code >= 500:
        raise ProviderUnavailableError('Massive is currently unavailable')
    raise ProviderRequestError('Massive could not validate the API key')


def validate_fmp_api_key(api_key: str) -> None:
    """Verify an FMP key against the one-minute chart, so a plan without intraday data is reported too."""
    try:
        # A fixed past date keeps the response to one trading day; the header keeps the key out of the URL.
        with requests.get(
            FMP_CREDENTIAL_TEST_URL,
            headers={'apikey': api_key},
            params={'symbol': 'AAPL', 'from': '2025-01-02', 'to': '2025-01-02'},
            timeout=FMP_CREDENTIAL_TEST_TIMEOUT_SECONDS,
            allow_redirects=False,
            stream=True,
        ) as response:
            status_code = response.status_code
            # Plan limits can also arrive as a successful status carrying an error object.
            payload = response.json() if status_code == 200 else None
    except requests.RequestException as exc:
        raise ProviderUnavailableError('FMP is currently unavailable') from exc
    except ValueError as exc:
        raise ProviderRequestError('FMP could not validate the API key') from exc

    if status_code == 200 and isinstance(payload, list):
        return
    if status_code == 401:
        raise ProviderAuthenticationError('FMP rejected the API key')
    error_message = payload.get('Error Message') if isinstance(payload, dict) else None
    if isinstance(error_message, str) and 'limit' in error_message.lower():
        raise ProviderRateLimitError('FMP usage limit reached')
    if status_code in (402, 403) or (status_code == 200 and isinstance(payload, dict)):
        raise ProviderEntitlementError('The FMP plan does not include one-minute historical data')
    if status_code == 429:
        raise ProviderRateLimitError('FMP rate limit reached')
    if status_code >= 500:
        raise ProviderUnavailableError('FMP is currently unavailable')
    raise ProviderRequestError('FMP could not validate the API key')
