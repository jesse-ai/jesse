from jesse.enums import exchanges as exchanges_enums, timeframes

JESSE_API_URL = 'https://api1.jesse.trade/api'
# JESSE_API_URL = 'http://localhost:8040/api'
JESSE_WEBSITE_URL = 'https://jesse.trade'
# JESSE_WEBSITE_URL = 'http://localhost:8040'

BYBIT_TIMEFRAMES = [timeframes.MINUTE_1, timeframes.MINUTE_3, timeframes.MINUTE_5, timeframes.MINUTE_15, timeframes.MINUTE_30,
                    timeframes.HOUR_1, timeframes.HOUR_2, timeframes.HOUR_4, timeframes.HOUR_6, timeframes.HOUR_12, timeframes.DAY_1]
BINANCE_TIMEFRAMES = [timeframes.MINUTE_1, timeframes.MINUTE_3, timeframes.MINUTE_5, timeframes.MINUTE_15, timeframes.MINUTE_30,
                      timeframes.HOUR_1, timeframes.HOUR_2, timeframes.HOUR_4, timeframes.HOUR_6, timeframes.HOUR_8, timeframes.HOUR_12, timeframes.DAY_1]
COINBASE_TIMEFRAMES = [timeframes.MINUTE_1, timeframes.MINUTE_5,
                       timeframes.MINUTE_15, timeframes.HOUR_1, timeframes.HOUR_6, timeframes.DAY_1]
APEX_PRO_TIMEFRAMES = [timeframes.MINUTE_1, timeframes.MINUTE_5, timeframes.MINUTE_15,
                       timeframes.MINUTE_30, timeframes.HOUR_1, timeframes.HOUR_2, timeframes.HOUR_4, timeframes.HOUR_6, timeframes.HOUR_12, timeframes.DAY_1]
GATE_TIMEFRAMES = [timeframes.MINUTE_1, timeframes.MINUTE_5, timeframes.MINUTE_15,
                   timeframes.MINUTE_30, timeframes.HOUR_1, timeframes.HOUR_2, timeframes.HOUR_4, timeframes.HOUR_6, timeframes.HOUR_8, timeframes.HOUR_12, timeframes.DAY_1, timeframes.WEEK_1]
FTX_TIMEFRAMES = [timeframes.MINUTE_1, timeframes.MINUTE_3, timeframes.MINUTE_5, timeframes.MINUTE_15, timeframes.MINUTE_30,
                  timeframes.HOUR_1, timeframes.HOUR_2, timeframes.HOUR_4, timeframes.HOUR_6, timeframes.HOUR_12, timeframes.DAY_1]
BITGET_TIMEFRAMES = [timeframes.MINUTE_1, timeframes.MINUTE_5, timeframes.MINUTE_15,
                     timeframes.MINUTE_30, timeframes.HOUR_1, timeframes.HOUR_4, timeframes.HOUR_12, timeframes.DAY_1]
DYDX_TIMEFRAMES = [timeframes.MINUTE_1, timeframes.MINUTE_5, timeframes.MINUTE_15,
                   timeframes.MINUTE_30, timeframes.HOUR_1, timeframes.HOUR_4, timeframes.DAY_1]
HYPERLIQUID_TIMEFRAMES = [timeframes.MINUTE_1, timeframes.MINUTE_3, timeframes.MINUTE_5, timeframes.MINUTE_15,
                         timeframes.MINUTE_30, timeframes.HOUR_1, timeframes.HOUR_2, timeframes.HOUR_4, timeframes.HOUR_6, timeframes.HOUR_8, timeframes.HOUR_12, timeframes.DAY_1]

exchange_info = {
    # BYBIT_USDT_PERPETUAL
    exchanges_enums.BYBIT_USDT_PERPETUAL: {
        "name": exchanges_enums.BYBIT_USDT_PERPETUAL,
        "url": JESSE_WEBSITE_URL + "/bybit",
        "fee": 0.00055,
        "type": "futures",
        "settlement_currency": "USDT",
        "supported_leverage_modes": ["cross", "isolated"],
        "supported_timeframes": BYBIT_TIMEFRAMES,
        "modes": {
            "backtesting": True,
            "live_trading": True,
        },
        "required_live_plan": "premium",
    },
    # BYBIT_USDT_PERPETUAL_TESTNET
    exchanges_enums.BYBIT_USDT_PERPETUAL_TESTNET: {
        "name": exchanges_enums.BYBIT_USDT_PERPETUAL_TESTNET,
        "url": JESSE_WEBSITE_URL + "/bybit",
        "fee": 0.00055,
        "type": "futures",
        "settlement_currency": "USDT",
        "supported_leverage_modes": ["cross", "isolated"],
        "supported_timeframes": BYBIT_TIMEFRAMES,
        "modes": {
            "backtesting": False,
            "live_trading": True,
        },
        "required_live_plan": "premium",
    },
    # BYBIT_USDT_PERPETUAL
    exchanges_enums.BYBIT_USDC_PERPETUAL: {
        "name": exchanges_enums.BYBIT_USDC_PERPETUAL,
        "url": JESSE_WEBSITE_URL + "/bybit",
        "fee": 0.00055,
        "type": "futures",
        "settlement_currency": "USDC",
        "supported_leverage_modes": ["cross", "isolated"],
        "supported_timeframes": BYBIT_TIMEFRAMES,
        "modes": {
            "backtesting": True,
            "live_trading": True,
        },
        "required_live_plan": "premium",
    },
    # BYBIT_USDC_PERPETUAL_TESTNET
    exchanges_enums.BYBIT_USDC_PERPETUAL_TESTNET: {
        "name": exchanges_enums.BYBIT_USDC_PERPETUAL_TESTNET,
        "url": JESSE_WEBSITE_URL + "/bybit",
        "fee": 0.00055,
        "type": "futures",
        "supported_leverage_modes": ["cross", "isolated"],
        "supported_timeframes": BYBIT_TIMEFRAMES,
        "settlement_currency": "USDC",
        "modes": {
            "backtesting": False,
            "live_trading": True,
        },
        "required_live_plan": "premium",
    },
    # BYBIT_SPOT_TESTNET
    exchanges_enums.BYBIT_SPOT: {
        "name": exchanges_enums.BYBIT_SPOT,
        "url": "https://jesse.trade/bybit",
        "fee": 0.001,
        "type": "spot",
        "supported_leverage_modes": ["cross", "isolated"],
        "supported_timeframes": BYBIT_TIMEFRAMES,
        "modes": {
            "backtesting": True,
            "live_trading": True,
        },
        "required_live_plan": "premium",
    },
    # BYBIT_SPOT_TESTNET
    exchanges_enums.BYBIT_SPOT_TESTNET: {
        "name": exchanges_enums.BYBIT_SPOT_TESTNET,
        "url": "https://jesse.trade/bybit",
        "fee": 0.001,
        "type": "spot",
        "supported_leverage_modes": ["cross", "isolated"],
        "supported_timeframes": BYBIT_TIMEFRAMES,
        "modes": {
            "backtesting": False,
            "live_trading": True,
        },
        "required_live_plan": "premium",
    },
    # BITFINEX_SPOT
    exchanges_enums.BITFINEX_SPOT: {
        "name": exchanges_enums.BITFINEX_SPOT,
        "url": "https://bitfinex.com",
        "fee": 0.002,
        "type": "spot",
        "supported_leverage_modes": ["cross"],
        "supported_timeframes": [
            timeframes.MINUTE_1,
            timeframes.MINUTE_5,
            timeframes.MINUTE_15,
            timeframes.MINUTE_30,
            timeframes.HOUR_1,
            timeframes.HOUR_3,
            timeframes.HOUR_6,
            timeframes.HOUR_12,
            timeframes.DAY_1,
        ],
        "modes": {
            "backtesting": True,
            "live_trading": False,
        },
        "required_live_plan": "premium",
    },
    # BINANCE_SPOT
    exchanges_enums.BINANCE_SPOT: {
        "name": exchanges_enums.BINANCE_SPOT,
        "url": "https://binance.com",
        "fee": 0.001,
        "type": "spot",
        "supported_leverage_modes": ["cross", "isolated"],
        "supported_timeframes": BINANCE_TIMEFRAMES,
        "modes": {
            "backtesting": True,
            "live_trading": True,
        },
        "required_live_plan": "premium",
    },
    # BINANCE_US_SPOT
    exchanges_enums.BINANCE_US_SPOT: {
        "name": exchanges_enums.BINANCE_US_SPOT,
        "url": "https://binance.us",
        "fee": 0.001,
        "type": "spot",
        "supported_leverage_modes": ["cross", "isolated"],
        "supported_timeframes": BINANCE_TIMEFRAMES,
        "modes": {
            "backtesting": True,
            "live_trading": True,
        },
        "required_live_plan": "premium",
    },
    # BINANCE_PERPETUAL_FUTURES
    exchanges_enums.BINANCE_PERPETUAL_FUTURES: {
        "name": exchanges_enums.BINANCE_PERPETUAL_FUTURES,
        "url": "https://binance.com",
        "fee": 0.0004,
        "type": "futures",
        "supported_leverage_modes": ["cross", "isolated"],
        "supported_timeframes": BINANCE_TIMEFRAMES,
        "modes": {
            "backtesting": True,
            "live_trading": True,
        },
        "required_live_plan": "premium",
    },
    # BINANCE_PERPETUAL_FUTURES_TESTNET
    exchanges_enums.BINANCE_PERPETUAL_FUTURES_TESTNET: {
        "name": exchanges_enums.BINANCE_PERPETUAL_FUTURES_TESTNET,
        "url": "https://binance.com",
        "fee": 0.0004,
        "type": "futures",
        "supported_leverage_modes": ["cross", "isolated"],
        "supported_timeframes": BINANCE_TIMEFRAMES,
        "modes": {
            "backtesting": False,
            "live_trading": True,
        },
        "required_live_plan": "premium",
    },
    # COINBASE_SPOT
    exchanges_enums.COINBASE_SPOT: {
        "name": exchanges_enums.COINBASE_SPOT,
        "url": "https://www.coinbase.com/advanced-trade/spot/BTC-USD",
        "fee": 0.0003,
        "type": "spot",
        "supported_leverage_modes": ["cross", "isolated"],
        "supported_timeframes": COINBASE_TIMEFRAMES,
        "modes": {
            "backtesting": True,
            "live_trading": True,
        },
        "required_live_plan": "premium",
    },
    # APEX_PRO_PERPETUAL_TESTNET
    exchanges_enums.APEX_PRO_PERPETUAL_TESTNET: {
        "name": exchanges_enums.APEX_PRO_PERPETUAL_TESTNET,
        "url": "https://testnet.pro.apex.exchange/trade/BTCUSD",
        "fee": 0.0005,
        "type": "futures",
        "supported_leverage_modes": ["cross"],
        "supported_timeframes": APEX_PRO_TIMEFRAMES,
        "modes": {
            "backtesting": False,
            "live_trading": False,
        },
        "required_live_plan": "free",
    },
    exchanges_enums.APEX_PRO_PERPETUAL: {
        "name": exchanges_enums.APEX_PRO_PERPETUAL,
        "url": "https://pro.apex.exchange/trade/BTCUSD",
        "fee": 0.0005,
        "type": "futures",
        "supported_leverage_modes": ["cross"],
        "supported_timeframes": APEX_PRO_TIMEFRAMES,
        "modes": {
            "backtesting": False,
            "live_trading": True,
        },
        "required_live_plan": "premium",
    },
    exchanges_enums.APEX_OMNI_PERPETUAL_TESTNET: {
        "name": exchanges_enums.APEX_OMNI_PERPETUAL_TESTNET,
        "url": "https://testnet.omni.apex.exchange/trade/BTCUSD",
        "fee": 0.0005,
        "type": "futures",
        "supported_leverage_modes": ["cross"],
        "supported_timeframes": APEX_PRO_TIMEFRAMES,
        "modes": {
            "backtesting": False,
            "live_trading": False,
        },
        "required_live_plan": "free",
    },
    exchanges_enums.APEX_OMNI_PERPETUAL: {
        "name": exchanges_enums.APEX_OMNI_PERPETUAL,
        "url": "https://omni.apex.exchange/trade/BTCUSD",
        "fee": 0.0005,
        "type": "futures",
        "supported_leverage_modes": ["cross"],
        "supported_timeframes": APEX_PRO_TIMEFRAMES,
        "modes": {
            "backtesting": False,
            "live_trading": True,
        },
        "required_live_plan": "premium",
    },
    exchanges_enums.GATE_USDT_PERPETUAL: {
        "name": exchanges_enums.GATE_USDT_PERPETUAL,
        "url": "https://jesse.trade/gate",
        "fee": 0.0005,
        "type": "futures",
        "supported_leverage_modes": ["cross", "isolated"],
        "supported_timeframes": GATE_TIMEFRAMES,
        "modes": {
            "backtesting": True,
            "live_trading": True,
        },
        "required_live_plan": "premium",
    },
    exchanges_enums.GATE_SPOT: {
        "name": exchanges_enums.GATE_SPOT,
        "url": "https://jesse.trade/gate",
        "fee": 0.0005,
        "type": "spot",
        "supported_leverage_modes": ["cross", "isolated"],
        "supported_timeframes": GATE_TIMEFRAMES,
        "modes": {
            "backtesting": False,
            "live_trading": True,
        },
        "required_live_plan": "premium",
    },
    # FTX_PERPETUAL_FUTURES
    exchanges_enums.FTX_PERPETUAL_FUTURES: {
        "name": exchanges_enums.FTX_PERPETUAL_FUTURES,
        "url": "https://ftx.com/markets/future",
        "fee": 0.0006,
        "type": "futures",
        "supported_leverage_modes": ["cross"],
        "supported_timeframes": FTX_TIMEFRAMES,
        "modes": {
            "backtesting": False,
            "live_trading": False,
        },
        "required_live_plan": "premium",
    },
    # FTX_SPOT
    exchanges_enums.FTX_SPOT: {
        "name": exchanges_enums.FTX_SPOT,
        "url": "https://ftx.com/markets/spot",
        "fee": 0.0007,
        "type": "spot",
        "supported_leverage_modes": ["cross"],
        "supported_timeframes": FTX_TIMEFRAMES,
        "modes": {
            "backtesting": False,
            "live_trading": False,
        },
        "required_live_plan": "premium",
    },
    # FTX_US_SPOT
    exchanges_enums.FTX_US_SPOT: {
        "name": exchanges_enums.FTX_US_SPOT,
        "url": "https://ftx.us",
        "fee": 0.002,
        "type": "spot",
        "supported_leverage_modes": ["cross"],
        "supported_timeframes": FTX_TIMEFRAMES,
        "modes": {
            "backtesting": False,
            "live_trading": False,
        },
        "required_live_plan": "premium",
    },
    # BITGET_USDT_PERPETUAL_TESTNET
    exchanges_enums.BITGET_USDT_PERPETUAL_TESTNET: {
        "name": exchanges_enums.BITGET_USDT_PERPETUAL_TESTNET,
        "url": JESSE_WEBSITE_URL + "/bitget",
        "fee": 0.0006,
        "type": "futures",
        "supported_leverage_modes": ["cross", "isolated"],
        "supported_timeframes": BITGET_TIMEFRAMES,
        "modes": {
            "backtesting": False,
            "live_trading": False,
        },
        "required_live_plan": "premium",
    },
    # BITGET_USDT_PERPETUAL
    exchanges_enums.BITGET_USDT_PERPETUAL: {
        "name": exchanges_enums.BITGET_USDT_PERPETUAL,
        "url": JESSE_WEBSITE_URL + "/bitget",
        "fee": 0.0006,
        "type": "futures",
        "supported_leverage_modes": ["cross", "isolated"],
        "supported_timeframes": BITGET_TIMEFRAMES,
        "modes": {
            "backtesting": False,
            "live_trading": False,
        },
        "required_live_plan": "premium",
    },
    # BITGET_SPOT
    exchanges_enums.BITGET_SPOT: {
        "name": exchanges_enums.BITGET_SPOT,
        "url": JESSE_WEBSITE_URL + "/bitget",
        "fee": 0.0006,
        "type": "spot",
        "supported_leverage_modes": ["cross", "isolated"],
        "supported_timeframes": BITGET_TIMEFRAMES,
        "modes": {
            "backtesting": False,
            "live_trading": False,
        },
        "required_live_plan": "premium",
    },
    # DyDx
    exchanges_enums.DYDX_PERPETUAL: {
        "name": exchanges_enums.DYDX_PERPETUAL,
        "url": JESSE_WEBSITE_URL + "/dydx",
        "fee": 0.0005,
        "type": "futures",
        "supported_leverage_modes": ["cross"],
        "supported_timeframes": DYDX_TIMEFRAMES,
        "modes": {
            "backtesting": False,
            "live_trading": False,
        },
        "required_live_plan": "premium",
    },
    # DyDx Testnet
    exchanges_enums.DYDX_PERPETUAL_TESTNET: {
        "name": exchanges_enums.DYDX_PERPETUAL_TESTNET,
        "url": "https://trade.stage.dydx.exchange/trade/ETH-USD",
        "fee": 0.0005,
        "type": "futures",
        "supported_leverage_modes": ["cross"],
        "supported_timeframes": DYDX_TIMEFRAMES,
        "modes": {
            "backtesting": False,
            "live_trading": False,
        },
        "required_live_plan": "premium",
    },
    # HyperLiquid
    exchanges_enums.HYPERLIQUID_PERPETUAL: {
        "name": exchanges_enums.HYPERLIQUID_PERPETUAL,
        "url": "https://app.hyperliquid.xyz/trade",
        "fee": 0.0001,
        "type": "futures",
        "supported_leverage_modes": ["cross", "isolated"],
        "supported_timeframes": HYPERLIQUID_TIMEFRAMES,
        "modes": {
            "backtesting": False,
            "live_trading": True,
        },
        "required_live_plan": "premium",
    },
    exchanges_enums.HYPERLIQUID_PERPETUAL_TESTNET: {
        "name": exchanges_enums.HYPERLIQUID_PERPETUAL_TESTNET,
        "url": "https://app.hyperliquid-testnet.xyz/trade",
        "fee": 0.0001,
        "type": "futures",
        "supported_leverage_modes": ["cross", "isolated"],
        "supported_timeframes": HYPERLIQUID_TIMEFRAMES,
        "modes": {
            "backtesting": False,
            "live_trading": True,
        },
        "required_live_plan": "free",
    },
}

# list of supported exchanges for backtesting
backtesting_exchanges = [k for k, v in exchange_info.items() if v['modes']['backtesting'] is True]
backtesting_exchanges = list(sorted(backtesting_exchanges))

# list of supported exchanges for live trading
live_trading_exchanges = [k for k, v in exchange_info.items() if v['modes']['live_trading'] is True]
live_trading_exchanges = list(sorted(live_trading_exchanges))

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
