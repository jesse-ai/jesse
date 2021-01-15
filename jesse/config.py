config = {
    # these values are related to the user's environment
    'env': {
        'databases': {
            'postgres_host': '127.0.0.1',
            'postgres_name': 'jesse_db',
            'postgres_port': 5432,
            'postgres_username': 'jesse_user',
            'postgres_password': 'password',
        },

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
            'Sandbox': {
                'fee': 0,
                'type': 'spot',
                # used only in margin trading
                'settlement_currency': 'USDT',
                'assets': [
                    {'asset': 'USDT', 'balance': 10000},
                    {'asset': 'BTC', 'balance': 0},
                ],
            },

            # https://www.bitfinex.com
            'Bitfinex': {
                'type': 'margin',
                # used only in margin trading
                'settlement_currency': 'USD',
                'fee': 0.002,
                'assets': [
                    {'asset': 'USDT', 'balance': 10000},
                    {'asset': 'USD', 'balance': 10000},
                    {'asset': 'BTC', 'balance': 0},
                ],
            },

            # https://www.binance.com
            'Binance': {
                'type': 'spot',
                # used only in margin trading
                'settlement_currency': 'USDT',
                'fee': 0.001,
                'assets': [
                    {'asset': 'USDT', 'balance': 10000},
                    {'asset': 'BTC', 'balance': 0},
                ],
            },

            # https://www.binance.com
            'Binance Futures': {
                'type': 'margin',
                # used only in margin trading
                'settlement_currency': 'USDT',
                'fee': 0.0002,
                'assets': [
                    {'asset': 'USDT', 'balance': 10000},
                ],
            },

            # https://testnet.binancefuture.com
            'Testnet Binance Futures': {
                'type': 'margin',
                # used only in margin trading
                'settlement_currency': 'USDT',
                'fee': 0.0002,
                'assets': [
                    {'asset': 'USDT', 'balance': 10000},
                ],
            },

            # https://pro.coinbase.com
            'Coinbase': {
                'type': 'spot',
                # used only in margin trading
                'settlement_currency': 'USDT',
                'fee': 0.005,
                'assets': [
                    {'asset': 'USDT', 'balance': 10000},
                    {'asset': 'BTC', 'balance': 0},
                ],
            },
        },

        # changes the metrics output of the backtest
        'metrics': {
            'sharpe_ratio': True,
            'calmar_ratio': False,
            'sortino_ratio': False,
            'omega_ratio': False,
            'winning_streak': False,
            'losing_streak': False,
            'largest_losing_trade': False,
            'largest_winning_trade': False,
            'total_winning_trades': False,
            'total_losing_trades': False,
        },

        # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
        # Optimize mode
        # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
        #
        # Below configurations are related to the optimize mode
        # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
        'optimization': {
            # sharpe, calmar, sortino, omega
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
            'warmup_candles_num': 210,
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
    },
}

backup_config = config.copy()


def set_config(c):
    global config
    config['env'] = c
    # add sandbox because it isn't in the local config file
    config['env']['exchanges']['Sandbox'] = {
        'type': 'spot',
        # used only in margin trading
        'settlement_currency': 'USDT',
        'fee': 0,
        'assets': [
            {'asset': 'USDT', 'balance': 10000},
            {'asset': 'BTC', 'balance': 0},
        ],
    }


def reset_config():
    global config
    config = backup_config.copy()
