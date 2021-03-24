config = {
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    # PostgreSQL Database
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    #
    # PostgreSQL is used as the database to store data such as candles.
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    'databases': {
        'postgres_host': '127.0.0.1',
        'postgres_name': 'jesse_db',
        'postgres_port': 5432,
        'postgres_username': 'jesse_user',
        'postgres_password': 'password',
    },

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    # Caching
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    #
    # In some cases such as loading candles in the backtest mode, a
    # caching mechanism is used to make further loadings faster.
    # Valid options (so far) are: 'pickle', None
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    'caching': {
        'driver': 'pickle'
    },

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    # Exchanges
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    #
    # Below values are used for exchanges.
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    'exchanges': {
        # https://www.bitfinex.com
        'Bitfinex': {
            'fee': 0.002,

            # backtest mode only: accepted are 'spot' and 'futures'
            'type': 'futures',

            # futures mode only
            'settlement_currency': 'USD',
            # accepted values are: 'cross' and 'isolated'
            'futures_leverage_mode': 'cross',
            # 1x, 2x, 10x, 50x, etc. Enter as integers
            'futures_leverage': 1,

            'assets': [
                {'asset': 'USDT', 'balance': 10_000},
                {'asset': 'USD', 'balance': 10_000},
                {'asset': 'BTC', 'balance': 0},
            ],
        },

        # https://www.binance.com
        'Binance': {
            'fee': 0.001,

            # backtest mode only: accepted are 'spot' and 'futures'
            'type': 'futures',

            # futures mode only
            'settlement_currency': 'USDT',
            # accepted values are: 'cross' and 'isolated'
            'futures_leverage_mode': 'cross',
            # 1x, 2x, 10x, 50x, etc. Enter as integers
            'futures_leverage': 1,

            'assets': [
                {'asset': 'USDT', 'balance': 10_000},
                {'asset': 'BTC', 'balance': 0},
            ],
        },

        # https://www.binance.com
        'Binance Futures': {
            'fee': 0.0004,

            # backtest mode only: accepted are 'spot' and 'futures'
            'type': 'futures',

            # futures mode only
            'settlement_currency': 'USDT',
            # accepted values are: 'cross' and 'isolated'
            'futures_leverage_mode': 'cross',
            # 1x, 2x, 10x, 50x, etc. Enter as integers
            'futures_leverage': 1,

            'assets': [
                {'asset': 'USDT', 'balance': 10_000},
            ],
        },

        # https://testnet.binancefuture.com
        'Testnet Binance Futures': {
            'fee': 0.0004,

            # backtest mode only: accepted are 'spot' and 'futures'
            'type': 'futures',

            # futures mode only
            'settlement_currency': 'USDT',
            # accepted values are: 'cross' and 'isolated'
            'futures_leverage_mode': 'cross',
            # 1x, 2x, 10x, 50x, etc. Enter as integers
            'futures_leverage': 1,

            'assets': [
                {'asset': 'USDT', 'balance': 10_000},
            ],
        },

        # https://pro.coinbase.com
        'Coinbase': {
            'fee': 0.005,

            # backtest mode only: accepted are 'spot' and 'futures'
            'type': 'futures',

            # futures mode only
            'settlement_currency': 'USD',
            # accepted values are: 'cross' and 'isolated'
            'futures_leverage_mode': 'cross',
            # 1x, 2x, 10x, 50x, etc. Enter as integers
            'futures_leverage': 1,

            'assets': [
                {'asset': 'USDT', 'balance': 10_000},
                {'asset': 'USD', 'balance': 10_000},
                {'asset': 'BTC', 'balance': 0},
            ],
        },
    },

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    # Logging
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    #
    # Below configurations are used to filter out the extra logging
    # info that are displayed when the "--debug" flag is enabled.
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
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

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    # Metrics
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    #
    # Below configurations are used to set the metrics
    # that are displayed after a backtest.
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
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
        'warmup_candles_num': 240,
    }
}
