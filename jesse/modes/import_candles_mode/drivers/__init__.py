from pydoc import locate
from jesse.modes.import_candles_mode.drivers.binance import Binance
from jesse.modes.import_candles_mode.drivers.binance_futures import BinanceFutures
from jesse.modes.import_candles_mode.drivers.bitfinex import Bitfinex
from jesse.modes.import_candles_mode.drivers.coinbase import Coinbase
from jesse.modes.import_candles_mode.drivers.testnet_binance_futures import TestnetBinanceFutures
from jesse.modes.import_candles_mode.drivers.bybit_perpetual import BybitPerpetual
from jesse.modes.import_candles_mode.drivers.testnet_bybit_perpetual import TestnetBybitPerpetual
from jesse.modes.import_candles_mode.drivers.ftx_futures import FTXFutures
# from jesse.modes.import_candles_mode.drivers.ftx_spot import FTXSpot


_builtin_drivers = {
    # Perpetual Futures
    'Binance': Binance,
    'Binance Futures': BinanceFutures,
    'Testnet Binance Futures': TestnetBinanceFutures,
    'Bitfinex': Bitfinex,
    'Coinbase': Coinbase,
    'Bybit Perpetual': BybitPerpetual,
    'Testnet Bybit Perpetual': TestnetBybitPerpetual,
    'FTX Futures': FTXFutures,

    # # SPOT
    # 'FTX Spot': FTXSpot,
}

_local_drivers = locate('plugins.import_candles_drivers')

# drivers must be a dict which is merge of _builtin_drivers and _local_drivers
drivers = {}
drivers.update(_builtin_drivers)
if _local_drivers is not None:
    drivers.update(_local_drivers)

