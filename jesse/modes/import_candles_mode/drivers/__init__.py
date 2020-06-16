from .binance import Binance
from .binance_futures import BinanceFutures
from .bitfinex import Bitfinex
from .coinbase import Coinbase
from .testnet_binance_futures import TestnetBinanceFutures

drivers = {
    'Binance': Binance,
    'Binance Futures': BinanceFutures,
    'Testnet Binance Futures': TestnetBinanceFutures,
    'Bitfinex': Bitfinex,
    'Coinbase': Coinbase,
}
