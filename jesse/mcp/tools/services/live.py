"""
Live and paper session management for MCP: the dashboard Live page's lifecycle through the
same authenticated Jesse routes it calls.

- Drafts: create, update, and copy ("New session") store the session form with
  /live/update-state, exactly as a dashboard Live tab saves itself. Each draft carries its own
  run configuration; shared settings are only read (see session_config.resolve_live_run_config).
- Start: /live with the dashboard Start button's payload and no check of its own beyond the
  form validation: the license, the plan's allowed exchanges, route counts, and timeframes, the
  paper-trading plan requirement, and the exchange connection are all checked by the live plugin
  inside the started session, exactly as for a dashboard start; a failure shows up as the
  session's error. Live and paper sessions are not metered by the MCP usage limits, matching the
  dashboard.
- Stop: /live/cancel, the dashboard's Stop button. It asks the session process to end; what
  happens to orders and positions is decided by the live plugin (see STOP_SEMANTICS).
- Notes and delete: /live/sessions/{id}/notes and /remove, with the dashboard's rule that an
  active session or one open in a dashboard tab is not deleted.

The /live routes themselves refuse to delete or rewrite the form of a session that is starting or
running, and draft edits are sent with `require_draft`, so a dashboard Start that lands between
one of these tools' checks and its write cannot be undone or overwritten (live_controller).

Credentials: sessions reference saved exchange and notification keys by ID only. Key lookups
keep id, name, exchange or driver; no secret is read, returned, or logged. Session errors and
logs, which can quote anything, are not returned here: get_session_results reads them with
the stored credentials of the session redacted.

The *_service functions return a result dict and never raise for Jesse or network failures;
the helpers raise _Failure, which _contained turns into that dict.
"""

import functools
import json
import uuid
from typing import Any, Callable, NamedTuple, Optional

import requests

import jesse.mcp.mcp_config as mcp_config
from jesse.info import jesse_supported_timeframes

from .auth import hash_password
from .config import get_config_service
from .locks import LIVE_SESSIONS_LOCK
from .session_config import (
    LIVE_CONFIG_FIELDS,
    LIVE_EXCHANGE_OVERRIDE_FIELDS,
    LIVE_LOGGING_FIELDS,
    NOTIFICATION_EVENTS,
    NOTIFICATION_FIELDS,
    live_engine_config,
    resolve_live_run_config,
)


# The same bound as the credential tools: these routes only read or write single database rows.
REQUEST_TIMEOUT_SECONDS = 30
ACTIVE_STATUSES = ('starting', 'running')
DRAFT_STATUS = 'draft'
LEVERAGE_MODES = ('cross', 'isolated')

# What stopping does, as implemented by the live plugin (LiveExchange._on_termination).
STOP_SEMANTICS = (
    'Stopping asks the session process to end; a running session notices within about a second, one '
    'still starting once its startup checks (such as the license check) finish. While ending, '
    'a paper session, or a live session whose persistency setting is off, cancels the open orders '
    "of its routes' symbols and closes their open positions with market orders. A live session "
    'with persistency on leaves its orders and positions on the exchange so a later session can '
    'continue them. The stop request does not wait for this; check the session summary and logs '
    'with get_session_results("live", session_id).'
)


class _Response(NamedTuple):
    status_code: int
    payload: Any


class _Failure(Exception):
    """A typed error to return to the assistant; the message never quotes secrets."""

    def __init__(self, error_type: str, message: str, **extra: Any):
        super().__init__(message)
        self.error_type = error_type
        self.message = message
        self.extra = extra


def _error(action: str, error_type: str, message: str, **extra: Any) -> dict:
    return {'status': 'error', 'action': action, 'error_type': error_type, 'message': message, **extra}


def _contained(action: str) -> Callable[[Callable[..., dict]], Callable[..., dict]]:
    """Return typed failures as error results and hide unexpected exception text."""

    def decorator(func: Callable[..., dict]) -> Callable[..., dict]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> dict:
            try:
                return func(*args, **kwargs)
            except _Failure as failure:
                return _error(action, failure.error_type, failure.message, **failure.extra)
            except Exception as exc:
                return _error(
                    action, 'internal_error',
                    f'The live session tool failed unexpectedly ({type(exc).__name__}).',
                )

        return wrapper

    return decorator


def _call(method: str, path: str, json_body: Any = None, timeout: int = REQUEST_TIMEOUT_SECONDS) -> _Response:
    api_url = mcp_config.JESSE_API_URL
    password = mcp_config.JESSE_PASSWORD
    if not api_url or not password:
        raise _Failure('config_error', 'The MCP worker has no Jesse API URL or dashboard password configured.')
    try:
        response = requests.request(
            method, f'{api_url}{path}', headers={'Authorization': hash_password(password)},
            json=json_body, timeout=timeout,
        )
    except requests.RequestException as exc:
        raise _Failure('connection_error', f'Could not reach the Jesse API ({type(exc).__name__}).') from None
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if response.status_code == 401:
        raise _Failure('authentication_failed', 'Jesse rejected the MCP worker credentials (dashboard password).')
    return _Response(response.status_code, payload)


def _message(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ('error', 'message'):
            if isinstance(payload.get(key), str):
                return payload[key]
    return ''


def _jesse_failure(what: str, response: _Response) -> _Failure:
    detail = _message(response.payload)
    return _Failure(
        'jesse_error', f'Jesse could not {what} (HTTP {response.status_code})' + (f': {detail}' if detail else '.'),
        http_status=response.status_code,
    )


# ---------------------------------------------------------------------------
# Jesse state lookups
# ---------------------------------------------------------------------------

def _local_info() -> dict:
    """Plugin availability, exchange metadata, and installed strategies, from the Jesse process."""
    response = _call('POST', '/system/general-info/local')
    if response.status_code != 200 or not isinstance(response.payload, dict):
        raise _jesse_failure('read its local information', response)
    info = response.payload
    if not info.get('has_live_plugin_installed'):
        raise _Failure(
            'live_plugin_unavailable',
            'Live and paper trading need the Jesse live trading plugin, which is not installed or is '
            'disabled on this Jesse instance.',
        )
    return info


def _session_id(value: Any) -> str:
    try:
        return str(uuid.UUID(str(value).strip()))
    except (ValueError, AttributeError):
        raise _Failure('invalid_request', 'session_id must be a live session UUID.') from None


def _load_session(session_id: str) -> dict:
    """The dashboard's view of one session (its running status reconciled like the dashboard)."""
    response = _call('POST', f'/live/sessions/{session_id}')
    if response.status_code == 404:
        raise _Failure('not_found', f'Live session {session_id} does not exist.')
    if response.status_code != 200 or not isinstance(response.payload, dict) or not isinstance(response.payload.get('session'), dict):
        raise _jesse_failure('read the live session', response)
    return response.payload['session']


def _session_form(session: dict) -> dict:
    state = session.get('state') if isinstance(session.get('state'), dict) else {}
    form = state.get('form') if isinstance(state.get('form'), dict) else {}
    return form


def _is_active(session: dict) -> bool:
    return bool(session.get('is_active')) or session.get('status') in ACTIVE_STATUSES


def _exchange_keys() -> list[dict]:
    response = _call('GET', '/exchange/api-keys')
    if response.status_code != 200 or not isinstance(response.payload, dict) or not isinstance(response.payload.get('data'), list):
        raise _jesse_failure('list the saved exchange API keys', response)
    keys = []
    for entry in response.payload['data']:
        if isinstance(entry, dict) and isinstance(entry.get('id'), str):
            # Only non-secret metadata is kept; the masked key fragments Jesse sends are dropped.
            keys.append({'id': entry['id'], 'name': entry.get('name'), 'exchange': entry.get('exchange')})
    return keys


def _notification_keys() -> list[dict]:
    response = _call('GET', '/notification/api-keys')
    if response.status_code != 200 or not isinstance(response.payload, dict) or not isinstance(response.payload.get('data'), list):
        raise _jesse_failure('list the saved notification keys', response)
    keys = []
    for entry in response.payload['data']:
        if isinstance(entry, dict) and isinstance(entry.get('id'), str):
            # The stored fields (bot tokens, chat IDs, webhooks) are never kept.
            keys.append({'id': entry['id'], 'name': entry.get('name'), 'driver': entry.get('driver')})
    return keys


def _open_dashboard_tabs() -> list[str]:
    response = _call('POST', '/tabs/list', {'module': 'live'})
    if response.status_code != 200 or not isinstance(response.payload, dict) or not isinstance(response.payload.get('ids'), list):
        raise _jesse_failure('list the open dashboard Live tabs', response)
    return [str(item) for item in response.payload['ids']]


def _settings() -> dict:
    """Saved settings, read only; a draft never falls back to invented defaults if they are unreadable."""
    result = get_config_service()
    if result.get('status') != 'success':
        raise _Failure('settings_unavailable', 'Could not read the saved settings needed for the session configuration.')
    settings = result.get('config', {})
    if isinstance(settings, dict) and set(settings) == {'data'}:
        settings = settings['data']
    return settings if isinstance(settings, dict) else {}


# ---------------------------------------------------------------------------
# Form validation (the dashboard's validateLiveForm and getRouteErrors)
# ---------------------------------------------------------------------------

def _explicit_mode(value: Any) -> bool:
    """
    paper_mode must be stated: JSON true/false, or the text "true"/"false" that some clients send
    for booleans. Nothing else, including a missing value, is taken as either mode.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ('true', 'false'):
        return value.strip().lower() == 'true'
    raise _Failure('invalid_request', 'paper_mode is required: true (simulated paper trading) or false (real funds).')


def _optional_id(value: Any, name: str) -> Optional[str]:
    """A saved key ID as text, or None. Any other value is refused without repeating it (it may be a secret)."""
    if value is None or isinstance(value, str):
        return value
    raise _Failure('invalid_request', f'{name} must be the ID of a saved key, as text.')


def _parse_json_list(value: Any, name: str) -> list:
    if isinstance(value, list):
        return value
    if not isinstance(value, str):
        raise _Failure('invalid_request', f'{name} must be a JSON array.')
    try:
        parsed = json.loads(value) if value.strip() else []
    except json.JSONDecodeError:
        raise _Failure('invalid_request', f'{name} is not valid JSON.') from None
    if not isinstance(parsed, list):
        raise _Failure('invalid_request', f'{name} must be a JSON array.')
    return parsed


def _check_flags(value: Any, allowed: tuple, name: str) -> None:
    """An object of known on/off switches, such as config.logging; field names only are quoted."""
    if not isinstance(value, dict):
        raise _Failure('invalid_request', f'{name} must be an object.')
    unknown = sorted(set(value) - set(allowed))
    if unknown:
        raise _Failure('invalid_request', f'Unknown {name} field(s): {", ".join(map(str, unknown))}. Allowed: {", ".join(allowed)}.')
    not_flags = sorted(key for key, flag in value.items() if not isinstance(flag, bool))
    if not_flags:
        raise _Failure('invalid_request', f'{name} values must be true or false: {", ".join(not_flags)}.')


def _parse_config(value: Any) -> Optional[dict]:
    """Validate the optional configuration overrides; unknown or invalid values are refused, not ignored."""
    if value in (None, ''):
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            raise _Failure('invalid_request', 'config is not valid JSON.') from None
    if not isinstance(value, dict):
        raise _Failure('invalid_request', 'config must be a JSON object.')
    unknown = sorted(set(value) - set(LIVE_CONFIG_FIELDS))
    if unknown:
        raise _Failure('invalid_request', f'Unknown config field(s): {", ".join(unknown)}. Allowed: {", ".join(LIVE_CONFIG_FIELDS)}.')
    for key in ('persistency', 'generate_candles_from_1m'):
        if key in value and not isinstance(value[key], bool):
            raise _Failure('invalid_request', f'config.{key} must be true or false.')
    if 'warm_up_candles' in value:
        warm_up = value['warm_up_candles']
        if isinstance(warm_up, bool) or not isinstance(warm_up, int) or warm_up < 0:
            raise _Failure('invalid_request', 'config.warm_up_candles must be a whole number of 0 or more.')
    if 'logging' in value:
        _check_flags(value['logging'], LIVE_LOGGING_FIELDS, 'config.logging')
    if 'notifications' in value:
        notifications = value['notifications']
        if not isinstance(notifications, dict):
            raise _Failure('invalid_request', 'config.notifications must be an object.')
        unknown = sorted(set(notifications) - set(NOTIFICATION_FIELDS))
        if unknown:
            raise _Failure('invalid_request', f'Unknown config.notifications field(s): {", ".join(unknown)}.')
        if 'enabled' in notifications and not isinstance(notifications['enabled'], bool):
            raise _Failure('invalid_request', 'config.notifications.enabled must be true or false.')
        # The live plugin converts this timeframe to minutes, so only Jesse's timeframes work.
        if 'position_report_timeframe' in notifications and notifications['position_report_timeframe'] not in jesse_supported_timeframes:
            raise _Failure('invalid_request', 'config.notifications.position_report_timeframe must be one of Jesse\'s timeframes, such as "1h".')
        if 'events' in notifications:
            _check_flags(notifications['events'], NOTIFICATION_EVENTS, 'config.notifications.events')
    exchange = value.get('exchange')
    if exchange is not None:
        if not isinstance(exchange, dict):
            raise _Failure('invalid_request', 'config.exchange must be an object.')
        unknown = sorted(set(exchange) - set(LIVE_EXCHANGE_OVERRIDE_FIELDS) - {'name'})
        if unknown:
            raise _Failure('invalid_request', f'Unknown config.exchange field(s): {", ".join(unknown)}.')
        for key in ('balance', 'fee'):
            if key in exchange and (isinstance(exchange[key], bool) or not isinstance(exchange[key], (int, float)) or exchange[key] < 0):
                raise _Failure('invalid_request', f'config.exchange.{key} must be a number of 0 or more.')
        leverage = exchange.get('futures_leverage')
        if leverage is not None and (isinstance(leverage, bool) or not isinstance(leverage, int) or leverage < 1):
            raise _Failure('invalid_request', 'config.exchange.futures_leverage must be a whole number of 1 or more.')
        mode = exchange.get('futures_leverage_mode')
        if mode is not None and mode not in LEVERAGE_MODES:
            raise _Failure('invalid_request', 'config.exchange.futures_leverage_mode must be "cross" or "isolated".')
        # "futures" is the older name the dashboard also accepts for perpetual_futures.
        if 'simulation_model' in exchange and exchange['simulation_model'] not in ('spot', 'perpetual_futures', 'futures'):
            raise _Failure('invalid_request', 'config.exchange.simulation_model must be "spot" or "perpetual_futures".')
        if 'type' in exchange and exchange['type'] not in ('spot', 'futures'):
            raise _Failure('invalid_request', 'config.exchange.type must be "spot" or "futures".')
        annualization = exchange.get('annualization')
        if 'annualization' in exchange and (isinstance(annualization, bool) or annualization not in (252, 365)):
            raise _Failure('invalid_request', 'config.exchange.annualization must be 365 or 252.')
        # The session's exchange always comes from the form (or the saved key), never from config.
        value = {**value, 'exchange': {k: v for k, v in exchange.items() if k != 'name'}}
    return value


def _clean_routes(routes: list, data_routes: list, exchange: str, strategies: list) -> tuple[list, list]:
    """Apply the dashboard's route rules (utils/routeValidation.ts) plus names Jesse can resolve."""
    errors = []
    trading = []
    for route in routes:
        if not isinstance(route, dict):
            raise _Failure('invalid_routes', 'Each route must be an object with strategy, symbol, and timeframe.')
        trading.append({key: str(route.get(key) or '').strip() for key in ('strategy', 'symbol', 'timeframe')})
    data = []
    for route in data_routes:
        if not isinstance(route, dict):
            raise _Failure('invalid_routes', 'Each data route must be an object with symbol and timeframe.')
        data.append({key: str(route.get(key) or '').strip() for key in ('symbol', 'timeframe')})

    if not trading:
        errors.append('At least one trading route is required')
    if any(not all(r.values()) for r in trading) or any(not all(r.values()) for r in data):
        errors.append('You must fill all the parameters')
    symbols = [r['symbol'] for r in trading + data if r['symbol']]
    if any('-' not in symbol for symbol in symbols):
        errors.append('Symbol parameter must contain "-" character!')
    trading_symbols = [r['symbol'] for r in trading if r['symbol']]
    if len(trading_symbols) != len(set(trading_symbols)):
        errors.append('each exchange-symbol pair can be traded only once! More info: https://docs.jesse.trade/docs/routes.html#trading-multiple-routes')
    quotes = {s[s.rfind('-') + 1:] for s in trading_symbols if '-' in s}
    if len(quotes) > 1:
        errors.append('All trading routes must use the same quote asset')
    data_keys = [(r['symbol'], r['timeframe']) for r in data if r['symbol'] and r['timeframe']]
    if len(data_keys) != len(set(data_keys)):
        errors.append('each exchange-symbol pair can be traded only once! More info: https://docs.jesse.trade/docs/routes.html#trading-multiple-routes')
    if {(r['symbol'], r['timeframe']) for r in trading} & set(data_keys):
        errors.append("Data routes' timeframe and trading routes' timeframe must be different")
    bad_timeframes = sorted({r['timeframe'] for r in trading + data if r['timeframe'] and r['timeframe'] not in jesse_supported_timeframes})
    if bad_timeframes:
        errors.append(f'Unsupported timeframe(s): {", ".join(bad_timeframes)}')
    missing = sorted({r['strategy'] for r in trading if r['strategy'] and r['strategy'] not in strategies})
    if missing:
        errors.append(f'Strategy not found in strategies/: {", ".join(missing)}')
    if errors:
        raise _Failure('invalid_routes', '; '.join(dict.fromkeys(errors)), exchange=exchange)
    return trading, data


def _resolve_context(info: dict, paper_mode: Any, exchange: Any, exchange_api_key_id: Any,
                     notification_api_key_id: Any, key_explicit: bool) -> dict:
    """Resolve and check the trading mode, exchange, and saved key references of a form."""
    if not isinstance(paper_mode, bool):
        raise _Failure('invalid_request', 'paper_mode must be true (simulated paper trading) or false (real funds).')
    exchanges = info.get('exchanges') if isinstance(info.get('exchanges'), dict) else {}
    live_exchanges = sorted(name for name, meta in exchanges.items() if isinstance(meta, dict) and (meta.get('modes') or {}).get('live_trading'))
    exchange = str(exchange or '').strip()
    key_id = str(exchange_api_key_id or '').strip()
    key = None
    if paper_mode:
        if key_explicit and key_id:
            raise _Failure(
                'invalid_request',
                'Paper sessions simulate orders and do not use an exchange API key. Omit exchange_api_key_id, '
                'or set paper_mode=false for a real-money session with that key.',
            )
        if exchange not in live_exchanges:
            raise _Failure(
                'unsupported_exchange',
                'Paper sessions need `exchange`: a live-trading exchange name exactly as Jesse lists it.',
                live_trading_exchanges=live_exchanges,
            )
    else:
        if not key_id:
            raise _Failure(
                'key_required',
                'Real-money (paper_mode=false) sessions trade with a saved exchange API key. Pass its '
                'exchange_api_key_id from get_exchange_api_keys(); store one with store_exchange_api_key() first.',
            )
        key = next((k for k in _exchange_keys() if k['id'] == key_id), None)
        if key is None:
            # The submitted value is not echoed: a secret pasted here by mistake would come straight back.
            raise _Failure('key_not_found', 'No saved exchange API key has that ID. List them with get_exchange_api_keys().')
        key_exchange = key.get('exchange') or ''
        if exchange and exchange != key_exchange:
            raise _Failure(
                'exchange_mismatch',
                f'The saved key "{key.get("name")}" belongs to {key_exchange}, not the exchange passed. A live '
                "session trades on its key's exchange; omit exchange or pass that one.",
            )
        exchange = key_exchange
        if exchange not in live_exchanges:
            raise _Failure('unsupported_exchange', f'{exchange} does not support live trading on this Jesse version.')
    notification_id = str(notification_api_key_id or '').strip()
    notification = None
    if notification_id:
        notification = next((k for k in _notification_keys() if k['id'] == notification_id), None)
        if notification is None:
            raise _Failure('notification_key_not_found', 'No saved notification key has that ID.')
    return {
        'paper_mode': paper_mode, 'exchange': exchange, 'exchange_api_key_id': key_id,
        'notification_api_key_id': notification_id, 'key': key, 'notification': notification,
    }


def _engine_shaped_config(config: Any, exchange: str) -> Any:
    """
    A started session stores the engine shape (`exchanges` keyed by name) instead of a tab's
    `exchange` profile; turn it back into a run config so copying keeps the session's values.
    """
    if isinstance(config, dict) and 'exchange' not in config and isinstance(config.get('exchanges'), dict):
        profile = config['exchanges'].get(exchange)
        return {**{k: v for k, v in config.items() if k != 'exchanges'}, **({'exchange': profile} if isinstance(profile, dict) else {})}
    return config


def _build_form(context: dict, routes: list, data_routes: list, debug_mode: bool, config: dict) -> dict:
    return {
        'debug_mode': debug_mode,
        'paper_mode': context['paper_mode'],
        'exchange_api_key_id': context['exchange_api_key_id'],
        'notification_api_key_id': context['notification_api_key_id'],
        'exchange': context['exchange'],
        'routes': routes,
        'data_routes': data_routes,
        'config': config,
    }


def _mode(paper_mode: bool) -> dict:
    if paper_mode:
        return {'mode': 'paper', 'trading': 'simulated orders against live market data; no real funds'}
    return {'mode': 'live', 'trading': 'REAL orders with real funds on the exchange account of the saved key'}


def _describe(session_id: str, form: dict, context: dict, status: str) -> dict:
    """Non-secret summary of a session form for tool results."""
    key = context.get('key')
    notification = context.get('notification')
    return {
        'session_id': session_id,
        'session_status': status,
        **_mode(form['paper_mode']),
        'exchange': form['exchange'],
        'exchange_api_key': {'id': key['id'], 'name': key.get('name')} if key else None,
        'notification_api_key': {'id': notification['id'], 'name': notification.get('name'), 'driver': notification.get('driver')} if notification else None,
        'routes': form['routes'],
        'data_routes': form['data_routes'],
        'debug_mode': form['debug_mode'],
        'config': form.get('config'),
        'dashboard_url': mcp_config.dashboard_url('live', session_id),
    }


def _save_state(session_id: str, form: dict) -> None:
    """Store a draft's form; the route refuses (409) once the session is no longer a draft."""
    response = _call('POST', '/live/update-state', {'id': session_id, 'state': {'form': form}, 'require_draft': True})
    if response.status_code == 409:
        raise _Failure(
            'not_draft',
            f'Live session {session_id} was started (or is no longer a draft) before this change was saved, so it '
            'was not changed. Use copy_live_session to make a new draft from it.',
        )
    if response.status_code != 200:
        raise _jesse_failure('save the live session draft', response)


def _save_notes(session_id: str, title: Optional[str], description: Optional[str]) -> None:
    body = {key: value for key, value in (('title', title), ('description', description)) if value is not None}
    if not body:
        return
    response = _call('POST', f'/live/sessions/{session_id}/notes', body)
    if response.status_code != 200:
        raise _jesse_failure('save the session notes', response)


def _require_draft(session: dict, session_id: str, doing: str) -> None:
    status = session.get('status')
    if status != DRAFT_STATUS or session.get('is_active'):
        raise _Failure(
            'not_draft',
            f'Live session {session_id} is {status}, not a draft, so it cannot be {doing}. Use '
            'copy_live_session to make a new draft from it (the dashboard\'s "New session").',
            session_status=status,
        )


def _prepare_form(info: dict, settings: dict, *, paper_mode: Any, exchange: Any, exchange_api_key_id: Any,
                  notification_api_key_id: Any, routes: list, data_routes: list, debug_mode: Any,
                  current_config: Any, overrides: Optional[dict], key_explicit: bool) -> tuple[dict, dict]:
    if not isinstance(debug_mode, bool):
        raise _Failure('invalid_request', 'debug_mode must be true or false.')
    context = _resolve_context(info, paper_mode, exchange, exchange_api_key_id, notification_api_key_id, key_explicit)
    strategies = info.get('strategies') if isinstance(info.get('strategies'), list) else []
    clean_routes, clean_data_routes = _clean_routes(routes, data_routes, context['exchange'], strategies)
    exchanges = info.get('exchanges') if isinstance(info.get('exchanges'), dict) else None
    config = resolve_live_run_config(
        settings, context['paper_mode'], context['exchange'], context['exchange_api_key_id'],
        current=_engine_shaped_config(current_config, context['exchange']), overrides=overrides, exchanges=exchanges,
    )
    # A real futures session uses the venue's margin modes; paper sessions simulate cross and isolated.
    supported_modes = ((exchanges or {}).get(context['exchange']) or {}).get('supported_leverage_modes') or []
    leverage_mode = config['exchange'].get('futures_leverage_mode')
    if (not context['paper_mode'] and config['exchange']['type'] == 'futures'
            and supported_modes and leverage_mode not in supported_modes):
        raise _Failure(
            'invalid_request',
            f'{context["exchange"]} supports the {", ".join(supported_modes)} margin mode(s) for live trading; '
            'set config.exchange.futures_leverage_mode to one of them.',
        )
    return _build_form(context, clean_routes, clean_data_routes, debug_mode, config), context


def _stored_bool(value: Any, default: bool) -> bool:
    """Read a boolean saved in a session form the way the dashboard does (normalizeBool)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 1
    if isinstance(value, str) and value.strip().lower() in ('1', 'true', '0', 'false'):
        return value.strip().lower() in ('1', 'true')
    return default if value is None else bool(value)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@_contained('live_draft_create_failed')
def create_live_draft_service(
    paper_mode: Any,
    routes: Any,
    exchange: Optional[str] = None,
    exchange_api_key_id: Optional[str] = None,
    data_routes: Any = '[]',
    notification_api_key_id: Optional[str] = None,
    debug_mode: Any = True,
    config: Any = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
) -> dict:
    """Create a validated live or paper draft with its own run configuration; nothing is started."""
    paper_mode = _explicit_mode(paper_mode)
    exchange_api_key_id = _optional_id(exchange_api_key_id, 'exchange_api_key_id')
    notification_api_key_id = _optional_id(notification_api_key_id, 'notification_api_key_id')
    overrides = _parse_config(config)
    route_list = _parse_json_list(routes, 'routes')
    data_route_list = _parse_json_list(data_routes, 'data_routes')
    # A new draft gets a fresh ID, so there is nothing to check-then-write and no lock is needed.
    info = _local_info()
    form, context = _prepare_form(
        info, _settings(), paper_mode=paper_mode, exchange=exchange, exchange_api_key_id=exchange_api_key_id,
        notification_api_key_id=notification_api_key_id, routes=route_list, data_routes=data_route_list,
        debug_mode=debug_mode, current_config=None, overrides=overrides, key_explicit=True,
    )
    session_id = str(uuid.uuid4())
    _save_state(session_id, form)
    _save_notes(session_id, title, description)
    return {
        'status': 'success',
        'action': 'live_draft_created',
        **_describe(session_id, form, context, DRAFT_STATUS),
        'message': (
            f'Created a {_mode(form["paper_mode"])["mode"]} session draft on {form["exchange"]}. Nothing is running yet; '
            'start it with start_live_session when the user asks.'
        ),
    }


@_contained('live_draft_update_failed')
def update_live_draft_service(
    session_id: str,
    paper_mode: Any = None,
    routes: Any = None,
    exchange: Optional[str] = None,
    exchange_api_key_id: Optional[str] = None,
    data_routes: Any = None,
    notification_api_key_id: Optional[str] = None,
    debug_mode: Any = None,
    config: Any = None,
) -> dict:
    """Change fields of a draft (only a draft); unspecified fields keep their stored values."""
    session_id = _session_id(session_id)
    exchange_api_key_id = _optional_id(exchange_api_key_id, 'exchange_api_key_id')
    notification_api_key_id = _optional_id(notification_api_key_id, 'notification_api_key_id')
    overrides = _parse_config(config)
    with LIVE_SESSIONS_LOCK:
        info = _local_info()
        session = _load_session(session_id)
        _require_draft(session, session_id, 'updated')
        stored = _session_form(session)
        new_paper_mode = (
            _stored_bool(stored.get('paper_mode'), session.get('session_mode') != 'livetrade') if paper_mode is None else paper_mode
        )
        if new_paper_mode:
            # Paper sessions trade the named exchange; a key passed now is refused as explicit.
            key_value = exchange_api_key_id or ''
            exchange_value = exchange if exchange is not None else stored.get('exchange')
        else:
            # Real sessions trade on their key's exchange; `exchange`, when passed, must match it.
            key_value = exchange_api_key_id if exchange_api_key_id is not None else stored.get('exchange_api_key_id')
            exchange_value = exchange or ''
        form, context = _prepare_form(
            info, _settings(),
            paper_mode=new_paper_mode,
            exchange=exchange_value,
            exchange_api_key_id=key_value,
            notification_api_key_id=notification_api_key_id if notification_api_key_id is not None else stored.get('notification_api_key_id'),
            routes=_parse_json_list(routes, 'routes') if routes is not None else _parse_json_list(stored.get('routes') or [], 'routes'),
            data_routes=_parse_json_list(data_routes, 'data_routes') if data_routes is not None else _parse_json_list(stored.get('data_routes') or [], 'data_routes'),
            debug_mode=debug_mode if debug_mode is not None else _stored_bool(stored.get('debug_mode'), True),
            current_config=stored.get('config'),
            overrides=overrides,
            key_explicit=exchange_api_key_id is not None,
        )
        if new_paper_mode and exchange_api_key_id is None and stored.get('exchange_api_key_id'):
            # The dashboard keeps a paper tab's key selection for switching back; so does MCP.
            form['exchange_api_key_id'] = stored['exchange_api_key_id']
        _save_state(session_id, form)
    return {
        'status': 'success',
        'action': 'live_draft_updated',
        **_describe(session_id, form, context, DRAFT_STATUS),
        'message': 'Draft updated. Nothing is running yet.',
    }


@_contained('live_session_copy_failed')
def copy_live_session_service(session_id: str, title: Optional[str] = None) -> dict:
    """Make a new draft with the same form as an existing session (the dashboard's "New session")."""
    session_id = _session_id(session_id)
    # The copy is a new draft with a fresh ID; the source is only read, so no lock is needed.
    info = _local_info()
    source = _load_session(session_id)
    stored = _session_form(source)
    paper_mode = _stored_bool(stored.get('paper_mode'), source.get('session_mode') != 'livetrade')
    form, context = _prepare_form(
        info, _settings(),
        paper_mode=paper_mode,
        exchange=stored.get('exchange') or source.get('exchange'),
        exchange_api_key_id='' if paper_mode else stored.get('exchange_api_key_id'),
        notification_api_key_id=stored.get('notification_api_key_id'),
        routes=_parse_json_list(stored.get('routes') or [], 'routes'),
        data_routes=_parse_json_list(stored.get('data_routes') or [], 'data_routes'),
        debug_mode=_stored_bool(stored.get('debug_mode'), True),
        current_config=stored.get('config'),
        overrides=None,
        key_explicit=False,
    )
    if paper_mode and stored.get('exchange_api_key_id'):
        form['exchange_api_key_id'] = stored['exchange_api_key_id']
    new_id = str(uuid.uuid4())
    _save_state(new_id, form)
    _save_notes(new_id, title, None)
    return {
        'status': 'success',
        'action': 'live_session_copied',
        'source_session_id': session_id,
        **_describe(new_id, form, context, DRAFT_STATUS),
        'message': 'Created a new draft from the session. Nothing is running yet; start it with start_live_session.',
    }


@_contained('live_session_start_failed')
def start_live_session_service(session_id: str) -> dict:
    """Start a draft exactly like the dashboard's Start button: its form checks, then /live."""
    session_id = _session_id(session_id)
    with LIVE_SESSIONS_LOCK:
        info = _local_info()
        session = _load_session(session_id)
        _require_draft(session, session_id, 'started')
        stored = _session_form(session)
        paper_mode = _stored_bool(stored.get('paper_mode'), session.get('session_mode') != 'livetrade')
        form, context = _prepare_form(
            info, _settings(),
            paper_mode=paper_mode,
            exchange=stored.get('exchange'),
            exchange_api_key_id='' if paper_mode else stored.get('exchange_api_key_id'),
            notification_api_key_id=stored.get('notification_api_key_id'),
            routes=_parse_json_list(stored.get('routes') or [], 'routes'),
            data_routes=_parse_json_list(stored.get('data_routes') or [], 'data_routes'),
            debug_mode=_stored_bool(stored.get('debug_mode'), True),
            current_config=stored.get('config'),
            overrides=None,
            key_explicit=False,
        )
        response = _call('POST', '/live', {
            'id': session_id,
            'exchange': form['exchange'],
            # The dashboard never sends a key for a paper session.
            'exchange_api_key_id': '' if form['paper_mode'] else form['exchange_api_key_id'],
            'notification_api_key_id': form['notification_api_key_id'],
            'routes': form['routes'],
            'data_routes': form['data_routes'],
            'config': live_engine_config(form['config']),
            'debug_mode': form['debug_mode'],
            'paper_mode': form['paper_mode'],
        })
        if response.status_code == 409:
            raise _Failure('not_draft', f'Live session {session_id} was already started. Use copy_live_session for a new run.')
        if response.status_code != 202:
            raise _jesse_failure('start the live session', response)
    return {
        'status': 'success',
        'action': 'live_session_started',
        **_describe(session_id, form, context, 'starting'),
        'message': (
            f'Started a {_mode(form["paper_mode"])["mode"]} session on {form["exchange"]}. The session now validates the '
            'license and plan, connects to the exchange, and loads warm-up candles; any failure appears as the '
            'session error. Check get_session_results("live", session_id) until session_status is running.'
        ),
    }


@_contained('live_session_stop_failed')
def stop_live_session_service(session_id: str) -> dict:
    """Ask a running session to stop, like the dashboard's Stop button."""
    session_id = _session_id(session_id)
    # No LIVE_SESSIONS_LOCK: a stop must never queue behind another MCP call's reads of settings,
    # keys, and strategies. /live/cancel only removes the session's active marker (the route orders
    # it after a start in progress), so an overlapping start, update, or second stop cannot make it wrong.
    _local_info()
    session = _load_session(session_id)
    if not session.get('is_active'):
        raise _Failure(
            'not_running', f'Live session {session_id} is not running (status: {session.get("status")}).',
            session_status=session.get('status'),
        )
    form = _session_form(session)
    paper_mode = _stored_bool(form.get('paper_mode'), session.get('session_mode') != 'livetrade')
    response = _call('POST', '/live/cancel', {'id': session_id, 'paper_mode': paper_mode})
    if response.status_code != 200:
        raise _jesse_failure('stop the live session', response)
    config = form.get('config') if isinstance(form.get('config'), dict) else {}
    return {
        'status': 'success',
        'action': 'live_session_stop_requested',
        'session_id': session_id,
        **_mode(paper_mode),
        'exchange': session.get('exchange'),
        'persistency': config.get('persistency') if isinstance(config.get('persistency'), bool) else None,
        'on_stop': STOP_SEMANTICS,
        'dashboard_url': mcp_config.dashboard_url('live', session_id),
        'message': 'Stop requested. ' + STOP_SEMANTICS,
    }


@_contained('live_session_notes_failed')
def update_live_session_notes_service(session_id: str, title: Optional[str] = None, description: Optional[str] = None) -> dict:
    """Set a session's title and/or description, as the dashboard's notes dialog does."""
    session_id = _session_id(session_id)
    if title is None and description is None:
        raise _Failure('invalid_request', 'Pass a title, a description, or both.')
    _local_info()
    _load_session(session_id)
    _save_notes(session_id, title, description)
    return {
        'status': 'success',
        'action': 'live_session_notes_updated',
        'session_id': session_id,
        'title': title,
        'description': description,
        'message': 'Session notes updated.',
    }


@_contained('live_session_delete_failed')
def delete_live_session_service(session_id: str) -> dict:
    """Delete a stored session that is not running and not open in a dashboard tab."""
    session_id = _session_id(session_id)
    with LIVE_SESSIONS_LOCK:
        _local_info()
        session = _load_session(session_id)
        if _is_active(session):
            raise _Failure(
                'session_active', f'Live session {session_id} is {session.get("status")}; stop it before deleting it.',
                session_status=session.get('status'),
            )
        if session_id in _open_dashboard_tabs():
            raise _Failure(
                'open_in_dashboard_tab',
                'This session is open in a dashboard Live tab. Close the tab first, as the dashboard requires.',
            )
        response = _call('POST', f'/live/sessions/{session_id}/remove')
        if response.status_code == 404:
            raise _Failure('not_found', f'Live session {session_id} does not exist.')
        if response.status_code == 409:
            # Started from the dashboard after the check above; the route refuses to delete it.
            raise _Failure('session_active', f'Live session {session_id} was started; stop it before deleting it.')
        if response.status_code != 200:
            raise _jesse_failure('delete the live session', response)
    return {
        'status': 'success',
        'action': 'live_session_deleted',
        'session_id': session_id,
        'message': 'The session record was deleted. It never affected the exchange account.',
    }
