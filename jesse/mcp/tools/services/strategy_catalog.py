"""
Jesse Strategy Catalog Service Functions

Browse, inspect, and import strategies from the jesse.trade strategy catalog (the community
strategies shown on the dashboard's Strategies page). These are online strategies, not the
strategies installed in the Jesse project.

Every call goes through the same Jesse API routes the dashboard uses, so Jesse keeps doing
the talking to jesse.trade and jesse.trade keeps enforcing who may see and import which
strategy code:

- GET  /strategy/periods                     trading periods the catalog has metrics for
- POST /auth/jesse-trade-token               exchanges the project's LICENSE_API_TOKEN for a
                                             jesse.trade session token
- GET  /strategy/index                       ranked catalog for one period
- GET  /strategy/jesse-trade/{slug}/metrics  metrics for one symbol/timeframe/period
- POST /strategy/import                      writes a catalog strategy into strategies/

The jesse.trade session token only travels in the X-Jesse-Trade-Token request header, as
the dashboard sends it. It is exchanged again for each call that needs it and is never
stored, logged, or returned.
"""

import re
from datetime import datetime
from typing import Any, Optional

import requests

import jesse.mcp.mcp_config as mcp_config

from .auth import hash_password

# Jesse proxies every catalog call to jesse.trade with its own 10-second timeout, so this
# only has to outlast one upstream call plus Jesse's own work.
REQUEST_TIMEOUT_SECONDS = 30

# Sort labels exactly as the dashboard's Strategies page sends them. jesse.trade silently
# ranks by Sharpe Ratio for any other value, so they are validated here instead.
SORT_OPTIONS = ('Sharpe Ratio', 'PNL', 'Sortino Ratio', 'Calmar Ratio', 'Win Rate')
DEFAULT_SORT = 'Sharpe Ratio'
# Values of a catalog strategy's `type`, shown as the FREE/PREMIUM badge in the dashboard.
STRATEGY_TYPES = ('free', 'premium')

# jesse.trade returns the whole ranked list for a period at once, including every free
# strategy's source code and equity curve, so pages are cut here to keep tool results small.
# A page of 25 summaries, descriptions included, stays a comfortably sized tool result.
DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 25

# jesse.trade's slug rule (3-150 lowercase letters, digits, and hyphens), checked before any
# request so a typo fails with a clear message instead of a proxied 400.
_SLUG = re.compile(r'[a-z0-9-]{3,150}')

# Metric fields kept in each browse result. The full set (plus equity curve) is available per
# symbol/timeframe/period through get_catalog_strategy_metrics.
_SUMMARY_METRICS = (
    'exchange', 'symbol', 'timeframe', 'starting_date', 'finishing_date',
    'net_profit_percentage', 'annual_return', 'max_drawdown', 'sharpe_ratio', 'sortino_ratio',
    'calmar_ratio', 'win_rate', 'total_completed_trades',
)
# Metric fields that are bookkeeping or too large for a tool result.
_OMITTED_METRICS = ('id', 'strategy_id', 'equity_curve', 'created_at', 'updated_at')

CATALOG_SOURCE = (
    'jesse.trade strategy catalog: community strategies published online. These are not the '
    'strategies installed in this Jesse project until you import one.'
)
LICENSE_TOKEN_HELP = (
    'Create a LICENSE_API_TOKEN at https://jesse.trade/user/api-tokens, add it to the Jesse '
    "project's .env file as LICENSE_API_TOKEN=..., and restart Jesse. Free and premium "
    'strategies both need it to be imported.'
)
PREMIUM_HELP = (
    'Premium strategies need an active jesse.trade Premium plan (https://jesse.trade/pricing). '
    'After upgrading, retry the import.'
)


class _JesseTradeAuthError(Exception):
    """The LICENSE_API_TOKEN exchange failed; carries the MCP error fields to return."""

    def __init__(self, error_type: str, message: str):
        super().__init__(message)
        self.error_type = error_type
        self.message = message


def _error(action: str, error_type: str, message: str, **extra: Any) -> dict:
    return {'status': 'error', 'action': action, 'error_type': error_type, 'message': message, **extra}


def _request(
        method: str,
        path: str,
        *,
        params: Optional[dict] = None,
        json_body: Optional[dict] = None,
        jesse_trade_token: Optional[str] = None,
) -> requests.Response:
    """Call one Jesse API route with the dashboard credentials the MCP worker runs with."""
    headers = {'Authorization': hash_password(mcp_config.JESSE_PASSWORD)}  # Jesse uses the hash directly, not Bearer
    if jesse_trade_token:
        headers['X-Jesse-Trade-Token'] = jesse_trade_token
    return requests.request(
        method,
        f'{mcp_config.JESSE_API_URL}{path}',
        params=params,
        json=json_body,
        headers=headers,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )


def _payload(response: requests.Response) -> dict:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _message(response: requests.Response, payload: dict) -> str:
    return str(payload.get('message') or response.text or f'HTTP {response.status_code}')


def _rejected_dashboard_credentials(response: requests.Response, payload: dict) -> bool:
    """
    True when Jesse itself refused the MCP worker's dashboard password.

    Jesse's own 401 body is {"message": "Invalid password"}, while every failure it proxies
    from jesse.trade carries "status": "error". That is the only way to tell a bad dashboard
    password from jesse.trade rejecting the license token, which also arrives as a 401.
    """
    return response.status_code == 401 and payload.get('status') != 'error'


def _upstream_error(action: str, response: requests.Response, payload: dict, not_found_type: str) -> dict:
    """Map a failed proxied catalog call to a stable MCP error; Jesse forwards jesse.trade's status code."""
    message = _message(response, payload)
    if _rejected_dashboard_credentials(response, payload):
        return _error(action, 'authentication_failed', 'Jesse rejected the MCP credentials (dashboard password).')
    if response.status_code == 401:
        return _error(action, 'license_token_rejected', f'jesse.trade rejected the sign-in ({message}). {LICENSE_TOKEN_HELP}')
    if response.status_code == 404:
        return _error(action, not_found_type, message)
    if response.status_code == 400:
        return _error(action, 'invalid_request', message)
    if response.status_code >= 500:
        # Jesse answers 500 when it cannot reach jesse.trade and forwards jesse.trade's own 5xx.
        return _error(action, 'jesse_trade_unavailable', message, http_status=response.status_code)
    return _error(action, 'jesse_trade_error', message, http_status=response.status_code)


def _exchange_jesse_trade_token() -> str:
    """
    Exchange the project's LICENSE_API_TOKEN for a jesse.trade session token.

    This is the same exchange the dashboard performs on startup. Doing it per call means a
    plan upgrade or a new LICENSE_API_TOKEN takes effect without restarting anything, and no
    token outlives the call that needed it.
    """
    response = _request('POST', '/auth/jesse-trade-token')
    payload = _payload(response)
    token = payload.get('access_token')
    if response.status_code == 200 and payload.get('status') == 'success' and token:
        return str(token)
    if _rejected_dashboard_credentials(response, payload):
        raise _JesseTradeAuthError('authentication_failed', 'Jesse rejected the MCP credentials (dashboard password).')
    if response.status_code == 400:
        # Jesse's only 400 here is a missing or empty LICENSE_API_TOKEN.
        raise _JesseTradeAuthError('license_token_missing', f'LICENSE_API_TOKEN is not set. {LICENSE_TOKEN_HELP}')
    if response.status_code in (401, 403):
        raise _JesseTradeAuthError(
            'license_token_rejected',
            f'jesse.trade rejected the LICENSE_API_TOKEN ({_message(response, payload)}). {LICENSE_TOKEN_HELP}',
        )
    raise _JesseTradeAuthError(
        'jesse_trade_unavailable', f'Could not sign in to jesse.trade: {_message(response, payload)}'
    )


def _valid_slug(slug: str) -> bool:
    return bool(_SLUG.fullmatch(slug))


def _valid_date(value: str) -> bool:
    try:
        datetime.strptime(value, '%Y-%m-%d')
    except ValueError:
        return False
    return True


def _summarize(strategy: dict) -> dict:
    """Reduce one jesse.trade catalog entry to what is needed to compare and choose it."""
    user = strategy.get('user')
    metrics = strategy.get('strategy_metrics')
    return {
        'slug': strategy.get('slug'),
        'name': strategy.get('name'),
        'type': strategy.get('type'),
        'author': user.get('username') if isinstance(user, dict) else None,
        'description': strategy.get('description'),
        # jesse.trade only sends code the signed-in account may import (every free strategy;
        # premium ones only to Premium accounts and their author), so this is the import
        # permission without copying the code into the result.
        'code_available': bool(strategy.get('code')),
        'submitted_at': strategy.get('created_at'),
        'views': strategy.get('views'),
        'default_symbol': strategy.get('symbol'),
        'default_timeframe': strategy.get('timeframe'),
        'backtest_symbols': strategy.get('backtest_symbols') or [],
        'backtest_timeframes': strategy.get('backtest_timeframes') or [],
        'metrics': {key: metrics.get(key) for key in _SUMMARY_METRICS} if isinstance(metrics, dict) else None,
    }


def _matches(strategy: dict, query: Optional[str], strategy_type: Optional[str]) -> bool:
    if strategy_type and strategy.get('type') != strategy_type:
        return False
    if query:
        needle = query.casefold()
        return any(needle in str(strategy.get(key) or '').casefold() for key in ('name', 'description', 'author', 'slug'))
    return True


def _fetch_periods(action: str) -> list[str] | dict:
    """Return the catalog's trading periods in jesse.trade's order (most recent last), or the MCP error to return."""
    response = _request('GET', '/strategy/periods')
    payload = _payload(response)
    if response.status_code != 200:
        return _upstream_error(action, response, payload, 'jesse_trade_error')
    periods = payload.get('periods')
    if not isinstance(periods, list) or not periods:
        return _error(action, 'unexpected_response', 'jesse.trade returned no trading periods.')
    return [str(period) for period in periods]


def browse_strategy_catalog_service(
        period: Optional[str] = None,
        sort_by: str = DEFAULT_SORT,
        submitted_after: Optional[str] = None,
        submitted_before: Optional[str] = None,
        query: Optional[str] = None,
        strategy_type: Optional[str] = None,
        offset: int = 0,
        limit: int = DEFAULT_PAGE_SIZE,
) -> dict:
    """
    List one page of the jesse.trade strategy catalog, ranked the way the dashboard ranks it.

    period, sort_by and the submission dates are sent to jesse.trade exactly as the dashboard
    sends them. query, strategy_type, offset and limit are applied here to the ranked list
    jesse.trade returns, because jesse.trade has no search, type filter, or pagination.
    """
    action = 'strategy_catalog_browse_failed'
    query = (query or '').strip() or None
    strategy_type = (strategy_type or '').strip().lower() or None
    submitted_after = (submitted_after or '').strip() or None
    submitted_before = (submitted_before or '').strip() or None

    if sort_by not in SORT_OPTIONS:
        return _error(action, 'invalid_request', f'sort_by must be one of: {", ".join(SORT_OPTIONS)}.')
    if strategy_type and strategy_type not in STRATEGY_TYPES:
        return _error(action, 'invalid_request', f'strategy_type must be one of: {", ".join(STRATEGY_TYPES)}.')
    for name, value in (('submitted_after', submitted_after), ('submitted_before', submitted_before)):
        if value and not _valid_date(value):
            return _error(action, 'invalid_request', f'{name} must be a date in YYYY-MM-DD format.')
    # ISO dates compare correctly as strings.
    if submitted_after and submitted_before and submitted_after > submitted_before:
        return _error(action, 'invalid_request', 'submitted_after must not be later than submitted_before.')
    if offset < 0:
        return _error(action, 'invalid_request', 'offset must be 0 or greater.')
    if not 1 <= limit <= MAX_PAGE_SIZE:
        return _error(action, 'invalid_request', f'limit must be between 1 and {MAX_PAGE_SIZE}.')

    try:
        periods = _fetch_periods(action)
        if isinstance(periods, dict):
            return periods

        # Same default as the dashboard's Strategies page: the second most recent entry.
        default_period = periods[-2] if len(periods) > 1 else periods[0]
        selected_period = (period or '').strip() or default_period
        if selected_period not in periods:
            return _error(
                action, 'invalid_period',
                f'"{selected_period}" is not a catalog trading period. Use one of available_periods.',
                available_periods=periods,
            )

        # Browsing works without a jesse.trade account, as on the dashboard. Signing in only
        # decides which strategies' code (and therefore imports) the account can access.
        auth_note = None
        token = None
        try:
            token = _exchange_jesse_trade_token()
        except _JesseTradeAuthError as e:
            if e.error_type == 'authentication_failed':
                return _error(action, e.error_type, e.message)
            auth_note = {'error_type': e.error_type, 'message': e.message}

        params = {'period': selected_period, 'sort_by': sort_by}
        if submitted_after:
            params['submitted_after'] = submitted_after
        if submitted_before:
            params['submitted_before'] = submitted_before
        response = _request('GET', '/strategy/index', params=params, jesse_trade_token=token)
    except requests.exceptions.RequestException as e:
        return _error(action, 'connection_error', f'Could not connect to Jesse API: {e}')

    payload = _payload(response)
    if response.status_code != 200:
        return _upstream_error(action, response, payload, 'jesse_trade_error')
    raw_strategies = payload.get('strategies')
    if not isinstance(raw_strategies, list):
        return _error(action, 'unexpected_response', 'jesse.trade returned no strategy list.')

    ranked = [_summarize(strategy) for strategy in raw_strategies if isinstance(strategy, dict)]
    matches = [strategy for strategy in ranked if _matches(strategy, query, strategy_type)]
    page = matches[offset:offset + limit]
    has_more = offset + len(page) < len(matches)

    if not ranked:
        message = f'jesse.trade has no ranked strategies for {selected_period} with these submission dates. Try another period.'
    elif not matches:
        message = f'None of the {len(ranked)} strategies ranked for {selected_period} match query/strategy_type.'
    elif not page:
        message = f'offset {offset} is past the last of {len(matches)} matching strategies.'
    else:
        message = f'Showing {offset + 1}-{offset + len(page)} of {len(matches)} matching catalog strategies for {selected_period}.'

    return {
        'status': 'success',
        'action': 'strategy_catalog_browsed',
        'source': CATALOG_SOURCE,
        'message': message,
        'filters': {
            'period': selected_period,
            'sort_by': sort_by,
            'submitted_after': submitted_after,
            'submitted_before': submitted_before,
            'query': query,
            'strategy_type': strategy_type,
        },
        'available_filters': {
            'periods': periods,
            'default_period': default_period,
            'sort_by': list(SORT_OPTIONS),
            'strategy_type': list(STRATEGY_TYPES),
        },
        'pagination': {
            'offset': offset,
            'limit': limit,
            'returned': len(page),
            'total_matches': len(matches),
            'total_ranked_in_period': len(ranked),
            'has_more': has_more,
            'next_offset': offset + len(page) if has_more else None,
        },
        'jesse_trade_signed_in': token is not None,
        'jesse_trade_auth': auth_note,
        'strategies': page,
    }


def get_catalog_strategy_metrics_service(slug: str, period: str, symbol: str, timeframe: str) -> dict:
    """Fetch the jesse.trade backtest metrics of one catalog strategy for one symbol/timeframe/period."""
    action = 'catalog_strategy_metrics_failed'
    slug = slug.strip()
    if not _valid_slug(slug):
        return _error(action, 'invalid_request', 'slug must be the catalog slug from browse_strategy_catalog, e.g. "my-strategy-1".')
    params = {'period': period.strip(), 'symbol': symbol.strip().upper(), 'timeframe': timeframe.strip()}
    if not all(params.values()):
        return _error(action, 'invalid_request', 'period, symbol, and timeframe are all required.')

    try:
        # Metrics are public on jesse.trade, so the dashboard fetches them without signing in too.
        response = _request('GET', f'/strategy/jesse-trade/{slug}/metrics', params=params)
    except requests.exceptions.RequestException as e:
        return _error(action, 'connection_error', f'Could not connect to Jesse API: {e}')

    payload = _payload(response)
    if response.status_code != 200:
        # jesse.trade answers 404 both for an unknown slug and for a combination it never backtested.
        return _upstream_error(action, response, payload, 'not_found') | {'slug': slug, **params}

    return {
        'status': 'success',
        'action': 'catalog_strategy_metrics_retrieved',
        'source': CATALOG_SOURCE,
        'slug': slug,
        **params,
        'metrics': {key: value for key, value in payload.items() if key not in _OMITTED_METRICS},
    }


def import_catalog_strategy_service(slug: str) -> dict:
    """
    Import one catalog strategy into the project's strategies/ folder through Jesse's import route.

    Jesse names the local strategy after the first class in the downloaded code and refuses to
    replace an existing strategy, so nothing local is ever overwritten.
    """
    action = 'catalog_strategy_import_failed'
    slug = slug.strip()
    if not _valid_slug(slug):
        return _error(action, 'invalid_request', 'slug must be the catalog slug from browse_strategy_catalog, e.g. "my-strategy-1".')

    try:
        # Importing always needs a jesse.trade account, so any sign-in failure stops here,
        # exactly where the dashboard shows its "Authentication Required" dialog.
        token = _exchange_jesse_trade_token()
        response = _request('POST', '/strategy/import', json_body={'slug': slug}, jesse_trade_token=token)
    except _JesseTradeAuthError as e:
        return _error(action, e.error_type, e.message, slug=slug)
    except requests.exceptions.RequestException as e:
        return _error(action, 'connection_error', f'Could not connect to Jesse API: {e}', slug=slug)

    payload = _payload(response)
    local_name = payload.get('name')
    if response.status_code == 200 and payload.get('status') == 'success' and local_name:
        return {
            'status': 'success',
            'action': 'catalog_strategy_imported',
            'slug': slug,
            'local_name': local_name,
            'path': payload.get('path'),
            'dashboard_url': mcp_config.dashboard_url('strategy', local_name),
            'message': (
                f'Imported as the local strategy "{local_name}". Use this name with read_strategy, '
                'write_strategy, and backtests. It appears in the dashboard Strategies list the '
                'next time that page loads.'
            ),
        }
    if response.status_code == 409:
        return _error(
            action, 'strategy_exists',
            f'{_message(response, payload)} Nothing was changed. A local strategy with the class name '
            'of this catalog strategy already exists; it may be an earlier import or an unrelated '
            'strategy. Ask the user whether to use it as is or to rename or delete it in the '
            'dashboard before importing again.',
            slug=slug, local_name=local_name,
        )
    if response.status_code == 403:
        return _error(
            action, 'strategy_access_denied',
            f'{_message(response, payload)} {PREMIUM_HELP}',
            slug=slug,
        )
    return _upstream_error(action, response, payload, 'catalog_strategy_not_found') | {'slug': slug}
