from .binance import Binance
from .binance_futures import BinanceFutures
from .binance_inverse_futures import BinanceInverseFutures
from .bitfinex import Bitfinex
from .coinbase import Coinbase
from .testnet_binance_futures import TestnetBinanceFutures

drivers = {
    'Binance': Binance,
    'Binance Futures': BinanceFutures,
    'Binance Inverse Futures': BinanceInverseFutures,
    'Testnet Binance Futures': TestnetBinanceFutures,
    'Bitfinex': Bitfinex,
    'Coinbase': Coinbase,
}
