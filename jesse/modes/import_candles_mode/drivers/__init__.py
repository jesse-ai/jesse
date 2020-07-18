from .binance import Binance
from .binance_futures import BinanceFutures
from .bitfinex import Bitfinex
from .coinbase import Coinbase
from .testnet_binance_futures import TestnetBinanceFutures
import jesse.helpers as jh
from jesse import exceptions
from pydoc import locate
import sys

drivers = {
    'Binance': Binance,
    'Binance Futures': BinanceFutures,
    'Testnet Binance Futures': TestnetBinanceFutures,
    'Bitfinex': Bitfinex,
    'Coinbase': Coinbase,
}


def get_driver(name: str):
    if name in drivers.keys():
        return drivers[name]
    if jh.is_unit_testing():
        exists = jh.file_exists(sys.path[0] + '/jesse/modes/import_candles_mode/drivers/{}.py'.format(name.lower()))
        driver_class_path = 'jesse.modes.import_candles_mode.drivers.{}.{}'.format(name.lower(), name)
    else:
        exists = jh.file_exists('plugins/CandlesImportDrivers/{}.py'.format(name.lower()))
        driver_class_path = 'plugins.CandlesImportDrivers.{}.{}'.format(name.lower(), name)

    if not exists:
        raise exceptions.InvalidRoutes(
            'A Driver with the name of "{}" could not be found.'.format(name))
    return locate(driver_class_path)




