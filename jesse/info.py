from jesse.enums import exchanges as exchanges_enums, timeframes


BYBIT_TIMEFRAMES = [timeframes.MINUTE_1, timeframes.MINUTE_3, timeframes.MINUTE_5, timeframes.MINUTE_15, timeframes.MINUTE_30, timeframes.HOUR_1, timeframes.HOUR_2, timeframes.HOUR_4, timeframes.HOUR_6, timeframes.HOUR_12, timeframes.DAY_1]
FTX_TIMEFRAMES = [timeframes.MINUTE_1, timeframes.MINUTE_3, timeframes.MINUTE_5, timeframes.MINUTE_15, timeframes.MINUTE_30, timeframes.HOUR_1, timeframes.HOUR_2, timeframes.HOUR_4, timeframes.HOUR_6, timeframes.HOUR_12, timeframes.DAY_1]
BINANCE_TIMEFRAMES = [timeframes.MINUTE_1, timeframes.MINUTE_3, timeframes.MINUTE_5, timeframes.MINUTE_15, timeframes.MINUTE_30, timeframes.HOUR_1, timeframes.HOUR_2, timeframes.HOUR_4, timeframes.HOUR_6, timeframes.HOUR_8, timeframes.HOUR_12, timeframes.DAY_1]
COINBASE_TIMEFRAMES = [timeframes.MINUTE_1, timeframes.MINUTE_5, timeframes.MINUTE_15, timeframes.HOUR_1, timeframes.HOUR_6, timeframes.DAY_1]


exchange_info = {
    # BYBIT_USDT_PERPETUAL
    exchanges_enums.BYBIT_USDT_PERPETUAL: {
        'name': exchanges_enums.BYBIT_USDT_PERPETUAL,
        'url': 'https://jesse.trade/bybit',
        'fee': 0.00075,
        'type': 'futures',
        'supported_leverage_modes': ['cross', 'isolated'],
        'supported_timeframes': BYBIT_TIMEFRAMES,
        'modes': {
            'backtesting': True,
            'live_trading': True,
        }
    },
    # BYBIT_USDT_PERPETUAL_TESTNET
    exchanges_enums.BYBIT_USDT_PERPETUAL_TESTNET: {
        'name': exchanges_enums.BYBIT_USDT_PERPETUAL_TESTNET,
        'url': 'https://jesse.trade/bybit',
        'fee': 0.00075,
        'type': 'futures',
        'supported_leverage_modes': ['cross', 'isolated'],
        'supported_timeframes': BYBIT_TIMEFRAMES,
        'modes': {
            'backtesting': True,
            'live_trading': True,
        }
    },
    # FTX_PERPETUAL_FUTURES
    exchanges_enums.FTX_PERPETUAL_FUTURES: {
        'name': exchanges_enums.FTX_PERPETUAL_FUTURES,
        'url': 'https://ftx.com/markets/future',
        'fee': 0.0006,
        'type': 'futures',
        'supported_leverage_modes': ['cross'],
        'supported_timeframes': FTX_TIMEFRAMES,
        'modes': {
            'backtesting': True,
            'live_trading': True,
        }
    },
    # FTX_SPOT
    exchanges_enums.FTX_SPOT: {
        'name': exchanges_enums.FTX_SPOT,
        'url': 'https://ftx.com/markets/spot',
        'fee': 0.0007,
        'type': 'spot',
        'supported_leverage_modes': ['cross'],
        'supported_timeframes': FTX_TIMEFRAMES,
        'modes': {
            'backtesting': True,
            'live_trading': True,
        }
    },
    # FTX_US_SPOT
    exchanges_enums.FTX_US_SPOT: {
        'name': exchanges_enums.FTX_US_SPOT,
        'url': 'https://ftx.us',
        'fee': 0.002,
        'type': 'spot',
        'supported_leverage_modes': ['cross'],
        'supported_timeframes': FTX_TIMEFRAMES,
        'modes': {
            'backtesting': True,
            'live_trading': True,
        }
    },
    # BITFINEX_SPOT
    exchanges_enums.BITFINEX_SPOT: {
        'name': exchanges_enums.BITFINEX_SPOT,
        'url': 'https://bitfinex.com',
        'fee': 0.002,
        'type': 'spot',
        'supported_leverage_modes': ['cross'],
        'supported_timeframes': [timeframes.MINUTE_1, timeframes.MINUTE_5, timeframes.MINUTE_15, timeframes.MINUTE_30, timeframes.HOUR_1, timeframes.HOUR_3, timeframes.HOUR_6, timeframes.HOUR_12, timeframes.DAY_1],
        'modes': {
            'backtesting': True,
            'live_trading': False,
        }
    },
    # BINANCE_SPOT
    exchanges_enums.BINANCE_SPOT: {
        'name': exchanges_enums.BINANCE_SPOT,
        'url': 'https://binance.com',
        'fee': 0.001,
        'type': 'spot',
        'supported_leverage_modes': ['cross', 'isolated'],
        'supported_timeframes': BINANCE_TIMEFRAMES,
        'modes': {
            'backtesting': True,
            'live_trading': True,
        }
    },
    # BINANCE_US_SPOT
    exchanges_enums.BINANCE_US_SPOT: {
        'name': exchanges_enums.BINANCE_US_SPOT,
        'url': 'https://binance.us',
        'fee': 0.001,
        'type': 'spot',
        'supported_leverage_modes': ['cross', 'isolated'],
        'supported_timeframes': BINANCE_TIMEFRAMES,
        'modes': {
            'backtesting': True,
            'live_trading': True,
        }
    },
    # BINANCE_PERPETUAL_FUTURES
    exchanges_enums.BINANCE_PERPETUAL_FUTURES: {
        'name': exchanges_enums.BINANCE_PERPETUAL_FUTURES,
        'url': 'https://binance.com',
        'fee': 0.0004,
        'type': 'futures',
        'supported_leverage_modes': ['cross', 'isolated'],
        'supported_timeframes': BINANCE_TIMEFRAMES,
        'modes': {
            'backtesting': True,
            'live_trading': True,
        }
    },
    # BINANCE_PERPETUAL_FUTURES_TESTNET
    exchanges_enums.BINANCE_PERPETUAL_FUTURES_TESTNET: {
        'name': exchanges_enums.BINANCE_PERPETUAL_FUTURES_TESTNET,
        'url': 'https://binance.com',
        'fee': 0.0004,
        'type': 'futures',
        'supported_leverage_modes': ['cross', 'isolated'],
        'supported_timeframes': BINANCE_TIMEFRAMES,
        'modes': {
            'backtesting': True,
            'live_trading': True,
        }
    },
    # COINBASE_SPOT
    exchanges_enums.COINBASE_SPOT: {
        'name': exchanges_enums.COINBASE_SPOT,
        'url': 'https://pro.coinbase.com',
        'fee': 0.005,
        'type': 'spot',
        'supported_leverage_modes': ['cross', 'isolated'],
        'supported_timeframes': COINBASE_TIMEFRAMES,
        'modes': {
            'backtesting': True,
            'live_trading': False,
        }
    },
}

# list of supported exchanges for backtesting
backtesting_exchanges = [k for k, v in exchange_info.items() if v['modes']['backtesting'] is True]
backtesting_exchanges = list(sorted(backtesting_exchanges))

# list of supported exchanges for live trading
live_trading_exchanges = [k for k, v in exchange_info.items() if v['modes']['live_trading'] is True]
live_trading_exchanges = list(sorted(live_trading_exchanges))

# # list of supported exchanges for backtesting
# def get_backtesting_exchanges():
#     return list(sorted(
#         [k for k, v in exchange_info.items() if v['modes']['backtesting'] is True]
#     ))
#
#
# # list of supported exchanges for live trading
# def get_live_trading_exchanges():
#     return list(sorted(
#         [k for k, v in exchange_info.items() if v['modes']['live_trading'] is True]
#     ))

# used for backtesting, and live trading when local candle generation is enabled:
jesse_supported_timeframes = [
    timeframes.MINUTE_1,
    timeframes.MINUTE_3,
    timeframes.MINUTE_5,
    timeframes.MINUTE_15,
    timeframes.MINUTE_30,
    timeframes.MINUTE_45,
    timeframes.HOUR_1,
    timeframes.HOUR_2,
    timeframes.HOUR_3,
    timeframes.HOUR_4,
    timeframes.HOUR_6,
    timeframes.HOUR_8,
    timeframes.HOUR_12,
    timeframes.DAY_1,
]
