"""Session-owned configuration helpers shared by Jesse's MCP run tools."""

import json
from copy import deepcopy
from multiprocessing import cpu_count
from typing import Optional

from jesse.info import exchange_info


_BASE_LOGGING = {
    'order_submission': True,
    'order_cancellation': True,
    'order_execution': True,
    'position_opened': True,
    'position_increased': True,
    'position_reduced': True,
    'position_closed': True,
    'shorter_period_candles': False,
    'trading_candles': True,
    'balance_update': True,
}

_MODE_FIELDS = {
    'backtest': ('logging', 'warm_up_candles', 'exchange'),
    'optimization': (
        'objective_function',
        'warm_up_candles',
        'trials',
        'cpu_cores',
        'best_candidates_count',
        'exchange',
    ),
    'monte_carlo': ('warm_up_candles', 'cpu_cores', 'exchange'),
    'significance_test': ('warm_up_candles', 'exchange'),
}


def default_cpu_cores() -> int:
    """Leave one logical CPU free and cap unattended MCP jobs at four workers."""
    try:
        return max(1, min(cpu_count() - 1, 4))
    except Exception:
        return 2


def _merge(target: dict, source: object) -> dict:
    """Deep-merge JSON objects without sharing references with persisted settings."""
    if not isinstance(source, dict):
        return target

    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _merge(target[key], value)
        else:
            target[key] = deepcopy(value)
    return target


def _exchange_config(exchange_name: str, value: object, default_leverage: int) -> dict:
    metadata = exchange_info.get(exchange_name, {})
    supplied = value if isinstance(value, dict) else {}
    exchange_type = metadata.get('type') or supplied.get('type') or 'futures'
    config = {
        'name': exchange_name,
        'type': exchange_type,
        'balance': supplied.get('balance', 10_000),
        'fee': supplied.get('fee', metadata.get('fee', 0.0006)),
    }

    if exchange_type == 'futures':
        supported_modes = metadata.get('supported_leverage_modes') or ['cross']
        requested_mode = supplied.get('futures_leverage_mode', 'cross')
        config['futures_leverage_mode'] = (
            requested_mode if requested_mode in supported_modes else supported_modes[0]
        )
        config['futures_leverage'] = supplied.get('futures_leverage', default_leverage)

    return config


def _mode_defaults(mode: str, exchange_name: str) -> dict:
    # Backtests default to unleveraged execution; the research modes use the
    # Dashboard's 5x futures default when no saved session preference exists.
    leverage = 1 if mode == 'backtest' else 5
    exchange = _exchange_config(exchange_name, {}, leverage)
    if mode == 'backtest':
        return {
            'logging': deepcopy(_BASE_LOGGING),
            'warm_up_candles': 210,
            'exchange': exchange,
        }
    if mode == 'optimization':
        return {
            'objective_function': 'sharpe',
            'warm_up_candles': 210,
            'trials': 200,
            'cpu_cores': default_cpu_cores(),
            'best_candidates_count': 20,
            'exchange': exchange,
        }
    if mode == 'monte_carlo':
        return {
            'warm_up_candles': 210,
            'cpu_cores': default_cpu_cores(),
            'exchange': exchange,
        }
    if mode == 'significance_test':
        return {
            'warm_up_candles': 210,
            'exchange': exchange,
        }
    raise ValueError(f'Unsupported session configuration mode: {mode}')


def _legacy_config(settings: dict, mode: str, exchange_name: str) -> dict:
    legacy = settings.get(mode)
    if not isinstance(legacy, dict):
        return {}

    if mode != 'backtest':
        return legacy

    exchanges = legacy.get('exchanges')
    exchange = exchanges.get(exchange_name, {}) if isinstance(exchanges, dict) else {}
    return {
        'logging': legacy.get('logging', {}),
        'warm_up_candles': legacy.get('warm_up_candles', 210),
        'exchange': exchange,
    }


def _saved_layer(settings: object, mode: str, exchange_name: str) -> dict:
    """The saved settings that apply to one mode and exchange, before any explicit override."""
    settings_dict = settings if isinstance(settings, dict) else {}
    layer = _merge({}, _legacy_config(settings_dict, mode, exchange_name))

    session_defaults = settings_dict.get('session_defaults')
    mode_defaults = session_defaults.get(mode) if isinstance(session_defaults, dict) else None
    if isinstance(mode_defaults, dict):
        _merge(layer, mode_defaults.get('fallback'))
        by_exchange = mode_defaults.get('by_exchange')
        if isinstance(by_exchange, dict):
            _merge(layer, by_exchange.get(exchange_name))
    return layer


def resolve_session_run_config(
    settings: object,
    mode: str,
    exchange_name: str,
    overrides: Optional[dict] = None,
) -> dict:
    """Resolve one MCP run config using the same exchange-scoped precedence as tabs."""
    resolved = _mode_defaults(mode, exchange_name)
    _merge(resolved, _saved_layer(settings, mode, exchange_name))
    _merge(resolved, overrides)
    default_leverage = 1 if mode == 'backtest' else 5
    resolved['exchange'] = _exchange_config(
        exchange_name,
        resolved.get('exchange'),
        default_leverage,
    )
    if mode == 'backtest':
        logging = resolved.get('logging') if isinstance(resolved.get('logging'), dict) else {}
        resolved['logging'] = {
            key: logging.get(key, default)
            for key, default in _BASE_LOGGING.items()
        }

    # Persist only the documented fields consumed by the matching Dashboard
    # form and runtime mode.
    return {key: resolved[key] for key in _MODE_FIELDS[mode]}


def load_saved_settings() -> dict:
    """The saved Jesse settings, or {} when they cannot be read."""
    from .config import get_config_service

    try:
        result = get_config_service()
    except Exception:
        return {}
    settings = result.get('config', {}) if result.get('status') == 'success' else {}
    if isinstance(settings, dict) and set(settings) == {'data'}:
        settings = settings.get('data', {})
    return settings if isinstance(settings, dict) else {}


def load_session_run_config(
    mode: str,
    exchange_name: str,
    overrides: Optional[dict] = None,
) -> dict:
    """Load saved defaults when available and fall back to deterministic MCP values."""
    return resolve_session_run_config(load_saved_settings(), mode, exchange_name, overrides)


# ---------------------------------------------------------------------------
# Draft tool arguments
#
# The MCP draft tools for backtests, optimizations, Monte Carlo runs and significance tests
# take the run settings an agent most often sets (fee, leverage, leverage mode, balance,
# warm-up candles) as named arguments, plus `config_overrides` for any other documented field
# of the mode. They are the `overrides` of resolve_session_run_config, so a draft starts with
# them instead of the saved or built-in defaults. Each draft response reports where every
# value came from, and warns when fee or leverage is one of Jesse's built-in defaults.
# ---------------------------------------------------------------------------

DRAFT_CONFIG_ARGUMENTS = {
    'fee': ('exchange', 'fee'),
    'leverage': ('exchange', 'futures_leverage'),
    'leverage_mode': ('exchange', 'futures_leverage_mode'),
    'balance': ('exchange', 'balance'),
    'warm_up_candles': ('warm_up_candles',),
}
_ARGUMENT_NAMES = {path: name for name, path in DRAFT_CONFIG_ARGUMENTS.items()}
_EXCHANGE_OVERRIDE_KEYS = ('balance', 'fee', 'futures_leverage', 'futures_leverage_mode')
_LEVERAGE_KEYS = ('futures_leverage', 'futures_leverage_mode')
_OBJECTIVE_FUNCTIONS = ('sharpe', 'calmar', 'sortino', 'omega', 'serenity', 'smart sharpe', 'smart sortino')
_MODE_LABELS = {
    'backtest': 'backtests',
    'optimization': 'optimizations',
    'monte_carlo': 'Monte Carlo runs',
    'significance_test': 'significance tests',
}
_MODE_NAMES = {
    'backtest': 'backtest',
    'optimization': 'optimization',
    'monte_carlo': 'Monte Carlo',
    'significance_test': 'significance test',
}


def _label(path: tuple) -> str:
    """Name a field the way the agent sent it: the named argument when there is one."""
    return _ARGUMENT_NAMES.get(path) or f"config_overrides.{'.'.join(path)}"


def _check_number(path: tuple, value: object, minimum: float, integer: bool = False,
                  below: Optional[float] = None, strict_minimum: bool = False) -> None:
    label = _label(path)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{label} must be a number.')
    if value != value or value in (float('inf'), float('-inf')):
        raise ValueError(f'{label} must be a finite number.')
    if integer and int(value) != value:
        raise ValueError(f'{label} must be a whole number.')
    if value < minimum or (strict_minimum and value == minimum):
        raise ValueError(f"{label} must be {'more than' if strict_minimum else 'at least'} {minimum}.")
    if below is not None and value >= below:
        raise ValueError(f'{label} must be below {below}.')


def _parse_config_overrides(mode: str, value: object) -> dict:
    """Read `config_overrides` (a JSON object, as text or already decoded) for one mode."""
    if value is None or value == '':
        return {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as e:
            raise ValueError(f'config_overrides is not valid JSON: {e}')
    if not isinstance(value, dict):
        raise ValueError('config_overrides must be a JSON object.')

    allowed = _MODE_FIELDS[mode]
    unknown = sorted(key for key in value if key not in allowed)
    if unknown:
        raise ValueError(
            f"config_overrides has fields {mode} drafts do not use: {', '.join(unknown)}. "
            f"Allowed: {', '.join(allowed)}."
        )
    exchange = value.get('exchange')
    if exchange is not None:
        if not isinstance(exchange, dict):
            raise ValueError('config_overrides.exchange must be a JSON object.')
        unknown = sorted(key for key in exchange if key not in _EXCHANGE_OVERRIDE_KEYS)
        if unknown:
            raise ValueError(
                f"config_overrides.exchange cannot set: {', '.join(unknown)}. "
                f"Allowed: {', '.join(_EXCHANGE_OVERRIDE_KEYS)} (the exchange itself is the draft's "
                '`exchange` argument).'
            )
    return deepcopy(value)


def _validate_overrides(mode: str, exchange_name: str, overrides: dict) -> None:
    exchange = overrides.get('exchange', {})
    if 'fee' in exchange:
        _check_number(('exchange', 'fee'), exchange['fee'], 0, below=1)
    if 'balance' in exchange:
        _check_number(('exchange', 'balance'), exchange['balance'], 0, strict_minimum=True)
    if 'futures_leverage' in exchange:
        _check_number(('exchange', 'futures_leverage'), exchange['futures_leverage'], 1, integer=True)
    if 'futures_leverage_mode' in exchange:
        leverage_mode = exchange['futures_leverage_mode']
        supported = (exchange_info.get(exchange_name) or {}).get('supported_leverage_modes') or ['cross', 'isolated']
        if leverage_mode not in supported:
            raise ValueError(
                f"{_label(('exchange', 'futures_leverage_mode'))} must be one of: {', '.join(supported)}"
                f' (the modes {exchange_name} supports).'
            )
    for key in ('warm_up_candles',):
        if key in overrides:
            _check_number((key,), overrides[key], 0, integer=True)
    for key in ('trials', 'cpu_cores', 'best_candidates_count'):
        if key in overrides:
            _check_number((key,), overrides[key], 1, integer=True)
    if 'objective_function' in overrides:
        objective = overrides['objective_function']
        if not isinstance(objective, str) or objective.lower() not in _OBJECTIVE_FUNCTIONS:
            raise ValueError(
                f"{_label(('objective_function',))} must be one of: {', '.join(_OBJECTIVE_FUNCTIONS)}."
            )
    if 'logging' in overrides:
        logging = overrides['logging']
        if not isinstance(logging, dict) or any(
            key not in _BASE_LOGGING or not isinstance(flag, bool) for key, flag in logging.items()
        ):
            raise ValueError(
                f"config_overrides.logging must map these flags to true/false: {', '.join(_BASE_LOGGING)}."
            )


def parse_draft_config_arguments(
    mode: str,
    exchange_name: str,
    config_overrides: object = None,
    base: Optional[dict] = None,
    **arguments,
) -> tuple[dict, list]:
    """
    Validate a draft tool's run-config arguments into overrides for resolve_session_run_config.

    `base` holds the tool's own named mode-specific arguments (an optimization's `trials`, for
    example) and `arguments` the named DRAFT_CONFIG_ARGUMENTS (None means not given); named
    arguments win over the same field in `config_overrides`. Returns (overrides, warnings) and raises
    ValueError with a message meant for the agent.
    """
    unknown = sorted(name for name in arguments if name not in DRAFT_CONFIG_ARGUMENTS)
    if unknown:
        raise TypeError(f"Unknown draft config arguments: {', '.join(unknown)}")

    overrides = {**_parse_config_overrides(mode, config_overrides), **deepcopy(base or {})}
    for name, value in arguments.items():
        if value is None:
            continue
        *parents, key = DRAFT_CONFIG_ARGUMENTS[name]
        target = overrides
        for parent in parents:
            target = target.setdefault(parent, {})
        target[key] = value
    _validate_overrides(mode, exchange_name, overrides)

    warnings = []
    exchange = overrides.get('exchange')
    if (exchange_info.get(exchange_name) or {}).get('type') == 'spot' and isinstance(exchange, dict):
        ignored = [key for key in _LEVERAGE_KEYS if exchange.pop(key, None) is not None]
        if ignored:
            names = ' and '.join(_label(('exchange', key)) for key in ignored)
            warnings.append(f'{names} ignored: {exchange_name} is a spot exchange.')
    if isinstance(exchange, dict) and not exchange:
        overrides.pop('exchange')
    return overrides, warnings


def _get_path(source: object, path: tuple) -> tuple[bool, object]:
    for key in path:
        if not isinstance(source, dict) or key not in source:
            return False, None
        source = source[key]
    return True, source


def run_config_sources(
    settings: object,
    mode: str,
    exchange_name: str,
    config: dict,
    explicit: Optional[dict] = None,
    stored: Optional[dict] = None,
    tool_defaults: Optional[dict] = None,
) -> dict:
    """
    Say where each value of a resolved run config came from: "explicit" (this call's arguments),
    "stored" (the draft already had it), "tool_default" (the MCP tool's own default, such as its
    cpu_cores for unattended runs), "saved_default" (the saved settings for this mode and
    exchange), "exchange_default" (the exchange's listed fee) or "hard_default" (Jesse's built-in
    value). Logging flags are reported as one entry.
    """
    saved = _saved_layer(settings, mode, exchange_name)
    paths = [('exchange', key) for key in _EXCHANGE_OVERRIDE_KEYS]
    paths += [(key,) for key in _MODE_FIELDS[mode] if key != 'exchange']
    sources = {}
    for path in paths:
        if not _get_path(config, path)[0]:
            continue
        if _get_path(explicit, path)[0]:
            source = 'explicit'
        elif _get_path(stored, path)[0]:
            source = 'stored'
        elif _get_path(tool_defaults, path)[0]:
            source = 'tool_default'
        elif _get_path(saved, path)[0]:
            source = 'saved_default'
        elif path == ('exchange', 'fee') and 'fee' in (exchange_info.get(exchange_name) or {}):
            source = 'exchange_default'
        else:
            source = 'hard_default'
        sources['.'.join(path)] = source
    return sources


def _hard_default_warnings(mode: str, exchange_name: str, config: dict, sources: dict) -> list:
    warnings = []
    for path, argument in ((('exchange', 'fee'), 'fee'), (('exchange', 'futures_leverage'), 'leverage')):
        if sources.get('.'.join(path)) == 'hard_default':
            value = _get_path(config, path)[1]
            warnings.append(
                f"{argument} {value} is Jesse's built-in default: nothing is saved for "
                f'{_MODE_LABELS[mode]} on {exchange_name}. Pass {argument}= to choose it.'
            )
    return warnings


def _backtest_mismatch_warnings(settings: object, mode: str, exchange_name: str, config: dict,
                                sources: dict) -> list:
    """
    Flag a fee or leverage this draft inherits that differs from the backtest defaults of the
    same exchange. The Dashboard keeps separate defaults per mode (and seeds every exchange
    with its own), so an optimization can silently run at another fee than the backtests it
    follows up on.
    """
    if mode == 'backtest':
        return []
    backtest = resolve_session_run_config(settings, 'backtest', exchange_name)
    differences = []
    for path, argument in ((('exchange', 'fee'), 'fee'), (('exchange', 'futures_leverage'), 'leverage')):
        if sources.get('.'.join(path)) in ('explicit', 'stored', None):
            continue
        has_value, value = _get_path(config, path)
        has_backtest_value, backtest_value = _get_path(backtest, path)
        if has_value and has_backtest_value and value != backtest_value:
            differences.append((argument, value, backtest_value))
    if not differences:
        return []
    described = ', '.join(f'{argument} {value} (backtests: {backtest_value})'
                          for argument, value, backtest_value in differences)
    names = ' and '.join(f'{argument}=' for argument, _, _ in differences)
    return [
        f'The saved {_MODE_NAMES[mode]} defaults on {exchange_name} differ from its backtest '
        f'defaults: {described}. Pass {names} to choose explicitly.'
    ]


def resolve_draft_run_config(
    mode: str,
    exchange_name: str,
    overrides: Optional[dict] = None,
    stored: Optional[dict] = None,
    settings: Optional[dict] = None,
    tool_defaults: Optional[dict] = None,
) -> dict:
    """
    Resolve a draft's run config from the saved settings, the tool's own `tool_defaults` (which
    win over saved settings), the draft's `stored` config (when updating one) and this call's
    `overrides`, and describe it for the tool response.

    Returns {'config', 'config_source', 'warnings'}.
    """
    if settings is None:
        settings = load_saved_settings()
    requested = _merge(_merge({}, tool_defaults), stored)
    _merge(requested, overrides)
    config = resolve_session_run_config(settings, mode, exchange_name, requested)
    sources = run_config_sources(settings, mode, exchange_name, config, overrides, stored, tool_defaults)
    return {
        'config': config,
        'config_source': sources,
        'warnings': (
            _hard_default_warnings(mode, exchange_name, config, sources)
            + _backtest_mismatch_warnings(settings, mode, exchange_name, config, sources)
        ),
    }


def backtest_engine_config(run_config: dict) -> dict:
    """Convert a stored BacktestRunConfig into the engine's existing request shape."""
    exchange = deepcopy(run_config['exchange'])
    return {
        'logging': deepcopy(run_config['logging']),
        'warm_up_candles': int(run_config['warm_up_candles']),
        'exchanges': {exchange['name']: exchange},
    }


def optimization_engine_config(run_config: dict) -> dict:
    """Provide optimizer-only leverage fallbacks without polluting a spot form."""
    config = deepcopy(run_config)
    config.pop('cpu_cores', None)
    config['exchange'].setdefault('futures_leverage_mode', 'cross')
    config['exchange'].setdefault('futures_leverage', 1)
    return config


def monte_carlo_engine_config(run_config: dict) -> dict:
    """Expose exchange balance and fee where the Monte Carlo runner reads them."""
    config = deepcopy(run_config)
    config.pop('cpu_cores', None)
    config['starting_balance'] = config['exchange']['balance']
    config['fee'] = config['exchange']['fee']
    return config


# ---------------------------------------------------------------------------
# Live and paper sessions
#
# A Python port of dashboard-v1/app/utils/sessionConfig.ts (normalizeLiveRunConfig,
# normalizeSessionDefaults, resolveLiveRunConfig, syncRunConfigExchange, liveEngineConfig), so a
# draft made through MCP gets exactly the configuration a new dashboard Live tab would get for
# the same paper exchange or saved exchange key. Saved settings are only read here; unlike the
# dashboard's Start button, MCP never remembers a started session's configuration as the next
# default, so running a session never changes shared settings.
# ---------------------------------------------------------------------------

_LIVE_LOGGING = {**_BASE_LOGGING, 'strategy_execution': True, 'exchange_ws_reconnection': True}

_NOTIFICATION_EVENTS = (
    'errors', 'started_session', 'terminated_session', 'submitted_orders', 'cancelled_orders',
    'executed_orders', 'opened_position', 'updated_position', 'exchange_ws_reconnection',
    'closed_position', 'account_balance',
)

_DEFAULT_NOTIFICATIONS = {
    'enabled': True,
    'position_report_timeframe': '1h',
    # Account amounts require an explicit opt-in, matching the dashboard defaults.
    'events': {event: event != 'account_balance' for event in _NOTIFICATION_EVENTS},
}

# The dashboard's DEFAULT_RESEARCH_EXCHANGE, the base of every Live/Paper exchange profile.
_DEFAULT_LIVE_EXCHANGE = {
    'name': '',
    'type': 'futures',
    'simulation_model': 'perpetual_futures',
    'annualization': 365,
    'balance': 10_000,
    'fee': 0.0006,
    'futures_leverage_mode': 'cross',
    'futures_leverage': 5,
}

LIVE_CONFIG_FIELDS = (
    'persistency', 'generate_candles_from_1m', 'logging', 'warm_up_candles',
    'order_backup_check_seconds', 'candle_backup_refresh_seconds', 'notifications', 'exchange',
)
# The REST backup to the WebSocket: check open orders and refresh recent candles every N
# seconds, where 0 turns a check off and a candle refresh of None means 5 plus 1 per symbol.
DEFAULT_ORDER_BACKUP_CHECK_SECONDS = 10
DEFAULT_CANDLE_BACKUP_REFRESH_SECONDS = None
LIVE_LOGGING_FIELDS = tuple(_LIVE_LOGGING)
NOTIFICATION_FIELDS = tuple(_DEFAULT_NOTIFICATIONS)
NOTIFICATION_EVENTS = _NOTIFICATION_EVENTS
LIVE_EXCHANGE_OVERRIDE_FIELDS = (
    'balance', 'fee', 'futures_leverage', 'futures_leverage_mode', 'simulation_model', 'type', 'annualization',
)


def _record(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _finite_number(value: object, fallback, minimum: float = 0):
    """JavaScript `finiteNumber`: numbers and numeric strings at or above `minimum`, else fallback."""
    parsed: float
    if isinstance(value, bool):
        return fallback
    if isinstance(value, (int, float)):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = float(value)
        except ValueError:
            return fallback
    else:
        return fallback
    if parsed != parsed or parsed in (float('inf'), float('-inf')) or parsed < minimum:
        return fallback
    return parsed


def _optional_seconds(source: dict, key: str, fallback):
    """JavaScript `optionalSeconds`: an empty value means automatic (None); a missing key keeps the fallback."""
    if key not in source:
        return fallback
    value = source[key]
    if value is None or value == '':
        return None
    return _finite_number(value, fallback)


def _string_value(value: object, fallback: str) -> str:
    return value if isinstance(value, str) and value else fallback


def _boolean_value(value: object, fallback: bool) -> bool:
    return value if isinstance(value, bool) else fallback


def _normalize_logging(value: object, fallback: dict) -> dict:
    source = _record(value)
    normalized = {key: _boolean_value(source.get(key), fallback[key]) for key in _BASE_LOGGING}
    for key in ('strategy_execution', 'exchange_ws_reconnection'):
        if key in fallback or key in source:
            normalized[key] = _boolean_value(source.get(key), fallback.get(key, True))
    return normalized


def _normalize_notifications(value: object, fallback: dict) -> dict:
    source = _record(value)
    events = _record(source.get('events'))
    return {
        'enabled': _boolean_value(source.get('enabled'), fallback['enabled']),
        'position_report_timeframe': _string_value(
            source.get('position_report_timeframe'), fallback['position_report_timeframe'],
        ),
        'events': {event: _boolean_value(events.get(event), fallback['events'][event]) for event in _NOTIFICATION_EVENTS},
    }


def _normalize_simulation_model(value: object, fallback: str) -> str:
    if value in ('spot', 'perpetual_futures'):
        return str(value)
    if value == 'futures':
        return 'perpetual_futures'
    return fallback


def _legacy_type(simulation_model: str) -> str:
    return 'futures' if simulation_model == 'perpetual_futures' else 'spot'


def _normalize_annualization(value: object, fallback: int) -> int:
    parsed = value
    if isinstance(value, str):
        try:
            parsed = float(value)
        except ValueError:
            return fallback
    if isinstance(parsed, bool):
        return fallback
    return int(parsed) if parsed in (252, 365) else fallback


def _normalize_live_exchange(value: object, fallback: dict, forced_name: Optional[str] = None) -> dict:
    source = _record(value)
    fallback_model = _normalize_simulation_model(fallback.get('simulation_model') or fallback.get('type'), 'spot')
    requested_model = source.get('simulation_model') or source.get('market_type') or source.get('type')
    simulation_model = _normalize_simulation_model(requested_model, fallback_model)
    exchange_type = _legacy_type(simulation_model)
    normalized = {
        'name': forced_name if forced_name is not None else _string_value(source.get('name'), fallback.get('name', '')),
        'type': exchange_type,
        'simulation_model': simulation_model,
        'annualization': _normalize_annualization(source.get('annualization'), fallback.get('annualization') or 365),
        'balance': _finite_number(source.get('balance'), fallback['balance']),
        'fee': _finite_number(source.get('fee'), fallback['fee']),
    }
    if exchange_type == 'futures':
        normalized['futures_leverage_mode'] = _string_value(
            source.get('futures_leverage_mode'), fallback.get('futures_leverage_mode') or 'cross',
        )
        normalized['futures_leverage'] = _finite_number(
            source.get('futures_leverage'), fallback.get('futures_leverage') or 1, 1,
        )
    return normalized


def normalize_live_run_config(value: object, fallback: dict) -> dict:
    """Fill a (possibly partial or malformed) live run config from `fallback`, field by field."""
    source = _record(value)
    return {
        'persistency': _boolean_value(source.get('persistency'), fallback['persistency']),
        'generate_candles_from_1m': _boolean_value(
            source.get('generate_candles_from_1m'), fallback['generate_candles_from_1m'],
        ),
        'logging': _normalize_logging(source.get('logging'), fallback['logging']),
        'warm_up_candles': _finite_number(source.get('warm_up_candles'), fallback['warm_up_candles']),
        'order_backup_check_seconds': _finite_number(
            source.get('order_backup_check_seconds'), fallback['order_backup_check_seconds'],
        ),
        'candle_backup_refresh_seconds': _optional_seconds(
            source, 'candle_backup_refresh_seconds', fallback['candle_backup_refresh_seconds'],
        ),
        'notifications': _normalize_notifications(source.get('notifications'), fallback['notifications']),
        'exchange': _normalize_live_exchange(source.get('exchange'), fallback['exchange']),
    }


def _exchange_annualization(info: dict) -> int:
    if info.get('annualization'):
        return int(info['annualization'])
    asset_class = info.get('asset_class')
    return 365 if not asset_class or asset_class == 'crypto' else 252


def live_session_defaults(settings: object, exchanges: Optional[dict] = None) -> dict:
    """
    The dashboard's contextual Live/Paper defaults: a fallback, one profile per live-trading
    exchange (used for Paper sessions and for Live sessions without a credential profile), and
    the profiles remembered per saved exchange key.
    """
    exchanges = exchange_info if exchanges is None else exchanges
    root = _record(settings)
    live = _record(root.get('live'))
    legacy_exchanges = _record(live.get('exchanges'))
    derived_fallback = {
        'persistency': _boolean_value(live.get('persistency'), True),
        'generate_candles_from_1m': _boolean_value(live.get('generate_candles_from_1m'), False),
        'logging': _normalize_logging(live.get('logging'), _LIVE_LOGGING),
        'warm_up_candles': _finite_number(live.get('warm_up_candles'), 210),
        'order_backup_check_seconds': _finite_number(
            live.get('order_backup_check_seconds'), DEFAULT_ORDER_BACKUP_CHECK_SECONDS,
        ),
        'candle_backup_refresh_seconds': _optional_seconds(
            live, 'candle_backup_refresh_seconds', DEFAULT_CANDLE_BACKUP_REFRESH_SECONDS,
        ),
        'notifications': _normalize_notifications(live.get('notifications'), _DEFAULT_NOTIFICATIONS),
        'exchange': deepcopy(_DEFAULT_LIVE_EXCHANGE),
    }
    live_names = list(dict.fromkeys([
        *legacy_exchanges.keys(),
        *(name for name, info in exchanges.items() if _record(info.get('modes')).get('live_trading')),
    ]))
    derived_paper = {}
    for name in live_names:
        info = _record(exchanges.get(name))
        profile = {
            **_DEFAULT_LIVE_EXCHANGE,
            'name': name,
            'fee': info.get('fee', _DEFAULT_LIVE_EXCHANGE['fee']),
            'type': info.get('type', _DEFAULT_LIVE_EXCHANGE['type']),
            'simulation_model': _normalize_simulation_model(
                info.get('simulation_model') or info.get('type'), _DEFAULT_LIVE_EXCHANGE['simulation_model'],
            ),
            'annualization': _exchange_annualization(info),
        }
        derived_paper[name] = {
            **deepcopy(derived_fallback),
            'exchange': _normalize_live_exchange(legacy_exchanges.get(name), profile, name),
        }

    stored_live = _record(_record(root.get('session_defaults')).get('live'))
    stored_paper = _record(stored_live.get('paper_by_exchange'))
    stored_credentials = _record(stored_live.get('live_by_credential'))
    fallback = normalize_live_run_config(stored_live.get('fallback'), derived_fallback)
    paper_by_exchange = {
        name: normalize_live_run_config(stored_paper.get(name), derived_paper.get(name, fallback))
        for name in dict.fromkeys([*derived_paper.keys(), *stored_paper.keys()])
    }
    live_by_credential = {
        key_id: normalize_live_run_config(stored_credentials[key_id], fallback)
        for key_id in stored_credentials
    }
    return {'fallback': fallback, 'paper_by_exchange': paper_by_exchange, 'live_by_credential': live_by_credential}


def sync_live_exchange(config_exchange: dict, exchange_name: str, lock_to_exchange: bool,
                       exchanges: Optional[dict] = None) -> None:
    """
    Keep the exchange identity authoritative (the dashboard's syncRunConfigExchange). A real
    (non-paper) session always uses the venue's own market type and annualization.
    """
    exchanges = exchange_info if exchanges is None else exchanges
    info = exchanges.get(exchange_name)
    config_exchange['name'] = exchange_name
    authoritative = (info.get('simulation_model') or info.get('type')) if lock_to_exchange and info else None
    simulation_model = _normalize_simulation_model(
        authoritative or config_exchange.get('simulation_model') or config_exchange.get('type'), 'spot',
    )
    config_exchange['simulation_model'] = simulation_model
    config_exchange['type'] = _legacy_type(simulation_model)
    exchange_annualization = _exchange_annualization(info or {})
    config_exchange['annualization'] = (
        exchange_annualization if lock_to_exchange and info
        else _normalize_annualization(config_exchange.get('annualization'), exchange_annualization)
    )


def resolve_live_run_config(
    settings: object,
    paper_mode: bool,
    exchange_name: str,
    exchange_api_key_id: str = '',
    current: object = None,
    overrides: Optional[dict] = None,
    exchanges: Optional[dict] = None,
) -> dict:
    """
    Resolve one Live/Paper session's own run configuration.

    Mirrors a dashboard Live tab: the context default (the saved key's profile for a real
    session, else the exchange's paper profile, else the fallback) fills in whatever `current`
    (the draft's stored config) lacks, then `overrides` are merged and the exchange identity is
    synced. The result belongs to that one session only.
    """
    defaults = live_session_defaults(settings, exchanges)
    context_default = None
    if not paper_mode and exchange_api_key_id:
        context_default = defaults['live_by_credential'].get(exchange_api_key_id)
    if context_default is None:
        context_default = defaults['paper_by_exchange'].get(exchange_name, defaults['fallback'])
    config = normalize_live_run_config(current, context_default) if isinstance(current, dict) else deepcopy(context_default)
    if overrides:
        config = normalize_live_run_config(_merge(deepcopy(config), overrides), config)
    sync_live_exchange(config['exchange'], exchange_name, not paper_mode, exchanges)
    return config


def _live_default_source(settings: object, paper_mode: bool, exchange_name: str, exchange_api_key_id: str,
                         field: str, exchanges: Optional[dict] = None) -> str:
    """
    Where resolve_live_run_config takes an exchange `field` from when neither the call nor the
    session has it, following live_session_defaults: the saved profile of the key (a real session
    whose key the dashboard remembered), else the exchange's paper profile (saved, or the older
    live.exchanges settings, or the exchange's listed fee), else the fallback profile.
    """
    exchanges = exchange_info if exchanges is None else exchanges
    root = _record(settings)
    legacy = _record(_record(root.get('live')).get('exchanges'))
    stored_live = _record(_record(root.get('session_defaults')).get('live'))

    def saved_in(profile: object) -> bool:
        return field in _record(_record(profile).get('exchange'))

    fallback_source = 'saved_default' if saved_in(stored_live.get('fallback')) else 'hard_default'
    credentials = _record(stored_live.get('live_by_credential'))
    if not paper_mode and exchange_api_key_id and exchange_api_key_id in credentials:
        return 'saved_default' if saved_in(credentials[exchange_api_key_id]) else fallback_source
    if saved_in(_record(stored_live.get('paper_by_exchange')).get(exchange_name)):
        return 'saved_default'
    info = _record(exchanges.get(exchange_name))
    if exchange_name not in legacy and not _record(info.get('modes')).get('live_trading'):
        return fallback_source
    if field in _record(legacy.get(exchange_name)):
        return 'saved_default'
    if field == 'fee' and 'fee' in info:
        return 'exchange_default'
    return 'hard_default'


def live_config_sources(
    settings: object,
    paper_mode: bool,
    exchange_name: str,
    exchange_api_key_id: str,
    config: dict,
    explicit: Optional[dict] = None,
    carried: object = None,
    carried_as: str = 'stored',
    exchanges: Optional[dict] = None,
) -> dict:
    """
    Say where the money settings of a resolved live/paper config came from: "explicit" (this
    call's config), `carried_as` ("stored" for a draft's own config, "copied" for the session a
    copy or restart was made from), "saved_default", "exchange_default" (the listed fee) or
    "hard_default" (Jesse's built-in value). A real session trades with the venue's balance and
    fee, so only its leverage is reported; spot sessions have no leverage.
    """
    fields = ('futures_leverage', 'futures_leverage_mode') if config['exchange'].get('type') == 'futures' else ()
    if paper_mode:
        fields = ('balance', 'fee') + fields
    sources = {}
    for field in fields:
        path = ('exchange', field)
        if _get_path(explicit, path)[0]:
            source = 'explicit'
        elif _get_path(carried, path)[0]:
            source = carried_as
        else:
            source = _live_default_source(settings, paper_mode, exchange_name, exchange_api_key_id, field, exchanges)
        sources['.'.join(path)] = source
    return sources


def live_default_warnings(paper_mode: bool, exchange_name: str, config: dict, sources: dict) -> list:
    """Warn about a leverage or fee that is only Jesse's built-in default (nothing saved, nothing copied)."""
    where = f'paper sessions on {exchange_name}' if paper_mode else 'this API key'
    warnings = []
    for field, label in (('futures_leverage', 'leverage'), ('fee', 'fee')):
        if sources.get(f'exchange.{field}') == 'hard_default':
            warnings.append(
                f"{label} {config['exchange'][field]} is Jesse's built-in default: nothing is saved for {where}. "
                f'Set config.exchange.{field} to choose it.'
            )
    return warnings


def live_engine_config(run_config: dict) -> dict:
    """Convert a LiveRunConfig into the request shape /live passes to the live engine (liveEngineConfig)."""
    exchange = deepcopy(run_config['exchange'])
    return {
        'persistency': run_config['persistency'],
        'generate_candles_from_1m': run_config['generate_candles_from_1m'],
        'logging': deepcopy(run_config['logging']),
        'warm_up_candles': int(run_config['warm_up_candles']),
        'order_backup_check_seconds': run_config['order_backup_check_seconds'],
        'candle_backup_refresh_seconds': run_config['candle_backup_refresh_seconds'],
        'notifications': deepcopy(run_config['notifications']),
        'exchanges': {exchange['name']: exchange},
    }
