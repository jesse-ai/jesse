config = {
    # these values are related to the user's environment
    'env': {
        'databases': {
            'postgres_host': '127.0.0.1',
            'postgres_name': 'jesse_db',
            'postgres_port': 5432,
            'postgres_username': 'jesse_user',
            'postgres_password': '',

            'redis_host': 'localhost',
            'redis_port': 6379,
            'redis_expiration_seconds': 60 * 15,
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
            'Sandbox': {
                'fee': 0,
                'starting_balance': 10000,
            },

            # https://www.bitfinex.com
            'Bitfinex': {
                'fee': 0.002,
                'starting_balance': 10000,
            },

            # https://www.binance.com
            'Binance': {
                'fee': 0.001,
                'starting_balance': 10000,
            },

            # https://www.binance.com
            'Binance Futures': {
                'fee': 0.0002,
                'starting_balance': 10000,
            },

            # https://testnet.binancefuture.com
            'Testnet Binance Futures': {
                'fee': 0.0002,
                'starting_balance': 10000,
            },

            # https://pro.coinbase.com
            'Coinbase': {
                'fee': 0.005,
                'starting_balance': 10000,
            },
        }
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

        # variable used for test-driving the livetrade mode
        'is_test_driving': False,

        # this would enable many console.log()s in the code, which are helpful for debugging.
        'debug_mode': False,

        # setting this value to False would disable few validation checks which
        # are required for live trading on real markets, however, it is useful
        # for doing backtests simulations while faster strategy development.
        'strategy-validation': True
    }
}

backup_config = config.copy()


def set_config(c):
    global config
    config['env'] = c
    # add sandbox because it isn't in the local config file
    config['env']['exchanges']['Sandbox'] = {
        'fee': 0,
        'starting_balance': 10000,
    }


def reset_config():
    global config
    config = backup_config.copy()
