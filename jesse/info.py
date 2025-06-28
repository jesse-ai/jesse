from jesse.enums import Exchanges, Timeframe

JESSE_API_URL = 'https://api1.jesse.trade/api'
# JESSE_API_URL = 'http://localhost:8040/api'
JESSE_WEBSITE_URL = 'https://jesse.trade'
# JESSE_WEBSITE_URL = 'http://localhost:8040'

BYBIT_TIMEFRAMES = [Timeframe.MINUTE_1.value, Timeframe.MINUTE_3.value, Timeframe.MINUTE_5.value, Timeframe.MINUTE_15.value, Timeframe.MINUTE_30.value,
                    Timeframe.HOUR_1.value, Timeframe.HOUR_2.value, Timeframe.HOUR_4.value, Timeframe.HOUR_6.value, Timeframe.HOUR_12.value, Timeframe.DAY_1.value]
BINANCE_TIMEFRAMES = [Timeframe.MINUTE_1.value, Timeframe.MINUTE_3.value, Timeframe.MINUTE_5.value, Timeframe.MINUTE_15.value, Timeframe.MINUTE_30.value,
                      Timeframe.HOUR_1.value, Timeframe.HOUR_2.value, Timeframe.HOUR_4.value, Timeframe.HOUR_6.value, Timeframe.HOUR_8.value, Timeframe.HOUR_12.value, Timeframe.DAY_1.value]
COINBASE_TIMEFRAMES = [Timeframe.MINUTE_1.value, Timeframe.MINUTE_5.value,
                       Timeframe.MINUTE_15.value, Timeframe.HOUR_1.value, Timeframe.HOUR_6.value, Timeframe.DAY_1.value]
APEX_PRO_TIMEFRAMES = [Timeframe.MINUTE_1.value, Timeframe.MINUTE_5.value, Timeframe.MINUTE_15.value,
                       Timeframe.MINUTE_30.value, Timeframe.HOUR_1.value, Timeframe.HOUR_2.value, Timeframe.HOUR_4.value, Timeframe.HOUR_6.value, Timeframe.HOUR_12.value, Timeframe.DAY_1.value]
GATE_TIMEFRAMES = [Timeframe.MINUTE_1.value, Timeframe.MINUTE_5.value, Timeframe.MINUTE_15.value,
                   Timeframe.MINUTE_30.value, Timeframe.HOUR_1.value, Timeframe.HOUR_2.value, Timeframe.HOUR_4.value, Timeframe.HOUR_6.value, Timeframe.HOUR_8.value, Timeframe.HOUR_12.value, Timeframe.DAY_1.value, Timeframe.WEEK_1.value]
FTX_TIMEFRAMES = [Timeframe.MINUTE_1.value, Timeframe.MINUTE_3.value, Timeframe.MINUTE_5.value, Timeframe.MINUTE_15.value, Timeframe.MINUTE_30.value,
                  Timeframe.HOUR_1.value, Timeframe.HOUR_2.value, Timeframe.HOUR_4.value, Timeframe.HOUR_6.value, Timeframe.HOUR_12.value, Timeframe.DAY_1.value]
BITGET_TIMEFRAMES = [Timeframe.MINUTE_1.value, Timeframe.MINUTE_5.value, Timeframe.MINUTE_15.value,
                     Timeframe.MINUTE_30.value, Timeframe.HOUR_1.value, Timeframe.HOUR_4.value, Timeframe.HOUR_12.value, Timeframe.DAY_1.value]
DYDX_TIMEFRAMES = [Timeframe.MINUTE_1.value, Timeframe.MINUTE_5.value, Timeframe.MINUTE_15.value,
                   Timeframe.MINUTE_30.value, Timeframe.HOUR_1.value, Timeframe.HOUR_4.value, Timeframe.DAY_1.value]
HYPERLIQUID_TIMEFRAMES = [Timeframe.MINUTE_1.value, Timeframe.MINUTE_3.value, Timeframe.MINUTE_5.value, Timeframe.MINUTE_15.value,
                         Timeframe.MINUTE_30.value, Timeframe.HOUR_1.value, Timeframe.HOUR_2.value, Timeframe.HOUR_4.value, Timeframe.HOUR_6.value, Timeframe.HOUR_8.value, Timeframe.HOUR_12.value, Timeframe.DAY_1.value]

exchange_info = {
    # BYBIT_USDT_PERPETUAL
    Exchanges.BYBIT_USDT_PERPETUAL.value: {
        "name": Exchanges.BYBIT_USDT_PERPETUAL.value,
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
    Exchanges.BYBIT_USDT_PERPETUAL_TESTNET.value: {
        "name": Exchanges.BYBIT_USDT_PERPETUAL_TESTNET.value,
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
    Exchanges.BYBIT_USDC_PERPETUAL.value: {
        "name": Exchanges.BYBIT_USDC_PERPETUAL.value,
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
    Exchanges.BYBIT_USDC_PERPETUAL_TESTNET.value: {
        "name": Exchanges.BYBIT_USDC_PERPETUAL_TESTNET.value,
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
    Exchanges.BYBIT_SPOT.value: {
        "name": Exchanges.BYBIT_SPOT.value,
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
    Exchanges.BYBIT_SPOT_TESTNET.value: {
        "name": Exchanges.BYBIT_SPOT_TESTNET.value,
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
    Exchanges.BITFINEX_SPOT.value: {
        "name": Exchanges.BITFINEX_SPOT.value,
        "url": "https://bitfinex.com",
        "fee": 0.002,
        "type": "spot",
        "supported_leverage_modes": ["cross"],
        "supported_timeframes": [
            Timeframe.MINUTE_1.value,
            Timeframe.MINUTE_5.value,
            Timeframe.MINUTE_15.value,
            Timeframe.MINUTE_30.value,
            Timeframe.HOUR_1.value,
            Timeframe.HOUR_3.value,
            Timeframe.HOUR_6.value,
            Timeframe.HOUR_12.value,
            Timeframe.DAY_1.value,
        ],
        "modes": {
            "backtesting": True,
            "live_trading": False,
        },
        "required_live_plan": "premium",
    },
    # BINANCE_SPOT
    Exchanges.BINANCE_SPOT.value: {
        "name": Exchanges.BINANCE_SPOT.value,
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
    Exchanges.BINANCE_US_SPOT.value: {
        "name": Exchanges.BINANCE_US_SPOT.value,
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
    Exchanges.BINANCE_PERPETUAL_FUTURES.value: {
        "name": Exchanges.BINANCE_PERPETUAL_FUTURES.value,
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
    Exchanges.BINANCE_PERPETUAL_FUTURES_TESTNET.value: {
        "name": Exchanges.BINANCE_PERPETUAL_FUTURES_TESTNET.value,
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
    Exchanges.COINBASE_SPOT.value: {
        "name": Exchanges.COINBASE_SPOT.value,
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
    Exchanges.APEX_PRO_PERPETUAL_TESTNET.value: {
        "name": Exchanges.APEX_PRO_PERPETUAL_TESTNET.value,
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
    Exchanges.APEX_PRO_PERPETUAL.value: {
        "name": Exchanges.APEX_PRO_PERPETUAL.value,
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
    Exchanges.APEX_OMNI_PERPETUAL_TESTNET.value: {
        "name": Exchanges.APEX_OMNI_PERPETUAL_TESTNET.value,
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
    Exchanges.APEX_OMNI_PERPETUAL.value: {
        "name": Exchanges.APEX_OMNI_PERPETUAL.value,
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
    Exchanges.GATE_USDT_PERPETUAL.value: {
        "name": Exchanges.GATE_USDT_PERPETUAL.value,
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
    Exchanges.GATE_SPOT.value: {
        "name": Exchanges.GATE_SPOT.value,
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
    Exchanges.FTX_PERPETUAL_FUTURES.value: {
        "name": Exchanges.FTX_PERPETUAL_FUTURES.value,
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
    Exchanges.FTX_SPOT.value: {
        "name": Exchanges.FTX_SPOT.value,
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
    Exchanges.FTX_US_SPOT.value: {
        "name": Exchanges.FTX_US_SPOT.value,
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
    Exchanges.BITGET_USDT_PERPETUAL_TESTNET.value: {
        "name": Exchanges.BITGET_USDT_PERPETUAL_TESTNET.value,
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
    Exchanges.BITGET_USDT_PERPETUAL.value: {
        "name": Exchanges.BITGET_USDT_PERPETUAL.value,
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
    Exchanges.BITGET_SPOT.value: {
        "name": Exchanges.BITGET_SPOT.value,
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
    Exchanges.DYDX_PERPETUAL.value: {
        "name": Exchanges.DYDX_PERPETUAL.value,
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
    Exchanges.DYDX_PERPETUAL_TESTNET.value: {
        "name": Exchanges.DYDX_PERPETUAL_TESTNET.value,
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
    Exchanges.HYPERLIQUID_PERPETUAL.value: {
        "name": Exchanges.HYPERLIQUID_PERPETUAL.value,
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
    Exchanges.HYPERLIQUID_PERPETUAL_TESTNET.value: {
        "name": Exchanges.HYPERLIQUID_PERPETUAL_TESTNET.value,
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
    Timeframe.MINUTE_1.value,
    Timeframe.MINUTE_3.value,
    Timeframe.MINUTE_5.value,
    Timeframe.MINUTE_15.value,
    Timeframe.MINUTE_30.value,
    Timeframe.MINUTE_45.value,
    Timeframe.HOUR_1.value,
    Timeframe.HOUR_2.value,
    Timeframe.HOUR_3.value,
    Timeframe.HOUR_4.value,
    Timeframe.HOUR_6.value,
    Timeframe.HOUR_8.value,
    Timeframe.HOUR_12.value,
    Timeframe.DAY_1.value,
]
