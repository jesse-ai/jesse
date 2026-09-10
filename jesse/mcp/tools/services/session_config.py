"""Session-owned configuration helpers shared by Jesse's MCP run tools."""

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


def _default_cpu_cores() -> int:
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
    elif exchange_type == 'margin':
        # broker margin account: the same key is the leverage cap; the mode is always cross
        config['futures_leverage'] = supplied.get('futures_leverage', default_leverage)
        config['futures_leverage_mode'] = 'cross'

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
            'cpu_cores': _default_cpu_cores(),
            'best_candidates_count': 20,
            'exchange': exchange,
        }
    if mode == 'monte_carlo':
        return {
            'warm_up_candles': 210,
            'cpu_cores': _default_cpu_cores(),
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


def resolve_session_run_config(
    settings: object,
    mode: str,
    exchange_name: str,
    overrides: Optional[dict] = None,
) -> dict:
    """Resolve one MCP run config using the same exchange-scoped precedence as tabs."""
    settings_dict = settings if isinstance(settings, dict) else {}
    resolved = _mode_defaults(mode, exchange_name)
    _merge(resolved, _legacy_config(settings_dict, mode, exchange_name))

    session_defaults = settings_dict.get('session_defaults')
    mode_defaults = session_defaults.get(mode) if isinstance(session_defaults, dict) else None
    if isinstance(mode_defaults, dict):
        _merge(resolved, mode_defaults.get('fallback'))
        by_exchange = mode_defaults.get('by_exchange')
        if isinstance(by_exchange, dict):
            _merge(resolved, by_exchange.get(exchange_name))

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


def load_session_run_config(
    mode: str,
    exchange_name: str,
    overrides: Optional[dict] = None,
) -> dict:
    """Load saved defaults when available and fall back to deterministic MCP values."""
    from .config import get_config_service

    result = get_config_service()
    settings = result.get('config', {}) if result.get('status') == 'success' else {}
    if isinstance(settings, dict) and set(settings) == {'data'}:
        settings = settings.get('data', {})
    return resolve_session_run_config(settings, mode, exchange_name, overrides)


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
