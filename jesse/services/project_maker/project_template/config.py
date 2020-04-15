config = {
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    # Databases (PostgreSQL and Redis)
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    #
    # PostgreSQL is used as the primary database to store data
    # permanently.Redis is used as the caching layer to boost
    # start-up time by storing some data temporarily.
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    'databases': {
        'postgres_host': '127.0.0.1',
        'postgres_name': 'jesse_db',
        'postgres_port': 5432,
        'postgres_username': 'jesse_user',
        'postgres_password': 'password',

        'redis_host': 'localhost',
        'redis_port': 6379,
        'redis_expiration_seconds': 60 * 15,
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
}
