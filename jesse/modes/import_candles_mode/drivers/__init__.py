from .coinbase import Coinbase
from .bitfinex import Bitfinex
from .binance import Binance
from .binance_futures import BinanceFutures
from .testnet_binance_futures import TestnetBinanceFutures

drivers = {
    'Binance': Binance,
    'Binance Futures': BinanceFutures,
    'Testnet Binance Futures': TestnetBinanceFutures,
    'Bitfinex': Bitfinex,
    'Coinbase': Coinbase
}
