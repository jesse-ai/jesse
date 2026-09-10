from copy import deepcopy

import jesse.helpers as jh
from jesse.modes.utils import get_exchange_type
from jesse.enums import exchanges
from jesse.info import exchange_info
from jesse.services.simulation_assumptions import (
    Annualization,
    legacy_type_from_simulation_model,
    resolve_annualization,
    resolve_simulation_model,
    simulation_model_from_legacy_type,
)

# Main configuration used by the Jesse framework. These values are modified
# at runtime based on the mode (backtest, live, or optimize) and user settings.
config = {
    # these values are related to the user's environment
    'env': {
        'caching': {
            'driver': 'pickle'
        },

        'logging': {
            'strategy_execution': True,
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
            'exchange_ws_reconnection': True
        },

        # fill it later in this file using data in info.py
        'exchanges': {
            exchanges.SANDBOX: {
                'fee': 0,
                'type': 'futures',
                'annualization': 365,
                # accepted values are: 'cross' and 'isolated'
                'futures_leverage_mode': 'cross',
                # 1x, 2x, 10x, 50x, etc. Enter as integers
                'futures_leverage': 1,
                'balance': 10_000,
            },
        },

        # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
        # Optimize mode (using Optuna)
        # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
        #
        # Below configurations are related to the optimize mode
        # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
        'optimization': {
            # available ratio options: sharpe, calmar, sortino, omega, serenity, smart sharpe, smart sortino
            'objective_function': 'sharpe',
            # number of trials per each hyperparameter
            'trials': 200,
            # number of best candidates to keep and display
            'best_candidates_count': 20,
        },

        # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
        # Data
        # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
        #
        # Below configurations are related to the data
        # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
        'data': {
            # The minimum number of warmup candles that is loaded before each session.
            'warmup_candles_num': 240,
            'generate_candles_from_1m': False,
            'persistency': True,
        },

        'metrics': {
            'annualization': 365,
        },
    },

    # These values are just placeholders used by Jesse at runtime
    'app': {
        # list of currencies to consider
        'considering_symbols': [],
        # The symbol to trade.
        'trading_symbols': [],

        # list of time frames to consider
        'considering_timeframes': [],
        # Which candle type do you intend trade on
        'trading_timeframes': [],

        # list of exchanges to consider
        'considering_exchanges': [],
        # list of exchanges to consider
        'trading_exchanges': [],

        'considering_candles': [],

        # dict of registered live trade drivers
        'live_drivers': {},

        # Accepted values are: 'backtest', 'livetrade', 'fitness'.
        'trading_mode': '',

        # this would enable many console.log()s in the code, which are helpful for debugging.
        'debug_mode': False,

        # this is only used for the live unit tests
        'is_unit_testing': False,
    },
}

# set exchange config values based on the info
for key in exchange_info:
    config['env']['exchanges'][key] = {
        'fee': exchange_info[key]['fee'],
        'type': exchange_info[key]['type'],
        'annualization': resolve_annualization(exchange_info[key]),
        'futures_leverage_mode': 'cross',
        'futures_leverage': 1,
        'balance': 10_000
    }


def set_config(conf: dict) -> None:
    global config

    # optimization mode only
    if jh.is_optimizing():
        # objective function
        if 'objective_function' in conf:
            config['env']['optimization']['objective_function'] = conf['objective_function']
        # warm_up_candles
        config['env']['data']['warmup_candles_num'] = int(conf['warm_up_candles'])
        # number of trials per each hyperparameter
        config['env']['optimization']['trials'] = int(conf['trials'])
        # best candidates count
        if 'best_candidates_count' in conf:
            config['env']['optimization']['best_candidates_count'] = int(conf['best_candidates_count'])

    # backtest and live
    if jh.is_backtesting() or jh.is_live():
        # warm_up_candles
        config['env']['data']['warmup_candles_num'] = int(conf['warm_up_candles'])
        # logs
        config['env']['logging'] = conf['logging']
        # exchanges
        selected_annualization = None
        for key, e in conf['exchanges'].items():
            # The dashboard sends each exchange entry carrying its own 'name', but the
            # exchanges map is keyed by exchange name and scripted/MCP callers pass the
            # entries without a redundant 'name'. Fall back to the dict key so both the
            # dashboard payload and the natural dict-keyed config (what /config returns)
            # work. Without this, a missing 'name' raised KeyError deep inside a spawned
            # backtest/RST worker, which then exited silently (the traceback was lost on
            # the os._exit() that follows), leaving the MCP/dashboard session stuck.
            name = e.get('name') or key
            if jh.is_livetrading():
                simulation_model = simulation_model_from_legacy_type(get_exchange_type(name))
                annualization = resolve_annualization(exchange_info[name])
            else:
                default_type = exchange_info.get(name, {}).get(
                    'type',
                    config['env']['exchanges'].get(name, {}).get('type', 'futures'),
                )
                simulation_model = resolve_simulation_model(e, default_type)
                annualization = resolve_annualization(e)
            exchange_type = legacy_type_from_simulation_model(simulation_model)
            if selected_annualization is not None and selected_annualization != annualization:
                raise ValueError('All exchanges in one run must use the same annualization assumption')
            selected_annualization = annualization
            config['env']['exchanges'][name] = {
                'fee': float(e['fee']),
                'type': exchange_type,
                'simulation_model': simulation_model.value,
                'annualization': int(annualization),
                'balance': float(e['balance'])
            }
            if config['env']['exchanges'][name]['type'] == 'futures':
                # 1x, 2x, 10x, 50x, etc. Enter as integers
                config['env']['exchanges'][name]['futures_leverage'] = int(e.get('futures_leverage', 1))
                # accepted values are: 'cross' and 'isolated'
                config['env']['exchanges'][name]['futures_leverage_mode'] = e.get('futures_leverage_mode', 'cross')
            elif config['env']['exchanges'][name]['type'] == 'margin':
                # A broker margin account: the same key holds the user's leverage cap (>= 1) and the
                # mode is always cross, whatever the client sent.
                config['env']['exchanges'][name]['futures_leverage'] = max(1, int(e.get('futures_leverage', 1)))
                config['env']['exchanges'][name]['futures_leverage_mode'] = 'cross'
        if selected_annualization is not None:
            config['env']['metrics']['annualization'] = int(selected_annualization)

    # live mode only
    if jh.is_live():
        config['env']['notifications'] = conf['notifications']
        config['env']['data']['persistency'] = conf['persistency']
        config['env']['data']['generate_candles_from_1m'] = conf['generate_candles_from_1m']

    # TODO: must become a config value later when we go after multi account support?
    config['env']['identifier'] = 'main'


def reset_config() -> None:
    # Modules import this dictionary directly, so resetting must preserve its
    # identity while replacing every nested runtime mutation.
    config.clear()
    config.update(deepcopy(backup_config))
    jh.clear_config_caches()


backup_config = deepcopy(config)
