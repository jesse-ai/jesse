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
