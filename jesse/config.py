import jesse.helpers as jh
from jesse.modes.utils import get_exchange_type
from jesse.enums import exchanges


config = {
    # these values are related to the user's environment
    'env': {
        'caching': {
            'driver': 'pickle'
        },

        'logging': {
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
        },

        'exchanges': {
            exchanges.SANDBOX: {
                'fee': 0,
                'type': 'futures',
                # accepted values are: 'cross' and 'isolated'
                'futures_leverage_mode': 'cross',
                # 1x, 2x, 10x, 50x, etc. Enter as integers
                'futures_leverage': 1,
                'balance': 10_000,
            },

            exchanges.BYBIT_USDT_PERPETUAL: {
                'fee': 0.00075,
                'type': 'futures',
                'futures_leverage_mode': 'cross',
                'futures_leverage': 1,
                'balance': 10_000
            },

            exchanges.BYBIT_USDT_PERPETUAL_TESTNET: {
                'fee': 0.00075,
                'type': 'futures',
                'futures_leverage_mode': 'cross',
                'futures_leverage': 1,
                'balance': 10_000
            },

            # https://ftx.com/markets/future
            exchanges.FTX_PERPETUAL_FUTURES: {
                'fee': 0.0006,
                'type': 'futures',
                'futures_leverage_mode': 'cross',
                'futures_leverage': 1,
                'balance': 10_000
            },

            # https://ftx.com/markets/spot
            exchanges.FTX_SPOT: {
                'fee': 0.0007,
                'type': 'spot',
                'futures_leverage_mode': 'cross',
                'futures_leverage': 1,
                'balance': 10_000
            },

            # https://www.bitfinex.com
            exchanges.BITFINEX_SPOT: {
                'fee': 0.002,
                'type': 'futures',
                'futures_leverage_mode': 'cross',
                'futures_leverage': 1,
                'balance': 10_000
            },

            # https://www.binance.com
            exchanges.BINANCE_SPOT: {
                'fee': 0.001,
                'type': 'futures',
                'futures_leverage_mode': 'cross',
                'futures_leverage': 1,
                'balance': 10_000
            },

            # https://www.binance.com
            exchanges.BINANCE_PERPETUAL_FUTURES: {
                'fee': 0.0004,
                'type': 'futures',
                'futures_leverage_mode': 'cross',
                'futures_leverage': 1,
                'balance': 10_000
            },

            # https://testnet.binancefuture.com
            exchanges.BINANCE_PERPETUAL_FUTURES_TESTNET: {
                'fee': 0.0004,
                'type': 'futures',
                'futures_leverage_mode': 'cross',
                'futures_leverage': 1,
                'balance': 10_000
            },

            # https://pro.coinbase.com
            exchanges.COINBASE_SPOT: {
                'fee': 0.005,
                'type': 'futures',
                'balance': 10_000
            },
        },

        # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
        # Optimize mode
        # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
        #
        # Below configurations are related to the optimize mode
        # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
        'optimization': {
            # sharpe, calmar, sortino, omega, serenity, smart sharpe, smart sortino
            'ratio': 'sharpe',
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
            'persistency': True,
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


def set_config(conf: dict) -> None:
    global config

    # optimization mode only
    if jh.is_optimizing():
        # ratio
        config['env']['optimization']['ratio'] = conf['ratio']
        # exchange info (only one because the optimize mode supports only one trading route at the moment)
        config['env']['optimization']['exchange'] = conf['exchange']
        # warm_up_candles
        config['env']['optimization']['warmup_candles_num'] = int(conf['warm_up_candles'])

    # backtest and live
    if jh.is_backtesting() or jh.is_live():
        # warm_up_candles
        config['env']['data']['warmup_candles_num'] = int(conf['warm_up_candles'])
        # logs
        config['env']['logging'] = conf['logging']
        # exchanges
        for key, e in conf['exchanges'].items():
            if not jh.is_live() and e['type']:
                exchange_type = e['type']
            else:
                exchange_type = get_exchange_type(e['name'])
            config['env']['exchanges'][e['name']] = {
                'fee': float(e['fee']),
                'type': exchange_type,
                'balance': float(e['balance'])
            }
            if config['env']['exchanges'][e['name']]['type'] == 'futures':
                # 1x, 2x, 10x, 50x, etc. Enter as integers
                config['env']['exchanges'][e['name']]['futures_leverage'] = int(e['futures_leverage'])
                # accepted values are: 'cross' and 'isolated'
                config['env']['exchanges'][e['name']]['futures_leverage_mode'] = e['futures_leverage_mode']

    # live mode only
    if jh.is_live():
        config['env']['notifications'] = conf['notifications']
        config['env']['data']['persistency'] = conf['persistency']

    # TODO: must become a config value later when we go after multi account support?
    config['env']['identifier'] = 'main'

    # # add sandbox because it isn't in the local config file but it is needed since we might have replaced it
    # config['env']['exchanges']['Sandbox'] = {
    #     'type': 'spot',
    #     # used only in futures trading
    #     'fee': 0,
    #     'futures_leverage_mode': 'cross',
    #     'futures_leverage': 1,
    #     'assets': [
    #         {'asset': 'USDT', 'balance': 10_000},
    #         {'asset': 'BTC', 'balance': 0},
    #     ],
    # }


def reset_config() -> None:
    global config
    config = backup_config.copy()


backup_config = config.copy()
