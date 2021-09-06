from jesse.modes.import_candles_mode.drivers.binance import Binance
from jesse.modes.import_candles_mode.drivers.binance_futures import BinanceFutures
from jesse.modes.import_candles_mode.drivers.binance_inverse_futures import BinanceInverseFutures
from jesse.modes.import_candles_mode.drivers.bitfinex import Bitfinex
from jesse.modes.import_candles_mode.drivers.coinbase import Coinbase
from jesse.modes.import_candles_mode.drivers.testnet_binance_futures import TestnetBinanceFutures
from jesse.modes.import_candles_mode.drivers.bybit_perpetual import BybitPerpetual
from jesse.modes.import_candles_mode.drivers.testnet_bybit_perpetual import TestnetBybitPerpetual
from jesse.modes.import_candles_mode.drivers.ftx_futures import FTXFutures

import_candles_drivers = {
    'Binance': Binance,
    'Binance Futures': BinanceFutures,
    'Binance Inverse Futures': BinanceInverseFutures,
    'Testnet Binance Futures': TestnetBinanceFutures,
    'Bitfinex': Bitfinex,
    'Coinbase': Coinbase,
    'Bybit Perpetual': BybitPerpetual,
    'Testnet Bybit Perpetual': TestnetBybitPerpetual,
    'FTX Futures': FTXFutures,
}
